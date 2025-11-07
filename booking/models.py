from django.db import models
from django.contrib.auth.models import User
from solo.models import SingletonModel
from datetime import timedelta


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
