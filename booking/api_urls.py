"""
URL configuration for REST API v1.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from . import api_views

router = DefaultRouter()
router.register(r'cabinet-types', api_views.CabinetTypeViewSet, basename='api-cabinet-types')
router.register(r'cabinets', api_views.CabinetViewSet, basename='api-cabinets')
router.register(r'services', api_views.ServiceViewSet, basename='api-services')
router.register(r'service-variants', api_views.ServiceVariantViewSet, basename='api-service-variants')
router.register(r'specialists', api_views.SpecialistViewSet, basename='api-specialists')
router.register(r'specialist-schedules', api_views.SpecialistScheduleViewSet, basename='api-specialist-schedules')
router.register(r'schedule-templates', api_views.ScheduleTemplateViewSet, basename='api-schedule-templates')
router.register(r'guests', api_views.GuestViewSet, basename='api-guests')
router.register(r'bookings', api_views.BookingViewSet, basename='api-bookings')
router.register(r'booking-series', api_views.BookingSeriesViewSet, basename='api-booking-series')
router.register(r'calendar-notes', api_views.CalendarNoteViewSet, basename='api-calendar-notes')
router.register(r'cabinet-closures', api_views.CabinetClosureViewSet, basename='api-cabinet-closures')
router.register(r'deleted-bookings', api_views.DeletedBookingViewSet, basename='api-deleted-bookings')
router.register(r'api-keys', api_views.UserApiKeyViewSet, basename='api-api-keys')

urlpatterns = [
    # Auth
    path('auth/token/', TokenObtainPairView.as_view(), name='api_token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='api_token_verify'),
    path('auth/me/', api_views.MeView.as_view(), name='api_me'),

    # Legacy token paths (совместимость)
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Legacy / specialist schedule
    path('my-schedule/', api_views.MyScheduleAPI.as_view(), name='api_my_schedule'),

    # Legacy guest autocomplete (AllowAny) — keep path for existing frontend
    path('guests/autocomplete/', api_views.guest_autocomplete_view, name='api_guest_autocomplete'),

    # Query endpoints
    path('available-slots/', api_views.AvailableSlotsView.as_view(), name='api_available_slots'),
    path('available-cabinets/', api_views.AvailableCabinetsView.as_view(), name='api_available_cabinets'),
    path('specialists-for-service/', api_views.SpecialistsForServiceView.as_view(), name='api_specialists_for_service'),
    path('calendar-feed/', api_views.CalendarFeedAPIView.as_view(), name='api_calendar_feed'),
    path('reports/summary/', api_views.ReportSummaryView.as_view(), name='api_reports_summary'),

    # Settings
    path('system-settings/', api_views.SystemSettingsView.as_view(), name='api_system_settings'),

    # OpenAPI / Swagger
    path('schema/', SpectacularAPIView.as_view(), name='api_schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api_schema'), name='api_docs'),

    # ViewSets
    path('', include(router.urls)),
]
