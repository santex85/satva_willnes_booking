from django.db import models
from django.contrib.auth.models import User
from solo.models import SingletonModel
from datetime import timedelta
from django.utils import timezone
import calendar


class SystemSettings(SingletonModel):
    """Глобальные настройки системы"""
    spa_open_time = models.TimeField(default='09:00', verbose_name='Время открытия')
    spa_close_time = models.TimeField(default='21:00', verbose_name='Время закрытия')
    buffer_time_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Время на уборку (в минутах) между бронями.",
        verbose_name='Буферное время (мин)'
    )
    send_email_notifications = models.BooleanField(
        default=True,
        help_text="Отправлять email-уведомления специалистам о новых бронированиях",
        verbose_name='Email уведомления'
    )
    enable_booking_copy_shortcuts = models.BooleanField(
        default=True,
        help_text="Разрешить копирование/вставку бронирований с помощью горячих клавиш на календаре",
        verbose_name='Горячие клавиши копирования брони'
    )

    class Meta:
        verbose_name = 'Настройки системы'
        verbose_name_plural = 'Настройки системы'

    def __str__(self):
        return 'Настройки системы'


class CabinetType(models.Model):
    """Тип кабинета"""
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Напр., 'Массажный', 'Косметологический'",
        verbose_name='Название'
    )

    class Meta:
        verbose_name = 'Тип кабинета'
        verbose_name_plural = 'Типы кабинетов'

    def __str__(self):
        return self.name


class Cabinet(models.Model):
    """Кабинет"""
    name = models.CharField(
        max_length=100,
        help_text="Напр., 'Кабинет 1', 'VIP Комната'",
        verbose_name='Название'
    )
    cabinet_type = models.ForeignKey(
        CabinetType,
        on_delete=models.PROTECT,
        related_name='cabinets',
        verbose_name='Тип кабинета'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    class Meta:
        verbose_name = 'Кабинет'
        verbose_name_plural = 'Кабинеты'

    def __str__(self):
        return self.name


class Service(models.Model):
    """Услуга"""
    name = models.CharField(
        max_length=200,
        help_text="Напр., 'Тайский массаж'",
        verbose_name='Название'
    )
    description = models.TextField(blank=True, verbose_name='Описание')
    required_cabinet_types = models.ManyToManyField(
        CabinetType,
        help_text="Какие типы кабинетов нужны для этой услуги.",
        verbose_name='Требуемые типы кабинетов'
    )

    class Meta:
        verbose_name = 'Услуга'
        verbose_name_plural = 'Услуги'

    def __str__(self):
        return self.name


class ServiceVariant(models.Model):
    """Вариант услуги"""
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='variants',
        verbose_name='Услуга'
    )
    name_suffix = models.CharField(
        max_length=100,
        help_text="Напр., '60 мин', '90 мин', 'Интенсив'",
        verbose_name='Суффикс названия'
    )
    duration_minutes = models.PositiveIntegerField(verbose_name='Длительность (мин)')
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Цена'
    )

    class Meta:
        verbose_name = 'Вариант услуги'
        verbose_name_plural = 'Варианты услуг'

    def __str__(self):
        return f"{self.service.name} - {self.name_suffix}"


class SpecialistProfile(models.Model):
    """Профиль специалиста"""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        help_text="Аккаунт для входа в систему.",
        verbose_name='Пользователь'
    )
    full_name = models.CharField(max_length=200, verbose_name='Полное имя')
    services_can_perform = models.ManyToManyField(
        Service,
        help_text="Какие услуги может выполнять этот специалист.",
        verbose_name='Может выполнять услуги'
    )

    class Meta:
        verbose_name = 'Профиль специалиста'
        verbose_name_plural = 'Профили специалистов'

    def __str__(self):
        return self.full_name


class SpecialistSchedule(models.Model):
    """График работы специалиста"""
    DAYS_OF_WEEK = [
        (0, 'Понедельник'),
        (1, 'Вторник'),
        (2, 'Среда'),
        (3, 'Четверг'),
        (4, 'Пятница'),
        (5, 'Суббота'),
        (6, 'Воскресенье'),
    ]

    specialist = models.ForeignKey(
        SpecialistProfile,
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name='Специалист'
    )
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK, verbose_name='День недели')
    start_time = models.TimeField(verbose_name='Начало работы')
    end_time = models.TimeField(verbose_name='Окончание работы')

    class Meta:
        verbose_name = 'График работы'
        verbose_name_plural = 'Графики работы'
        unique_together = ('specialist', 'day_of_week')

    def __str__(self):
        day_name = dict(self.DAYS_OF_WEEK)[self.day_of_week]
        return f"{self.specialist.full_name} - {day_name} ({self.start_time}-{self.end_time})"


class ScheduleTemplate(models.Model):
    """Шаблон расписания для применения к специалистам"""
    name = models.CharField(
        max_length=200,
        verbose_name='Название шаблона',
        help_text='Например: "Стандартное полное рабочее время", "Выходные дни"'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Описание',
        help_text='Описание шаблона расписания'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Создано'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Обновлено'
    )

    class Meta:
        verbose_name = 'Шаблон расписания'
        verbose_name_plural = 'Шаблоны расписания'
        ordering = ['name']

    def __str__(self):
        return self.name

    def apply_to_specialist(self, specialist):
        """
        Применить шаблон к специалисту.
        Создает или обновляет записи SpecialistSchedule для дней, указанных в шаблоне.
        """
        for template_day in self.days.all():
            schedule, created = SpecialistSchedule.objects.update_or_create(
                specialist=specialist,
                day_of_week=template_day.day_of_week,
                defaults={
                    'start_time': template_day.start_time,
                    'end_time': template_day.end_time,
                }
            )
        return self.days.count()


class ScheduleTemplateDay(models.Model):
    """День недели в шаблоне расписания"""
    DAYS_OF_WEEK = SpecialistSchedule.DAYS_OF_WEEK

    template = models.ForeignKey(
        ScheduleTemplate,
        on_delete=models.CASCADE,
        related_name='days',
        verbose_name='Шаблон'
    )
    day_of_week = models.IntegerField(
        choices=DAYS_OF_WEEK,
        verbose_name='День недели'
    )
    start_time = models.TimeField(verbose_name='Начало работы')
    end_time = models.TimeField(verbose_name='Окончание работы')

    class Meta:
        verbose_name = 'День шаблона'
        verbose_name_plural = 'Дни шаблона'
        unique_together = ('template', 'day_of_week')
        ordering = ['day_of_week']

    def __str__(self):
        day_name = dict(self.DAYS_OF_WEEK)[self.day_of_week]
        return f"{self.template.name} - {day_name} ({self.start_time}-{self.end_time})"


class BookingSeries(models.Model):
    """Правило для повторяющихся бронирований"""

    FREQUENCY_DAILY = 'daily'
    FREQUENCY_WEEKLY = 'weekly'
    FREQUENCY_MONTHLY = 'monthly'
    FREQUENCY_YEARLY = 'yearly'

    FREQUENCY_CHOICES = [
        (FREQUENCY_DAILY, 'Каждый день'),
        (FREQUENCY_WEEKLY, 'Каждую неделю'),
        (FREQUENCY_MONTHLY, 'Каждый месяц'),
        (FREQUENCY_YEARLY, 'Каждый год'),
    ]

    start_time = models.DateTimeField(verbose_name='Начало серии')
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, verbose_name='Частота')
    interval = models.PositiveIntegerField(default=1, verbose_name='Интервал повторов')
    end_date = models.DateField(null=True, blank=True, verbose_name='Дата окончания')
    occurrence_count = models.PositiveIntegerField(null=True, blank=True, verbose_name='Количество повторений')
    weekdays = models.JSONField(default=list, blank=True, verbose_name='Дни недели (для еженедельных повторов)')
    excluded_dates = models.JSONField(default=list, blank=True, verbose_name='Исключенные даты')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='booking_series',
        verbose_name='Создано пользователем'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Серия бронирований'
        verbose_name_plural = 'Серии бронирований'

    def __str__(self):
        return f"Серия #{self.id} ({self.get_frequency_display()})"

    def add_exception(self, date_obj):
        iso_date = date_obj.isoformat()
        if iso_date not in self.excluded_dates:
            self.excluded_dates.append(iso_date)
            self.save(update_fields=['excluded_dates'])

    def remove_exception(self, date_obj):
        iso_date = date_obj.isoformat()
        if iso_date in self.excluded_dates:
            self.excluded_dates.remove(iso_date)
            self.save(update_fields=['excluded_dates'])

    def _add_months(self, dt, months):
        month = dt.month - 1 + months
        year = dt.year + month // 12
        month = month % 12 + 1
        day = min(dt.day, calendar.monthrange(year, month)[1])
        return dt.replace(year=year, month=month, day=day)

    def _add_years(self, dt, years):
        try:
            return dt.replace(year=dt.year + years)
        except ValueError:
            # 29 февраля в невисокосный год -> 28 февраля
            return dt.replace(month=2, day=28, year=dt.year + years)

    def generate_datetimes(self, *, from_datetime=None):
        """
        Генерирует список дат начала для серии.
        Возвращает список aware datetime. Использует настройки окончания.
        """
        if not from_datetime:
            current = timezone.localtime(self.start_time) if timezone.is_aware(self.start_time) else self.start_time
        else:
            current = from_datetime

        tz = timezone.get_current_timezone()
        if timezone.is_naive(current):
            current = timezone.make_aware(current, tz)

        occurrences = []
        excluded = set(self.excluded_dates or [])
        remaining = self.occurrence_count
        frequency = self.frequency
        interval = max(1, self.interval or 1)
        weekdays = sorted(set(self.weekdays or []))

        def add_occurrence(dt):
            local_dt = timezone.localtime(dt)
            if local_dt.date().isoformat() in excluded:
                return False
            occurrences.append(dt)
            return True

        if frequency == self.FREQUENCY_WEEKLY and not weekdays:
            weekdays = [current.weekday()]

        while True:
            if remaining is not None and remaining <= 0:
                break

            if self.end_date and timezone.localtime(current).date() > self.end_date:
                break

            # Для еженедельных повторов с несколькими днями
            if frequency == self.FREQUENCY_WEEKLY and len(weekdays) > 1:
                week_start = current - timedelta(days=current.weekday())
                for weekday in weekdays:
                    candidate = week_start + timedelta(days=weekday)
                    candidate = candidate.replace(hour=current.hour, minute=current.minute, second=current.second, microsecond=current.microsecond)
                    if candidate < current:
                        continue
                    candidate = candidate.astimezone(tz) if timezone.is_aware(self.start_time) else timezone.make_aware(candidate, tz)
                    if self.end_date and timezone.localtime(candidate).date() > self.end_date:
                        continue
                    if add_occurrence(candidate):
                        if remaining is not None:
                            remaining -= 1
                            if remaining <= 0:
                                break
                current = current + timedelta(weeks=interval)
                continue

            if add_occurrence(current):
                if remaining is not None:
                    remaining -= 1

            if remaining is not None and remaining <= 0:
                break

            if frequency == self.FREQUENCY_DAILY:
                current = current + timedelta(days=interval)
            elif frequency == self.FREQUENCY_WEEKLY:
                current = current + timedelta(weeks=interval)
            elif frequency == self.FREQUENCY_MONTHLY:
                current = self._add_months(current, interval)
            elif frequency == self.FREQUENCY_YEARLY:
                current = self._add_years(current, interval)
            else:
                break

        return occurrences


class Booking(models.Model):
    """Бронирование"""
    STATUS_CHOICES = [
        ('confirmed', 'Подтверждено'),
        ('paid', 'Оплачено'),
        ('completed', 'Выполнено'),
        ('canceled', 'Отменено'),
    ]

    guest_name = models.CharField(max_length=200, verbose_name='Имя гостя')
    guest_room_number = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Номер комнаты гостя'
    )
    service_variant = models.ForeignKey(
        ServiceVariant,
        on_delete=models.PROTECT,
        verbose_name='Вариант услуги'
    )
    specialist = models.ForeignKey(
        SpecialistProfile,
        on_delete=models.PROTECT,
        verbose_name='Специалист'
    )
    cabinet = models.ForeignKey(
        Cabinet,
        on_delete=models.PROTECT,
        verbose_name='Кабинет'
    )
    start_time = models.DateTimeField(verbose_name='Время начала')
    end_time = models.DateTimeField(
        editable=False,
        help_text="Рассчитывается автоматически: start_time + duration + buffer.",
        verbose_name='Время окончания'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_bookings',
        verbose_name='Создано пользователем'
    )
    series = models.ForeignKey(
        BookingSeries,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='bookings',
        verbose_name='Серия'
    )
    sequence = models.PositiveIntegerField(default=1, verbose_name='Порядок в серии')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='confirmed',
        verbose_name='Статус'
    )

    class Meta:
        verbose_name = 'Бронирование'
        verbose_name_plural = 'Бронирования'
        ordering = ['start_time']

    def __str__(self):
        return f"{self.guest_name} - {self.service_variant} ({self.start_time})"

    def save(self, *args, **kwargs):
        """Рассчитываем end_time автоматически"""
        settings = SystemSettings.get_solo()
        total_duration = self.service_variant.duration_minutes + settings.buffer_time_minutes
        self.end_time = self.start_time + timedelta(minutes=total_duration)
        super().save(*args, **kwargs)


class CabinetClosure(models.Model):
    """Запланированное закрытие кабинета на период."""

    cabinet = models.ForeignKey(
        Cabinet,
        on_delete=models.CASCADE,
        related_name='closures',
        verbose_name='Кабинет'
    )
    start_time = models.DateTimeField(verbose_name='Начало закрытия')
    end_time = models.DateTimeField(verbose_name='Окончание закрытия')
    reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Причина'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cabinet_closures',
        verbose_name='Создано пользователем'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Закрытие кабинета'
        verbose_name_plural = 'Закрытия кабинетов'
        ordering = ['-start_time']
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')),
                name='cabinetclosure_end_after_start'
            )
        ]

    def __str__(self):
        start = timezone.localtime(self.start_time).strftime('%d.%m.%Y %H:%M')
        end = timezone.localtime(self.end_time).strftime('%d.%m.%Y %H:%M')
        return f"{self.cabinet.name}: {start} — {end}"
