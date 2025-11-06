#!/usr/bin/env python
"""
Скрипт для создания специалиста и расписания работы.
Запуск: python manage.py shell < create_specialist_schedule.py
или: python create_specialist_schedule.py
"""

import os
import django
from datetime import time

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User, Group
from django.utils.dateparse import parse_time
from booking.models import (
    SystemSettings, CabinetType, Cabinet, Service, 
    ServiceVariant, SpecialistProfile, SpecialistSchedule
)

def create_specialist_and_schedule():
    print("=" * 60)
    print("Создание специалиста и расписания")
    print("=" * 60)
    
    # 1. Проверка/создание базовых данных
    print("\n1. Проверка базовых данных...")
    
    # Группы
    specialist_group, _ = Group.objects.get_or_create(name='Specialist')
    print("  ✓ Группа 'Specialist' готова")
    
    # Настройки системы
    settings, _ = SystemSettings.objects.get_or_create()
    if not hasattr(settings, 'buffer_time_minutes') or settings.buffer_time_minutes == 0:
        settings.buffer_time_minutes = 15
        settings.save()
    print("  ✓ Настройки системы готовы")
    
    # Типы кабинетов
    massaj_type, _ = CabinetType.objects.get_or_create(name='Массажный')
    kosmet_type, _ = CabinetType.objects.get_or_create(name='Косметологический')
    vip_type, _ = CabinetType.objects.get_or_create(name='VIP')
    print("  ✓ Типы кабинетов готовы")
    
    # Кабинеты
    cabinets_created = 0
    cabinets_data = [
        ('Кабинет 1', massaj_type),
        ('Кабинет 2', massaj_type),
        ('Кабинет 3', massaj_type),
        ('Косметологический кабинет 1', kosmet_type),
        ('Косметологический кабинет 2', kosmet_type),
    ]
    
    for name, ct_type in cabinets_data:
        _, created = Cabinet.objects.get_or_create(
            name=name, 
            cabinet_type=ct_type, 
            defaults={'is_active': True}
        )
        if created:
            cabinets_created += 1
    
    if cabinets_created > 0:
        print(f"  ✓ Создано кабинетов: {cabinets_created}")
    else:
        print(f"  ✓ Кабинеты уже существуют")
    
    # Услуги
    massaj_service, _ = Service.objects.get_or_create(
        name='Тайский массаж',
        defaults={'description': 'Классический тайский массаж'}
    )
    if massaj_service.required_cabinet_types.count() == 0:
        massaj_service.required_cabinet_types.add(massaj_type)
    
    kosmet_service, _ = Service.objects.get_or_create(
        name='Уход за лицом',
        defaults={'description': 'Профессиональный уход за лицом'}
    )
    if kosmet_service.required_cabinet_types.count() == 0:
        kosmet_service.required_cabinet_types.add(kosmet_type)
    
    print("  ✓ Услуги готовы")
    
    # Варианты услуг
    service_variants_data = [
        (massaj_service, '60 мин', 60, 2500),
        (massaj_service, '90 мин', 90, 3500),
        (kosmet_service, '60 мин', 60, 3000),
        (kosmet_service, '90 мин', 90, 4500),
    ]
    
    variants_created = 0
    for service, suffix, duration, price in service_variants_data:
        _, created = ServiceVariant.objects.get_or_create(
            service=service,
            name_suffix=suffix,
            defaults={
                'duration_minutes': duration,
                'price': price
            }
        )
        if created:
            variants_created += 1
    
    if variants_created > 0:
        print(f"  ✓ Создано вариантов услуг: {variants_created}")
    
    # 2. Создание специалиста
    print("\n2. Создание специалиста...")
    
    username = 'specialist1'
    
    # Проверяем существование пользователя
    try:
        user = User.objects.get(username=username)
        print(f"  ⚠ Пользователь '{username}' уже существует")
        user_created = False
    except User.DoesNotExist:
        user = User.objects.create_user(
            username=username,
            password='specialist123',
            email='specialist1@example.com',
            first_name='Иван',
            last_name='Иванов'
        )
        user.groups.add(specialist_group)
        print(f"  ✓ Создан пользователь: {username} (пароль: specialist123)")
        user_created = True
    
    # Создание/обновление профиля специалиста
    profile, profile_created = SpecialistProfile.objects.get_or_create(
        user=user,
        defaults={'full_name': 'Иванов Иван Иванович'}
    )
    
    # Добавляем услуги специалисту
    profile.services_can_perform.add(massaj_service, kosmet_service)
    
    if profile_created:
        print(f"  ✓ Создан профиль специалиста: {profile.full_name}")
    else:
        print(f"  ✓ Профиль специалиста уже существует: {profile.full_name}")
    
    # 3. Создание расписания
    print("\n3. Создание расписания работы...")
    
    # Расписание: Пн-Пт с 09:00 до 18:00
    schedule_data = [
        (0, '09:00', '18:00'),  # Понедельник
        (1, '09:00', '18:00'),  # Вторник
        (2, '09:00', '18:00'),  # Среда
        (3, '09:00', '18:00'),  # Четверг
        (4, '09:00', '18:00'),  # Пятница
    ]
    
    schedules_created = 0
    for day_of_week, start_str, end_str in schedule_data:
        start_time = parse_time(start_str)
        end_time = parse_time(end_str)
        
        # Удаляем старое расписание для этого дня, если есть
        SpecialistSchedule.objects.filter(
            specialist=profile,
            day_of_week=day_of_week
        ).delete()
        
        # Создаем новое
        schedule = SpecialistSchedule.objects.create(
            specialist=profile,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time
        )
        schedules_created += 1
        
        day_names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
        print(f"  ✓ Расписание для {day_names[day_of_week]}: {start_str} - {end_str}")
    
    print(f"\n✓ Создано расписаний: {schedules_created}")
    
    # 4. Итоговая статистика
    print("\n" + "=" * 60)
    print("✓ Готово!")
    print("=" * 60)
    print(f"\nДанные для входа:")
    print(f"  Логин: {username}")
    print(f"  Пароль: specialist123")
    print(f"\nСтатистика:")
    print(f"  - Специалистов: {SpecialistProfile.objects.count()}")
    print(f"  - Услуг: {Service.objects.count()}")
    print(f"  - Вариантов услуг: {ServiceVariant.objects.count()}")
    print(f"  - Кабинетов: {Cabinet.objects.count()}")
    print(f"  - Расписаний: {SpecialistSchedule.objects.count()}")
    
    # Проверяем что есть хотя бы один вариант услуги для тестирования
    if ServiceVariant.objects.count() > 0:
        first_variant = ServiceVariant.objects.first()
        print(f"\n✓ Для тестирования можно использовать:")
        print(f"  - Услуга: {first_variant.service.name} ({first_variant.name_suffix})")
        print(f"  - ID варианта услуги: {first_variant.id}")

if __name__ == '__main__':
    create_specialist_and_schedule()

