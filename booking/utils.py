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
    
    Формат: [{'start_time': datetime, 'specialist': Specialist, 'cabinet': Cabinet}, ...]
    
    Args:
        date: Дата для поиска слотов
        service_variant: Вариант услуги, для которой ищем слоты
        
    Returns:
        Список доступных слотов
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
                # 7. Проверка: Свободен ли кабинет? (Логика Q.8)
                # Находим кабинеты, занятые в этот слот КЕМ УГОДНО
                busy_cabinets_ids = existing_bookings.filter(
                    start_time__lt=slot_datetime_end,
                    end_time__gt=slot_datetime_start
                ).values_list('cabinet_id', flat=True)
                
                # Находим свободный кабинет нужного типа
                available_cabinet = valid_cabinets.exclude(id__in=busy_cabinets_ids).first()
                
                if available_cabinet:
                    # Слот найден!
                    available_slots.append({
                        'start_time': slot_datetime_start,
                        'specialist': specialist,
                        'cabinet': available_cabinet
                    })
            
            # Двигаемся к следующему слоту
            slot_datetime_start += datetime.timedelta(minutes=time_increment)
            slot_datetime_end = slot_datetime_start + datetime.timedelta(minutes=total_slot_duration)
    
    return available_slots

