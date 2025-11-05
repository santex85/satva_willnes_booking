"""
Сигналы Django для обработки событий моделей
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings
import logging

from .models import Booking, SystemSettings

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

