from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from django.contrib import messages
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
    ScheduleTemplate,
    ScheduleTemplateDay,
    CabinetClosure,
)


class ServiceVariantInline(admin.TabularInline):
    model = ServiceVariant
    extra = 1


class SpecialistScheduleInline(admin.TabularInline):
    """Inline для управления расписанием специалиста"""
    model = SpecialistSchedule
    extra = 0
    max_num = 7
    fields = ('day_of_week', 'start_time', 'end_time')
    verbose_name = 'День расписания'
    verbose_name_plural = 'Расписание работы'


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name',)
    inlines = [ServiceVariantInline]
    filter_horizontal = ('required_cabinet_types',)


@admin.register(SpecialistProfile)
class SpecialistProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user')
    filter_horizontal = ('services_can_perform',)
    inlines = [SpecialistScheduleInline]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('start_time', 'guest_name', 'service_variant', 'specialist', 'cabinet', 'status')
    list_filter = ('status', 'specialist', 'start_time')
    readonly_fields = ('end_time',)


class SpecialistScheduleAdmin(admin.ModelAdmin):
    """Admin с недельным видом для расписания специалистов"""
    list_display = ('specialist', 'day_of_week', 'start_time', 'end_time')
    list_filter = ('specialist', 'day_of_week')
    search_fields = ('specialist__full_name',)
    ordering = ('specialist__full_name', 'day_of_week')
    change_list_template = 'admin/booking/specialistschedule/change_list.html'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('week-view/', self.admin_site.admin_view(self.week_view), name='booking_specialistschedule_week_view'),
        ]
        return custom_urls + urls
    
    def week_view(self, request):
        """Недельный вид расписания: специалисты - строки, дни недели - колонки"""
        specialists = SpecialistProfile.objects.all().order_by('full_name')
        days_of_week = SpecialistSchedule.DAYS_OF_WEEK
        
        # Получаем все расписания с prefetch для оптимизации
        schedules = SpecialistSchedule.objects.select_related('specialist').all()
        
        # Создаем словарь для быстрого доступа: {specialist_id: {day_of_week: schedule}}
        schedule_dict = {}
        for schedule in schedules:
            if schedule.specialist.id not in schedule_dict:
                schedule_dict[schedule.specialist.id] = {}
            schedule_dict[schedule.specialist.id][schedule.day_of_week] = schedule
        
        # Формируем данные для шаблона
        schedule_data = []
        for specialist in specialists:
            row = {
                'specialist': specialist,
                'days': []
            }
            for day_value, day_name in days_of_week:
                schedule = schedule_dict.get(specialist.id, {}).get(day_value)
                row['days'].append({
                    'day_value': day_value,
                    'day_name': day_name,
                    'schedule': schedule,
                })
            schedule_data.append(row)
        
        context = {
            **self.admin_site.each_context(request),
            'title': 'Недельный вид расписания',
            'schedule_data': schedule_data,
            'days_of_week': days_of_week,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
        }
        
        return render(request, 'admin/booking/specialistschedule/week_view.html', context)


class ScheduleTemplateDayInline(admin.TabularInline):
    """Inline для дней шаблона расписания"""
    model = ScheduleTemplateDay
    extra = 0
    max_num = 7
    fields = ('day_of_week', 'start_time', 'end_time')
    verbose_name = 'День шаблона'
    verbose_name_plural = 'Дни шаблона'


@admin.register(ScheduleTemplate)
class ScheduleTemplateAdmin(admin.ModelAdmin):
    """Admin для шаблонов расписания"""
    list_display = ('name', 'description_short', 'days_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'description')
    inlines = [ScheduleTemplateDayInline]
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def description_short(self, obj):
        """Короткое описание для списка"""
        if obj.description:
            return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
        return '-'
    description_short.short_description = 'Описание'
    
    def days_count(self, obj):
        """Количество дней в шаблоне"""
        return obj.days.count()
    days_count.short_description = 'Дней в шаблоне'
    
    actions = ['create_template_from_specialist']
    
    def create_template_from_specialist(self, request, queryset):
        """Действие для создания шаблона из расписания специалиста"""
        specialist_id = request.POST.get('specialist_id')
        if not specialist_id:
            messages.error(request, 'Не указан специалист')
            return
        
        try:
            specialist = SpecialistProfile.objects.get(id=specialist_id)
            schedules = SpecialistSchedule.objects.filter(specialist=specialist)
            
            if not schedules.exists():
                messages.error(request, f'У специалиста {specialist.full_name} нет расписания')
                return
            
            # Создаем шаблон
            template_name = f'Шаблон из расписания {specialist.full_name}'
            template = ScheduleTemplate.objects.create(
                name=template_name,
                description=f'Создан из расписания специалиста {specialist.full_name}'
            )
            
            # Копируем дни
            for schedule in schedules:
                ScheduleTemplateDay.objects.create(
                    template=template,
                    day_of_week=schedule.day_of_week,
                    start_time=schedule.start_time,
                    end_time=schedule.end_time
                )
            
            messages.success(request, f'Шаблон "{template_name}" успешно создан из расписания {specialist.full_name}')
        except SpecialistProfile.DoesNotExist:
            messages.error(request, 'Специалист не найден')
        except Exception as e:
            messages.error(request, f'Ошибка при создании шаблона: {e}')
    
    create_template_from_specialist.short_description = 'Создать шаблон из расписания специалиста'


admin.site.register(SystemSettings, SingletonModelAdmin)
admin.site.register(CabinetType)
admin.site.register(Cabinet)
admin.site.register(SpecialistSchedule, SpecialistScheduleAdmin)
admin.site.register(ServiceVariant)
admin.site.register(CabinetClosure)
