from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0004_scheduletemplate_scheduletemplateday'),
    ]

    operations = [
        migrations.CreateModel(
            name='BookingSeries',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_time', models.DateTimeField(verbose_name='Начало серии')),
                ('frequency', models.CharField(choices=[('daily', 'Каждый день'), ('weekly', 'Каждую неделю'), ('monthly', 'Каждый месяц'), ('yearly', 'Каждый год')], max_length=20, verbose_name='Частота')),
                ('interval', models.PositiveIntegerField(default=1, verbose_name='Интервал повторов')),
                ('end_date', models.DateField(blank=True, null=True, verbose_name='Дата окончания')),
                ('occurrence_count', models.PositiveIntegerField(blank=True, null=True, verbose_name='Количество повторений')),
                ('weekdays', models.JSONField(blank=True, default=list, verbose_name='Дни недели (для еженедельных повторов)')),
                ('excluded_dates', models.JSONField(blank=True, default=list, verbose_name='Исключенные даты')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='booking_series', to=settings.AUTH_USER_MODEL, verbose_name='Создано пользователем')),
            ],
            options={
                'verbose_name': 'Серия бронирований',
                'verbose_name_plural': 'Серии бронирований',
            },
        ),
        migrations.AddField(
            model_name='booking',
            name='sequence',
            field=models.PositiveIntegerField(default=1, verbose_name='Порядок в серии'),
        ),
        migrations.AddField(
            model_name='booking',
            name='series',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to='booking.bookingseries', verbose_name='Серия'),
        ),
    ]

