"""
Утилиты для работы с бронированиями и поиска слотов
"""
from django.db.models import Q
from django.utils import timezone
import datetime
from .models import ServiceVariant, SpecialistSchedule, Booking, SystemSettings, Cabinet, SpecialistProfile


def find_available_slots(date: datetime.date, service_variant: ServiceVariant) -> list:
    """
    Возвращает список словарей со свободными слотами.
    
    Новый формат: [{'start_time': datetime, 'specialist': Specialist, 'available_cabinets': [Cabinet, ...]}, ...]
    Старый формат (для обратной совместимости): [{'start_time': datetime, 'specialist': Specialist, 'cabinet': Cabinet}, ...]
    
    Для обратной совместимости, если в слоте есть 'available_cabinets', то 'cabinet' будет равен первому доступному кабинету.
    
    Args:
        date: Дата для поиска слотов
        service_variant: Вариант услуги, для которой ищем слоты
        
    Returns:
        Список доступных слотов с доступными кабинетами
    """
    
    # 1. Получаем все входные данные
    settings = SystemSettings.get_solo()
    duration = service_variant.duration_minutes
    buffer = settings.buffer_time_minutes
    total_slot_duration = duration + buffer
    
    # 2. Находим валидных специалистов и кабинеты
    service = service_variant.service
    required_cabinet_types = service.required_cabinet_types.all()
    
    valid_specialists = SpecialistProfile.objects.filter(services_can_perform=service)
    valid_cabinets = Cabinet.objects.filter(
        cabinet_type__in=required_cabinet_types, 
        is_active=True
    )
    
    # 3. Находим графики работы на этот день
    day_of_week = date.weekday()
    schedules = SpecialistSchedule.objects.filter(
        specialist__in=valid_specialists,
        day_of_week=day_of_week
    )
    
    # 4. Получаем ВСЕ бронирования на этот день (для проверки конфликтов)
    day_start = timezone.make_aware(datetime.datetime.combine(date, datetime.time.min))
    day_end = timezone.make_aware(datetime.datetime.combine(date, datetime.time.max))
    
    existing_bookings = Booking.objects.filter(
        start_time__range=(day_start, day_end),
        status='confirmed'
    ).select_related('specialist', 'cabinet')
    
    # 5. Генерируем "сетку" времени (напр., с шагом 15 мин)
    time_increment = 15  # Шаг проверки
    available_slots = []
    
    # Используем словарь для группировки слотов по времени и специалисту
    slots_dict = {}
    
    for schedule in schedules:
        specialist = schedule.specialist
        current_time = schedule.start_time
        
        # Создаем начальное время для итерации
        slot_datetime_start = timezone.make_aware(
            datetime.datetime.combine(date, current_time)
        )
        slot_datetime_end = slot_datetime_start + datetime.timedelta(minutes=total_slot_duration)
        
        while slot_datetime_end.time() <= schedule.end_time:
            
            # 6. Проверка: Свободен ли специалист?
            is_specialist_busy = existing_bookings.filter(
                specialist=specialist,
                start_time__lt=slot_datetime_end,
                end_time__gt=slot_datetime_start
            ).exists()
            
            if not is_specialist_busy:
                # 7. Находим все доступные кабинеты для этого слота
                # Находим кабинеты, занятые в этот слот КЕМ УГОДНО
                busy_cabinets_ids = existing_bookings.filter(
                    start_time__lt=slot_datetime_end,
                    end_time__gt=slot_datetime_start
                ).values_list('cabinet_id', flat=True)
                
                # Находим все свободные кабинеты нужного типа
                available_cabinets = list(valid_cabinets.exclude(id__in=busy_cabinets_ids))
                
                if available_cabinets:
                    # Создаем ключ для группировки: время + специалист
                    slot_key = (slot_datetime_start, specialist.id)
                    
                    # Если слот с таким временем и специалистом уже есть, объединяем кабинеты
                    if slot_key in slots_dict:
                        # Объединяем списки кабинетов, убирая дубликаты
                        existing_cabinets = slots_dict[slot_key]['available_cabinets']
                        all_cabinets = existing_cabinets + available_cabinets
                        # Убираем дубликаты, сохраняя порядок
                        unique_cabinets = []
                        seen_ids = set()
                        for cab in all_cabinets:
                            if cab.id not in seen_ids:
                                unique_cabinets.append(cab)
                                seen_ids.add(cab.id)
                        slots_dict[slot_key]['available_cabinets'] = unique_cabinets
                    else:
                        # Создаем новый слот
                        slots_dict[slot_key] = {
                            'start_time': slot_datetime_start,
                            'specialist': specialist,
                            'available_cabinets': available_cabinets,
                            # Для обратной совместимости добавляем первый кабинет
                            'cabinet': available_cabinets[0] if available_cabinets else None
                        }
            
            # Двигаемся к следующему слоту
            slot_datetime_start += datetime.timedelta(minutes=time_increment)
            slot_datetime_end = slot_datetime_start + datetime.timedelta(minutes=total_slot_duration)
    
    # Конвертируем словарь в список
    available_slots = list(slots_dict.values())
    
    # Сортируем по времени начала
    available_slots.sort(key=lambda x: x['start_time'])
    
    return available_slots


def check_booking_conflicts(start_time, service_variant, specialist, cabinet, exclude_booking_id=None):
    """
    Проверяет конфликты для указанного времени, специалиста, кабинета и услуги.
    
    Args:
        start_time: datetime - время начала бронирования (timezone-aware)
        service_variant: ServiceVariant - вариант услуги
        specialist: SpecialistProfile - специалист
        cabinet: Cabinet - кабинет
        exclude_booking_id: int (optional) - ID бронирования, которое нужно исключить из проверки
        
    Returns:
        dict с информацией о конфликтах или None если конфликтов нет
        Формат: {
            'specialist_busy': bool,
            'cabinet_busy': bool,
            'specialist_not_available': bool,
            'cabinet_not_available': bool
        }
    """
    conflicts = {
        'specialist_busy': False,
        'cabinet_busy': False,
        'specialist_not_available': False,
        'cabinet_not_available': False
    }
    
    # Получаем настройки для расчета времени окончания
    settings = SystemSettings.get_solo()
    duration = service_variant.duration_minutes
    buffer = settings.buffer_time_minutes
    total_duration = duration + buffer
    end_time = start_time + datetime.timedelta(minutes=total_duration)
    
    # Проверяем что время в будущем (или текущее)
    if start_time < timezone.now():
        # Это не конфликт, но может быть проблемой - не обрабатываем здесь
        pass
    
    # Проверяем график работы специалиста
    date = timezone.localtime(start_time).date()
    day_of_week = date.weekday()
    local_start_time = timezone.localtime(start_time).time()
    
    schedule = SpecialistSchedule.objects.filter(
        specialist=specialist,
        day_of_week=day_of_week
    ).first()
    
    if not schedule:
        conflicts['specialist_not_available'] = True
    else:
        # Проверяем что время начала входит в рабочие часы
        if local_start_time < schedule.start_time:
            conflicts['specialist_not_available'] = True
        else:
            # Проверяем что время окончания не выходит за рабочие часы
            local_end_time = timezone.localtime(end_time).time()
            if local_end_time > schedule.end_time:
                conflicts['specialist_not_available'] = True
    
    # Проверяем что кабинет активен
    if not cabinet.is_active:
        conflicts['cabinet_not_available'] = True
    
    # Проверяем конфликты с существующими бронированиями
    # Получаем все бронирования, которые пересекаются с нашим временем
    overlapping_bookings = Booking.objects.filter(
        start_time__lt=end_time,
        end_time__gt=start_time,
        status='confirmed'  # Проверяем только подтвержденные бронирования
    ).select_related('specialist', 'cabinet')
    
    # Исключаем текущее бронирование если указано
    if exclude_booking_id:
        overlapping_bookings = overlapping_bookings.exclude(id=exclude_booking_id)
    
    # Проверяем занятость специалиста
    specialist_conflicts = overlapping_bookings.filter(specialist=specialist)
    if specialist_conflicts.exists():
        conflicts['specialist_busy'] = True
    
    # Проверяем занятость кабинета
    cabinet_conflicts = overlapping_bookings.filter(cabinet=cabinet)
    if cabinet_conflicts.exists():
        conflicts['cabinet_busy'] = True
    
    # Возвращаем None если нет конфликтов, иначе словарь с конфликтами
    if any(conflicts.values()):
        return conflicts
    else:
        return None

