"""
Утилиты для логирования действий с бронированиями
"""
from django.utils import timezone
from .models import BookingLog, Booking
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Получает IP адрес клиента из запроса"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_booking_action(booking, action, user, message, old_values=None, new_values=None, request=None):
    """
    Логирует действие с бронированием
    
    Args:
        booking: Booking - бронирование
        action: str - тип действия (из BookingLog.ACTION_CHOICES)
        user: User - пользователь, выполнивший действие
        message: str - описание действия
        old_values: dict - старые значения полей (опционально)
        new_values: dict - новые значения полей (опционально)
        request: HttpRequest - запрос для получения IP адреса (опционально)
    """
    try:
        ip_address = None
        if request:
            ip_address = get_client_ip(request)
        
        BookingLog.objects.create(
            booking=booking,
            action=action,
            user=user,
            message=message,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address
        )
        
        logger.info(f"Booking log created: booking_id={booking.id}, action={action}, user={user.username if user else 'None'}")
        
    except Exception as e:
        logger.error(f"Error creating booking log: {e}", exc_info=True)
        # Не прерываем выполнение, если логирование не удалось


def get_booking_changes(old_instance, new_instance):
    """
    Определяет изменения между двумя экземплярами бронирования
    
    Returns:
        tuple: (old_values, new_values) - словари с измененными полями
    """
    old_values = {}
    new_values = {}
    
    fields_to_check = [
        'guest_name', 'guest_room_number', 'status', 'start_time',
        'service_variant_id', 'specialist_id', 'cabinet_id'
    ]
    
    for field in fields_to_check:
        old_val = getattr(old_instance, field, None)
        new_val = getattr(new_instance, field, None)
        
        # Для ForeignKey получаем ID
        if hasattr(old_val, 'id'):
            old_val = old_val.id
        if hasattr(new_val, 'id'):
            new_val = new_val.id
        
        # Для datetime конвертируем в строку
        if hasattr(old_val, 'isoformat'):
            old_val = old_val.isoformat()
        if hasattr(new_val, 'isoformat'):
            new_val = new_val.isoformat()
        
        if old_val != new_val:
            old_values[field] = old_val
            new_values[field] = new_val
    
    return old_values, new_values




