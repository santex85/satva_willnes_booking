from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.forms import modelformset_factory
from django.db import transaction, models
from django.db.models import Count, Sum
from django.utils import timezone
from django.contrib import messages
from django.template.loader import render_to_string
import datetime
import logging
import csv
from decimal import Decimal

from django.contrib.auth.models import User, Group
from .models import (
    Booking,
    SpecialistProfile,
    Cabinet,
    ServiceVariant,
    SpecialistSchedule,
    ScheduleTemplate,
    BookingSeries,
    CabinetClosure,
    SystemSettings,
    DeletedBooking,
)
from .decorators import admin_required, specialist_required, staff_required
from .utils import find_available_slots, check_booking_conflicts
from .restore_utils import restore_booking, restore_series, check_restore_conflicts
from .signals import set_current_user, clear_thread_locals
from .log_utils import log_booking_action, get_booking_changes
from .forms import (
    QuickBookingForm,
    SelectServiceForm,
    SpecialistScheduleForm,
    ReportForm,
    BookingEditForm,
    SpecialistRegistrationForm,
    CabinetClosureForm,
)

from collections import defaultdict

logger = logging.getLogger(__name__)


class RecurrenceError(Exception):
    """Исключение для ошибок работы с сериями бронирований."""


def build_series_from_payload(start_time, recurrence_payload, *, created_by=None, series=None):
    """
    Создает (или обновляет) экземпляр BookingSeries из данных формы.
    """
    target_series = series or BookingSeries()
    target_series.start_time = start_time
    target_series.frequency = recurrence_payload['frequency']
    target_series.interval = recurrence_payload['interval']
    if recurrence_payload['end_type'] == 'count':
        target_series.occurrence_count = recurrence_payload['occurrences']
        target_series.end_date = None
    else:
        target_series.end_date = recurrence_payload['end_date']
        target_series.occurrence_count = None
    target_series.weekdays = recurrence_payload.get('weekdays', [])
    target_series.excluded_dates = recurrence_payload.get('excluded_dates', [])
    if created_by is not None:
        target_series.created_by = created_by
    return target_series


def detect_occurrence_conflicts(occurrences, service_variant, specialist, cabinet, exclude_ids=None):
    """
    Проверяет конфликты для списка дат.
    """
    issues = []
    for index, start_dt in enumerate(occurrences, start=1):
        exclude_id = None
        if exclude_ids and index - 1 < len(exclude_ids):
            exclude_id = exclude_ids[index - 1]
        conflicts = check_booking_conflicts(
            start_time=start_dt,
            service_variant=service_variant,
            specialist=specialist,
            cabinet=cabinet,
            exclude_booking_id=exclude_id
        )
        if conflicts:
            issues.append((index, start_dt, conflicts))
    return issues


def format_conflict_message(conflicts):
    parts = []
    if conflicts.get('specialist_busy'):
        parts.append('специалист занят')
    if conflicts.get('cabinet_busy'):
        parts.append('кабинет занят')
    if conflicts.get('specialist_not_available'):
        parts.append('специалист не работает')
    if conflicts.get('cabinet_not_available'):
        parts.append('кабинет недоступен')
    return ', '.join(parts)


def handle_single_booking_update(booking, updated_booking, recurrence_enabled, user):
    with transaction.atomic():
        updated_booking.created_by = updated_booking.created_by or user
        if booking.series and not recurrence_enabled:
            series = booking.series
            updated_booking.series = None
            updated_booking.sequence = 1
            updated_booking.save()
            # Обновляем последовательность оставшихся бронирований серии
            remaining = list(series.bookings.order_by('start_time'))
            if not remaining:
                series.delete()
            else:
                for index, item in enumerate(remaining, start=1):
                    if item.sequence != index:
                        item.sequence = index
                        item.save(update_fields=['sequence'])
            return 'Бронирование обновлено (повтор отключён)'
        else:
            if booking.series:
                updated_booking.series = booking.series
                updated_booking.sequence = booking.sequence
            else:
                updated_booking.series = None
                updated_booking.sequence = 1
            updated_booking.save()
    return 'Бронирование обновлено'


def handle_series_booking_update(booking, updated_booking, recurrence_payload, user):
    existing_series = booking.series

    if recurrence_payload is None:
        if not existing_series:
            updated_booking.series = None
            updated_booking.sequence = 1
            updated_booking.created_by = updated_booking.created_by or user
            updated_booking.save()
            return 'Бронирование обновлено'

        with transaction.atomic():
            # Удаляем будущие бронирования серии
            future_qs = existing_series.bookings.filter(start_time__gte=booking.start_time).exclude(pk=booking.pk)
            removed_count = future_qs.count()
            future_qs.delete()
            # Отвязываем прошлые бронирования
            existing_series.bookings.filter(start_time__lt=booking.start_time).update(series=None, sequence=1)
            existing_series.delete()
            updated_booking.series = None
            updated_booking.sequence = 1
            updated_booking.created_by = updated_booking.created_by or user
            updated_booking.save()
        return 'Повтор отключён, серия удалена'

    # Создаем/обновляем серию
    series = build_series_from_payload(
        start_time=updated_booking.start_time,
        recurrence_payload=recurrence_payload,
        created_by=(existing_series.created_by if existing_series else user),
        series=existing_series
    )

    if existing_series:
        replace_qs = existing_series.bookings.filter(start_time__gte=booking.start_time).order_by('start_time')
        exclude_ids = [item.id for item in replace_qs]
    else:
        replace_qs = []
        exclude_ids = None

    occurrences = series.generate_datetimes()
    if not occurrences:
        raise RecurrenceError('Не удалось построить повторяющиеся даты')

    conflicts = detect_occurrence_conflicts(
        occurrences,
        service_variant=updated_booking.service_variant,
        specialist=updated_booking.specialist,
        cabinet=updated_booking.cabinet,
        exclude_ids=exclude_ids
    )
    # Сохраняем информацию о конфликтах для предупреждения, но не блокируем
    conflict_warning = None
    if conflicts:
        messages_list = []
        for index, start_dt, conflict_data in conflicts[:3]:
            local_dt = timezone.localtime(start_dt)
            conflict_text = format_conflict_message(conflict_data)
            messages_list.append(
                f"{local_dt.strftime('%d.%m.%Y %H:%M')} ({conflict_text})"
            )
        if len(conflicts) > 3:
            messages_list.append('и другие конфликты…')
        conflict_warning = 'Конфликты при обновлении серии: ' + '; '.join(messages_list)

    with transaction.atomic():
        series.created_by = series.created_by or user
        series.save()

        # Отвязываем прошлые бронирования, которые не должны входить в обновленную серию
        if existing_series:
            existing_series.bookings.filter(start_time__lt=booking.start_time).update(series=None, sequence=1)
            existing_series.bookings.filter(start_time__gte=booking.start_time).exclude(pk=booking.pk).delete()

        # Обновляем текущее бронирование как первый элемент серии
        updated_booking.series = series
        updated_booking.sequence = 1
        updated_booking.start_time = occurrences[0]
        updated_booking.created_by = updated_booking.created_by or user
        updated_booking.save()

        # Создаем остальные бронирования серии
        for sequence, start_dt in enumerate(occurrences[1:], start=2):
            Booking.objects.create(
                guest_name=updated_booking.guest_name,
                guest_room_number=updated_booking.guest_room_number,
                service_variant=updated_booking.service_variant,
                specialist=updated_booking.specialist,
                cabinet=updated_booking.cabinet,
                start_time=start_dt,
                created_by=user,
                status=updated_booking.status,
                series=series,
                sequence=sequence
            )

    result_message = f'Обновлено бронирование и серия ({len(occurrences)} записей)' if existing_series else f'Создана серия бронирований ({len(occurrences)} записей)'
    
    # Добавляем предупреждение о конфликтах если есть
    if conflict_warning:
        result_message += f'. Внимание: {conflict_warning}'
    
    return result_message


@login_required
def index_view(request):
    """
    Главная страница - перенаправляет пользователя на его рабочую страницу
    в зависимости от роли.
    """
    # Проверяем роль пользователя
    user_groups = request.user.groups.values_list('name', flat=True)
    
    if request.user.is_superuser or 'Admin' in user_groups or 'SuperAdmin' in user_groups:
        return redirect('calendar')
    elif 'Specialist' in user_groups:
        return redirect('my_schedule')
    else:
        # Если пользователь не входит ни в одну группу - показываем заглушку
        return HttpResponse(
            '<h1>Добро пожаловать!</h1><p>Ваш аккаунт ожидает назначения роли.</p>',
            status=200
        )


@login_required
def calendar_view(request):
    """
    Страница календаря для администраторов.
    """
    # Добавляем форму для модального окна
    quick_form = QuickBookingForm()
    
    # Получаем список услуг и кабинетов
    services_qs = ServiceVariant.objects.select_related('service').prefetch_related('service__required_cabinet_types').order_by('service__name', 'duration_minutes')
    services = list(services_qs)
    cabinets = list(Cabinet.objects.filter(is_active=True).select_related('cabinet_type').order_by('id'))
    service_groups = build_service_variant_groups(services, cabinets)
    quick_form.fields['service_variant'].queryset = services_qs
    cabinet_colors = generate_cabinet_colors(cabinets)
    
    # Добавляем цвета к кабинетам для отображения в легенде
    cabinets_with_colors = []
    for cabinet in cabinets:
        colors = cabinet_colors.get(cabinet.id, {'bg': '#3788d8', 'border': '#2e6da4'})
        cabinets_with_colors.append({
            'cabinet': cabinet,
            'bg_color': colors['bg'],
            'border_color': colors['border']
        })
    
    can_manage_closures = request.user.is_staff or request.user.is_superuser
    closure_form = None
    if can_manage_closures:
        closure_form = CabinetClosureForm()
        closure_form.fields['cabinet'].queryset = Cabinet.objects.filter(is_active=True).order_by('name')

    settings_obj = SystemSettings.get_solo()
    copy_shortcuts_enabled = getattr(settings_obj, 'enable_booking_copy_shortcuts', True)

    return render(request, 'calendar.html', {
        'quick_form': quick_form,
        'service_groups': service_groups,
        'cabinets_with_colors': cabinets_with_colors,
        'closure_form': closure_form,
        'can_manage_closures': can_manage_closures,
        'copy_shortcuts_enabled': copy_shortcuts_enabled,
    })


@admin_required
def specialists_overview_view(request):
    """
    Таблица графика работы всех специалистов на неделю.
    """
    week_days = SpecialistSchedule.DAYS_OF_WEEK

    specialists = (
        SpecialistProfile.objects
        .select_related('user')
        .prefetch_related('services_can_perform', 'schedules')
        .order_by('full_name')
    )

    specialists_data = []
    for specialist in specialists:
        schedules_map = {day: None for day, _ in week_days}
        for schedule in specialist.schedules.all():
            schedules_map[schedule.day_of_week] = schedule

        day_entries = []
        for day_value, day_label in week_days:
            day_entries.append({
                'day_value': day_value,
                'day_label': day_label,
                'schedule': schedules_map.get(day_value),
            })

        specialists_data.append({
            'specialist': specialist,
            'services': list(specialist.services_can_perform.all()),
            'day_entries': day_entries,
        })

    context = {
        'week_days': week_days,
        'specialists_data': specialists_data,
    }

    return render(request, 'specialists_overview.html', context)


@specialist_required
def my_schedule_view(request):
    """
    Страница графика для специалистов - показываем бронирования на неделю.
    """
    specialist = get_object_or_404(SpecialistProfile, user=request.user)
    today = datetime.date.today()
    
    # Получаем бронирования на неделю вперед (7 дней)
    week_end = today + datetime.timedelta(days=6)
    
    # Получаем все бронирования на неделю
    bookings = Booking.objects.filter(
        specialist=specialist,
        start_time__date__range=[today, week_end],
        status='confirmed'
    ).order_by('start_time')
    
    # Группируем бронирования по дням
    bookings_by_date = {}
    for booking in bookings:
        booking_date = timezone.localtime(booking.start_time).date()
        if booking_date not in bookings_by_date:
            bookings_by_date[booking_date] = []
        bookings_by_date[booking_date].append(booking)
    
    # Создаем список дней недели с бронированиями
    week_days = []
    for i in range(7):
        day = today + datetime.timedelta(days=i)
        day_bookings = bookings_by_date.get(day, [])
        week_days.append({
            'date': day,
            'bookings': day_bookings,
            'is_today': day == today
        })
    
    # Подсчитываем общее количество бронирований
    total_bookings = bookings.count()
    
    # Получаем все услуги, которые может выполнять специалист
    services = specialist.services_can_perform.all().order_by('name')
    
    return render(request, 'specialist_schedule.html', {
        'week_days': week_days,
        'today': today,
        'week_end': week_end,
        'total_bookings': total_bookings,
        'specialist': specialist,
        'services': services
    })


# Calendar feed and resources
@admin_required
def calendar_feed_view(request):
    """
    Возвращает события для FullCalendar в формате JSON.
    """
    start = request.GET.get('start')
    end = request.GET.get('end')
    
    try:
        start_date = timezone.datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_date = timezone.datetime.fromisoformat(end.replace('Z', '+00:00'))
    except (ValueError, AttributeError) as e:
        logger.error(f"Invalid date format in calendar_feed_view: {e}")
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    bookings = Booking.objects.filter(
        start_time__range=[start_date, end_date]
    ).select_related('service_variant', 'specialist', 'cabinet').order_by('start_time')
    
    # Получаем все уникальные кабинеты для генерации цветов
    cabinets = Cabinet.objects.filter(is_active=True).order_by('id')
    cabinet_colors = generate_cabinet_colors(cabinets)
    
    events = []
    for b in bookings:
        # Показываем клиенту "чистое" время без буфера
        end_time = b.start_time + datetime.timedelta(minutes=b.service_variant.duration_minutes)
        
        # Получаем цвета для кабинета
        colors = cabinet_colors.get(b.cabinet.id, {'bg': '#3788d8', 'border': '#2e6da4', 'text': '#ffffff'})
        
        # Формируем название с индикатором статуса, именем гостя, специалистом и услугой
        status_icons = {
            'unconfirmed': '? ',
            'confirmed': '',
            'paid': '$ ',
            'completed': '✓ ',
            'canceled': '✗ '
        }
        status_icon = status_icons.get(b.status, '')
        # Формат: [статус] Гость - Специалист (услуга)
        specialist_short = b.specialist.full_name.split()[0]  # Только имя
        title = f"{status_icon}{b.guest_name} - {specialist_short} ({b.service_variant.name_suffix})"
        
        events.append({
            'id': b.id,
            'title': title.strip(),
            'start': b.start_time.isoformat(),
            'end': end_time.isoformat(),
            'resourceId': b.specialist.id,  # Для вида "по специалистам"
            'extendedProps': {
                'eventType': 'booking',
                'cabinetId': b.cabinet.id,  # Для вида "по кабинетам"
                'status': b.status,
                'specialist': b.specialist.full_name,
                'cabinet': b.cabinet.name,
                'guest_name': b.guest_name,
                'guest_room': b.guest_room_number,
                'seriesId': b.series_id or None
            },
            'backgroundColor': colors['bg'],
            'borderColor': colors['border'],
            'textColor': colors['text']
        })
    
    return JsonResponse(events, safe=False)


@staff_required
def cabinet_closure_feed_view(request):
    """
    Возвращает события-закрытия кабинетов для FullCalendar.
    """
    start = request.GET.get('start')
    end = request.GET.get('end')

    try:
        start_date = timezone.datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_date = timezone.datetime.fromisoformat(end.replace('Z', '+00:00'))
    except (ValueError, AttributeError) as e:
        logger.error(f"Invalid date format in cabinet_closure_feed_view: {e}")
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    closures = CabinetClosure.objects.filter(
        start_time__lt=end_date,
        end_time__gt=start_date
    ).select_related('cabinet').order_by('start_time')

    can_delete = request.user.is_staff or request.user.is_superuser
    events = []
    for closure in closures:
        events.append({
            'id': closure.id,
            'title': f"Кабинет {closure.cabinet.name} закрыт",
            'start': closure.start_time.isoformat(),
            'end': closure.end_time.isoformat(),
            'allDay': False,
            'editable': False,
            'backgroundColor': '#adb5bd',
            'borderColor': '#6c757d',
            'textColor': '#212529',
            'classNames': ['cabinet-closure-event'],
            'extendedProps': {
                'eventType': 'closure',
                'cabinet': closure.cabinet.name,
                'reason': closure.reason or '',
                'canDelete': can_delete,
            }
        })

    return JsonResponse(events, safe=False)


def generate_cabinet_colors(cabinets):
    """
    Генерирует уникальные цвета для каждого кабинета.
    Возвращает словарь {cabinet_id: {'bg': '#color', 'border': '#color', 'text': '#color'}}
    """
    # Палитра красивых цветов
    color_palette = [
        {'bg': '#3498db', 'border': '#2980b9', 'text': '#ffffff'},  # Синий
        {'bg': '#e74c3c', 'border': '#c0392b', 'text': '#ffffff'},  # Красный
        {'bg': '#2ecc71', 'border': '#27ae60', 'text': '#ffffff'},  # Зеленый
        {'bg': '#f39c12', 'border': '#d68910', 'text': '#ffffff'},  # Оранжевый
        {'bg': '#9b59b6', 'border': '#8e44ad', 'text': '#ffffff'},  # Фиолетовый
        {'bg': '#1abc9c', 'border': '#16a085', 'text': '#ffffff'},  # Бирюзовый
        {'bg': '#e67e22', 'border': '#d35400', 'text': '#ffffff'},  # Морковный
        {'bg': '#34495e', 'border': '#2c3e50', 'text': '#ffffff'},  # Темно-серый
        {'bg': '#16a085', 'border': '#138d75', 'text': '#ffffff'},  # Зелено-синий
        {'bg': '#c0392b', 'border': '#a93226', 'text': '#ffffff'},  # Темно-красный
        {'bg': '#2980b9', 'border': '#2471a3', 'text': '#ffffff'},  # Темно-синий
        {'bg': '#8e44ad', 'border': '#7d3c98', 'text': '#ffffff'},  # Темно-фиолетовый
        {'bg': '#d35400', 'border': '#ba4a00', 'text': '#ffffff'},  # Темно-оранжевый
        {'bg': '#27ae60', 'border': '#229954', 'text': '#ffffff'},  # Темно-зеленый
        {'bg': '#2c3e50', 'border': '#1b2631', 'text': '#ffffff'},  # Почти черный
    ]
    
    cabinet_colors = {}
    for idx, cabinet in enumerate(cabinets):
        # Используем цвета по кругу
        color_idx = idx % len(color_palette)
        cabinet_colors[cabinet.id] = color_palette[color_idx]
    
    return cabinet_colors


@admin_required
def specialist_resources_view(request):
    """
    Возвращает список специалистов как ресурсы для FullCalendar.
    """
    specialists = SpecialistProfile.objects.all()
    resources = [{'id': s.id, 'title': s.full_name} for s in specialists]
    return JsonResponse(resources, safe=False)


@admin_required
def cabinet_resources_view(request):
    """
    Возвращает список кабинетов как ресурсы для FullCalendar.
    """
    cabinets = Cabinet.objects.filter(is_active=True)
    resources = [{'id': c.id, 'title': c.name} for c in cabinets]
    return JsonResponse(resources, safe=False)


@admin_required
def get_specialists_for_service_view(request):
    """
    Возвращает список специалистов, которые могут выполнить указанную услугу.
    """
    service_variant_id = request.GET.get('service_variant_id')
    
    if not service_variant_id:
        return JsonResponse({'error': 'Не указан ID варианта услуги'}, status=400)
    
    try:
        service_variant = get_object_or_404(ServiceVariant, id=service_variant_id)
        specialists = SpecialistProfile.objects.filter(
            services_can_perform=service_variant.service
        ).values('id', 'full_name')
        
        return JsonResponse(list(specialists), safe=False)
    except ServiceVariant.DoesNotExist:
        return JsonResponse({'error': 'Вариант услуги не найден'}, status=404)


@admin_required
def get_available_cabinets_view(request):
    """
    Возвращает список доступных кабинетов для указанного времени, специалиста и услуги.
    
    Примечание: @admin_required уже проверяет авторизацию через request.user,
    поэтому @login_required не нужен.
    """
    logger.info(f"get_available_cabinets_view called: path={request.path}, method={request.method}, user={request.user}")
    service_variant_id = request.GET.get('service_variant_id')
    specialist_id = request.GET.get('specialist_id')
    datetime_str = request.GET.get('datetime')
    exclude_booking_id = request.GET.get('exclude_booking_id')  # ID бронирования для исключения из проверки
    
    if not service_variant_id or not specialist_id or not datetime_str:
        logger.warning(f"Missing parameters: service_variant_id={service_variant_id}, specialist_id={specialist_id}, datetime={datetime_str}")
        return JsonResponse({'error': 'Не указаны обязательные параметры'}, status=400)
    
    try:
        service_variant = get_object_or_404(ServiceVariant, id=service_variant_id)
        specialist = get_object_or_404(SpecialistProfile, id=specialist_id)
        
        # Парсим datetime (формат: YYYY-MM-DDTHH:MM в локальном времени)
        try:
            # Парсим как naive datetime (локальное время)
            naive_dt = datetime.datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M')
            # Делаем aware используя текущую timezone Django
            start_datetime = timezone.make_aware(naive_dt)
        except ValueError:
            # Попробуем ISO формат
            try:
                start_datetime = timezone.datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                if timezone.is_naive(start_datetime):
                    start_datetime = timezone.make_aware(start_datetime)
            except ValueError:
                logger.warning(f"Invalid datetime format: {datetime_str}")
                return JsonResponse({'error': 'Неверный формат даты и времени'}, status=400)
        
        # Получаем все кабинеты подходящего типа для услуги (без проверки конфликтов)
        service = service_variant.service
        required_cabinet_types = service.required_cabinet_types.all()
        valid_cabinets = Cabinet.objects.filter(
            cabinet_type__in=required_cabinet_types,
            is_active=True
        ).order_by('name')
        
        # Возвращаем все подходящие кабинеты без проверки доступности
        cabinets_data = [{'id': cab.id, 'name': cab.name} for cab in valid_cabinets]
        
        if not cabinets_data:
            logger.warning(f"No suitable cabinets for service {service_variant_id}")
            return JsonResponse({'error': 'Нет подходящих кабинетов для данной услуги'}, status=404)
        
        logger.debug(f"Returning {len(cabinets_data)} suitable cabinets for service")
        return JsonResponse({'cabinets': cabinets_data}, safe=False)
        
    except (ValueError, ServiceVariant.DoesNotExist, SpecialistProfile.DoesNotExist) as e:
        logger.error(f"Error getting available cabinets: {e}", exc_info=True)
        return JsonResponse({'error': 'Ошибка при получении доступных кабинетов'}, status=500)


@staff_required
@require_POST
def create_cabinet_closure_view(request):
    """
    Создание закрытия кабинета.
    """
    form = CabinetClosureForm(request.POST)
    if form.is_valid():
        closure = form.save(commit=False)
        closure.created_by = request.user
        closure.save()
        logger.info(
            "Cabinet closure created by %s: cabinet=%s, start=%s, end=%s",
            request.user.username,
            closure.cabinet_id,
            closure.start_time,
            closure.end_time,
        )
        return JsonResponse({
            'success': True,
            'message': 'Закрытие кабинета создано',
            'closure_id': closure.id,
        })

    logger.warning("Cabinet closure form invalid: %s", form.errors)
    return JsonResponse({'success': False, 'errors': form.errors}, status=400)


@staff_required
@require_POST
def delete_cabinet_closure_view(request, pk):
    """
    Удаление закрытия кабинета.
    """
    closure = get_object_or_404(CabinetClosure, pk=pk)
    closure.delete()
    logger.info(
        "Cabinet closure %s deleted by %s",
        pk,
        request.user.username,
    )
    return JsonResponse({'success': True, 'message': 'Закрытие кабинета удалено'})


# Booking wizard views
@admin_required
def select_service_view(request):
    """
    Шаг 1: Выбор услуги и даты.
    """
    if request.method == 'GET':
        services_qs = ServiceVariant.objects.select_related('service').prefetch_related('service__required_cabinet_types').order_by('service__name', 'duration_minutes')
        services = list(services_qs)
        cabinets = list(Cabinet.objects.filter(is_active=True).select_related('cabinet_type').order_by('cabinet_type__name', 'name'))
        service_groups = build_service_variant_groups(services, cabinets)

        form = SelectServiceForm()
        form.fields['service_variant'].queryset = services_qs

        return render(request, 'booking/select_service.html', {
            'form': form,
            'service_groups': service_groups
        })
    return redirect('select_service')


@admin_required
def select_slot_view(request):
    """
    Шаг 2: Выбор доступного слота.
    """
    service_variant_id = request.GET.get('service_variant')
    date_str = request.GET.get('date')
    
    if not service_variant_id or not date_str:
        return redirect('select_service')
    
    service_variant = get_object_or_404(ServiceVariant, id=service_variant_id)
    date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    
    # Используем функцию поиска слотов из utils.py
    available_slots = find_available_slots(date, service_variant)
    
    # Группируем слоты по специалистам
    slots_by_specialist = {}
    for slot in available_slots:
        specialist = slot['specialist']
        if specialist.id not in slots_by_specialist:
            slots_by_specialist[specialist.id] = {
                'specialist': specialist,
                'slots': []
            }
        slots_by_specialist[specialist.id]['slots'].append(slot)
    
    # Преобразуем в список и сортируем по имени специалиста
    grouped_slots = sorted(slots_by_specialist.values(), key=lambda x: x['specialist'].full_name)
    
    context = {
        'slots': available_slots,  # Оставляем для обратной совместимости
        'grouped_slots': grouped_slots,  # Новая структура для группировки
        'form_data': request.GET,
        'service_variant': service_variant,
        'date': date
    }
    return render(request, 'booking/select_slot.html', context)


@admin_required
@require_POST
def create_booking_view(request):
    """
    Шаг 3: Создание бронирования.
    """
    try:
        selected_slot = request.POST.get('selected_slot')
        if not selected_slot:
            messages.error(request, 'Слот не выбран')
            return redirect('select_service')
        
        slot_data = selected_slot.split('|')
        if len(slot_data) < 2:
            raise ValueError("Invalid slot format")
        
        start_time = timezone.datetime.fromisoformat(slot_data[0])
        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time)
        
        specialist_id = int(slot_data[1])
        
        # Кабинет может быть в slot_data[2] или отсутствовать (для обратной совместимости)
        if len(slot_data) >= 3:
            cabinet_id = int(slot_data[2])
        else:
            # Если кабинет не указан, используем первый доступный из слота
            # Это для обратной совместимости со старым форматом
            service_variant_id = int(request.POST.get('service_variant'))
            service_variant = get_object_or_404(ServiceVariant, id=service_variant_id)
            date = start_time.date()
            available_slots = find_available_slots(date, service_variant)
            
            # Ищем слот с соответствующим временем и специалистом
            suitable_slot = None
            for slot in available_slots:
                if (slot['specialist'].id == specialist_id and 
                    slot['start_time'] == start_time):
                    suitable_slot = slot
                    break
            
            if not suitable_slot:
                raise ValueError("Slot not found")
            
            # Используем первый доступный кабинет
            if suitable_slot.get('available_cabinets'):
                cabinet_id = suitable_slot['available_cabinets'][0].id
            elif suitable_slot.get('cabinet'):
                cabinet_id = suitable_slot['cabinet'].id
            else:
                raise ValueError("No available cabinet")
        
        service_variant_id = int(request.POST.get('service_variant'))
        service_variant = get_object_or_404(ServiceVariant, id=service_variant_id)
        specialist = get_object_or_404(SpecialistProfile, id=specialist_id)
        cabinet = get_object_or_404(Cabinet, id=cabinet_id)
        
        # Валидация: проверяем что кабинет подходит для услуги
        service = service_variant.service
        required_cabinet_types = service.required_cabinet_types.all()
        if cabinet.cabinet_type not in required_cabinet_types:
            messages.error(request, 'Выбранный кабинет не подходит для данной услуги')
            return redirect('select_service')
        
        # Валидация: проверяем что кабинет свободен в выбранное время
        date = start_time.date()
        available_slots = find_available_slots(date, service_variant)
        
        # Ищем слот с соответствующим временем и специалистом
        suitable_slot = None
        for slot in available_slots:
            if (slot['specialist'].id == specialist_id and 
                slot['start_time'] == start_time):
                suitable_slot = slot
                break
        
        if not suitable_slot:
            messages.error(request, 'Выбранный слот недоступен')
            return redirect('select_service')
        
        # Проверяем что выбранный кабинет есть в списке доступных
        available_cabinets = suitable_slot.get('available_cabinets', [])
        if available_cabinets:
            cabinet_ids = [cab.id for cab in available_cabinets]
            if cabinet_id not in cabinet_ids:
                messages.error(request, 'Выбранный кабинет недоступен для данного времени')
                return redirect('select_service')
        elif suitable_slot.get('cabinet') and suitable_slot['cabinet'].id != cabinet_id:
            # Для обратной совместимости со старым форматом
            messages.error(request, 'Выбранный кабинет недоступен для данного времени')
            return redirect('select_service')
        
        # Создаем бронирование
        booking = Booking.objects.create(
            guest_name=request.POST.get('guest_name'),
            guest_room_number=request.POST.get('guest_room_number'),
            service_variant_id=service_variant_id,
            specialist_id=specialist_id,
            cabinet_id=cabinet_id,
            start_time=start_time,
            created_by=request.user,
            status='confirmed'
        )
        
        # Логируем создание
        log_booking_action(
            booking=booking,
            action='created',
            user=request.user,
            message=f'Создано бронирование для гостя {booking.guest_name}',
            request=request
        )
        
        messages.success(request, 'Бронирование успешно создано')
        return redirect('calendar')
        
    except (ValueError, IndexError, TypeError) as e:
        logger.error(f"Error creating booking: {e}", exc_info=True)
        messages.error(request, 'Ошибка при создании бронирования')
        return redirect('select_service')


# Booking detail view
@admin_required
def booking_detail_view(request, pk):
    """
    Детальная страница бронирования с возможностью редактирования
    """
    booking = get_object_or_404(Booking, pk=pk)
    
    ajax_request = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = BookingEditForm(request.POST, instance=booking)
    else:
        form = BookingEditForm(instance=booking)

    context = {
        'booking': booking,
        'form': form,
        'form_action': reverse('booking_detail', args=[booking.pk]),
        'calendar_url': reverse('calendar'),
        'back_url': reverse('calendar'),
        'validate_url': reverse('validate_booking_edit', args=[booking.pk]),
        'logs_url': reverse('booking_logs', args=[booking.pk]),
        'available_cabinets_url': reverse('available_cabinets'),
        'specialists_url': reverse('specialists_for_service'),
        'delete_url': reverse('booking_delete', args=[booking.pk]),
        'show_back_button': not ajax_request,
        'submit_via_ajax': ajax_request,
        'show_delete_button': ajax_request,
    }
    if booking.series:
        context['series'] = booking.series
        context['series_count'] = booking.series.bookings.count()
    else:
        context['series'] = None
        context['series_count'] = 0

    if request.method == 'POST':
        if form.is_valid():
            # Проверяем наличие предупреждений о конфликтах
            conflicts_warning = form.cleaned_data.get('conflicts_warning')
            
            updated_booking = form.save(commit=False)
            recurrence_payload = form.cleaned_data.get('recurrence_payload')
            recurrence_enabled = form.cleaned_data.get('recurrence_enabled')
            apply_scope = form.cleaned_data.get('apply_scope') or 'single'

            if not booking.series and recurrence_payload:
                apply_scope = 'series'

            try:
                # Сохраняем старые значения для логирования
                old_booking = Booking.objects.get(pk=booking.pk)
                
                if apply_scope == 'series':
                    message_text = handle_series_booking_update(
                        booking=booking,
                        updated_booking=updated_booking,
                        recurrence_payload=recurrence_payload,
                        user=request.user
                    )
                    action = 'series_updated'
                else:
                    message_text = handle_single_booking_update(
                        booking=booking,
                        updated_booking=updated_booking,
                        recurrence_enabled=recurrence_enabled,
                        user=request.user
                    )
                    action = 'updated'
                
                # Получаем обновленное бронирование
                booking.refresh_from_db()
                
                # Определяем изменения
                old_values, new_values = get_booking_changes(old_booking, booking)
                
                # Определяем тип изменений для более детального сообщения
                changes = []
                if old_values.get('start_time') != new_values.get('start_time'):
                    changes.append('время')
                if old_values.get('specialist_id') != new_values.get('specialist_id'):
                    changes.append('специалист')
                if old_values.get('cabinet_id') != new_values.get('cabinet_id'):
                    changes.append('кабинет')
                if old_values.get('service_variant_id') != new_values.get('service_variant_id'):
                    changes.append('услуга')
                if old_values.get('status') != new_values.get('status'):
                    changes.append('статус')
                    action = 'status_changed'
                if old_values.get('guest_name') != new_values.get('guest_name'):
                    changes.append('имя гостя')
                
                change_text = ', '.join(changes) if changes else 'данные'
                log_message = f'Обновлено бронирование: изменено {change_text}'
                
                # Логируем обновление
                log_booking_action(
                    booking=booking,
                    action=action,
                    user=request.user,
                    message=log_message,
                    old_values=old_values if old_values else None,
                    new_values=new_values if new_values else None,
                    request=request
                )

                logger.info(f"Booking {booking.id} updated by {request.user.username} scope={apply_scope}")
                
                # Показываем предупреждение если есть конфликты
                if conflicts_warning:
                    if ajax_request:
                        return JsonResponse({
                            'success': True, 
                            'message': message_text,
                            'warning': conflicts_warning
                        })
                    messages.warning(request, f'{message_text}. Внимание: {conflicts_warning}')
                else:
                    if ajax_request:
                        return JsonResponse({'success': True, 'message': message_text})
                    messages.success(request, message_text)
                
                return redirect('calendar')

            except RecurrenceError as recur_error:
                error_message = str(recur_error)
                logger.warning(f"Recurrence error for booking {booking.id}: {error_message}")
                if ajax_request:
                    context['form'] = form
                    html = render_to_string('booking/partials/booking_edit_form.html', context, request=request)
                    return JsonResponse({'success': False, 'html': html, 'error': error_message}, status=400)
                messages.error(request, error_message)
            except Exception as e:
                logger.error(f"Error updating booking {booking.id}: {e}", exc_info=True)
                if ajax_request:
                    context['form'] = form
                    html = render_to_string('booking/partials/booking_edit_form.html', context, request=request)
                    return JsonResponse({'success': False, 'html': html, 'error': 'Ошибка при обновлении бронирования. Попробуйте еще раз.'}, status=500)
                messages.error(request, 'Ошибка при обновлении бронирования. Попробуйте еще раз.')
        else:
            logger.warning(f"Form validation errors for booking {booking.id}: {form.errors}")
            if ajax_request:
                context['form'] = form
                html = render_to_string('booking/partials/booking_edit_form.html', context, request=request)
                return JsonResponse({'success': False, 'html': html, 'errors': form.errors}, status=400)
            messages.error(request, 'Ошибка при обновлении бронирования. Проверьте введенные данные.')
    
    if ajax_request and request.method == 'GET':
        html = render_to_string('booking/partials/booking_edit_form.html', context, request=request)
        return JsonResponse({'success': True, 'html': html})

    context['show_delete_button'] = False
    return render(request, 'booking/booking_detail.html', context)


@admin_required
def validate_booking_edit_view(request, pk):
    """
    AJAX endpoint для валидации редактирования бронирования без сохранения
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запросы'}, status=405)
    
    booking = get_object_or_404(Booking, pk=pk)
    
    try:
        # Получаем данные из запроса
        start_datetime_str = request.POST.get('start_datetime')
        service_variant_id = request.POST.get('service_variant')
        specialist_id = request.POST.get('specialist')
        cabinet_id = request.POST.get('cabinet')
        
        if not all([start_datetime_str, service_variant_id, specialist_id, cabinet_id]):
            return JsonResponse({
                'valid': False,
                'error': 'Не указаны все обязательные поля'
            }, status=400)
        
        # Парсим datetime
        try:
            naive_dt = datetime.datetime.strptime(start_datetime_str, '%Y-%m-%dT%H:%M')
            if timezone.is_naive(naive_dt):
                start_time = timezone.make_aware(naive_dt)
            else:
                start_time = naive_dt
        except ValueError:
            return JsonResponse({
                'valid': False,
                'error': 'Неверный формат даты и времени'
            }, status=400)
        
        # Получаем объекты
        service_variant = get_object_or_404(ServiceVariant, id=service_variant_id)
        specialist = get_object_or_404(SpecialistProfile, id=specialist_id)
        cabinet = get_object_or_404(Cabinet, id=cabinet_id)
        
        # Проверяем конфликты (только для предупреждения, не блокируем)
        conflicts = check_booking_conflicts(
            start_time=start_time,
            service_variant=service_variant,
            specialist=specialist,
            cabinet=cabinet,
            exclude_booking_id=booking.id
        )
        
        # Формируем предупреждение если есть конфликты, но не блокируем
        warning = None
        if conflicts:
            conflict_messages = []
            if conflicts.get('specialist_busy'):
                conflict_messages.append('Специалист занят в это время')
            if conflicts.get('cabinet_busy'):
                conflict_messages.append('Кабинет занят в это время')
            if conflicts.get('specialist_not_available'):
                conflict_messages.append('Специалист не работает в это время')
            if conflicts.get('cabinet_not_available'):
                conflict_messages.append('Кабинет недоступен в это время')
            
            warning = '; '.join(conflict_messages) if conflict_messages else 'Выбранное время имеет конфликты'
        
        # Проверяем что специалист может выполнять услугу
        service = service_variant.service
        if not specialist.services_can_perform.filter(id=service.id).exists():
            return JsonResponse({
                'valid': False,
                'error': 'Выбранный специалист не может выполнять данную услугу'
            })
        
        # Проверяем что кабинет подходит для услуги
        required_cabinet_types = service.required_cabinet_types.all()
        if cabinet.cabinet_type not in required_cabinet_types:
            return JsonResponse({
                'valid': False,
                'error': 'Выбранный кабинет не подходит для данной услуги'
            })
        
        response_data = {
            'valid': True,
            'message': 'Данные валидны'
        }
        
        # Добавляем предупреждение если есть конфликты
        if warning:
            response_data['warning'] = warning
            response_data['conflicts'] = conflicts
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error validating booking edit {pk}: {e}", exc_info=True)
        return JsonResponse({
            'valid': False,
            'error': 'Ошибка при проверке данных'
        }, status=500)


@admin_required
def booking_logs_view(request, pk):
    """
    API endpoint для получения логов бронирования
    """
    booking = get_object_or_404(Booking, pk=pk)
    
    from .models import BookingLog
    logs = BookingLog.objects.filter(booking=booking).select_related('user').order_by('-created_at')[:50]
    
    logs_data = []
    for log in logs:
        logs_data.append({
            'id': log.id,
            'action': log.action,
            'action_display': log.get_action_display(),
            'message': log.message,
            'user': log.user.username if log.user else 'Система',
            'user_full_name': log.user.get_full_name() if log.user and hasattr(log.user, 'get_full_name') else (log.user.username if log.user else 'Система'),
            'created_at': timezone.localtime(log.created_at).strftime('%d.%m.%Y %H:%M:%S'),
            'ip_address': str(log.ip_address) if log.ip_address else None,
            'old_values': log.old_values,
            'new_values': log.new_values,
        })
    
    return JsonResponse({
        'success': True,
        'logs': logs_data,
        'count': len(logs_data)
    })


@admin_required
def quick_create_booking_view(request):
    """
    Быстрое создание бронирования через AJAX (модальное окно)
    """
    if request.method == 'POST':
        form = QuickBookingForm(request.POST)
        if form.is_valid():
            try:
                # Получаем данные из формы
                service_variant = form.cleaned_data['service_variant']
                specialist = form.cleaned_data['specialist']
                guest_name = form.cleaned_data['guest_name']
                guest_room_number = form.cleaned_data.get('guest_room_number', '')
                start_datetime = form.cleaned_data['start_datetime']
                
                # Убеждаемся, что дата timezone-aware
                if timezone.is_naive(start_datetime):
                    start_datetime = timezone.make_aware(start_datetime)
                
                # Используем время из формы напрямую (без проверки слотов)
                final_start_time = start_datetime
                
                logger.info(f"Quick booking attempt: date={timezone.localtime(start_datetime).date()}, time={timezone.localtime(start_datetime).time()}, specialist={specialist.id}, service={service_variant.id}")
                
                # Определяем кабинет
                selected_cabinet = form.cleaned_data.get('cabinet')
                service = service_variant.service
                required_cabinet_types = service.required_cabinet_types.all()
                
                if selected_cabinet:
                    # Проверяем что выбранный кабинет подходит для услуги
                    if selected_cabinet.cabinet_type not in required_cabinet_types:
                        return JsonResponse({
                            'error': 'Выбранный кабинет не подходит для данной услуги'
                        }, status=400)
                    cabinet = selected_cabinet
                else:
                    # Если кабинет не выбран, берем первый подходящий кабинет для услуги
                    cabinet = Cabinet.objects.filter(
                        cabinet_type__in=required_cabinet_types,
                        is_active=True
                    ).first()
                    
                    if not cabinet:
                        return JsonResponse({
                            'error': 'Нет доступных кабинетов для данной услуги'
                        }, status=400)
                
                recurrence_payload = form.cleaned_data.get('recurrence_payload')

                with transaction.atomic():
                    if recurrence_payload:
                        series = build_series_from_payload(
                            start_time=final_start_time,
                            recurrence_payload=recurrence_payload,
                            created_by=request.user
                        )
                        occurrences = series.generate_datetimes()
                        if not occurrences:
                            return JsonResponse({
                                'error': 'Не удалось построить расписание повторов'
                            }, status=400)

                        conflicts = detect_occurrence_conflicts(
                            occurrences,
                            service_variant=service_variant,
                            specialist=specialist,
                            cabinet=cabinet
                        )
                        # Формируем предупреждение о конфликтах, но не блокируем создание
                        conflict_warning = None
                        if conflicts:
                            messages_list = []
                            for index, start_dt, conflict_data in conflicts[:3]:
                                local_dt = timezone.localtime(start_dt)
                                conflict_text = format_conflict_message(conflict_data)
                                messages_list.append(
                                    f"{local_dt.strftime('%d.%m.%Y %H:%M')} ({conflict_text})"
                                )
                            if len(conflicts) > 3:
                                messages_list.append('и другие конфликты…')
                            conflict_warning = 'Конфликты при создании серии: ' + '; '.join(messages_list)

                        series.save()
                        created_bookings = []
                        for index, start_dt in enumerate(occurrences, start=1):
                            booking = Booking.objects.create(
                                guest_name=guest_name,
                                guest_room_number=guest_room_number,
                                service_variant=service_variant,
                                specialist=specialist,
                                cabinet=cabinet,
                                start_time=start_dt,
                                created_by=request.user,
                                status='confirmed',
                                series=series,
                                sequence=index
                            )
                            created_bookings.append(booking)

                        created_count = len(created_bookings)
                        logger.info(f"Created booking series #{series.id} with {created_count} items by {request.user.username}")
                        
                        # Логируем создание серии
                        for booking in created_bookings:
                            log_booking_action(
                                booking=booking,
                                action='series_created',
                                user=request.user,
                                message=f'Создано бронирование в серии ({index} из {created_count})',
                                request=request
                            )
                        
                        response_data = {
                            'success': True,
                            'message': f'Создано {created_count} повторяющихся бронирований',
                            'booking_id': created_bookings[0].id,
                            'series_id': series.id
                        }
                        # Добавляем предупреждение если есть конфликты
                        if conflict_warning:
                            response_data['warning'] = conflict_warning
                        return JsonResponse(response_data)
                    else:
                        booking = Booking.objects.create(
                            guest_name=guest_name,
                            guest_room_number=guest_room_number,
                            service_variant=service_variant,
                            specialist=specialist,
                            cabinet=cabinet,
                            start_time=final_start_time,
                            created_by=request.user,
                            status='confirmed'
                        )
                        
                        # Логируем создание
                        log_booking_action(
                            booking=booking,
                            action='created',
                            user=request.user,
                            message=f'Быстрое создание бронирования для гостя {guest_name}',
                            request=request
                        )
                        
                        logger.info(f"Quick booking created: {booking.id} by {request.user.username}")
                        return JsonResponse({
                            'success': True,
                            'message': 'Бронирование успешно создано',
                            'booking_id': booking.id
                        })
                
            except Exception as e:
                logger.error(f"Error creating quick booking: {e}", exc_info=True)
                import traceback
                logger.error(traceback.format_exc())
                return JsonResponse({'error': f'Ошибка при создании бронирования: {str(e)}'}, status=500)
        else:
            logger.error(f"Form validation errors: {form.errors}")
            return JsonResponse({'error': 'Неверные данные формы', 'errors': form.errors}, status=400)
    
    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)


@admin_required
@require_POST
def duplicate_booking_view(request):
    """
    Дублирование одиночного бронирования на новую дату и время.
    """
    booking_id = request.POST.get('booking_id')
    start_datetime_str = request.POST.get('start_datetime')

    if not booking_id or not start_datetime_str:
        return JsonResponse({'success': False, 'error': 'Не переданы обязательные параметры'}, status=400)

    try:
        original_booking = Booking.objects.select_related(
            'service_variant',
            'specialist',
            'cabinet'
        ).get(pk=booking_id)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Бронирование не найдено'}, status=404)

    if original_booking.series_id:
        return JsonResponse({
            'success': False,
            'error': 'Нельзя копировать бронирования, входящие в серию'
        }, status=400)

    try:
        if 'T' in start_datetime_str and len(start_datetime_str) == 16:
            naive_dt = datetime.datetime.strptime(start_datetime_str, '%Y-%m-%dT%H:%M')
            target_start = timezone.make_aware(naive_dt)
        else:
            iso_str = start_datetime_str.replace('Z', '+00:00')
            target_start = timezone.datetime.fromisoformat(iso_str)
            if timezone.is_naive(target_start):
                target_start = timezone.make_aware(target_start)
            target_start = timezone.localtime(target_start)
            naive_local = timezone.localtime(target_start).replace(tzinfo=None)
            target_start = timezone.make_aware(naive_local)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Неверный формат даты'}, status=400)

    conflicts = check_booking_conflicts(
        start_time=target_start,
        service_variant=original_booking.service_variant,
        specialist=original_booking.specialist,
        cabinet=original_booking.cabinet
    )

    # Формируем предупреждение о конфликтах, но не блокируем копирование
    conflict_warning = None
    if conflicts:
        conflict_messages = []
        if conflicts.get('specialist_busy'):
            conflict_messages.append('Специалист занят в это время')
        if conflicts.get('cabinet_busy'):
            conflict_messages.append('Кабинет занят в это время')
        if conflicts.get('specialist_not_available'):
            conflict_messages.append('Специалист не работает в это время')
        if conflicts.get('cabinet_not_available'):
            conflict_messages.append('Кабинет недоступен в это время')
        conflict_warning = '; '.join(conflict_messages) if conflict_messages else 'Выбранное время имеет конфликты'

    try:
        with transaction.atomic():
            duplicated_booking = Booking.objects.create(
                guest_name=original_booking.guest_name,
                guest_room_number=original_booking.guest_room_number,
                service_variant=original_booking.service_variant,
                specialist=original_booking.specialist,
                cabinet=original_booking.cabinet,
                start_time=target_start,
                created_by=request.user,
                status=original_booking.status
            )
            
            # Логируем копирование
            log_booking_action(
                booking=duplicated_booking,
                action='duplicated',
                user=request.user,
                message=f'Скопировано из бронирования #{original_booking.id}',
                request=request
            )
            
            # Логируем в оригинальное бронирование
            log_booking_action(
                booking=original_booking,
                action='duplicated',
                user=request.user,
                message=f'Создана копия: бронирование #{duplicated_booking.id}',
                request=request
            )
    except Exception as exc:
        logger.error(
            f"Unable to duplicate booking #{original_booking.id}: {exc}",
            exc_info=True
        )
        return JsonResponse({'success': False, 'error': 'Не удалось создать копию бронирования'}, status=500)

    logger.info(
        "Booking duplicated: %s -> %s by %s",
        original_booking.id,
        duplicated_booking.id,
        request.user.username
    )

    response_data = {
        'success': True,
        'message': 'Бронирование скопировано',
        'booking_id': duplicated_booking.id
    }
    
    # Добавляем предупреждение если есть конфликты
    if conflict_warning:
        response_data['warning'] = conflict_warning
    
    return JsonResponse(response_data)


@admin_required
@require_POST
def update_booking_time_view(request):
    """
    Обновление времени бронирования через AJAX (drag & drop)
    """
    try:
        booking_id = request.POST.get('booking_id')
        start_datetime_str = request.POST.get('start_datetime')
        
        if not booking_id or not start_datetime_str:
            return JsonResponse({'error': 'Не указаны обязательные параметры'}, status=400)
        
        # Получаем бронирование
        booking = get_object_or_404(Booking, pk=booking_id)
        
        # Парсим дату (может быть в ISO формате с Z или без)
        try:
            # Пробуем парсить как naive datetime (локальное время) - формат YYYY-MM-DDTHH:MM
            if 'T' in start_datetime_str and len(start_datetime_str) == 16:
                naive_dt = datetime.datetime.strptime(start_datetime_str, '%Y-%m-%dT%H:%M')
                new_start_time = timezone.make_aware(naive_dt)
            else:
                # Пробуем ISO формат (может быть с Z или timezone offset)
                iso_str = start_datetime_str.replace('Z', '+00:00')
                new_start_time = timezone.datetime.fromisoformat(iso_str)
                if timezone.is_naive(new_start_time):
                    new_start_time = timezone.make_aware(new_start_time)
                # Конвертируем UTC в локальное время
                new_start_time = timezone.localtime(new_start_time)
                # Делаем aware снова для работы с БД (сохраняем локальное время)
                naive_local = timezone.localtime(new_start_time).replace(tzinfo=None)
                new_start_time = timezone.make_aware(naive_local)
            
            logger.debug(f"Parsed datetime: {start_datetime_str} -> {new_start_time} (local: {timezone.localtime(new_start_time)})")
        except ValueError as e:
            logger.error(f"Invalid datetime format in update_booking_time_view: {start_datetime_str}, error: {e}")
            return JsonResponse({'error': 'Неверный формат даты и времени'}, status=400)
        
        # Проверяем конфликты для предупреждения (не блокируем обновление)
        conflicts = check_booking_conflicts(
            start_time=new_start_time,
            service_variant=booking.service_variant,
            specialist=booking.specialist,
            cabinet=booking.cabinet,
            exclude_booking_id=booking.id
        )
        
        # Формируем предупреждение о конфликтах
        conflict_warning = None
        if conflicts:
            conflict_messages = []
            if conflicts.get('specialist_busy'):
                conflict_messages.append('Специалист занят в это время')
            if conflicts.get('cabinet_busy'):
                conflict_messages.append('Кабинет занят в это время')
            if conflicts.get('specialist_not_available'):
                conflict_messages.append('Специалист не работает в это время')
            if conflicts.get('cabinet_not_available'):
                conflict_messages.append('Кабинет недоступен в это время')
            conflict_warning = '; '.join(conflict_messages) if conflict_messages else 'Выбранное время имеет конфликты'
        
        # Сохраняем старое время для логирования
        old_start_time = booking.start_time
        
        # Обновляем бронирование (даже при конфликтах)
        booking.start_time = new_start_time
        booking.save()
        
        # Логируем изменение времени
        log_booking_action(
            booking=booking,
            action='time_changed',
            user=request.user,
            message=f'Время изменено с {timezone.localtime(old_start_time).strftime("%d.%m.%Y %H:%M")} на {timezone.localtime(new_start_time).strftime("%d.%m.%Y %H:%M")}',
            old_values={'start_time': old_start_time.isoformat()},
            new_values={'start_time': new_start_time.isoformat()},
            request=request
        )
        
        logger.info(f"Booking time updated: {booking.id} by {request.user.username}, new time: {new_start_time}")
        
        response_data = {
            'success': True,
            'message': 'Время бронирования успешно изменено'
        }
        
        # Добавляем предупреждение если есть конфликты
        if conflict_warning:
            response_data['warning'] = conflict_warning
        
        return JsonResponse(response_data)
        
    except (ValueError, TypeError) as e:
        logger.error(f"Error updating booking time: {e}", exc_info=True)
        return JsonResponse({'error': 'Неверный формат данных'}, status=400)
    except Exception as e:
        logger.error(f"Error updating booking time: {e}", exc_info=True)
        return JsonResponse({'error': 'Ошибка при обновлении времени'}, status=500)


# Delete booking view
@method_decorator(admin_required, name='dispatch')
class BookingDeleteView(DeleteView):
    """Удаление бронирования"""
    model = Booking
    template_name = 'booking/booking_confirm_delete.html'
    success_url = reverse_lazy('calendar')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        booking = self.object
        series = booking.series
        if series:
            context['series'] = series
            context['series_count'] = series.bookings.count()
        else:
            context['series'] = None
            context['series_count'] = 0
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        booking = self.object
        scope = request.POST.get('scope', 'single')
        deletion_reason = request.POST.get('deletion_reason', '')
        booking = self.object
        series = booking.series
        success_url = self.get_success_url()

        # Устанавливаем пользователя и причину удаления для сигнала
        set_current_user(
            user=request.user,
            deletion_reason=deletion_reason,
            deletion_scope=scope
        )

        try:
            if scope == 'series' and series:
                with transaction.atomic():
                    count = series.bookings.count()
                    # Логируем удаление каждого бронирования в серии
                    for b in series.bookings.all():
                        log_booking_action(
                            booking=b,
                            action='deleted',
                            user=request.user,
                            message=f'Удалено из серии (удалена вся серия из {count} бронирований)',
                            request=request
                        )
                    # Удаляем все бронирования серии (сигнал сработает для каждого)
                    series.bookings.all().delete()
                    series.delete()
                messages.success(request, f'Удалена серия из {count} бронирований')
                return redirect(success_url)

            with transaction.atomic():
                series_to_update = booking.series
                # Логируем удаление
                log_booking_action(
                    booking=booking,
                    action='deleted',
                    user=request.user,
                    message=f'Бронирование удалено' + (f'. Причина: {deletion_reason}' if deletion_reason else ''),
                    request=request
                )
                # Удаляем бронирование (сигнал pre_delete сработает автоматически)
                booking.delete()
                messages.success(request, 'Бронирование удалено')

                if series_to_update:
                    remaining = series_to_update.bookings.order_by('start_time')
                    if not remaining.exists():
                        series_to_update.delete()
                    else:
                        for index, item in enumerate(remaining, start=1):
                            if item.sequence != index:
                                item.sequence = index
                                item.save(update_fields=['sequence'])
        finally:
            # Очищаем thread-local storage
            clear_thread_locals()

        return redirect(success_url)


# Manage schedules view
@admin_required
def manage_schedules_view(request):
    """
    Управление графиками работы специалистов.
    """
    SpecialistScheduleFormSet = modelformset_factory(
        SpecialistSchedule,
        form=SpecialistScheduleForm,
        extra=7,
        max_num=7,
        can_delete=True
    )
    
    specialist_id = request.GET.get('specialist') or request.POST.get('specialist')
    specialist = None
    
    if specialist_id:
        specialist = get_object_or_404(SpecialistProfile, id=specialist_id)
    
    if request.method == 'POST':
        formset = SpecialistScheduleFormSet(request.POST, request.FILES)
        if formset.is_valid():
            instances = formset.save(commit=False)
            for instance in instances:
                instance.specialist = specialist
                instance.save()
            formset.save_m2m()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, 'Расписание успешно сохранено')
            redirect_url = reverse('manage_schedules')
            return redirect(f'{redirect_url}?specialist={specialist.id}')
    else:
        if specialist:
            formset = SpecialistScheduleFormSet(queryset=SpecialistSchedule.objects.filter(specialist=specialist))
        else:
            formset = SpecialistScheduleFormSet(queryset=SpecialistSchedule.objects.none())
    
    # Загружаем шаблоны для отображения
    from .models import ScheduleTemplate
    templates = ScheduleTemplate.objects.all()
    
    return render(request, 'booking/manage_schedules.html', {
        'formset': formset,
        'specialists': SpecialistProfile.objects.all(),
        'selected_specialist': specialist,
        'templates': templates
    })


@admin_required
def copy_schedule_view(request):
    """
    Копирование расписания от одного специалиста к другому.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запросы'}, status=405)
    
    source_specialist_id = request.POST.get('source_specialist_id')
    target_specialist_id = request.POST.get('target_specialist_id')
    
    if not source_specialist_id or not target_specialist_id:
        return JsonResponse({'error': 'Не указаны специалисты'}, status=400)
    
    if source_specialist_id == target_specialist_id:
        return JsonResponse({'error': 'Нельзя копировать расписание к самому себе'}, status=400)
    
    try:
        source_specialist = get_object_or_404(SpecialistProfile, id=source_specialist_id)
        target_specialist = get_object_or_404(SpecialistProfile, id=target_specialist_id)
        
        # Получаем все расписания исходного специалиста
        source_schedules = SpecialistSchedule.objects.filter(specialist=source_specialist)
        
        copied_count = 0
        for source_schedule in source_schedules:
            # Создаем или обновляем расписание целевого специалиста
            schedule, created = SpecialistSchedule.objects.update_or_create(
                specialist=target_specialist,
                day_of_week=source_schedule.day_of_week,
                defaults={
                    'start_time': source_schedule.start_time,
                    'end_time': source_schedule.end_time,
                }
            )
            if created or schedule.start_time != source_schedule.start_time or schedule.end_time != source_schedule.end_time:
                copied_count += 1
        
        logger.info(f"Schedule copied from {source_specialist.full_name} to {target_specialist.full_name}, {copied_count} days copied")
        
        return JsonResponse({
            'success': True,
            'message': f'Расписание успешно скопировано ({copied_count} дней)'
        })
        
    except Exception as e:
        logger.error(f"Error copying schedule: {e}", exc_info=True)
        return JsonResponse({'error': 'Ошибка при копировании расписания'}, status=500)


@admin_required
def apply_template_view(request):
    """
    Применение шаблона расписания к специалисту.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запросы'}, status=405)
    
    specialist_id = request.POST.get('specialist_id')
    template_id = request.POST.get('template_id')
    
    if not specialist_id or not template_id:
        return JsonResponse({'error': 'Не указаны специалист или шаблон'}, status=400)
    
    try:
        specialist = get_object_or_404(SpecialistProfile, id=specialist_id)
        template = get_object_or_404(ScheduleTemplate, id=template_id)
        
        # Применяем шаблон к специалисту
        applied_count = template.apply_to_specialist(specialist)
        
        logger.info(f"Template '{template.name}' applied to {specialist.full_name}, {applied_count} days applied")
        
        return JsonResponse({
            'success': True,
            'message': f'Шаблон "{template.name}" успешно применен ({applied_count} дней)'
        })
        
    except Exception as e:
        logger.error(f"Error applying template: {e}", exc_info=True)
        return JsonResponse({'error': 'Ошибка при применении шаблона'}, status=500)


# Reports view
@admin_required
def reports_view(request):
    """
    Страница отчетов.
    """
    form = ReportForm(request.GET or None)
    service_popularity = None
    specialist_load = None
    
    if form.is_valid():
        start = form.cleaned_data['start_date']
        end = form.cleaned_data['end_date']
        specialist = form.cleaned_data.get('specialist')
        
        # Фильтр для всех запросов
        bookings_filter = Booking.objects.filter(
            start_time__date__range=[start, end],
            status='confirmed'
        )
        
        if specialist:
            bookings_filter = bookings_filter.filter(specialist=specialist)
        
        service_popularity = bookings_filter.values('service_variant__service__name').annotate(
            count=Count('id')
        ).order_by('-count')
        
        specialist_load_qs = bookings_filter.values('specialist__full_name').annotate(
            total_duration=Sum('service_variant__duration_minutes')
        ).order_by('-total_duration')

        specialist_load = []
        for item in specialist_load_qs:
            minutes = item.get('total_duration') or 0
            if minutes >= 60:
                hours = minutes // 60
                remaining_minutes = minutes % 60
                if remaining_minutes:
                    display = f"{hours} ч {remaining_minutes} мин"
                else:
                    display = f"{hours} ч"
            else:
                display = f"{minutes} мин"

            specialist_load.append({
                **item,
                'total_duration_display': display,
                'total_duration_minutes': minutes
            })
    
    return render(request, 'booking/reports.html', {
        'form': form,
        'service_popularity': service_popularity,
        'specialist_load': specialist_load,
        'has_filters': form.is_valid()
    })


@admin_required
def download_report_view(request):
    """
    Скачивание отчета по бронированиям в формате CSV
    """
    form = ReportForm(request.GET or None)
    
    if not form.is_valid():
        messages.error(request, 'Неверные параметры отчета')
        return redirect('reports')
    
    start = form.cleaned_data['start_date']
    end = form.cleaned_data['end_date']
    specialist = form.cleaned_data.get('specialist')
    
    # Получаем бронирования с фильтрацией
    bookings_query = Booking.objects.filter(
        start_time__date__range=[start, end],
        status='confirmed'
    ).select_related(
        'service_variant', 'service_variant__service',
        'specialist', 'cabinet'
    ).order_by('start_time')
    
    if specialist:
        bookings_query = bookings_query.filter(specialist=specialist)
    
    # Создаем CSV ответ
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    
    # Формируем имя файла
    filename_parts = [f'otchet_{start.strftime("%Y-%m-%d")}_{end.strftime("%Y-%m-%d")}']
    if specialist:
        filename_parts.append(specialist.full_name.replace(' ', '_'))
    filename = '_'.join(filename_parts) + '.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Настраиваем CSV writer с поддержкой UTF-8 BOM для Excel
    response.write('\ufeff')  # UTF-8 BOM для корректного отображения в Excel
    writer = csv.writer(response, delimiter=';')
    
    # Заголовки
    headers = [
        'Дата',
        'Время начала',
        'Время окончания',
        'Гость',
        'Номер комнаты',
        'Процедура',
        'Длительность (мин)',
        'Стоимость',
        'Специалист',
        'Кабинет',
        'Статус'
    ]
    writer.writerow(headers)
    
    total_cost = Decimal('0')
    
    # Данные
    for booking in bookings_query:
        local_start = timezone.localtime(booking.start_time)
        local_end = timezone.localtime(booking.end_time)
        
        cost = booking.service_variant.price
        total_cost += cost
        
        row = [
            local_start.strftime('%d.%m.%Y'),
            local_start.strftime('%H:%M'),
            local_end.strftime('%H:%M'),
            booking.guest_name,
            booking.guest_room_number or '',
            str(booking.service_variant),
            booking.service_variant.duration_minutes,
            str(cost).replace('.', ','),  # Замена точки на запятую для Excel
            booking.specialist.full_name,
            booking.cabinet.name,
            booking.get_status_display()
        ]
        writer.writerow(row)
    
    # Итоговая строка
    writer.writerow([])  # Пустая строка
    writer.writerow(['ИТОГО:', '', '', '', '', '', '', str(total_cost).replace('.', ','), '', '', ''])
    
    logger.info(f"Report downloaded: period={start} to {end}, specialist={specialist.full_name if specialist else 'all'}, bookings={bookings_query.count()}")
    
    return response


def specialist_register_view(request):
    """Регистрация нового специалиста"""
    if request.user.is_authenticated:
        messages.info(request, 'Вы уже авторизованы. Для регистрации нового специалиста выйдите из системы.')
        return redirect('index')
    
    if request.method == 'POST':
        form = SpecialistRegistrationForm(request.POST)
        if form.is_valid():
            # Создаем пользователя
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'] or '',
                password=form.cleaned_data['password1']
            )
            
            # Добавляем в группу Specialist
            try:
                specialist_group = Group.objects.get(name='Specialist')
                user.groups.add(specialist_group)
            except Group.DoesNotExist:
                # Если группа не существует, создаем её
                specialist_group = Group.objects.create(name='Specialist')
                user.groups.add(specialist_group)
            
            # Создаем профиль специалиста
            SpecialistProfile.objects.create(
                user=user,
                full_name=form.cleaned_data['full_name']
            )
            
            messages.success(request, 'Регистрация успешна! Теперь вы можете войти в систему.')
            return redirect('login')
    else:
        form = SpecialistRegistrationForm()
    
    return render(request, 'registration/specialist_register.html', {
        'form': form
    })


def build_service_variant_groups(service_variants, cabinets):
    """Группирует варианты услуг по типам кабинетов с указанием доступных кабинетов."""
    cabinets_by_type = defaultdict(list)
    for cabinet in cabinets:
        cabinets_by_type[cabinet.cabinet_type_id].append(cabinet.name)
    for names in cabinets_by_type.values():
        names.sort(key=str.lower)

    groups = {}

    for variant in service_variants:
        cabinet_types = list(variant.service.required_cabinet_types.all())
        if cabinet_types:
            for cabinet_type in cabinet_types:
                key = ('type', cabinet_type.id)
                entry = groups.setdefault(key, {
                    'label': '',
                    'variants': []
                })
                if not entry['label']:
                    names = cabinets_by_type.get(cabinet_type.id, [])
                    entry['label'] = f"{cabinet_type.name} ({', '.join(names)})" if names else cabinet_type.name
                entry['variants'].append(variant)
        else:
            entry = groups.setdefault(('unassigned', None), {
                'label': 'Без привязки к кабинету',
                'variants': []
            })
            entry['variants'].append(variant)

    # Удаляем дубликаты, сохраняя порядок
    for entry in groups.values():
        seen = set()
        unique_variants = []
        for variant in entry['variants']:
            if variant.id not in seen:
                unique_variants.append(variant)
                seen.add(variant.id)
        entry['variants'] = unique_variants

    sorted_entries = sorted(
        groups.items(),
        key=lambda item: (item[0][0] == 'unassigned', item[1]['label'].lower())
    )

    return [entry for _, entry in sorted_entries]


# Deleted bookings views
def format_iso_datetime_str(iso_str):
    """Вспомогательная функция для форматирования ISO datetime строки"""
    if not iso_str:
        return "—"
    try:
        from datetime import datetime
        if isinstance(iso_str, str) and 'T' in iso_str:
            dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            local_dt = timezone.localtime(dt)
            return local_dt.strftime('%d.%m.%Y %H:%M')
        return str(iso_str)
    except (ValueError, AttributeError, TypeError):
        return str(iso_str)


@admin_required
def deleted_bookings_view(request):
    """
    Список удаленных бронирований.
    """
    deleted_bookings = DeletedBooking.objects.all().select_related('deleted_by', 'restored_by')
    
    # Фильтры
    restored_filter = request.GET.get('restored', '')
    if restored_filter == 'yes':
        deleted_bookings = deleted_bookings.filter(restored=True)
    elif restored_filter == 'no':
        deleted_bookings = deleted_bookings.filter(restored=False)
    
    scope_filter = request.GET.get('scope', '')
    if scope_filter in ['single', 'series']:
        deleted_bookings = deleted_bookings.filter(deletion_scope=scope_filter)
    
    # Поиск
    search_query = request.GET.get('search', '')
    if search_query:
        deleted_bookings = deleted_bookings.filter(
            models.Q(booking_data__guest_name__icontains=search_query) |
            models.Q(booking_data__specialist_name__icontains=search_query) |
            models.Q(booking_data__cabinet_name__icontains=search_query)
        )
    
    # Пагинация
    from django.core.paginator import Paginator
    paginator = Paginator(deleted_bookings, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Форматируем даты для каждого бронирования на текущей странице
    for deleted in page_obj:
        if deleted.booking_data and deleted.booking_data.get('start_time'):
            deleted.booking_data['start_time_formatted'] = format_iso_datetime_str(
                deleted.booking_data['start_time']
            )
    
    return render(request, 'booking/deleted_bookings_list.html', {
        'page_obj': page_obj,
        'restored_filter': restored_filter,
        'scope_filter': scope_filter,
        'search_query': search_query,
    })


@admin_required
def deleted_booking_detail_view(request, pk):
    """
    Детали удаленного бронирования.
    """
    deleted_booking = get_object_or_404(DeletedBooking, pk=pk)
    
    # Форматируем даты
    if deleted_booking.booking_data:
        if deleted_booking.booking_data.get('start_time'):
            deleted_booking.booking_data['start_time_formatted'] = format_iso_datetime_str(
                deleted_booking.booking_data['start_time']
            )
        if deleted_booking.booking_data.get('end_time'):
            from datetime import datetime
            end_time_str = deleted_booking.booking_data['end_time']
            try:
                if isinstance(end_time_str, str) and 'T' in end_time_str:
                    dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt)
                    local_dt = timezone.localtime(dt)
                    deleted_booking.booking_data['end_time_formatted'] = local_dt.strftime('%H:%M')
                else:
                    deleted_booking.booking_data['end_time_formatted'] = str(end_time_str)
            except (ValueError, AttributeError, TypeError):
                deleted_booking.booking_data['end_time_formatted'] = str(end_time_str)
    
    # Проверяем конфликты для восстановления
    conflicts = None
    if not deleted_booking.restored:
        conflicts = check_restore_conflicts(
            deleted_booking.booking_data,
            deleted_booking.series_data
        )
    
    return render(request, 'booking/deleted_booking_detail.html', {
        'deleted_booking': deleted_booking,
        'conflicts': conflicts,
    })


@admin_required
@require_POST
def restore_booking_view(request, pk):
    """
    Восстановление удаленного бронирования.
    """
    deleted_booking = get_object_or_404(DeletedBooking, pk=pk)
    
    if deleted_booking.restored:
        messages.error(request, 'Бронирование уже было восстановлено ранее')
        return redirect('deleted_bookings')
    
    scope = request.POST.get('scope', 'single')
    
    if scope == 'series' and deleted_booking.series_id:
        success, bookings, message = restore_series(deleted_booking.id, request.user)
    else:
        success, booking, message = restore_booking(deleted_booking.id, request.user)
        bookings = [booking] if booking else []
    
    if success:
        count = len(bookings)
        messages.success(request, f'{message}. Восстановлено бронирований: {count}')
        return redirect('calendar')
    else:
        messages.error(request, f'Не удалось восстановить: {message}')
        return redirect('deleted_booking_detail', pk=pk)


@admin_required
@require_POST
def permanently_delete_view(request, pk):
    """
    Окончательное удаление из архива.
    """
    deleted_booking = get_object_or_404(DeletedBooking, pk=pk)
    
    if deleted_booking.restored:
        messages.error(request, 'Нельзя удалить восстановленное бронирование')
        return redirect('deleted_booking_detail', pk=pk)
    
    booking_data = deleted_booking.booking_data or {}
    guest_name = booking_data.get('guest_name', 'Неизвестно')
    
    deleted_booking.delete()
    messages.success(request, f'Бронирование "{guest_name}" окончательно удалено из архива')
    
    return redirect('deleted_bookings')
