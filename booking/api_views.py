"""
REST API v1 views для Django REST Framework.
"""
import datetime
import logging

from django.db import transaction
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, generics, status, mixins
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from drf_spectacular.utils import extend_schema
import django_filters

from .authentication import ApiKeyAuthentication

from .models import (
    Booking,
    BookingSeries,
    BookingLog,
    SpecialistProfile,
    SpecialistSchedule,
    ScheduleTemplate,
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
from .serializers import (
    BookingSerializer,
    BookingSeriesSerializer,
    BookingLogSerializer,
    SpecialistProfileSerializer,
    SpecialistScheduleSerializer,
    ScheduleTemplateSerializer,
    ApplyTemplateSerializer,
    CabinetSerializer,
    CabinetTypeSerializer,
    CabinetClosureSerializer,
    CalendarNoteSerializer,
    ServiceSerializer,
    ServiceVariantSerializer,
    GuestSerializer,
    MergeGuestsSerializer,
    DeletedBookingSerializer,
    SystemSettingsSerializer,
    DuplicateBookingSerializer,
    ConflictCheckSerializer,
    AvailableSlotsQuerySerializer,
    AvailableCabinetsQuerySerializer,
    SpecialistsForServiceQuerySerializer,
    CalendarFeedQuerySerializer,
    ReportSummaryQuerySerializer,
    MeSerializer,
    UserApiKeySerializer,
    UserApiKeyCreateSerializer,
)
from .permissions import (
    IsAdminRole,
    IsStaffRole,
    IsSpecialistRole,
    IsAdminOrReadOnly,
    IsAdminOrStaffWrite,
    IsAdminOrOwnSpecialistRead,
    is_admin_user,
    is_staff_user,
    is_specialist_user,
)
from .utils import find_available_slots, check_booking_conflicts
from .restore_utils import restore_booking, restore_series
from .log_utils import log_booking_action, get_booking_changes
from .guest_utils import find_similar_guests, normalize_guest_name, find_duplicate_groups, merge_guests
from .views import (
    build_series_from_payload,
    format_conflict_message,
)

logger = logging.getLogger(__name__)

API_AUTH_CLASSES = [JWTAuthentication, ApiKeyAuthentication, SessionAuthentication]


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

class BookingFilter(django_filters.FilterSet):
    start = django_filters.IsoDateTimeFilter(field_name='start_time', lookup_expr='gte')
    end = django_filters.IsoDateTimeFilter(field_name='start_time', lookup_expr='lt')
    specialist = django_filters.NumberFilter(field_name='specialist_id')
    cabinet = django_filters.NumberFilter(field_name='cabinet_id')
    status = django_filters.CharFilter(field_name='status')
    series = django_filters.NumberFilter(field_name='series_id')
    guest_name = django_filters.CharFilter(field_name='guest_name', lookup_expr='icontains')

    class Meta:
        model = Booking
        fields = ['specialist', 'cabinet', 'status', 'series', 'guest_name']


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------

class CabinetTypeViewSet(viewsets.ModelViewSet):
    queryset = CabinetType.objects.all().order_by('name')
    serializer_class = CabinetTypeSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ['name']
    ordering_fields = ['name', 'id']


class CabinetViewSet(viewsets.ModelViewSet):
    queryset = Cabinet.objects.select_related('cabinet_type').all().order_by('name')
    serializer_class = CabinetSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ['cabinet_type', 'is_active']
    search_fields = ['name']
    ordering_fields = ['name', 'id']


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.prefetch_related('variants', 'required_cabinet_types').all().order_by('name')
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'id']


class ServiceVariantViewSet(viewsets.ModelViewSet):
    queryset = ServiceVariant.objects.select_related('service').all().order_by('service__name', 'duration_minutes')
    serializer_class = ServiceVariantSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ['service']
    search_fields = ['name_suffix', 'service__name']
    ordering_fields = ['duration_minutes', 'price', 'id']


class SpecialistViewSet(viewsets.ModelViewSet):
    queryset = SpecialistProfile.objects.select_related('user').prefetch_related(
        'services_can_perform', 'schedules'
    ).all().order_by('full_name')
    serializer_class = SpecialistProfileSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ['full_name', 'user__username', 'user__email']
    ordering_fields = ['full_name', 'id']


class SpecialistScheduleViewSet(viewsets.ModelViewSet):
    queryset = SpecialistSchedule.objects.select_related('specialist').all().order_by('specialist__full_name', 'day_of_week')
    serializer_class = SpecialistScheduleSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ['specialist', 'day_of_week']
    ordering_fields = ['day_of_week', 'id']


class ScheduleTemplateViewSet(viewsets.ModelViewSet):
    queryset = ScheduleTemplate.objects.prefetch_related('days').all().order_by('name')
    serializer_class = ScheduleTemplateSerializer
    permission_classes = [IsAdminRole]
    search_fields = ['name', 'description']

    @action(detail=True, methods=['post'], url_path='apply')
    def apply(self, request, pk=None):
        template = self.get_object()
        serializer = ApplyTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        specialist = get_object_or_404(SpecialistProfile, pk=serializer.validated_data['specialist_id'])
        count = template.apply_to_specialist(specialist)
        return Response({
            'success': True,
            'message': f'Шаблон применён ({count} дней)',
            'specialist_id': specialist.id,
            'days_applied': count,
        })


class GuestViewSet(viewsets.ModelViewSet):
    queryset = Guest.objects.all().order_by('display_name')
    serializer_class = GuestSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ['display_name', 'normalized_name']
    ordering_fields = ['display_name', 'created_at', 'id']

    @action(detail=False, methods=['get'], url_path='autocomplete')
    def autocomplete(self, request):
        query = request.query_params.get('q', '').strip()
        limit = int(request.query_params.get('limit', 10))
        if not query or len(query) < 2:
            return Response([])

        normalized_query = normalize_guest_name(query)
        if len(query) <= 3:
            guests = Guest.objects.filter(
                Q(normalized_name__icontains=query) |
                Q(display_name__icontains=query) |
                Q(normalized_name__icontains=normalized_query)
            ).distinct().order_by('display_name')[:limit]
        else:
            similar = find_similar_guests(query, threshold=0.5, limit=limit)
            exact = Guest.objects.filter(
                Q(normalized_name__istartswith=normalized_query) |
                Q(display_name__istartswith=query)
            ).exclude(id__in=[g.id for g in similar]).distinct()[: max(0, limit - len(similar))]
            guests = list(similar) + list(exact)

        results = []
        seen = set()
        for guest in list(guests)[:limit]:
            if guest.id in seen:
                continue
            seen.add(guest.id)
            results.append({
                'id': guest.id,
                'display_name': guest.display_name,
                'normalized_name': guest.normalized_name,
                'booking_count': guest.bookings.count(),
            })
        return Response(results)

    @action(detail=False, methods=['get'], url_path='duplicates', permission_classes=[IsAdminRole])
    def duplicates(self, request):
        threshold = float(request.query_params.get('threshold', 0.85))
        groups = find_duplicate_groups(threshold=threshold)
        return Response(groups)

    @action(detail=False, methods=['post'], url_path='merge', permission_classes=[IsAdminRole])
    def merge(self, request):
        serializer = MergeGuestsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        primary = get_object_or_404(Guest, pk=serializer.validated_data['primary_guest_id'])
        duplicates = list(Guest.objects.filter(pk__in=serializer.validated_data['duplicate_guest_ids']))
        if not duplicates:
            return Response({'error': 'Дубликаты не найдены'}, status=status.HTTP_400_BAD_REQUEST)
        display = serializer.validated_data.get('primary_display_name') or None
        moved = merge_guests(primary, duplicates, primary_display_name=display)
        return Response({
            'success': True,
            'primary_guest_id': primary.id,
            'bookings_moved': moved,
        })


# ---------------------------------------------------------------------------
# Бронирования
# ---------------------------------------------------------------------------

class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [IsAdminOrOwnSpecialistRead]
    filterset_class = BookingFilter
    search_fields = ['guest_name', 'guest_room_number', 'comment']
    ordering_fields = ['start_time', 'id', 'status']
    ordering = ['start_time']

    def get_queryset(self):
        qs = Booking.objects.select_related(
            'specialist', 'cabinet', 'service_variant', 'service_variant__service', 'series', 'guest'
        ).all()
        user = self.request.user
        if is_admin_user(user) or is_staff_user(user):
            return qs
        if is_specialist_user(user):
            specialist = SpecialistProfile.objects.get(user=user)
            return qs.filter(specialist=specialist)
        return qs.none()

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'duplicate'):
            return [IsAdminRole()]
        if self.action in ('check_conflicts',):
            return [IsAdminRole()]
        return super().get_permissions()

    def perform_create(self, serializer):
        recurrence = serializer.validated_data.pop('recurrence', None)
        with transaction.atomic():
            if recurrence:
                start_time = serializer.validated_data['start_time']
                if timezone.is_naive(start_time):
                    start_time = timezone.make_aware(start_time)
                series = build_series_from_payload(
                    start_time=start_time,
                    recurrence_payload=recurrence,
                    created_by=self.request.user,
                )
                occurrences = series.generate_datetimes()
                if not occurrences:
                    raise serializers_validation_error('Не удалось построить расписание повторов')
                series.save()
                created = []
                for index, start_dt in enumerate(occurrences, start=1):
                    booking = Booking.objects.create(
                        guest_name=serializer.validated_data['guest_name'],
                        guest_room_number=serializer.validated_data.get('guest_room_number', ''),
                        comment=serializer.validated_data.get('comment', ''),
                        service_variant=serializer.validated_data['service_variant'],
                        specialist=serializer.validated_data['specialist'],
                        cabinet=serializer.validated_data['cabinet'],
                        start_time=start_dt,
                        status=serializer.validated_data.get('status', 'confirmed'),
                        created_by=self.request.user,
                        series=series,
                        sequence=index,
                    )
                    created.append(booking)
                    log_booking_action(
                        booking=booking,
                        action='series_created',
                        user=self.request.user,
                        message=f'Создано бронирование в серии ({index} из {len(created)})',
                        request=self.request,
                    )
                # Сохраняем первый в serializer.instance для ответа
                serializer.instance = created[0]
            else:
                booking = serializer.save(created_by=self.request.user)
                log_booking_action(
                    booking=booking,
                    action='created',
                    user=self.request.user,
                    message=f'Создано бронирование для гостя {booking.guest_name}',
                    request=self.request,
                )

    def perform_update(self, serializer):
        serializer.validated_data.pop('recurrence', None)
        old = Booking.objects.get(pk=serializer.instance.pk)
        booking = serializer.save()
        old_values, new_values = get_booking_changes(old, booking)
        log_booking_action(
            booking=booking,
            action='updated',
            user=self.request.user,
            message='Обновлено бронирование через API',
            old_values=old_values,
            new_values=new_values,
            request=self.request,
        )

    def perform_destroy(self, instance):
        log_booking_action(
            booking=instance,
            action='deleted',
            user=self.request.user,
            message='Удалено бронирование через API',
            request=self.request,
        )
        instance.delete()

    @action(detail=True, methods=['post'], url_path='duplicate')
    def duplicate(self, request, pk=None):
        original = self.get_object()
        if original.series_id:
            return Response(
                {'error': 'Нельзя копировать бронирования, входящие в серию'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = DuplicateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_start = serializer.validated_data['start_time']
        if timezone.is_naive(target_start):
            target_start = timezone.make_aware(target_start)

        conflicts = check_booking_conflicts(
            start_time=target_start,
            service_variant=original.service_variant,
            specialist=original.specialist,
            cabinet=original.cabinet,
        )
        duplicated = Booking.objects.create(
            guest_name=original.guest_name,
            guest_room_number=original.guest_room_number,
            comment=original.comment,
            service_variant=original.service_variant,
            specialist=original.specialist,
            cabinet=original.cabinet,
            start_time=target_start,
            created_by=request.user,
            status=original.status,
        )
        log_booking_action(
            booking=duplicated,
            action='duplicated',
            user=request.user,
            message=f'Скопировано из бронирования #{original.id}',
            request=request,
        )
        data = BookingSerializer(duplicated).data
        response = {'success': True, 'booking': data}
        if conflicts:
            response['warning'] = format_conflict_message(conflicts)
        return Response(response, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='check-conflicts')
    def check_conflicts(self, request):
        serializer = ConflictCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        start = data['start_time']
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
        conflicts = check_booking_conflicts(
            start_time=start,
            service_variant=data['service_variant'],
            specialist=data['specialist'],
            cabinet=data['cabinet'],
            exclude_booking_id=data.get('exclude_booking_id'),
        )
        return Response({
            'has_conflicts': bool(conflicts),
            'conflicts': conflicts or {},
            'message': format_conflict_message(conflicts) if conflicts else '',
        })

    @action(detail=True, methods=['get'], url_path='logs')
    def logs(self, request, pk=None):
        booking = self.get_object()
        logs = BookingLog.objects.filter(booking=booking).select_related('user').order_by('-created_at')[:50]
        return Response(BookingLogSerializer(logs, many=True).data)


def serializers_validation_error(message):
    from rest_framework.exceptions import ValidationError
    raise ValidationError({'detail': message})


class BookingSeriesViewSet(viewsets.ModelViewSet):
    queryset = BookingSeries.objects.prefetch_related('bookings').all().order_by('-created_at')
    serializer_class = BookingSeriesSerializer
    permission_classes = [IsAdminRole]
    filterset_fields = ['frequency']
    ordering_fields = ['start_time', 'created_at', 'id']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


# ---------------------------------------------------------------------------
# Заметки и закрытия
# ---------------------------------------------------------------------------

class CalendarNoteViewSet(viewsets.ModelViewSet):
    queryset = CalendarNote.objects.select_related('created_by').all().order_by('start_time')
    serializer_class = CalendarNoteSerializer
    permission_classes = [IsAdminOrStaffWrite]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['start_time', 'id']

    def get_queryset(self):
        qs = super().get_queryset()
        start = self.request.query_params.get('start')
        end = self.request.query_params.get('end')
        if start and end:
            try:
                start_dt = timezone.datetime.fromisoformat(start.replace('Z', '+00:00'))
                end_dt = timezone.datetime.fromisoformat(end.replace('Z', '+00:00'))
                qs = qs.filter(start_time__lt=end_dt, end_time__gt=start_dt)
            except (ValueError, AttributeError):
                pass
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class CabinetClosureViewSet(viewsets.ModelViewSet):
    queryset = CabinetClosure.objects.select_related('cabinet', 'created_by').all().order_by('-start_time')
    serializer_class = CabinetClosureSerializer
    permission_classes = [IsAdminOrStaffWrite]
    filterset_fields = ['cabinet']
    ordering_fields = ['start_time', 'id']

    def get_queryset(self):
        qs = super().get_queryset()
        start = self.request.query_params.get('start')
        end = self.request.query_params.get('end')
        if start and end:
            try:
                start_dt = timezone.datetime.fromisoformat(start.replace('Z', '+00:00'))
                end_dt = timezone.datetime.fromisoformat(end.replace('Z', '+00:00'))
                qs = qs.filter(start_time__lt=end_dt, end_time__gt=start_dt)
            except (ValueError, AttributeError):
                pass
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


# ---------------------------------------------------------------------------
# Удалённые бронирования
# ---------------------------------------------------------------------------

class DeletedBookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = DeletedBooking.objects.select_related('deleted_by', 'restored_by').all().order_by('-deleted_at')
    serializer_class = DeletedBookingSerializer
    permission_classes = [IsAdminRole]
    filterset_fields = ['restored', 'deletion_scope', 'series_id']
    search_fields = ['deletion_reason']
    ordering_fields = ['deleted_at', 'id']

    @action(detail=True, methods=['post'], url_path='restore')
    def restore(self, request, pk=None):
        deleted = self.get_object()
        restore_series_flag = request.data.get('restore_series', False)
        if restore_series_flag and deleted.series_id:
            success, bookings, message = restore_series(deleted.id, restored_by=request.user)
            return Response({
                'success': success,
                'message': message,
                'booking_ids': [b.id for b in (bookings or [])],
            }, status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST)
        success, booking, message = restore_booking(deleted.id, restored_by=request.user)
        return Response({
            'success': success,
            'message': message,
            'booking_id': booking.id if booking else None,
        }, status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'], url_path='permanent-delete')
    def permanent_delete(self, request, pk=None):
        deleted = self.get_object()
        deleted.delete()
        return Response({'success': True, 'message': 'Запись удалена безвозвратно'}, status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------

class SystemSettingsView(APIView):
    permission_classes = [IsAdminRole]
    authentication_classes = API_AUTH_CLASSES

    @extend_schema(responses=SystemSettingsSerializer)
    def get(self, request):
        settings_obj = SystemSettings.get_solo()
        return Response(SystemSettingsSerializer(settings_obj).data)

    @extend_schema(request=SystemSettingsSerializer, responses=SystemSettingsSerializer)
    def put(self, request):
        settings_obj = SystemSettings.get_solo()
        serializer = SystemSettingsSerializer(settings_obj, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(request=SystemSettingsSerializer, responses=SystemSettingsSerializer)
    def patch(self, request):
        settings_obj = SystemSettings.get_solo()
        serializer = SystemSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Auth / me
# ---------------------------------------------------------------------------

class MeView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = API_AUTH_CLASSES

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        user = request.user
        groups = list(user.groups.values_list('name', flat=True))
        roles = []
        if user.is_superuser or 'SuperAdmin' in groups:
            roles.append('superadmin')
        if 'Admin' in groups or user.is_superuser:
            roles.append('admin')
        if user.is_staff:
            roles.append('staff')
        specialist = None
        try:
            specialist = SpecialistProfile.objects.prefetch_related(
                'services_can_perform', 'schedules'
            ).select_related('user').get(user=user)
            roles.append('specialist')
        except SpecialistProfile.DoesNotExist:
            pass

        data = {
            'id': user.id,
            'username': user.username,
            'email': user.email or '',
            'full_name': user.get_full_name() or '',
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'groups': groups,
            'roles': roles,
            'specialist': SpecialistProfileSerializer(specialist).data if specialist else None,
        }
        return Response(MeSerializer(data).data)


class UserApiKeyViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin):
    """
    Управление персональными API-ключами.
    Ключ действует от имени текущего пользователя с его правами.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = API_AUTH_CLASSES
    serializer_class = UserApiKeySerializer

    def get_queryset(self):
        return UserApiKey.objects.filter(user=self.request.user).order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return UserApiKeyCreateSerializer
        return UserApiKeySerializer

    @extend_schema(request=UserApiKeyCreateSerializer, responses={201: UserApiKeySerializer})
    def create(self, request, *args, **kwargs):
        serializer = UserApiKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        api_key = UserApiKey.create_for_user(
            user=request.user,
            name=serializer.validated_data['name'],
            expires_at=serializer.validated_data.get('expires_at'),
        )
        data = UserApiKeySerializer(api_key).data
        data['key'] = api_key._plain_key
        data['message'] = 'Сохраните ключ — он больше не будет показан'
        return Response(data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if not instance.is_active:
            return
        instance.is_active = False
        instance.save(update_fields=['is_active'])


class MyScheduleAPI(generics.ListAPIView):
    """Расписание текущего специалиста (совместимость со старым эндпоинтом)."""
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated, IsSpecialistRole]
    authentication_classes = API_AUTH_CLASSES
    queryset = Booking.objects.none()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Booking.objects.none()
        specialist = SpecialistProfile.objects.get(user=self.request.user)
        return Booking.objects.filter(specialist=specialist).select_related(
            'specialist', 'cabinet', 'service_variant', 'service_variant__service'
        ).order_by('start_time')


# ---------------------------------------------------------------------------
# Query endpoints
# ---------------------------------------------------------------------------

class AvailableSlotsView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        serializer = AvailableSlotsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        date = serializer.validated_data['date']
        service_variant = serializer.validated_data['service_variant']
        slots = find_available_slots(date, service_variant)
        result = []
        for slot in slots:
            cabinets = slot.get('available_cabinets') or []
            if not cabinets and slot.get('cabinet'):
                cabinets = [slot['cabinet']]
            result.append({
                'start_time': slot['start_time'].isoformat(),
                'specialist_id': slot['specialist'].id,
                'specialist_name': slot['specialist'].full_name,
                'cabinets': [{'id': c.id, 'name': c.name} for c in cabinets],
            })
        return Response(result)


class AvailableCabinetsView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        serializer = AvailableCabinetsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        service_variant = get_object_or_404(ServiceVariant, pk=data['service_variant_id'])
        get_object_or_404(SpecialistProfile, pk=data['specialist_id'])
        start_datetime = data['datetime']
        if timezone.is_naive(start_datetime):
            start_datetime = timezone.make_aware(start_datetime)

        required_types = service_variant.service.required_cabinet_types.all()
        cabinets = Cabinet.objects.filter(
            cabinet_type__in=required_types,
            is_active=True,
        ).order_by('name')
        return Response({
            'cabinets': [{'id': c.id, 'name': c.name} for c in cabinets],
        })


class SpecialistsForServiceView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        serializer = SpecialistsForServiceQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        service_variant = get_object_or_404(
            ServiceVariant, pk=serializer.validated_data['service_variant_id']
        )
        specialists = SpecialistProfile.objects.filter(
            services_can_perform=service_variant.service
        ).values('id', 'full_name')
        return Response(list(specialists))


class CalendarFeedAPIView(APIView):
    """Объединённый фид событий для календаря (брони + заметки + закрытия)."""
    permission_classes = [IsAdminOrStaffWrite]

    def get(self, request):
        serializer = CalendarFeedQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        start_date = serializer.validated_data['start']
        end_date = serializer.validated_data['end']
        if timezone.is_naive(start_date):
            start_date = timezone.make_aware(start_date)
        if timezone.is_naive(end_date):
            end_date = timezone.make_aware(end_date)

        events = []

        bookings = Booking.objects.filter(
            start_time__range=[start_date, end_date]
        ).select_related('service_variant', 'specialist', 'cabinet')
        for b in bookings:
            end_time = b.start_time + datetime.timedelta(minutes=b.service_variant.duration_minutes)
            specialist_short = b.specialist.full_name.split()[0]
            title = f"{b.guest_name} - {specialist_short} ({b.service_variant.name_suffix})"
            events.append({
                'id': b.id,
                'title': title,
                'start': b.start_time.isoformat(),
                'end': end_time.isoformat(),
                'eventType': 'booking',
                'status': b.status,
                'specialist': b.specialist.full_name,
                'cabinet': b.cabinet.name,
                'guest_name': b.guest_name,
                'comment': (b.comment or '').strip(),
                'seriesId': b.series_id,
            })

        notes = CalendarNote.objects.filter(start_time__lt=end_date, end_time__gt=start_date)
        for note in notes:
            raw = (note.comment or '').strip()
            title = (raw[:50] + '…') if len(raw) > 50 else (raw or 'Техническая запись')
            events.append({
                'id': f'note-{note.pk}',
                'title': title,
                'start': note.start_time.isoformat(),
                'end': note.end_time.isoformat(),
                'eventType': 'technical_note',
                'noteId': note.pk,
                'comment': note.comment,
            })

        if is_staff_user(request.user):
            closures = CabinetClosure.objects.filter(
                start_time__lt=end_date, end_time__gt=start_date
            ).select_related('cabinet')
            for closure in closures:
                events.append({
                    'id': f'closure-{closure.pk}',
                    'title': f'Закрыт: {closure.cabinet.name}',
                    'start': closure.start_time.isoformat(),
                    'end': closure.end_time.isoformat(),
                    'eventType': 'closure',
                    'cabinetId': closure.cabinet_id,
                    'cabinet': closure.cabinet.name,
                    'reason': closure.reason,
                    'canDelete': True,
                })

        return Response(events)


class ReportSummaryView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        serializer = ReportSummaryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        start_date = serializer.validated_data['start_date']
        end_date = serializer.validated_data['end_date']
        specialist = serializer.validated_data.get('specialist')

        start_dt = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
        end_dt = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))

        qs = Booking.objects.filter(start_time__gte=start_dt, start_time__lte=end_dt)
        if specialist:
            qs = qs.filter(specialist=specialist)

        by_status = list(qs.values('status').annotate(count=Count('id')).order_by('status'))
        by_specialist = list(
            qs.values('specialist_id', 'specialist__full_name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        by_service = list(
            qs.values('service_variant__service__name', 'service_variant__name_suffix')
            .annotate(count=Count('id'), revenue=Sum('service_variant__price'))
            .order_by('-count')
        )

        return Response({
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'total_bookings': qs.count(),
            'by_status': by_status,
            'by_specialist': by_specialist,
            'by_service': by_service,
        })


# Совместимость: старый guest autocomplete без авторизации
@api_view(['GET'])
@permission_classes([AllowAny])
def guest_autocomplete_view(request):
    """
    Legacy endpoint: GET /api/v1/guests/autocomplete/?q=
    (также доступен через GuestViewSet.autocomplete с авторизацией)
    """
    query = request.GET.get('q', '').strip()
    limit = int(request.GET.get('limit', 10))
    if not query or len(query) < 2:
        return Response([])

    normalized_query = normalize_guest_name(query)
    if len(query) <= 3:
        guests = Guest.objects.filter(
            Q(normalized_name__icontains=query) |
            Q(display_name__icontains=query) |
            Q(normalized_name__icontains=normalized_query)
        ).distinct().order_by('display_name')[:limit]
    else:
        similar = find_similar_guests(query, threshold=0.5, limit=limit)
        exact = Guest.objects.filter(
            Q(normalized_name__istartswith=normalized_query) |
            Q(display_name__istartswith=query)
        ).exclude(id__in=[g.id for g in similar]).distinct()[: max(0, limit - len(similar))]
        guests = list(similar) + list(exact)

    results = []
    seen = set()
    for guest in list(guests)[:limit]:
        if guest.id in seen:
            continue
        seen.add(guest.id)
        results.append({
            'id': guest.id,
            'display_name': guest.display_name,
            'normalized_name': guest.normalized_name,
            'booking_count': guest.bookings.count(),
        })
    return Response(results)
