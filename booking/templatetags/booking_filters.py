"""
Кастомные фильтры для шаблонов booking app
"""
from django import template
from datetime import datetime
from django.utils import timezone

register = template.Library()


@register.filter
def format_iso_datetime(value):
    """
    Форматирует ISO datetime строку в читаемый формат.
    Пример: "2025-11-17T12:30:00+07:00" -> "17.11.2025 12:30"
    """
    if not value:
        return "—"
    
    try:
        if isinstance(value, str):
            # Парсим ISO строку
            if 'T' in value:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt)
                local_dt = timezone.localtime(dt)
                return local_dt.strftime('%d.%m.%Y %H:%M')
            else:
                return value
        else:
            # Если это уже datetime объект
            if timezone.is_naive(value):
                value = timezone.make_aware(value)
            local_dt = timezone.localtime(value)
            return local_dt.strftime('%d.%m.%Y %H:%M')
    except (ValueError, AttributeError, TypeError):
        return str(value)


@register.filter
def format_iso_time(value):
    """
    Форматирует ISO datetime строку в формат времени.
    Пример: "2025-11-17T12:30:00+07:00" -> "12:30"
    """
    if not value:
        return "—"
    
    try:
        if isinstance(value, str):
            if 'T' in value:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt)
                local_dt = timezone.localtime(dt)
                return local_dt.strftime('%H:%M')
            else:
                return value
        else:
            if timezone.is_naive(value):
                value = timezone.make_aware(value)
            local_dt = timezone.localtime(value)
            return local_dt.strftime('%H:%M')
    except (ValueError, AttributeError, TypeError):
        return str(value)

