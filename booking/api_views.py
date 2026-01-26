"""
API views для Django REST Framework
"""
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from django.http import JsonResponse
import logging

from .models import Booking, SpecialistProfile, Guest
from .serializers import BookingSerializer
from .guest_utils import find_similar_guests, normalize_guest_name

logger = logging.getLogger(__name__)


class IsSpecialistPermission(permissions.BasePermission):
    """
    Разрешение для специалистов: доступ только к своим бронированиям
    """
    def has_permission(self, request, view):
        # Проверяем, что пользователь аутентифицирован
        if not request.user.is_authenticated:
            return False
        
        # Проверяем, что пользователь является специалистом
        try:
            SpecialistProfile.objects.get(user=request.user)
            return True
        except SpecialistProfile.DoesNotExist:
            logger.warning(f"User {request.user.id} attempted to access specialist API without profile")
            return False


class MyScheduleAPI(generics.ListAPIView):
    """
    API для получения расписания специалиста (только для чтения).
    
    Возвращает все бронирования для текущего авторизованного специалиста.
    
    Endpoint: GET /api/v1/my-schedule/
    
    Response:
    [
        {
            "id": 1,
            "guest_name": "Иван Иванов",
            "guest_room_number": "101",
            "specialist_name": "Петров Петр Петрович",
            "cabinet_name": "Кабинет 1",
            "service_name": "Тайский массаж",
            "service_duration": 60,
            "start_time": "2025-11-03T10:00:00Z",
            "end_time": "2025-11-03T11:15:00Z",
            "status": "confirmed"
        }
    ]
    """
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated, IsSpecialistPermission]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    
    def get_queryset(self):
        """
        Возвращает все подтверждённые бронирования для текущего специалиста
        """
        try:
            specialist = SpecialistProfile.objects.get(user=self.request.user)
            return Booking.objects.filter(
                specialist=specialist,
                status='confirmed'
            ).select_related(
                'specialist', 'cabinet', 
                'service_variant', 'service_variant__service'
            ).order_by('start_time')
        except SpecialistProfile.DoesNotExist:
            logger.error(f"SpecialistProfile not found for user {self.request.user.id}")
            return Booking.objects.none()


@api_view(['GET'])
@permission_classes([AllowAny])
def guest_autocomplete_view(request):
    from django.db.models import Q
    """
    API endpoint для автодополнения имен гостей.
    
    Endpoint: GET /api/v1/guests/autocomplete/?q=<query>
    
    Response:
    [
        {
            "id": 1,
            "display_name": "Иван Иванов",
            "normalized_name": "Иван Иванов",
            "booking_count": 5
        },
        ...
    ]
    """
    query = request.GET.get('q', '').strip()
    limit = int(request.GET.get('limit', 10))
    
    if not query or len(query) < 2:
        return JsonResponse([], safe=False)
    
    # Нормализуем запрос
    normalized_query = normalize_guest_name(query)
    
    # Для коротких запросов (2-3 символа) используем более простой поиск
    from django.db.models import Q
    
    if len(query) <= 3:
        # Для очень коротких запросов используем icontains (содержит) для более широкого поиска
        all_guests = Guest.objects.filter(
            Q(normalized_name__icontains=query) |
            Q(display_name__icontains=query) |
            Q(normalized_name__icontains=normalized_query)
        ).distinct().order_by('display_name')[:limit]
    else:
        # Для длинных запросов используем поиск похожих
        similar_guests = find_similar_guests(query, threshold=0.5, limit=limit)
        
        # Также ищем по началу имени (быстрый поиск)
        exact_matches = Guest.objects.filter(
            Q(normalized_name__istartswith=normalized_query) |
            Q(display_name__istartswith=query)
        ).exclude(
            id__in=[g.id for g in similar_guests]
        ).distinct()[:limit - len(similar_guests)]
        
        # Объединяем результаты
        all_guests = list(similar_guests) + list(exact_matches)
    
    # Формируем ответ
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

