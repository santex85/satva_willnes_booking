from decimal import Decimal

from django.db.models import Count, Max, Sum
from rest_framework import serializers
from .models import (
    CabinetType,
    Cabinet,
    Service,
    ServiceVariant,
    SpecialistProfile,
    SpecialistSchedule,
    Booking,
    Guest,
)
from .clinical_models import SOAPNote

class CabinetTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CabinetType
        fields = ['id', 'name']


class CabinetSerializer(serializers.ModelSerializer):
    cabinet_type_name = serializers.CharField(source='cabinet_type.name', read_only=True)

    class Meta:
        model = Cabinet
        fields = ['id', 'name', 'cabinet_type', 'cabinet_type_name', 'is_active']


class ServiceSerializer(serializers.ModelSerializer):
    required_cabinet_type_names = serializers.StringRelatedField(source='required_cabinet_types', many=True, read_only=True)

    class Meta:
        model = Service
        fields = ['id', 'name', 'description', 'required_cabinet_types', 'required_cabinet_type_names']


class ServiceVariantSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)

    class Meta:
        model = ServiceVariant
        fields = ['id', 'service', 'service_name', 'name_suffix', 'duration_minutes', 'price']


class SpecialistProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = SpecialistProfile
        fields = ['id', 'username', 'email', 'full_name', 'services_can_perform']


class SpecialistScheduleSerializer(serializers.ModelSerializer):
    specialist_name = serializers.CharField(source='specialist.full_name', read_only=True)
    day_name = serializers.CharField(source='get_day_of_week_display', read_only=True)

    class Meta:
        model = SpecialistSchedule
        fields = ['id', 'specialist', 'specialist_name', 'day_of_week', 'day_name', 'start_time', 'end_time']


class GuestSerializer(serializers.ModelSerializer):
    booking_count = serializers.IntegerField(source='get_booking_count', read_only=True)
    total_visits = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    last_visit = serializers.SerializerMethodField()

    class Meta:
        model = Guest
        fields = [
            'id',
            'display_name',
            'normalized_name',
            'booking_count',
            'total_visits',
            'total_amount',
            'last_visit',
            'created_at',
        ]
        read_only_fields = ['normalized_name']

    def _booking_stats(self, obj):
        cached = getattr(obj, '_cached_booking_stats', None)
        if cached is not None:
            return cached
        stats = obj.bookings.exclude(status='canceled').aggregate(
            total_visits=Count('id'),
            total_amount=Sum('service_variant__price'),
            last_visit=Max('start_time'),
        )
        obj._cached_booking_stats = stats
        return stats

    def get_total_visits(self, obj):
        return self._booking_stats(obj).get('total_visits') or 0

    def get_total_amount(self, obj):
        total = self._booking_stats(obj).get('total_amount') or Decimal('0')
        return str(total)

    def get_last_visit(self, obj):
        last = self._booking_stats(obj).get('last_visit')
        return last.isoformat() if last else None

    def create(self, validated_data):
        from .guest_utils import normalize_guest_name
        display_name = validated_data.get('display_name')
        validated_data['normalized_name'] = normalize_guest_name(display_name)
        return super().create(validated_data)


class BookingSerializer(serializers.ModelSerializer):
    """Полнофункциональный сериализатор для бронирований (на чтение и запись)"""
    specialist_name = serializers.CharField(source='specialist.full_name', read_only=True)
    cabinet_name = serializers.CharField(source='cabinet.name', read_only=True)
    service_name = serializers.CharField(source='service_variant.service.name', read_only=True)
    service_duration = serializers.IntegerField(source='service_variant.duration_minutes', read_only=True)
    guest_display_name = serializers.CharField(source='guest.display_name', read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id',
            'guest',
            'guest_display_name',
            'guest_name',
            'guest_room_number',
            'comment',
            'service_variant',
            'service_name',
            'service_duration',
            'specialist',
            'specialist_name',
            'cabinet',
            'cabinet_name',
            'start_time',
            'end_time',
            'status',
            'created_by',
        ]
        read_only_fields = ['end_time', 'created_by']

    def validate(self, attrs):
        # Проверяем конфликты
        from .utils import check_booking_conflicts
        
        # Получаем данные (включая существующие при обновлении)
        specialist = attrs.get('specialist', self.instance.specialist if self.instance else None)
        cabinet = attrs.get('cabinet', self.instance.cabinet if self.instance else None)
        service_variant = attrs.get('service_variant', self.instance.service_variant if self.instance else None)
        start_time = attrs.get('start_time', self.instance.start_time if self.instance else None)
        
        if specialist and cabinet and service_variant and start_time:
            conflicts = check_booking_conflicts(
                start_time=start_time,
                service_variant=service_variant,
                specialist=specialist,
                cabinet=cabinet,
                exclude_booking_id=self.instance.id if self.instance else None
            )
            if conflicts:
                err_msgs = []
                if conflicts.get('specialist_busy'):
                    err_msgs.append("Специалист уже занят на это время")
                if conflicts.get('cabinet_busy'):
                    err_msgs.append("Кабинет уже занят на это время")
                if conflicts.get('specialist_not_available'):
                    err_msgs.append("Специалист не работает по графику в это время")
                if conflicts.get('cabinet_not_available'):
                    err_msgs.append("Кабинет недоступен в это время")
                raise serializers.ValidationError(err_msgs)
                
        return attrs


class SOAPNoteSerializer(serializers.ModelSerializer):
    guest_name = serializers.CharField(source='guest.display_name', read_only=True)
    specialist_name = serializers.CharField(source='specialist.full_name', read_only=True)

    class Meta:
        model = SOAPNote
        fields = [
            'id',
            'guest',
            'guest_name',
            'specialist',
            'specialist_name',
            'created_at',
            'subjective',
            'objective',
            'assessment',
            'plan',
            'body_map_data',
        ]
