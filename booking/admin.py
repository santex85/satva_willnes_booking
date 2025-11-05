from django.contrib import admin
from solo.admin import SingletonModelAdmin
from .models import (
    SystemSettings,
    CabinetType,
    Cabinet,
    Service,
    ServiceVariant,
    SpecialistProfile,
    SpecialistSchedule,
    Booking,
)


class ServiceVariantInline(admin.TabularInline):
    model = ServiceVariant
    extra = 1


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name',)
    inlines = [ServiceVariantInline]
    filter_horizontal = ('required_cabinet_types',)


@admin.register(SpecialistProfile)
class SpecialistProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user')
    filter_horizontal = ('services_can_perform',)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('start_time', 'guest_name', 'service_variant', 'specialist', 'cabinet', 'status')
    list_filter = ('status', 'specialist', 'start_time')
    readonly_fields = ('end_time',)


admin.site.register(SystemSettings, SingletonModelAdmin)
admin.site.register(CabinetType)
admin.site.register(Cabinet)
admin.site.register(SpecialistSchedule)
admin.site.register(ServiceVariant)
