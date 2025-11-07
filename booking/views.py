from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.forms import modelformset_factory
from django.db.models import Count, Sum
from django.utils import timezone
from django.contrib import messages
import datetime
import logging

from django.contrib.auth.models import User, Group
from .models import Booking, SpecialistProfile, Cabinet, ServiceVariant, SpecialistSchedule, ScheduleTemplate
from .decorators import admin_required, specialist_required
from .utils import find_available_slots, check_booking_conflicts
from .forms import SelectServiceForm, SpecialistScheduleForm, ReportForm, BookingEditForm, QuickBookingForm, SpecialistRegistrationForm

logger = logging.getLogger(__name__)


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
    
    # Получаем список услуг для dropdown
    services = ServiceVariant.objects.all().select_related('service').order_by('service__name', 'duration_minutes')
    
    # Получаем кабинеты для легенды
    cabinets = Cabinet.objects.filter(is_active=True).order_by('id')
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
    
    return render(request, 'calendar.html', {
        'quick_form': quick_form,
        'services': services,
        'cabinets_with_colors': cabinets_with_colors
    })


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
                'cabinetId': b.cabinet.id,  # Для вида "по кабинетам"
                'status': b.status,
                'specialist': b.specialist.full_name,
                'cabinet': b.cabinet.name,
                'guest_name': b.guest_name,
                'guest_room': b.guest_room_number
            },
            'backgroundColor': colors['bg'],
            'borderColor': colors['border'],
            'textColor': colors['text']
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
        
        # Используем check_booking_conflicts для проверки доступности кабинетов
        # Это позволяет исключить текущее бронирование из проверки
        from .utils import check_booking_conflicts
        
        # Получаем все кабинеты подходящего типа для услуги
        service = service_variant.service
        required_cabinet_types = service.required_cabinet_types.all()
        valid_cabinets = Cabinet.objects.filter(
            cabinet_type__in=required_cabinet_types,
            is_active=True
        )
        
        # Проверяем каждый кабинет на доступность
        available_cabinets = []
        exclude_id = int(exclude_booking_id) if exclude_booking_id else None
        
        for cabinet in valid_cabinets:
            conflicts = check_booking_conflicts(
                start_time=start_datetime,
                service_variant=service_variant,
                specialist=specialist,
                cabinet=cabinet,
                exclude_booking_id=exclude_id
            )
            
            if not conflicts:
                available_cabinets.append(cabinet)
        
        if not available_cabinets:
            logger.warning(f"No available cabinets for specialist {specialist_id}, datetime {datetime_str}, exclude_booking_id={exclude_id}")
            return JsonResponse({'error': 'Слот не найден или недоступен'}, status=404)
        
        cabinets_data = [{'id': cab.id, 'name': cab.name} for cab in available_cabinets]
        
        logger.debug(f"Returning {len(cabinets_data)} available cabinets for slot, exclude_booking_id={exclude_id}")
        return JsonResponse({'cabinets': cabinets_data}, safe=False)
        
    except (ValueError, ServiceVariant.DoesNotExist, SpecialistProfile.DoesNotExist) as e:
        logger.error(f"Error getting available cabinets: {e}", exc_info=True)
        return JsonResponse({'error': 'Ошибка при получении доступных кабинетов'}, status=500)


# Booking wizard views
@admin_required
def select_service_view(request):
    """
    Шаг 1: Выбор услуги и даты.
    """
    if request.method == 'GET':
        form = SelectServiceForm()
        return render(request, 'booking/select_service.html', {'form': form})
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
        Booking.objects.create(
            guest_name=request.POST.get('guest_name'),
            guest_room_number=request.POST.get('guest_room_number'),
            service_variant_id=service_variant_id,
            specialist_id=specialist_id,
            cabinet_id=cabinet_id,
            start_time=start_time,
            created_by=request.user,
            status='confirmed'
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
    
    if request.method == 'POST':
        form = BookingEditForm(request.POST, instance=booking)
        if form.is_valid():
            try:
                form.save()
                logger.info(f"Booking {booking.id} updated by {request.user.username}")
                messages.success(request, 'Бронирование успешно обновлено')
                return redirect('booking_detail', pk=booking.pk)
            except Exception as e:
                logger.error(f"Error updating booking {booking.id}: {e}", exc_info=True)
                messages.error(request, 'Ошибка при обновлении бронирования. Попробуйте еще раз.')
        else:
            logger.warning(f"Form validation errors for booking {booking.id}: {form.errors}")
            messages.error(request, 'Ошибка при обновлении бронирования. Проверьте введенные данные.')
    else:
        form = BookingEditForm(instance=booking)
    
    return render(request, 'booking/booking_detail.html', {
        'booking': booking,
        'form': form
    })


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
        
        # Проверяем конфликты
        conflicts = check_booking_conflicts(
            start_time=start_time,
            service_variant=service_variant,
            specialist=specialist,
            cabinet=cabinet,
            exclude_booking_id=booking.id
        )
        
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
            
            return JsonResponse({
                'valid': False,
                'error': '; '.join(conflict_messages) if conflict_messages else 'Выбранное время недоступно',
                'conflicts': conflicts
            })
        
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
        
        return JsonResponse({
            'valid': True,
            'message': 'Данные валидны'
        })
        
    except Exception as e:
        logger.error(f"Error validating booking edit {pk}: {e}", exc_info=True)
        return JsonResponse({
            'valid': False,
            'error': 'Ошибка при проверке данных'
        }, status=500)


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
                
                # Конвертируем в локальное время для сравнения
                local_start = timezone.localtime(start_datetime)
                
                logger.info(f"Quick booking attempt: date={local_start.date()}, time={local_start.time()}, specialist={specialist.id}, service={service_variant.id}")
                
                # Проверяем доступность слота
                date = local_start.date()
                available_slots = find_available_slots(date, service_variant)
                
                logger.info(f"Found {len(available_slots)} available slots for date {date}")
                
                # Фильтруем слоты по специалисту
                specialist_slots = [slot for slot in available_slots if slot['specialist'].id == specialist.id]
                logger.info(f"Found {len(specialist_slots)} slots for specialist {specialist.id}")
                
                # Ищем подходящий слот - сначала точное совпадение, затем ближайший
                suitable_slot = None
                min_diff = None
                
                for slot in specialist_slots:
                    slot_start = slot['start_time']
                    # Конвертируем в локальное время для сравнения
                    local_slot = timezone.localtime(slot_start)
                    
                    # Точное совпадение по часам и минутам
                    if (local_slot.year == local_start.year and
                        local_slot.month == local_start.month and
                        local_slot.day == local_start.day and
                        local_slot.hour == local_start.hour and
                        local_slot.minute == local_start.minute):
                        suitable_slot = slot
                        break
                    
                    # Если точного совпадения нет, находим ближайший слот (не ранее выбранного времени)
                    if local_slot >= local_start:
                        diff = (local_slot - local_start).total_seconds()
                        if min_diff is None or diff < min_diff:
                            min_diff = diff
                            suitable_slot = slot
                
                if not suitable_slot:
                    if not specialist_slots:
                        return JsonResponse({
                            'error': f'Нет доступных слотов для специалиста {specialist.full_name} на {date.strftime("%d.%m.%Y")}. Проверьте график работы специалиста.'
                        }, status=400)
                    else:
                        return JsonResponse({
                            'error': f'Выбранное время ({local_start.strftime("%H:%M")}) недоступно. Ближайшие доступные слоты начинаются с {timezone.localtime(specialist_slots[0]["start_time"]).strftime("%H:%M")}'
                        }, status=400)
                
                # Используем время из найденного слота (правильное время из графика)
                final_start_time = suitable_slot['start_time']
                
                # Определяем кабинет
                selected_cabinet = form.cleaned_data.get('cabinet')
                if selected_cabinet:
                    # Проверяем что выбранный кабинет доступен для этого слота
                    available_cabinets = suitable_slot.get('available_cabinets', [])
                    if available_cabinets:
                        cabinet_ids = [cab.id for cab in available_cabinets]
                        if selected_cabinet.id not in cabinet_ids:
                            return JsonResponse({
                                'error': 'Выбранный кабинет недоступен для данного времени'
                            }, status=400)
                        cabinet = selected_cabinet
                    elif suitable_slot.get('cabinet'):
                        # Для обратной совместимости со старым форматом
                        if suitable_slot['cabinet'].id != selected_cabinet.id:
                            return JsonResponse({
                                'error': 'Выбранный кабинет недоступен для данного времени'
                            }, status=400)
                        cabinet = selected_cabinet
                    else:
                        cabinet = selected_cabinet
                else:
                    # Если кабинет не выбран, используем первый доступный из слота
                    if suitable_slot.get('available_cabinets'):
                        cabinet = suitable_slot['available_cabinets'][0]
                    elif suitable_slot.get('cabinet'):
                        cabinet = suitable_slot['cabinet']
                    else:
                        return JsonResponse({
                            'error': 'Нет доступных кабинетов для данного времени'
                        }, status=400)
                
                # Дополнительная валидация: проверяем что кабинет подходит для услуги
                service = service_variant.service
                required_cabinet_types = service.required_cabinet_types.all()
                if cabinet.cabinet_type not in required_cabinet_types:
                    return JsonResponse({
                        'error': 'Выбранный кабинет не подходит для данной услуги'
                    }, status=400)
                
                # Создаем бронирование
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
        
        # Проверяем доступность нового слота используя check_booking_conflicts
        # Это исключает само изменяемое бронирование из проверки
        from .utils import check_booking_conflicts
        
        # Сначала проверяем текущий кабинет
        conflicts = check_booking_conflicts(
            start_time=new_start_time,
            service_variant=booking.service_variant,
            specialist=booking.specialist,
            cabinet=booking.cabinet,
            exclude_booking_id=booking.id
        )
        
        new_cabinet = booking.cabinet
        
        # Если текущий кабинет недоступен, ищем доступный
        if conflicts:
            logger.debug(f"Current cabinet {booking.cabinet.id} not available, searching for alternatives")
            
            # Получаем все кабинеты подходящего типа для услуги
            service = booking.service_variant.service
            required_cabinet_types = service.required_cabinet_types.all()
            valid_cabinets = Cabinet.objects.filter(
                cabinet_type__in=required_cabinet_types,
                is_active=True
            )
            
            # Проверяем каждый кабинет на доступность
            found_cabinet = None
            for cab in valid_cabinets:
                cab_conflicts = check_booking_conflicts(
                    start_time=new_start_time,
                    service_variant=booking.service_variant,
                    specialist=booking.specialist,
                    cabinet=cab,
                    exclude_booking_id=booking.id
                )
                if not cab_conflicts:
                    found_cabinet = cab
                    logger.debug(f"Found available cabinet {cab.id} for booking {booking.id}")
                    break
            
            if not found_cabinet:
                logger.warning(f"No available cabinet found for booking {booking.id} at {new_start_time}")
                return JsonResponse({'error': 'Нет доступных кабинетов для выбранного времени'}, status=400)
            
            new_cabinet = found_cabinet
            logger.info(f"Using alternative cabinet {new_cabinet.id} for booking {booking.id}")
        else:
            logger.debug(f"Current cabinet {booking.cabinet.id} is available for new time")
        
        # Обновляем бронирование
        booking.start_time = new_start_time
        booking.cabinet = new_cabinet
        booking.save()
        
        logger.info(f"Booking time updated: {booking.id} by {request.user.username}, new time: {new_start_time}, cabinet: {new_cabinet.id}")
        return JsonResponse({
            'success': True,
            'message': 'Время бронирования успешно изменено'
        })
        
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
            return redirect(f'manage_schedules?specialist={specialist.id}')
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
        
        service_popularity = Booking.objects.filter(
            start_time__date__range=[start, end],
            status='confirmed'
        ).values('service_variant__service__name').annotate(
            count=Count('id')
        ).order_by('-count')
        
        specialist_load = Booking.objects.filter(
            start_time__date__range=[start, end],
            status='confirmed'
        ).values('specialist__full_name').annotate(
            total_duration=Sum('service_variant__duration_minutes')
        ).order_by('-total_duration')
    
    return render(request, 'booking/reports.html', {
        'form': form,
        'service_popularity': service_popularity,
        'specialist_load': specialist_load
    })


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
