"""
Утилиты для восстановления удаленных бронирований.
"""
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
import logging

from .models import DeletedBooking, Booking, BookingSeries, ServiceVariant, SpecialistProfile, Cabinet
from .utils import check_booking_conflicts

logger = logging.getLogger(__name__)


def check_restore_conflicts(booking_data, series_data=None):
    """
    Проверяет конфликты при восстановлении бронирования.
    
    Args:
        booking_data: Словарь с данными бронирования
        series_data: Словарь с данными серии (опционально)
    
    Returns:
        dict: Словарь с информацией о конфликтах или None, если конфликтов нет
    """
    try:
        # Проверяем существование связанных объектов
        service_variant_id = booking_data.get('service_variant_id')
        specialist_id = booking_data.get('specialist_id')
        cabinet_id = booking_data.get('cabinet_id')
        
        if not service_variant_id or not ServiceVariant.objects.filter(id=service_variant_id).exists():
            return {'error': 'Услуга больше не существует'}
        
        if not specialist_id or not SpecialistProfile.objects.filter(id=specialist_id).exists():
            return {'error': 'Специалист больше не существует'}
        
        if not cabinet_id or not Cabinet.objects.filter(id=cabinet_id).exists():
            return {'error': 'Кабинет больше не существует'}
        
        service_variant = ServiceVariant.objects.get(id=service_variant_id)
        specialist = SpecialistProfile.objects.get(id=specialist_id)
        cabinet = Cabinet.objects.get(id=cabinet_id)
        
        # Парсим время начала
        start_time_str = booking_data.get('start_time')
        if not start_time_str:
            return {'error': 'Не указано время начала'}
        
        from datetime import datetime
        if isinstance(start_time_str, str):
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            if timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)
        else:
            start_time = start_time_str
        
        # Проверяем конфликты
        conflicts = check_booking_conflicts(
            start_time=start_time,
            service_variant=service_variant,
            specialist=specialist,
            cabinet=cabinet
        )
        
        if conflicts:
            return conflicts
        
        # Если есть серия, проверяем все вхождения
        if series_data:
            from .models import BookingSeries
            series = BookingSeries()
            series.frequency = series_data.get('frequency')
            series.interval = series_data.get('interval')
            series.start_time = start_time
            series.end_date = None
            if series_data.get('end_date'):
                from datetime import date
                end_date_str = series_data.get('end_date')
                if isinstance(end_date_str, str):
                    series.end_date = date.fromisoformat(end_date_str.split('T')[0])
                else:
                    series.end_date = end_date_str
            series.occurrence_count = series_data.get('occurrence_count')
            series.weekdays = series_data.get('weekdays', [])
            excluded_dates = series_data.get('excluded_dates', [])
            if excluded_dates:
                from datetime import date
                parsed_excluded = []
                for d in excluded_dates:
                    if isinstance(d, str):
                        parsed_excluded.append(date.fromisoformat(d.split('T')[0]))
                    else:
                        parsed_excluded.append(d)
                series.excluded_dates = parsed_excluded
            
            occurrences = series.generate_datetimes()
            if occurrences:
                # Импортируем функцию из views
                from booking.views import detect_occurrence_conflicts
                series_conflicts = detect_occurrence_conflicts(
                    occurrences,
                    service_variant=service_variant,
                    specialist=specialist,
                    cabinet=cabinet
                )
                if series_conflicts:
                    return {'series_conflicts': series_conflicts}
        
        return None
        
    except Exception as e:
        logger.error(f"Error checking restore conflicts: {e}", exc_info=True)
        return {'error': f'Ошибка при проверке конфликтов: {str(e)}'}


@transaction.atomic
def restore_booking(deleted_booking_id, restored_by=None):
    """
    Восстанавливает удаленное бронирование.
    
    Args:
        deleted_booking_id: ID записи DeletedBooking
        restored_by: Пользователь, который восстанавливает
    
    Returns:
        tuple: (success: bool, booking: Booking or None, message: str)
    """
    try:
        deleted_booking = DeletedBooking.objects.get(id=deleted_booking_id)
        
        if deleted_booking.restored:
            return False, None, 'Бронирование уже было восстановлено ранее'
        
        booking_data = deleted_booking.booking_data
        if not booking_data:
            return False, None, 'Данные бронирования отсутствуют'
        
        # Проверяем конфликты
        conflicts = check_restore_conflicts(booking_data, deleted_booking.series_data)
        if conflicts:
            if 'error' in conflicts:
                return False, None, conflicts['error']
            elif 'series_conflicts' in conflicts:
                return False, None, 'Обнаружены конфликты при восстановлении серии'
            else:
                conflict_messages = []
                if conflicts.get('specialist_busy'):
                    conflict_messages.append('специалист занят')
                if conflicts.get('cabinet_busy'):
                    conflict_messages.append('кабинет занят')
                if conflicts.get('specialist_not_available'):
                    conflict_messages.append('специалист не работает')
                if conflicts.get('cabinet_not_available'):
                    conflict_messages.append('кабинет недоступен')
                return False, None, f'Конфликты: {", ".join(conflict_messages)}'
        
        # Восстанавливаем связанные объекты
        service_variant = ServiceVariant.objects.get(id=booking_data['service_variant_id'])
        specialist = SpecialistProfile.objects.get(id=booking_data['specialist_id'])
        cabinet = Cabinet.objects.get(id=booking_data['cabinet_id'])
        
        # Парсим время
        from datetime import datetime
        start_time_str = booking_data['start_time']
        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time)
        
        end_time_str = booking_data.get('end_time')
        if end_time_str:
            end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            if timezone.is_naive(end_time):
                end_time = timezone.make_aware(end_time)
        else:
            # Вычисляем end_time автоматически
            from .models import SystemSettings
            settings = SystemSettings.get_solo()
            total_duration = service_variant.duration_minutes + settings.buffer_time_minutes
            from datetime import timedelta
            end_time = start_time + timedelta(minutes=total_duration)
        
        # Восстанавливаем серию, если была
        series = None
        if deleted_booking.series_data and deleted_booking.series_id:
            series_data = deleted_booking.series_data
            series, created = BookingSeries.objects.get_or_create(
                id=deleted_booking.series_id,
                defaults={
                    'start_time': start_time,
                    'frequency': series_data.get('frequency'),
                    'interval': series_data.get('interval'),
                    'occurrence_count': series_data.get('occurrence_count'),
                    'end_date': None,
                    'weekdays': series_data.get('weekdays', []),
                    'excluded_dates': [],
                    'created_by': restored_by,
                }
            )
            if not created:
                # Серия уже существует, обновляем её
                series.start_time = start_time
                series.frequency = series_data.get('frequency')
                series.interval = series_data.get('interval')
                series.occurrence_count = series_data.get('occurrence_count')
                series.end_date = None
                if series_data.get('end_date'):
                    from datetime import date
                    end_date_str = series_data.get('end_date')
                    if isinstance(end_date_str, str):
                        series.end_date = date.fromisoformat(end_date_str.split('T')[0])
                series.weekdays = series_data.get('weekdays', [])
                excluded_dates = series_data.get('excluded_dates', [])
                if excluded_dates:
                    from datetime import date
                    parsed_excluded = []
                    for d in excluded_dates:
                        if isinstance(d, str):
                            parsed_excluded.append(date.fromisoformat(d.split('T')[0]))
                        else:
                            parsed_excluded.append(d)
                    series.excluded_dates = parsed_excluded
                series.save()
        
        # Создаем бронирование
        created_by_id = booking_data.get('created_by_id')
        created_by = None
        if created_by_id:
            from django.contrib.auth.models import User
            try:
                created_by = User.objects.get(id=created_by_id)
            except User.DoesNotExist:
                pass
        
        booking = Booking.objects.create(
            guest_name=booking_data['guest_name'],
            guest_room_number=booking_data.get('guest_room_number', ''),
            service_variant=service_variant,
            specialist=specialist,
            cabinet=cabinet,
            start_time=start_time,
            end_time=end_time,
            status=booking_data.get('status', 'confirmed'),
            created_by=created_by or restored_by,
            series=series,
            sequence=booking_data.get('sequence', 1),
        )
        
        # Помечаем как восстановленное
        deleted_booking.restored = True
        deleted_booking.restored_at = timezone.now()
        deleted_booking.restored_by = restored_by
        deleted_booking.save()
        
        logger.info(f"Booking {booking.id} restored from DeletedBooking {deleted_booking_id}")
        
        return True, booking, 'Бронирование успешно восстановлено'
        
    except DeletedBooking.DoesNotExist:
        return False, None, 'Запись об удаленном бронировании не найдена'
    except Exception as e:
        logger.error(f"Error restoring booking {deleted_booking_id}: {e}", exc_info=True)
        return False, None, f'Ошибка при восстановлении: {str(e)}'


@transaction.atomic
def restore_series(deleted_booking_id, restored_by=None):
    """
    Восстанавливает всю серию бронирований.
    
    Args:
        deleted_booking_id: ID записи DeletedBooking (любого из серии)
        restored_by: Пользователь, который восстанавливает
    
    Returns:
        tuple: (success: bool, bookings: list, message: str)
    """
    try:
        deleted_booking = DeletedBooking.objects.get(id=deleted_booking_id)
        
        if not deleted_booking.series_id:
            return False, [], 'Это не серия бронирований'
        
        # Находим все удаленные бронирования этой серии
        deleted_bookings = DeletedBooking.objects.filter(
            series_id=deleted_booking.series_id,
            restored=False
        ).order_by('booking_data__sequence')
        
        if not deleted_bookings.exists():
            return False, [], 'Нет невосстановленных бронирований в этой серии'
        
        restored_bookings = []
        errors = []
        
        for deleted in deleted_bookings:
            success, booking, message = restore_booking(deleted.id, restored_by)
            if success:
                restored_bookings.append(booking)
            else:
                errors.append(f"Бронирование {deleted.original_id}: {message}")
        
        if errors:
            return False, restored_bookings, f'Восстановлено {len(restored_bookings)}, ошибок: {len(errors)}. {"; ".join(errors[:3])}'
        
        return True, restored_bookings, f'Восстановлено {len(restored_bookings)} бронирований серии'
        
    except DeletedBooking.DoesNotExist:
        return False, [], 'Запись об удаленном бронировании не найдена'
    except Exception as e:
        logger.error(f"Error restoring series {deleted_booking_id}: {e}", exc_info=True)
        return False, [], f'Ошибка при восстановлении серии: {str(e)}'

