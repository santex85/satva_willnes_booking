"""
URL configuration for booking app
"""
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
import logging

from . import views, api_views

logger = logging.getLogger(__name__)

# Явная проверка что функция доступна
try:
    _available_cabinets_view = views.get_available_cabinets_view
    # Используем print для гарантированного вывода при старте
    print(f"✓ get_available_cabinets_view imported successfully: {_available_cabinets_view}")
    logger.info(f"✓ get_available_cabinets_view imported successfully: {_available_cabinets_view}")
except AttributeError as e:
    print(f"✗ ERROR: get_available_cabinets_view not found in views: {e}")
    logger.error(f"✗ get_available_cabinets_view not found in views: {e}")
    raise

urlpatterns = [
    path('', views.index_view, name='index'),
    path('register/specialist/', views.specialist_register_view, name='specialist_register'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/feed/', views.calendar_feed_view, name='calendar_feed'),
    path('calendar/resources/specialists/', views.specialist_resources_view, name='specialist_resources'),
    path('calendar/resources/cabinets/', views.cabinet_resources_view, name='cabinet_resources'),
    path('api/specialists-for-service/', views.get_specialists_for_service_view, name='specialists_for_service'),
    # Явно указываем функцию для диагностики
    path('api/available-cabinets/', _available_cabinets_view, name='available_cabinets'),
    path('select-service/', views.select_service_view, name='select_service'),
    path('select-slot/', views.select_slot_view, name='select_slot'),
    path('create-booking/', views.create_booking_view, name='create_booking'),
    path('booking/quick-create/', views.quick_create_booking_view, name='quick_create_booking'),
    path('booking/update-time/', views.update_booking_time_view, name='update_booking_time'),
    path('booking/<int:pk>/', views.booking_detail_view, name='booking_detail'),
    path('booking/<int:pk>/delete/', views.BookingDeleteView.as_view(), name='booking_delete'),
    path('manage-schedules/', views.manage_schedules_view, name='manage_schedules'),
    path('reports/', views.reports_view, name='reports'),
    path('my-schedule/', views.my_schedule_view, name='my_schedule'),
    
    # API endpoints
    path('api/v1/my-schedule/', api_views.MyScheduleAPI.as_view(), name='api_my_schedule'),
    path('api/v1/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

