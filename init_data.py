#!/usr/bin/env python
"""
Скрипт для инициализации базовых данных в системе бронирования.
Запуск: python manage.py shell < init_data.py
"""

import os
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User, Group
from booking.models import (
    SystemSettings, CabinetType, Cabinet, Service, 
    ServiceVariant, SpecialistProfile, SpecialistSchedule
)

def init_data():
    print("Инициализация данных системы бронирования...")
    
    # Создание групп пользователей
    print("Создание групп пользователей...")
    superadmin_group, _ = Group.objects.get_or_create(name='SuperAdmin')
    admin_group, _ = Group.objects.get_or_create(name='Admin')
    specialist_group, _ = Group.objects.get_or_create(name='Specialist')
    print("✓ Группы созданы")
    
    # Проверка SystemSettings
    print("Проверка настроек системы...")
    settings, _ = SystemSettings.objects.get_or_create()
    if not _:
        print("  Настройки уже существуют")
    else:
        print("✓ Настройки созданы")
    
    # Создание типов кабинетов
    print("Создание типов кабинетов...")
    cabinet_types_data = [
        'Массажный',
        'Косметологический',
        'VIP',
    ]
    
    for ct_name in cabinet_types_data:
        ct, created = CabinetType.objects.get_or_create(name=ct_name)
        if created:
            print(f"  ✓ Создан тип: {ct_name}")
    
    # Создание кабинетов
    print("Создание кабинетов...")
    massaj_type = CabinetType.objects.get(name='Массажный')
    kosmet_type = CabinetType.objects.get(name='Косметологический')
    vip_type = CabinetType.objects.get(name='VIP')
    
    cabinets_data = [
        ('Кабинет 1', massaj_type),
        ('Кабинет 2', massaj_type),
        ('Косметологический кабинет', kosmet_type),
        ('VIP Комната', vip_type),
    ]
    
    for name, ct_type in cabinets_data:
        cab, created = Cabinet.objects.get_or_create(name=name, cabinet_type=ct_type)
        if created:
            print(f"  ✓ Создан кабинет: {name}")
    
    # Создание услуг
    print("Создание услуг...")
    massaj_service, created = Service.objects.get_or_create(
        name='Тайский массаж',
        defaults={'description': 'Классический тайский массаж'}
    )
    if created:
        massaj_service.required_cabinet_types.add(massaj_type)
        print(f"  ✓ Создана услуга: Тайский массаж")
    
    kosmet_service, created = Service.objects.get_or_create(
        name='Уход за лицом',
        defaults={'description': 'Профессиональный уход за лицом'}
    )
    if created:
        kosmet_service.required_cabinet_types.add(kosmet_type)
        print(f"  ✓ Создана услуга: Уход за лицом")
    
    # Создание вариантов услуг
    print("Создание вариантов услуг...")
    service_variants_data = [
        (massaj_service, '60 мин', 60, 2000),
        (massaj_service, '90 мин', 90, 2800),
        (kosmet_service, '60 мин', 60, 2500),
        (kosmet_service, '90 мин', 90, 3500),
    ]
    
    for service, suffix, duration, price in service_variants_data:
        sv, created = ServiceVariant.objects.get_or_create(
            service=service,
            name_suffix=suffix,
            defaults={
                'duration_minutes': duration,
                'price': price
            }
        )
        if created:
            print(f"  ✓ Создан вариант: {service.name} - {suffix}")
    
    # Создание тестового специалиста
    print("Создание профилей специалистов...")
    # Проверяем, есть ли пользователь specialist1
    try:
        specialist_user = User.objects.get(username='specialist1')
    except User.DoesNotExist:
        specialist_user = User.objects.create_user(
            username='specialist1',
            password='specialist123',
            email='specialist1@example.com'
        )
        print(f"  ✓ Создан пользователь: specialist1")
    
    spec_profile, created = SpecialistProfile.objects.get_or_create(
        user=specialist_user,
        defaults={'full_name': 'Иванов Иван Иванович'}
    )
    if created:
        spec_profile.services_can_perform.add(massaj_service)
        print(f"  ✓ Создан профиль специалиста: {spec_profile.full_name}")
    
    # Создание графика работы
    print("Создание графиков работы...")
    schedule_data = [
        (0, '09:00', '18:00'),  # Понедельник
        (1, '09:00', '18:00'),  # Вторник
        (2, '09:00', '18:00'),  # Среда
        (3, '09:00', '18:00'),  # Четверг
        (4, '09:00', '18:00'),  # Пятница
    ]
    
    from django.utils.dateparse import parse_time
    
    for day, start, end in schedule_data:
        schedule, created = SpecialistSchedule.objects.get_or_create(
            specialist=spec_profile,
            day_of_week=day,
            defaults={
                'start_time': parse_time(start),
                'end_time': parse_time(end),
            }
        )
        if created:
            day_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
            print(f"  ✓ Создан график: {day_names[day]} {start}-{end}")
    
    print("\n✓ Инициализация данных завершена успешно!")
    print("\nДанные для входа:")
    print("  SuperAdmin: superadmin / admin123")
    print("  Specialist: specialist1 / specialist123")

if __name__ == '__main__':
    init_data()


