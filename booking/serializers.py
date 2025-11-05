"""
Serializers для Django REST Framework API
"""
from rest_framework import serializers
import logging

from .models import Booking, SpecialistProfile

logger = logging.getLogger(__name__)


class BookingSerializer(serializers.ModelSerializer):
    """Сериализатор для Booking"""
    specialist_name = serializers.CharField(source='specialist.full_name', read_only=True)
    cabinet_name = serializers.CharField(source='cabinet.name', read_only=True)
    service_name = serializers.CharField(source='service_variant.service.name', read_only=True)
    service_duration = serializers.IntegerField(source='service_variant.duration_minutes', read_only=True)
    
    class Meta:
        model = Booking
        fields = [
            'id',
            'guest_name',
            'guest_room_number',
            'specialist_name',
            'cabinet_name',
            'service_name',
            'service_duration',
            'start_time',
            'end_time',
            'status',
            'created_by',
        ]
        read_only_fields = ['end_time', 'created_by']
    
    def validate_guest_name(self, value):
        """Валидация имени гостя"""
        if not value or len(value.strip()) < 2:
            raise serializers.ValidationError("Имя гостя должно содержать минимум 2 символа")
        return value.strip()

