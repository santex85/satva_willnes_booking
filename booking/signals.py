"""
Сигналы Django для обработки событий моделей
"""
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings
import logging
import json

from .models import Booking, SystemSettings, DeletedBooking, BookingSeries

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Booking)
def send_booking_notification(sender, instance, created, **kwargs):
    """
    Отправляет email-уведомление специалисту при создании нового бронирования
    """
    # Отправляем уведомление только при создании нового бронирования
    if not created:
        return
    
    # Проверяем настройки системы
    try:
        system_settings = SystemSettings.get_solo()
        if not system_settings.send_email_notifications:
            logger.debug("Email notifications are disabled in system settings")
            return
    except Exception as e:
        logger.error(f"Error getting system settings: {e}")
        return
    
    # Проверяем, есть ли email у специалиста
    specialist = instance.specialist
    user = specialist.user
    
    if not user.email:
        logger.debug(f"Specialist {specialist.full_name} has no email address")
        return
    
    try:
        # Форматируем дату и время для письма
        local_start = timezone.localtime(instance.start_time)
        local_end = timezone.localtime(instance.end_time)
        
        # Подготовка контекста для шаблона
        context = {
            'specialist_name': specialist.full_name,
            'guest_name': instance.guest_name,
            'guest_room': instance.guest_room_number or 'Не указан',
            'service_name': instance.service_variant.service.name,
            'service_variant': instance.service_variant.name_suffix,
            'cabinet_name': instance.cabinet.name,
            'start_time': local_start.strftime('%d.%m.%Y в %H:%M'),
            'end_time': local_end.strftime('%H:%M'),
            'date': local_start.strftime('%d.%m.%Y'),
            'time_range': f"{local_start.strftime('%H:%M')} - {local_end.strftime('%H:%M')}",
            'status': dict(Booking.STATUS_CHOICES).get(instance.status, instance.status),
        }
        
        # Рендерим текст письма
        email_subject = f'Новое бронирование на {context["date"]}'
        email_body = render_to_string('booking/emails/new_booking_notification.txt', context)
        email_html = render_to_string('booking/emails/new_booking_notification.html', context)
        
        # Отправляем email
        send_mail(
            subject=email_subject,
            message=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=email_html,
            fail_silently=False,
        )
        
        logger.info(f"Email notification sent to {user.email} for booking {instance.id}")
        
    except Exception as e:
        logger.error(f"Error sending email notification for booking {instance.id}: {e}", exc_info=True)
        # Не прерываем выполнение, если email не отправился


# Thread-local storage для хранения текущего пользователя и причины удаления
import threading
_thread_locals = threading.local()


def set_current_user(user, deletion_reason='', deletion_scope='single'):
    """Устанавливает текущего пользователя для сигналов удаления."""
    _thread_locals.user = user
    _thread_locals.deletion_reason = deletion_reason
    _thread_locals.deletion_scope = deletion_scope


def get_current_user():
    """Получает текущего пользователя из thread-local storage."""
    return getattr(_thread_locals, 'user', None)


def get_deletion_reason():
    """Получает причину удаления из thread-local storage."""
    return getattr(_thread_locals, 'deletion_reason', '')


def get_deletion_scope():
    """Получает область удаления из thread-local storage."""
    return getattr(_thread_locals, 'deletion_scope', 'single')


def clear_thread_locals():
    """Очищает thread-local storage."""
    if hasattr(_thread_locals, 'user'):
        delattr(_thread_locals, 'user')
    if hasattr(_thread_locals, 'deletion_reason'):
        delattr(_thread_locals, 'deletion_reason')
    if hasattr(_thread_locals, 'deletion_scope'):
        delattr(_thread_locals, 'deletion_scope')


@receiver(pre_delete, sender=Booking)
def log_deleted_booking(sender, instance, **kwargs):
    """
    Логирует удаленное бронирование перед его удалением из базы данных.
    """
    try:
        # Получаем данные бронирования
        booking_data = {
            'guest_name': instance.guest_name,
            'guest_room_number': instance.guest_room_number,
            'service_variant_id': instance.service_variant_id,
            'service_variant_name': str(instance.service_variant),
            'specialist_id': instance.specialist_id,
            'specialist_name': instance.specialist.full_name if instance.specialist else None,
            'cabinet_id': instance.cabinet_id,
            'cabinet_name': instance.cabinet.name if instance.cabinet else None,
            'start_time': instance.start_time.isoformat() if instance.start_time else None,
            'end_time': instance.end_time.isoformat() if instance.end_time else None,
            'status': instance.status,
            'created_by_id': instance.created_by_id,
            'created_by_username': instance.created_by.username if instance.created_by else None,
            'series_id': instance.series_id,
            'sequence': instance.sequence,
        }

        # Получаем данные серии, если есть
        series_data = None
        if instance.series:
            series = instance.series
            series_data = {
                'id': series.id,
                'start_time': series.start_time.isoformat() if series.start_time else None,
                'frequency': series.frequency,
                'interval': series.interval,
                'occurrence_count': series.occurrence_count,
                'end_date': series.end_date.isoformat() if series.end_date else None,
                'weekdays': series.weekdays,
                'excluded_dates': [d.isoformat() if isinstance(d, type(timezone.now().date())) else str(d) for d in (series.excluded_dates or [])],
                'created_by_id': series.created_by_id,
            }

        # Получаем пользователя и причину удаления из thread-local storage
        deleted_by = get_current_user()
        deletion_reason = get_deletion_reason()
        deletion_scope = get_deletion_scope()

        # Создаем запись в архиве удаленных бронирований
        DeletedBooking.objects.create(
            original_id=instance.id,
            booking_data=booking_data,
            series_id=instance.series_id if instance.series else None,
            series_data=series_data,
            deleted_by=deleted_by,
            deletion_reason=deletion_reason,
            deletion_scope=deletion_scope,
        )

        logger.info(f"Booking {instance.id} logged to DeletedBooking archive before deletion")

    except Exception as e:
        logger.error(f"Error logging deleted booking {instance.id}: {e}", exc_info=True)
        # Не прерываем удаление, если логирование не удалось

