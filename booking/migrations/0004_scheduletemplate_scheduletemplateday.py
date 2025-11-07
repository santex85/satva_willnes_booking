# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0003_systemsettings_send_email_notifications'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScheduleTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Например: "Стандартное полное рабочее время", "Выходные дни"', max_length=200, verbose_name='Название шаблона')),
                ('description', models.TextField(blank=True, help_text='Описание шаблона расписания', verbose_name='Описание')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
            ],
            options={
                'verbose_name': 'Шаблон расписания',
                'verbose_name_plural': 'Шаблоны расписания',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ScheduleTemplateDay',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day_of_week', models.IntegerField(choices=[(0, 'Понедельник'), (1, 'Вторник'), (2, 'Среда'), (3, 'Четверг'), (4, 'Пятница'), (5, 'Суббота'), (6, 'Воскресенье')], verbose_name='День недели')),
                ('start_time', models.TimeField(verbose_name='Начало работы')),
                ('end_time', models.TimeField(verbose_name='Окончание работы')),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='days', to='booking.scheduletemplate', verbose_name='Шаблон')),
            ],
            options={
                'verbose_name': 'День шаблона',
                'verbose_name_plural': 'Дни шаблона',
                'ordering': ['day_of_week'],
                'unique_together': {('template', 'day_of_week')},
            },
        ),
    ]

