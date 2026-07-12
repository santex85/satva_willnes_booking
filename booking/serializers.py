"""
Serializers для Django REST Framework API v1
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from django.utils import timezone
import datetime
import logging

from .models import (
    Booking,
    BookingSeries,
    BookingLog,
    SpecialistProfile,
    SpecialistSchedule,
    ScheduleTemplate,
    ScheduleTemplateDay,
    Cabinet,
    CabinetType,
    CabinetClosure,
    CalendarNote,
    Service,
    ServiceVariant,
    Guest,
    DeletedBooking,
    SystemSettings,
    UserApiKey,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------

class CabinetTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CabinetType
        fields = ['id', 'name']


class CabinetSerializer(serializers.ModelSerializer):
    cabinet_type_name = serializers.CharField(source='cabinet_type.name', read_only=True)

    class Meta:
        model = Cabinet
        fields = ['id', 'name', 'cabinet_type', 'cabinet_type_name', 'is_active']


class ServiceVariantSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)

    class Meta:
        model = ServiceVariant
        fields = [
            'id', 'service', 'service_name', 'name_suffix',
            'duration_minutes', 'price',
        ]


class ServiceSerializer(serializers.ModelSerializer):
    variants = ServiceVariantSerializer(many=True, read_only=True)
    required_cabinet_type_ids = serializers.PrimaryKeyRelatedField(
        source='required_cabinet_types',
        queryset=CabinetType.objects.all(),
        many=True,
        required=False,
    )
    required_cabinet_types = CabinetTypeSerializer(many=True, read_only=True)

    class Meta:
        model = Service
        fields = [
            'id', 'name', 'description',
            'required_cabinet_types', 'required_cabinet_type_ids',
            'variants',
        ]


class SpecialistScheduleSerializer(serializers.ModelSerializer):
    specialist_name = serializers.CharField(source='specialist.full_name', read_only=True)
    day_of_week_display = serializers.CharField(source='get_day_of_week_display', read_only=True)

    class Meta:
        model = SpecialistSchedule
        fields = [
            'id', 'specialist', 'specialist_name',
            'day_of_week', 'day_of_week_display',
            'start_time', 'end_time',
        ]

    def validate(self, attrs):
        start = attrs.get('start_time') or getattr(self.instance, 'start_time', None)
        end = attrs.get('end_time') or getattr(self.instance, 'end_time', None)
        if start and end and start >= end:
            raise serializers.ValidationError({'end_time': 'Время окончания должно быть больше начала'})
        return attrs


class SpecialistProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    service_ids = serializers.PrimaryKeyRelatedField(
        source='services_can_perform',
        queryset=Service.objects.all(),
        many=True,
        required=False,
    )
    services = serializers.SerializerMethodField()
    schedules = SpecialistScheduleSerializer(many=True, read_only=True)

    class Meta:
        model = SpecialistProfile
        fields = [
            'id', 'user', 'username', 'email', 'full_name',
            'service_ids', 'services', 'schedules',
        ]
        read_only_fields = ['user']

    def get_services(self, obj):
        return [{'id': s.id, 'name': s.name} for s in obj.services_can_perform.all()]


class ScheduleTemplateDaySerializer(serializers.ModelSerializer):
    day_of_week_display = serializers.CharField(source='get_day_of_week_display', read_only=True)

    class Meta:
        model = ScheduleTemplateDay
        fields = ['id', 'day_of_week', 'day_of_week_display', 'start_time', 'end_time']


class ScheduleTemplateSerializer(serializers.ModelSerializer):
    days = ScheduleTemplateDaySerializer(many=True, required=False)

    class Meta:
        model = ScheduleTemplate
        fields = ['id', 'name', 'description', 'days', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def create(self, validated_data):
        days_data = validated_data.pop('days', [])
        template = ScheduleTemplate.objects.create(**validated_data)
        for day in days_data:
            ScheduleTemplateDay.objects.create(template=template, **day)
        return template

    def update(self, instance, validated_data):
        days_data = validated_data.pop('days', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if days_data is not None:
            instance.days.all().delete()
            for day in days_data:
                ScheduleTemplateDay.objects.create(template=instance, **day)
        return instance


class ApplyTemplateSerializer(serializers.Serializer):
    specialist_id = serializers.IntegerField()


class GuestSerializer(serializers.ModelSerializer):
    booking_count = serializers.SerializerMethodField()

    class Meta:
        model = Guest
        fields = [
            'id', 'display_name', 'normalized_name',
            'booking_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['normalized_name', 'created_at', 'updated_at']

    def get_booking_count(self, obj):
        return obj.bookings.count()

    def create(self, validated_data):
        from .guest_utils import normalize_guest_name
        display = validated_data['display_name'].strip()
        normalized = normalize_guest_name(display)
        guest, _ = Guest.objects.get_or_create(
            normalized_name=normalized,
            defaults={'display_name': display},
        )
        return guest


class MergeGuestsSerializer(serializers.Serializer):
    primary_guest_id = serializers.IntegerField()
    duplicate_guest_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
    )
    primary_display_name = serializers.CharField(required=False, allow_blank=True)


# ---------------------------------------------------------------------------
# Бронирования и серии
# ---------------------------------------------------------------------------

class RecurrencePayloadSerializer(serializers.Serializer):
    frequency = serializers.ChoiceField(choices=BookingSeries.FREQUENCY_CHOICES)
    interval = serializers.IntegerField(min_value=1, default=1)
    end_type = serializers.ChoiceField(choices=[('count', 'count'), ('until', 'until')])
    occurrences = serializers.IntegerField(min_value=2, required=False)
    end_date = serializers.DateField(required=False)
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        required=False,
        default=list,
    )
    excluded_dates = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )

    def validate(self, attrs):
        if attrs['end_type'] == 'count' and not attrs.get('occurrences'):
            raise serializers.ValidationError({'occurrences': 'Укажите количество повторов'})
        if attrs['end_type'] == 'until' and not attrs.get('end_date'):
            raise serializers.ValidationError({'end_date': 'Укажите дату окончания'})
        return attrs


class BookingSerializer(serializers.ModelSerializer):
    specialist_name = serializers.CharField(source='specialist.full_name', read_only=True)
    cabinet_name = serializers.CharField(source='cabinet.name', read_only=True)
    service_name = serializers.CharField(source='service_variant.service.name', read_only=True)
    service_variant_name = serializers.CharField(source='service_variant.name_suffix', read_only=True)
    service_duration = serializers.IntegerField(source='service_variant.duration_minutes', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    series_id = serializers.IntegerField(source='series.id', read_only=True, allow_null=True)
    recurrence = RecurrencePayloadSerializer(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Booking
        fields = [
            'id',
            'guest',
            'guest_name',
            'guest_room_number',
            'comment',
            'service_variant',
            'service_name',
            'service_variant_name',
            'service_duration',
            'specialist',
            'specialist_name',
            'cabinet',
            'cabinet_name',
            'start_time',
            'end_time',
            'status',
            'status_display',
            'series',
            'series_id',
            'sequence',
            'created_by',
            'recurrence',
        ]
        read_only_fields = ['end_time', 'created_by', 'sequence', 'series']

    def validate_guest_name(self, value):
        if not value or len(value.strip()) < 2:
            raise serializers.ValidationError('Имя гостя должно содержать минимум 2 символа')
        return value.strip()

    def validate(self, attrs):
        service_variant = attrs.get('service_variant') or getattr(self.instance, 'service_variant', None)
        cabinet = attrs.get('cabinet') or getattr(self.instance, 'cabinet', None)
        if service_variant and cabinet:
            required = service_variant.service.required_cabinet_types.all()
            if required.exists() and cabinet.cabinet_type not in required:
                raise serializers.ValidationError({
                    'cabinet': 'Кабинет не подходит для выбранной услуги'
                })
        return attrs


class BookingLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = BookingLog
        fields = [
            'id', 'booking', 'action', 'action_display',
            'message', 'user', 'user_name',
            'old_values', 'new_values',
            'created_at', 'ip_address',
        ]

    def get_user_name(self, obj):
        if not obj.user:
            return 'Система'
        return obj.user.get_full_name() or obj.user.username


class BookingSeriesSerializer(serializers.ModelSerializer):
    frequency_display = serializers.CharField(source='get_frequency_display', read_only=True)
    booking_count = serializers.SerializerMethodField()

    class Meta:
        model = BookingSeries
        fields = [
            'id', 'start_time', 'frequency', 'frequency_display',
            'interval', 'end_date', 'occurrence_count',
            'weekdays', 'excluded_dates',
            'created_by', 'created_at', 'updated_at',
            'booking_count',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_booking_count(self, obj):
        return obj.bookings.count()


class DuplicateBookingSerializer(serializers.Serializer):
    start_time = serializers.DateTimeField()


class ConflictCheckSerializer(serializers.Serializer):
    start_time = serializers.DateTimeField()
    service_variant = serializers.PrimaryKeyRelatedField(queryset=ServiceVariant.objects.all())
    specialist = serializers.PrimaryKeyRelatedField(queryset=SpecialistProfile.objects.all())
    cabinet = serializers.PrimaryKeyRelatedField(queryset=Cabinet.objects.all())
    exclude_booking_id = serializers.IntegerField(required=False, allow_null=True)


# ---------------------------------------------------------------------------
# Заметки, закрытия, удалённые
# ---------------------------------------------------------------------------

class CalendarNoteSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CalendarNote
        fields = [
            'id', 'start_time', 'end_time', 'comment',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return obj.created_by.get_full_name() or obj.created_by.username

    def validate(self, attrs):
        start = attrs.get('start_time') or getattr(self.instance, 'start_time', None)
        end = attrs.get('end_time')
        if end is None and self.instance is None and start:
            attrs['end_time'] = start + datetime.timedelta(hours=2)
            end = attrs['end_time']
        elif end is None and self.instance:
            end = self.instance.end_time
        if start and end and end <= start:
            raise serializers.ValidationError({'end_time': 'Окончание должно быть позже начала'})
        return attrs


class CabinetClosureSerializer(serializers.ModelSerializer):
    cabinet_name = serializers.CharField(source='cabinet.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CabinetClosure
        fields = [
            'id', 'cabinet', 'cabinet_name',
            'start_time', 'end_time', 'reason',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return obj.created_by.get_full_name() or obj.created_by.username

    def validate(self, attrs):
        start = attrs.get('start_time') or getattr(self.instance, 'start_time', None)
        end = attrs.get('end_time') or getattr(self.instance, 'end_time', None)
        if start and end and end <= start:
            raise serializers.ValidationError({'end_time': 'Окончание должно быть позже начала'})
        return attrs


class DeletedBookingSerializer(serializers.ModelSerializer):
    deleted_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DeletedBooking
        fields = [
            'id', 'original_id', 'booking_data', 'series_id', 'series_data',
            'deleted_by', 'deleted_by_name', 'deleted_at',
            'deletion_reason', 'deletion_scope',
            'restored', 'restored_at', 'restored_by',
        ]
        read_only_fields = fields

    def get_deleted_by_name(self, obj):
        if not obj.deleted_by:
            return None
        return obj.deleted_by.get_full_name() or obj.deleted_by.username


class SystemSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSettings
        fields = [
            'spa_open_time', 'spa_close_time', 'buffer_time_minutes',
            'send_email_notifications', 'enable_booking_copy_shortcuts',
        ]


# ---------------------------------------------------------------------------
# Query / auth input
# ---------------------------------------------------------------------------

class AvailableSlotsQuerySerializer(serializers.Serializer):
    date = serializers.DateField()
    service_variant = serializers.PrimaryKeyRelatedField(queryset=ServiceVariant.objects.all())


class AvailableCabinetsQuerySerializer(serializers.Serializer):
    service_variant_id = serializers.IntegerField()
    specialist_id = serializers.IntegerField()
    datetime = serializers.DateTimeField()


class SpecialistsForServiceQuerySerializer(serializers.Serializer):
    service_variant_id = serializers.IntegerField()


class CalendarFeedQuerySerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()


class ReportSummaryQuerySerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    specialist = serializers.PrimaryKeyRelatedField(
        queryset=SpecialistProfile.objects.all(),
        required=False,
        allow_null=True,
    )


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    full_name = serializers.CharField(allow_blank=True)
    is_staff = serializers.BooleanField()
    is_superuser = serializers.BooleanField()
    groups = serializers.ListField(child=serializers.CharField())
    roles = serializers.ListField(child=serializers.CharField())
    specialist = SpecialistProfileSerializer(allow_null=True)


class UserApiKeySerializer(serializers.ModelSerializer):
    prefix_display = serializers.SerializerMethodField()

    class Meta:
        model = UserApiKey
        fields = [
            'id', 'name', 'prefix', 'prefix_display', 'is_active',
            'created_at', 'last_used_at', 'expires_at',
        ]
        read_only_fields = fields

    def get_prefix_display(self, obj):
        return f'{obj.prefix}…'


class UserApiKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError('Название должно быть не короче 2 символов')
        return value
