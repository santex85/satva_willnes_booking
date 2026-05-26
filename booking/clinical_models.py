from django.db import models
from django.contrib.auth.models import User
from .models import Guest, SpecialistProfile

class SOAPNote(models.Model):
    """SOAP заметка специалиста по сеансу массажа/спа"""
    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name='soap_notes', verbose_name="Гость")
    specialist = models.ForeignKey(SpecialistProfile, on_delete=models.PROTECT, verbose_name="Специалист")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    
    # SOAP Структура
    subjective = models.TextField(verbose_name="Жалобы клиента (S)", help_text="Что говорит клиент", blank=True)
    objective = models.TextField(verbose_name="Объективные показатели (O)", help_text="Тонус мышц, триггеры", blank=True)
    assessment = models.TextField(verbose_name="Оценка специалиста (A)", help_text="Результаты диагностики", blank=True)
    plan = models.TextField(verbose_name="План дальнейшей терапии (P)", help_text="Рекомендации по процедурам", blank=True)
    
    # Разметка тела в JSON формате (карты триггерных точек на SVG силуэте)
    body_map_data = models.JSONField(default=dict, blank=True, verbose_name="Разметка триггерных точек")

    class Meta:
        verbose_name = 'SOAP карта гостя'
        verbose_name_plural = 'SOAP карты гостей'
        ordering = ['-created_at']

    def __str__(self):
        return f"SOAP карта - {self.guest.display_name} ({self.created_at.strftime('%d.%m.%Y')})"
