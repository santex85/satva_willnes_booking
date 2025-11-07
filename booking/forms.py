"""
Формы для бронирования
"""
from django import forms
from django.utils import timezone
from .models import ServiceVariant, SpecialistProfile, Cabinet, SpecialistSchedule, Booking
import datetime


class SelectServiceForm(forms.Form):
    """Форма выбора услуги и даты"""
    service_variant = forms.ModelChoiceField(
        queryset=ServiceVariant.objects.all().select_related('service').order_by('service__name', 'duration_minutes'),
        label='Услуга',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label='Дата',
        initial=datetime.date.today
    )


class QuickBookingForm(forms.Form):
    """Форма для быстрого создания бронирования"""
    service_variant = forms.ModelChoiceField(
        queryset=ServiceVariant.objects.all().select_related('service').order_by('service__name', 'duration_minutes'),
        label='Услуга',
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )
    specialist = forms.ModelChoiceField(
        queryset=SpecialistProfile.objects.all(),
        label='Специалист',
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )
    cabinet = forms.ModelChoiceField(
        queryset=Cabinet.objects.filter(is_active=True),
        label='Кабинет',
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,  # Будет валидироваться динамически в view
        empty_label='-- Выберите кабинет --'
    )
    guest_name = forms.CharField(
        max_length=200,
        label='Имя гостя',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=True
    )
    guest_room_number = forms.CharField(
        max_length=20,
        label='Номер комнаты',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False
    )
    start_datetime = forms.DateTimeField(
        widget=forms.HiddenInput(),
        required=True,
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S']
    )


class SpecialistScheduleForm(forms.ModelForm):
    """Форма для графика работы специалиста"""
    
    class Meta:
        model = SpecialistSchedule
        fields = ['day_of_week', 'start_time', 'end_time']
        widgets = {
            'day_of_week': forms.Select(attrs={'class': 'form-select'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        if start_time and end_time:
            if start_time >= end_time:
                raise forms.ValidationError({
                    'end_time': 'Время окончания должно быть больше времени начала'
                })
        
        return cleaned_data


class ReportForm(forms.Form):
    """Форма для отчетов"""
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label='Начальная дата',
        initial=datetime.date.today
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label='Конечная дата',
        initial=datetime.date.today
    )


class SpecialistRegistrationForm(forms.Form):
    """Форма регистрации специалиста"""
    username = forms.CharField(
        max_length=150,
        label='Имя пользователя',
        widget=forms.TextInput(attrs={'class': 'form-control', 'autofocus': True}),
        help_text='Требуется. Не более 150 символов. Только буквы, цифры и @/./+/-/_'
    )
    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
        required=False
    )
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        min_length=8,
        help_text='Минимум 8 символов'
    )
    password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        help_text='Введите тот же пароль для подтверждения'
    )
    full_name = forms.CharField(
        max_length=200,
        label='Полное имя',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Ваше полное имя для отображения в системе'
    )
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        from django.contrib.auth.models import User
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Пользователь с таким именем уже существует.')
        return username
    
    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Пароли не совпадают.')
        return password2


class BookingEditForm(forms.ModelForm):
    """Форма для редактирования бронирования"""
    start_datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        label='Дата и время начала',
        input_formats=['%Y-%m-%dT%H:%M']
    )
    
    class Meta:
        model = Booking
        fields = ['guest_name', 'guest_room_number', 'status']
        widgets = {
            'guest_name': forms.TextInput(attrs={'class': 'form-control'}),
            'guest_room_number': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
    
    service_variant = forms.ModelChoiceField(
        queryset=ServiceVariant.objects.all().select_related('service').order_by('service__name', 'duration_minutes'),
        label='Услуга',
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )
    specialist = forms.ModelChoiceField(
        queryset=SpecialistProfile.objects.all(),
        label='Специалист',
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )
    cabinet = forms.ModelChoiceField(
        queryset=Cabinet.objects.filter(is_active=True),
        label='Кабинет',
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        empty_label='-- Выберите кабинет --'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Конвертируем timezone-aware datetime в naive для HTML input
            local_time = timezone.localtime(self.instance.start_time)
            self.initial['start_datetime'] = local_time.strftime('%Y-%m-%dT%H:%M')
            # Устанавливаем начальные значения для новых полей
            self.initial['service_variant'] = self.instance.service_variant
            self.initial['specialist'] = self.instance.specialist
            self.initial['cabinet'] = self.instance.cabinet
    
    def clean(self):
        cleaned_data = super().clean()
        start_datetime_str = cleaned_data.get('start_datetime')
        service_variant = cleaned_data.get('service_variant')
        specialist = cleaned_data.get('specialist')
        cabinet = cleaned_data.get('cabinet')
        
        # Если нет обязательных полей, пропускаем валидацию (будут ошибки полей)
        if not all([start_datetime_str, service_variant, specialist, cabinet]):
            return cleaned_data
        
        # Парсим datetime
        if isinstance(start_datetime_str, str):
            naive_dt = datetime.datetime.strptime(start_datetime_str, '%Y-%m-%dT%H:%M')
            if timezone.is_naive(naive_dt):
                start_time = timezone.make_aware(naive_dt)
            else:
                start_time = start_datetime_str
        else:
            start_time = start_datetime_str
        
        # Проверка что специалист может выполнять услугу
        service = service_variant.service
        if not specialist.services_can_perform.filter(id=service.id).exists():
            raise forms.ValidationError({
                'specialist': 'Выбранный специалист не может выполнять данную услугу'
            })
        
        # Проверка что кабинет подходит для услуги
        required_cabinet_types = service.required_cabinet_types.all()
        if cabinet.cabinet_type not in required_cabinet_types:
            raise forms.ValidationError({
                'cabinet': 'Выбранный кабинет не подходит для данной услуги'
            })
        
        # Проверка конфликтов (исключая текущее бронирование)
        from .utils import check_booking_conflicts
        booking_id = self.instance.pk if self.instance else None
        conflicts = check_booking_conflicts(
            start_time=start_time,
            service_variant=service_variant,
            specialist=specialist,
            cabinet=cabinet,
            exclude_booking_id=booking_id
        )
        
        if conflicts:
            conflict_messages = []
            if conflicts.get('specialist_busy'):
                conflict_messages.append('Специалист занят в это время')
            if conflicts.get('cabinet_busy'):
                conflict_messages.append('Кабинет занят в это время')
            if conflicts.get('specialist_not_available'):
                conflict_messages.append('Специалист не работает в это время')
            if conflicts.get('cabinet_not_available'):
                conflict_messages.append('Кабинет недоступен в это время')
            
            raise forms.ValidationError({
                'start_datetime': '; '.join(conflict_messages) if conflict_messages else 'Выбранное время недоступно'
            })
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        start_datetime_str = self.cleaned_data['start_datetime']
        
        # Обновляем поля из формы
        instance.service_variant = self.cleaned_data['service_variant']
        instance.specialist = self.cleaned_data['specialist']
        instance.cabinet = self.cleaned_data['cabinet']
        
        # Парсим datetime из формы
        if isinstance(start_datetime_str, str):
            naive_dt = datetime.datetime.strptime(start_datetime_str, '%Y-%m-%dT%H:%M')
            # Делаем aware если naive
            if timezone.is_naive(naive_dt):
                instance.start_time = timezone.make_aware(naive_dt)
            else:
                instance.start_time = start_datetime_str
        else:
            instance.start_time = start_datetime_str
        
        # Обновляем end_time при изменении start_time или service_variant
        from .models import SystemSettings
        settings = SystemSettings.get_solo()
        total_duration = instance.service_variant.duration_minutes + settings.buffer_time_minutes
        instance.end_time = instance.start_time + datetime.timedelta(minutes=total_duration)
        
        if commit:
            instance.save()
        return instance

