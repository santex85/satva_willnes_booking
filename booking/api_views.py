from rest_framework import viewsets, permissions, generics, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from django.http import JsonResponse, StreamingHttpResponse
from django.db import transaction
import logging

from .models import (
    Booking,
    SpecialistProfile,
    Guest,
    Cabinet,
    CabinetType,
    Service,
    ServiceVariant,
    SpecialistSchedule,
)
from .clinical_models import SOAPNote
from .serializers import (
    BookingSerializer,
    CabinetSerializer,
    CabinetTypeSerializer,
    ServiceSerializer,
    ServiceVariantSerializer,
    SpecialistProfileSerializer,
    SpecialistScheduleSerializer,
    GuestSerializer,
    SOAPNoteSerializer,
)
from .guest_utils import find_similar_guests, normalize_guest_name, merge_guests
from .analytics_utils import (
    parse_date_range,
    parse_specialist_id,
    build_bookings_filter,
    get_service_popularity,
    get_specialist_load,
    get_guest_statistics,
    iter_csv_report_rows,
)

logger = logging.getLogger(__name__)


class BookingViewSet(viewsets.ModelViewSet):
    """ViewSet для управления бронированиями (CRUD)"""
    queryset = Booking.objects.all().select_related(
        'specialist', 'cabinet', 'service_variant', 'service_variant__service', 'guest'
    )
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _filtered_bookings(self, request):
        start, end = parse_date_range(request)
        specialist_id = parse_specialist_id(request)
        return build_bookings_filter(start, end, specialist_id)

    @action(detail=False, methods=['get'], url_path='service_popularity')
    def service_popularity(self, request):
        """GET /api/v1/bookings/service_popularity/?start_date=&end_date="""
        bookings = self._filtered_bookings(request)
        return Response(get_service_popularity(bookings))

    @action(detail=False, methods=['get'], url_path='specialist_load')
    def specialist_load(self, request):
        """GET /api/v1/bookings/specialist_load/?start_date=&end_date="""
        bookings = self._filtered_bookings(request)
        return Response(get_specialist_load(bookings))

    @action(detail=False, methods=['get'], url_path='export_csv')
    def export_csv(self, request):
        """GET /api/v1/bookings/export_csv/?start_date=&end_date="""
        start, end = parse_date_range(request)
        specialist_id = parse_specialist_id(request)

        bookings_query = Booking.objects.filter(
            start_time__date__range=[start, end],
        ).exclude(status='canceled').select_related(
            'service_variant', 'service_variant__service',
            'specialist', 'cabinet', 'guest',
        ).order_by('start_time')

        if specialist_id is not None:
            bookings_query = bookings_query.filter(specialist_id=specialist_id)

        def row_generator():
            yield '\ufeff'
            import csv
            import io
            buffer = io.StringIO()
            writer = csv.writer(buffer, delimiter=';')
            for row in iter_csv_report_rows(bookings_query):
                writer.writerow(row)
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)

        filename_parts = [f'otchet_{start.strftime("%Y-%m-%d")}_{end.strftime("%Y-%m-%d")}']
        if specialist_id is not None:
            try:
                specialist = SpecialistProfile.objects.get(pk=specialist_id)
                filename_parts.append(specialist.full_name.replace(' ', '_'))
            except SpecialistProfile.DoesNotExist:
                pass
        filename = '_'.join(filename_parts) + '.csv'

        response = StreamingHttpResponse(
            row_generator(),
            content_type='text/csv; charset=utf-8',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        logger.info(
            'CSV export: period=%s to %s, specialist_id=%s, user=%s',
            start, end, specialist_id, request.user.username,
        )
        return response


class CabinetViewSet(viewsets.ModelViewSet):
    """ViewSet для управления кабинетами (CRUD)"""
    queryset = Cabinet.objects.all().select_related('cabinet_type')
    serializer_class = CabinetSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]


class CabinetTypeViewSet(viewsets.ModelViewSet):
    """ViewSet для управления типами кабинетов (CRUD)"""
    queryset = CabinetType.objects.all()
    serializer_class = CabinetTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]


class ServiceViewSet(viewsets.ModelViewSet):
    """ViewSet для управления услугами (CRUD)"""
    queryset = Service.objects.all().prefetch_related('required_cabinet_types')
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]


class ServiceVariantViewSet(viewsets.ModelViewSet):
    """ViewSet для управления вариантами услуг (CRUD)"""
    queryset = ServiceVariant.objects.all().select_related('service')
    serializer_class = ServiceVariantSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]


class SpecialistProfileViewSet(viewsets.ModelViewSet):
    """ViewSet для управления профилями специалистов (CRUD)"""
    queryset = SpecialistProfile.objects.all().select_related('user').prefetch_related('services_can_perform')
    serializer_class = SpecialistProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]


class SpecialistScheduleViewSet(viewsets.ModelViewSet):
    """ViewSet для управления графиками смен специалистов (CRUD)"""
    queryset = SpecialistSchedule.objects.all().select_related('specialist')
    serializer_class = SpecialistScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]


class GuestViewSet(viewsets.ModelViewSet):
    """ViewSet для управления клиентами/гостями (CRUD)"""
    queryset = Guest.objects.all()
    serializer_class = GuestSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    @action(detail=False, methods=['get'], url_path='statistics')
    def statistics(self, request):
        """GET /api/v1/guests/statistics/?start_date=&end_date="""
        start, end = parse_date_range(request)
        specialist_id = parse_specialist_id(request)
        bookings = build_bookings_filter(start, end, specialist_id)
        return Response(get_guest_statistics(bookings))

    @action(detail=False, methods=['post'], url_path='merge')
    def merge(self, request):
        """POST /api/v1/guests/merge/ — объединение дубликатов гостей."""
        primary_id = request.data.get('primary_id')
        duplicate_ids = request.data.get('duplicate_ids', [])
        primary_display_name = request.data.get('primary_display_name')

        if not primary_id:
            return Response(
                {'success': False, 'error': 'primary_id обязателен.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not duplicate_ids or not isinstance(duplicate_ids, list):
            return Response(
                {'success': False, 'error': 'duplicate_ids должен быть непустым массивом.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            primary_guest = Guest.objects.get(pk=primary_id)
        except Guest.DoesNotExist:
            return Response(
                {'success': False, 'error': f'Гость с id={primary_id} не найден.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        duplicate_guests = list(Guest.objects.filter(pk__in=duplicate_ids).exclude(pk=primary_id))
        if not duplicate_guests:
            return Response(
                {'success': False, 'error': 'Не найдено дубликатов для объединения.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                bookings_updated = merge_guests(
                    primary_guest,
                    duplicate_guests,
                    primary_display_name.strip() if primary_display_name else None,
                )
        except Exception as exc:
            logger.error('Error merging guests: %s', exc, exc_info=True)
            return Response(
                {'success': False, 'error': f'Ошибка при объединении: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        primary_guest.refresh_from_db()
        logger.info(
            'User %s merged %s guests into %s. Bookings updated: %s',
            request.user.username,
            len(duplicate_guests),
            primary_guest.display_name,
            bookings_updated,
        )

        return Response({
            'success': True,
            'message': (
                f'Объединено {len(duplicate_guests)} гостей с «{primary_guest.display_name}». '
                f'Перенесено {bookings_updated} бронирований.'
            ),
            'primary_guest': {
                'id': primary_guest.id,
                'display_name': primary_guest.display_name,
            },
            'merged_count': len(duplicate_guests),
            'bookings_updated': bookings_updated,
        })


class SOAPNoteViewSet(viewsets.ModelViewSet):
    """ViewSet для ведения клинических SOAP-карт гостей (CRUD)"""
    queryset = SOAPNote.objects.all().select_related('guest', 'specialist')
    serializer_class = SOAPNoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]


# Сохраняем старые вьюсеты/функции для обратной совместимости
class IsSpecialistPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        try:
            SpecialistProfile.objects.get(user=request.user)
            return True
        except SpecialistProfile.DoesNotExist:
            return False


class MyScheduleAPI(generics.ListAPIView):
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated, IsSpecialistPermission]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        try:
            specialist = SpecialistProfile.objects.get(user=self.request.user)
            return Booking.objects.filter(
                specialist=specialist
            ).select_related(
                'specialist', 'cabinet',
                'service_variant', 'service_variant__service', 'guest'
            ).order_by('start_time')
        except SpecialistProfile.DoesNotExist:
            return Booking.objects.none()


@api_view(['GET'])
@permission_classes([AllowAny])
def guest_autocomplete_view(request):
    query = request.GET.get('q', '').strip()
    limit = int(request.GET.get('limit', 10))

    if not query or len(query) < 2:
        return JsonResponse([], safe=False)

    normalized_query = normalize_guest_name(query)

    from django.db.models import Q
    if len(query) <= 3:
        all_guests = Guest.objects.filter(
            Q(normalized_name__icontains=query) |
            Q(display_name__icontains=query) |
            Q(normalized_name__icontains=normalized_query)
        ).distinct().order_by('display_name')[:limit]
    else:
        similar_guests = find_similar_guests(query, threshold=0.5, limit=limit)
        exact_matches = Guest.objects.filter(
            Q(normalized_name__istartswith=normalized_query) |
            Q(display_name__istartswith=query)
        ).exclude(
            id__in=[g.id for g in similar_guests]
        ).distinct()[:limit - len(similar_guests)]
        all_guests = list(similar_guests) + list(exact_matches)

    results = []
    seen_ids = set()
    for guest in all_guests[:limit]:
        if guest.id in seen_ids:
            continue
        seen_ids.add(guest.id)
        results.append({
            'id': guest.id,
            'display_name': guest.display_name,
            'normalized_name': guest.normalized_name,
            'booking_count': guest.bookings.count(),
        })

    return JsonResponse(results, safe=False)
