"""
API views для Django REST Framework
"""
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
import logging

from .models import Booking, SpecialistProfile
from .serializers import BookingSerializer

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

