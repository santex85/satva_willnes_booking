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

urlpatterns = [
    path('', views.index_view, name='index'),
    path('register/specialist/', views.specialist_register_view, name='specialist_register'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/feed/', views.calendar_feed_view, name='calendar_feed'),
    path('calendar/closures/', views.cabinet_closure_feed_view, name='calendar_closure_feed'),
    path('calendar/closures/create/', views.create_cabinet_closure_view, name='create_cabinet_closure'),
    path('calendar/closures/<int:pk>/delete/', views.delete_cabinet_closure_view, name='delete_cabinet_closure'),
    path('calendar/resources/specialists/', views.specialist_resources_view, name='specialist_resources'),
    path('calendar/resources/cabinets/', views.cabinet_resources_view, name='cabinet_resources'),
    path('api/specialists-for-service/', views.get_specialists_for_service_view, name='specialists_for_service'),
    path('api/available-cabinets/', views.get_available_cabinets_view, name='available_cabinets'),
    path('select-service/', views.select_service_view, name='select_service'),
    path('select-slot/', views.select_slot_view, name='select_slot'),
    path('create-booking/', views.create_booking_view, name='create_booking'),
    path('booking/quick-create/', views.quick_create_booking_view, name='quick_create_booking'),
    path('booking/update-time/', views.update_booking_time_view, name='update_booking_time'),
    path('booking/<int:pk>/', views.booking_detail_view, name='booking_detail'),
    path('booking/<int:pk>/validate/', views.validate_booking_edit_view, name='validate_booking_edit'),
    path('booking/<int:pk>/delete/', views.BookingDeleteView.as_view(), name='booking_delete'),
    path('manage-schedules/', views.manage_schedules_view, name='manage_schedules'),
    path('schedules/copy/', views.copy_schedule_view, name='copy_schedule'),
    path('schedules/apply-template/', views.apply_template_view, name='apply_template'),
    path('reports/', views.reports_view, name='reports'),
    path('my-schedule/', views.my_schedule_view, name='my_schedule'),
    
    # API endpoints
    path('api/v1/my-schedule/', api_views.MyScheduleAPI.as_view(), name='api_my_schedule'),
    path('api/v1/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

