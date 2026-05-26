"""
URL configuration for booking app — API + React SPA.
"""
from django.urls import path, re_path
from django.views.static import serve
from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from . import api_views, spa_views

router = DefaultRouter()
router.register(r'api/v1/bookings', api_views.BookingViewSet, basename='api_bookings')
router.register(r'api/v1/cabinets', api_views.CabinetViewSet, basename='api_cabinets')
router.register(r'api/v1/cabinet-types', api_views.CabinetTypeViewSet, basename='api_cabinet_types')
router.register(r'api/v1/services', api_views.ServiceViewSet, basename='api_services')
router.register(r'api/v1/service-variants', api_views.ServiceVariantViewSet, basename='api_service_variants')
router.register(r'api/v1/specialists', api_views.SpecialistProfileViewSet, basename='api_specialists')
router.register(r'api/v1/schedules', api_views.SpecialistScheduleViewSet, basename='api_schedules')
router.register(r'api/v1/guests', api_views.GuestViewSet, basename='api_guests')
router.register(r'api/v1/soap-notes', api_views.SOAPNoteViewSet, basename='api_soap_notes')

urlpatterns = [
    # REST API
    path('api/v1/my-schedule/', api_views.MyScheduleAPI.as_view(), name='api_my_schedule'),
    path('api/v1/guests/autocomplete/', api_views.guest_autocomplete_view, name='api_guest_autocomplete'),
    path('api/v1/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    *router.urls,

    # Vite build assets
    path(
        'assets/<path:path>',
        serve,
        {'document_root': settings.FRONTEND_DIST / 'assets'},
        name='frontend_assets',
    ),

    # React SPA
    path('', spa_views.index, name='index'),
    re_path(r'^(?!api/|assets/).*$', spa_views.index, name='spa_fallback'),
]
