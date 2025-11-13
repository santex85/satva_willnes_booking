from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0005_bookingseries'),
    ]

    operations = [
        migrations.CreateModel(
            name='CabinetClosure',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_time', models.DateTimeField(verbose_name='Начало закрытия')),
                ('end_time', models.DateTimeField(verbose_name='Окончание закрытия')),
                ('reason', models.CharField(blank=True, max_length=255, verbose_name='Причина')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
                ('cabinet', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='closures', to='booking.cabinet', verbose_name='Кабинет')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cabinet_closures', to=settings.AUTH_USER_MODEL, verbose_name='Создано пользователем')),
            ],
            options={
                'verbose_name': 'Закрытие кабинета',
                'verbose_name_plural': 'Закрытия кабинетов',
                'ordering': ['-start_time'],
            },
        ),
        migrations.AddConstraint(
            model_name='cabinetclosure',
            constraint=models.CheckConstraint(check=models.Q(('end_time__gt', models.F('start_time'))), name='cabinetclosure_end_after_start'),
        ),
    ]

