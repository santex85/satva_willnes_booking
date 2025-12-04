"""
Формы для бронирования
"""
from django import forms
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_cf_turnstile.fields import TurnstileCaptchaField
from .models import (
    ServiceVariant,
    SpecialistProfile,
    Cabinet,
    SpecialistSchedule,
    Booking,
    BookingSeries,
    CabinetClosure,
)
import datetime
import json


WEEKDAY_CHOICES = [
    (0, 'Понедельник'),
    (1, 'Вторник'),
    (2, 'Среда'),
    (3, 'Четверг'),
    (4, 'Пятница'),
    (5, 'Суббота'),
    (6, 'Воскресенье'),
]


RECURRENCE_END_CHOICES = [
    ('count', 'После количества повторов'),
    ('until', 'До даты'),
]


def _parse_recurrence_excluded_dates(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    value = value.strip()
    if not value:
        return []
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(item) for item in data if item]
    except (json.JSONDecodeError, TypeError):
        pass
    return [part.strip() for part in value.split(',') if part.strip()]


def validate_recurrence(cleaned_data, start_datetime):
    enabled = cleaned_data.get('recurrence_enabled')
    if not enabled:
        return None

    frequency = cleaned_data.get('recurrence_frequency')
    interval = cleaned_data.get('recurrence_interval') or 1
    end_type = cleaned_data.get('recurrence_end_type')
    end_date = cleaned_data.get('recurrence_end_date')
    occurrences = cleaned_data.get('recurrence_occurrences')
    weekdays = cleaned_data.get('recurrence_weekdays') or []
    excluded_raw = cleaned_data.get('recurrence_excluded_dates')
    excluded_dates = _parse_recurrence_excluded_dates(excluded_raw)

    if frequency not in dict(BookingSeries.FREQUENCY_CHOICES):
        raise forms.ValidationError({
            'recurrence_frequency': 'Выберите частоту повторения'
        })

    if interval < 1:
        raise forms.ValidationError({
            'recurrence_interval': 'Интервал должен быть не меньше 1'
        })

    if frequency == BookingSeries.FREQUENCY_WEEKLY:
        weekdays = [int(day) for day in weekdays] or [start_datetime.weekday()]
        if any(day not in range(0, 7) for day in weekdays):
            raise forms.ValidationError({
                'recurrence_weekdays': 'Выберите корректные дни недели'
            })
    else:
        weekdays = []

    max_occurrences = 200
    if end_type == 'count':
        if not occurrences:
            raise forms.ValidationError({
                'recurrence_occurrences': 'Укажите количество повторов'
            })
        if occurrences < 2:
            raise forms.ValidationError({
                'recurrence_occurrences': 'Количество повторов должно быть больше 1'
            })
        if occurrences > max_occurrences:
            raise forms.ValidationError({
                'recurrence_occurrences': f'Количество повторов не может превышать {max_occurrences}'
            })
        end_date = None
    elif end_type == 'until':
        if not end_date:
            raise forms.ValidationError({
                'recurrence_end_date': 'Укажите дату окончания'
            })
        if end_date < start_datetime.date():
            raise forms.ValidationError({
                'recurrence_end_date': 'Дата окончания должна быть позже даты начала'
            })
        if (end_date - start_datetime.date()).days > 365:
            raise forms.ValidationError({
                'recurrence_end_date': 'Диапазон повторов не может превышать один год'
            })
        occurrences = None
    else:
        raise forms.ValidationError({
            'recurrence_end_type': 'Выберите способ завершения повторов'
        })

    parsed_excluded = []
    for iso_value in excluded_dates:
        try:
            parsed_date = datetime.date.fromisoformat(str(iso_value))
        except ValueError:
            raise forms.ValidationError({
                'recurrence_excluded_dates': 'Некорректный формат даты для исключения'
            })
        if parsed_date < start_datetime.date():
            continue
        parsed_excluded.append(parsed_date.isoformat())

    return {
        'frequency': frequency,
        'interval': interval,
        'end_type': end_type,
        'end_date': end_date,
        'occurrences': occurrences,
        'weekdays': weekdays,
        'excluded_dates': parsed_excluded,
    }


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
    recurrence_enabled = forms.BooleanField(
        required=False,
        label='Повторять бронирование',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    recurrence_frequency = forms.ChoiceField(
        choices=BookingSeries.FREQUENCY_CHOICES,
        required=False,
        label='Частота повтора',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    recurrence_interval = forms.IntegerField(
        required=False,
        min_value=1,
        initial=1,
        label='Интервал',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1})
    )
    recurrence_end_type = forms.ChoiceField(
        choices=RECURRENCE_END_CHOICES,
        required=False,
        initial='count',
        label='Окончание повтора',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    recurrence_end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label='Дата окончания'
    )
    recurrence_occurrences = forms.IntegerField(
        required=False,
        min_value=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 2}),
        label='Количество повторов'
    )
    recurrence_weekdays = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='Дни недели'
    )
    recurrence_excluded_dates = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )

    def clean(self):
        cleaned_data = super().clean()
        start_datetime = cleaned_data.get('start_datetime')
        if not start_datetime:
            return cleaned_data

        if isinstance(start_datetime, str):
            parsed = parse_datetime(start_datetime)
            if parsed is None:
                try:
                    parsed = datetime.datetime.strptime(start_datetime[:16], '%Y-%m-%dT%H:%M')
                except ValueError:
                    parsed = None
            start_datetime = parsed

        if start_datetime is None:
            return cleaned_data

        if timezone.is_naive(start_datetime):
            start_datetime = timezone.make_aware(start_datetime)

        recurrence = validate_recurrence(cleaned_data, timezone.localtime(start_datetime))
        cleaned_data['recurrence_payload'] = recurrence
        cleaned_data['start_datetime'] = start_datetime
        return cleaned_data


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
    specialist = forms.ModelChoiceField(
        queryset=SpecialistProfile.objects.all().order_by('full_name'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Специалист',
        empty_label='Все специалисты'
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
    captcha = TurnstileCaptchaField(
        label='Проверка безопасности'
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
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={
                'class': 'form-control',
                'autocomplete': 'off',
                'data-datetime-picker': 'booking-start'
            }
        ),
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
    recurrence_enabled = forms.BooleanField(
        required=False,
        label='Повторять бронирование',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    recurrence_frequency = forms.ChoiceField(
        choices=BookingSeries.FREQUENCY_CHOICES,
        required=False,
        label='Частота повтора',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    recurrence_interval = forms.IntegerField(
        required=False,
        min_value=1,
        initial=1,
        label='Интервал',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1})
    )
    recurrence_end_type = forms.ChoiceField(
        choices=RECURRENCE_END_CHOICES,
        required=False,
        initial='count',
        label='Окончание повтора',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    recurrence_end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label='Дата окончания'
    )
    recurrence_occurrences = forms.IntegerField(
        required=False,
        min_value=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 2}),
        label='Количество повторов'
    )
    recurrence_weekdays = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='Дни недели'
    )
    recurrence_excluded_dates = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    apply_scope = forms.ChoiceField(
        choices=[
            ('single', 'Применить только к этому бронированию'),
            ('series', 'Применить ко всей серии'),
        ],
        required=False,
        widget=forms.RadioSelect,
        label='Применить изменения',
        initial='single'
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
            series = self.instance.series
            if series:
                self.initial['recurrence_enabled'] = True
                self.initial['recurrence_frequency'] = series.frequency
                self.initial['recurrence_interval'] = series.interval
                if series.occurrence_count:
                    self.initial['recurrence_end_type'] = 'count'
                    self.initial['recurrence_occurrences'] = series.occurrence_count
                else:
                    self.initial['recurrence_end_type'] = 'until'
                    self.initial['recurrence_end_date'] = series.end_date
                self.initial['recurrence_weekdays'] = [str(day) for day in (series.weekdays or [])]
                if series.excluded_dates:
                    self.initial['recurrence_excluded_dates'] = json.dumps(series.excluded_dates, ensure_ascii=False)
                self.initial['apply_scope'] = 'single'
            else:
                self.initial['recurrence_enabled'] = False
                self.fields['apply_scope'].widget = forms.HiddenInput()
        else:
            if 'start_datetime' in self.fields:
                self.fields['start_datetime'].initial = timezone.localtime(timezone.now()).strftime('%Y-%m-%dT%H:%M')
            self.fields['apply_scope'].widget = forms.HiddenInput()
    
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
        
        # Проверка конфликтов (исключая текущее бронирование) - только для предупреждения
        from .utils import check_booking_conflicts
        booking_id = self.instance.pk if self.instance else None
        conflicts = check_booking_conflicts(
            start_time=start_time,
            service_variant=service_variant,
            specialist=specialist,
            cabinet=cabinet,
            exclude_booking_id=booking_id
        )
        
        # Сохраняем информацию о конфликтах для предупреждения (не блокируем сохранение)
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
            
            # Сохраняем предупреждение вместо блокировки
            cleaned_data['conflicts'] = conflicts
            cleaned_data['conflicts_warning'] = '; '.join(conflict_messages) if conflict_messages else 'Выбранное время имеет конфликты'

        cleaned_data['start_datetime'] = start_time

        scope = cleaned_data.get('apply_scope') or 'single'
        if scope not in {'single', 'series'}:
            scope = 'single'
        cleaned_data['apply_scope'] = scope

        local_start = timezone.localtime(start_time)
        recurrence = validate_recurrence(cleaned_data, local_start)
        cleaned_data['recurrence_payload'] = recurrence

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


class CabinetClosureForm(forms.ModelForm):
    """Форма создания закрытия кабинета."""

    class Meta:
        model = CabinetClosure
        fields = ['cabinet', 'start_time', 'end_time', 'reason']
        widgets = {
            'cabinet': forms.Select(attrs={'class': 'form-select'}),
            'start_time': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={
                    'class': 'form-control',
                    'autocomplete': 'off',
                    'data-datetime-picker': 'closure-start'
                }
            ),
            'end_time': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={
                    'class': 'form-control',
                    'autocomplete': 'off',
                    'data-datetime-picker': 'closure-end'
                }
            ),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Например: техобслуживание'}),
        }
        labels = {
            'cabinet': 'Кабинет',
            'start_time': 'Начало закрытия',
            'end_time': 'Окончание закрытия',
            'reason': 'Причина',
        }

    def clean(self):
        cleaned_data = super().clean()
        cabinet = cleaned_data.get('cabinet')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        if not all([cabinet, start_time, end_time]):
            return cleaned_data

        if end_time <= start_time:
            raise forms.ValidationError('Окончание закрытия должно быть позже начала.')

        overlap_filter = CabinetClosure.objects.filter(
            cabinet=cabinet,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if self.instance.pk:
            overlap_filter = overlap_filter.exclude(pk=self.instance.pk)
        if overlap_filter.exists():
            raise forms.ValidationError('На выбранный период уже запланировано закрытие кабинета.')

        conflicting_bookings = Booking.objects.filter(
            cabinet=cabinet,
            status='confirmed',
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if conflicting_bookings.exists():
            raise forms.ValidationError(
                'В выбранный период у кабинета есть подтверждённые бронирования. '
                'Перенесите или отмените их перед закрытием.'
            )

        return cleaned_data

