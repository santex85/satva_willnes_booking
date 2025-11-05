#!/usr/bin/env python
"""
Скрипт для генерации тестовых данных с бронированиями для системы бронирования.
Запуск: python manage.py shell < generate_test_data.py
или: python generate_test_data.py
"""

import os
import django
from datetime import datetime, timedelta, date, time
import random

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.utils.dateparse import parse_time
from booking.models import (
    SystemSettings, CabinetType, Cabinet, Service,
    ServiceVariant, SpecialistProfile, SpecialistSchedule, Booking
)

def generate_test_data():
    print("=" * 60)
    print("Генерация тестовых данных для системы бронирования")
    print("=" * 60)
    
    # Сначала инициализируем базовые данные
    print("\n1. Инициализация базовых данных...")
    init_basic_data()
    
    # Создаем дополнительные специалисты
    print("\n2. Создание дополнительных специалистов...")
    specialists = create_specialists()
    
    # Создаем графики работы
    print("\n3. Создание графиков работы...")
    create_schedules(specialists)
    
    # Создаем бронирования
    print("\n4. Создание тестовых бронирований...")
    create_bookings(specialists)
    
    print("\n" + "=" * 60)
    print("✓ Генерация тестовых данных завершена успешно!")
    print("=" * 60)
    print("\nСтатистика:")
    print(f"  - Специалистов: {SpecialistProfile.objects.count()}")
    print(f"  - Услуг: {Service.objects.count()}")
    print(f"  - Кабинетов: {Cabinet.objects.count()}")
    print(f"  - Бронирований: {Booking.objects.count()}")
    print(f"  - Подтвержденных: {Booking.objects.filter(status='confirmed').count()}")
    print(f"  - Выполненных: {Booking.objects.filter(status='completed').count()}")
    print(f"  - Отмененных: {Booking.objects.filter(status='canceled').count()}")


def init_basic_data():
    """Инициализация базовых данных (услуги, кабинеты, настройки)"""
    
    # Группы пользователей
    Group.objects.get_or_create(name='SuperAdmin')
    Group.objects.get_or_create(name='Admin')
    Group.objects.get_or_create(name='Specialist')
    
    # Настройки системы
    settings, _ = SystemSettings.objects.get_or_create()
    settings.buffer_time_minutes = 15
    settings.save()
    
    # Типы кабинетов
    massaj_type, _ = CabinetType.objects.get_or_create(name='Массажный')
    kosmet_type, _ = CabinetType.objects.get_or_create(name='Косметологический')
    vip_type, _ = CabinetType.objects.get_or_create(name='VIP')
    
    # Кабинеты
    cabinets_data = [
        ('Кабинет 1', massaj_type),
        ('Кабинет 2', massaj_type),
        ('Кабинет 3', massaj_type),
        ('Косметологический кабинет 1', kosmet_type),
        ('Косметологический кабинет 2', kosmet_type),
        ('VIP Комната 1', vip_type),
        ('VIP Комната 2', vip_type),
    ]
    
    for name, ct_type in cabinets_data:
        Cabinet.objects.get_or_create(name=name, cabinet_type=ct_type, defaults={'is_active': True})
    
    # Услуги
    massaj_service, _ = Service.objects.get_or_create(
        name='Тайский массаж',
        defaults={'description': 'Классический тайский массаж'}
    )
    massaj_service.required_cabinet_types.add(massaj_type)
    
    kosmet_service, _ = Service.objects.get_or_create(
        name='Уход за лицом',
        defaults={'description': 'Профессиональный уход за лицом'}
    )
    kosmet_service.required_cabinet_types.add(kosmet_type)
    
    facial_service, _ = Service.objects.get_or_create(
        name='Массаж лица',
        defaults={'description': 'Омолаживающий массаж лица'}
    )
    facial_service.required_cabinet_types.add(kosmet_type)
    
    vip_service, _ = Service.objects.get_or_create(
        name='VIP Комплекс',
        defaults={'description': 'Эксклюзивный VIP комплекс услуг'}
    )
    vip_service.required_cabinet_types.add(vip_type)
    
    # Варианты услуг
    service_variants_data = [
        (massaj_service, '60 мин', 60, 2000),
        (massaj_service, '90 мин', 90, 2800),
        (massaj_service, '120 мин', 120, 3500),
        (kosmet_service, '60 мин', 60, 2500),
        (kosmet_service, '90 мин', 90, 3500),
        (facial_service, '45 мин', 45, 1800),
        (vip_service, '120 мин', 120, 5000),
        (vip_service, '180 мин', 180, 7000),
    ]
    
    for service, suffix, duration, price in service_variants_data:
        ServiceVariant.objects.get_or_create(
            service=service,
            name_suffix=suffix,
            defaults={
                'duration_minutes': duration,
                'price': price
            }
        )


def create_specialists():
    """Создание специалистов"""
    specialists = []
    
    # Получаем услуги
    massaj_service = Service.objects.get(name='Тайский массаж')
    kosmet_service = Service.objects.get(name='Уход за лицом')
    facial_service = Service.objects.get(name='Массаж лица')
    vip_service = Service.objects.get(name='VIP Комплекс')
    
    specialist_group = Group.objects.get(name='Specialist')
    
    specialists_data = [
        {
            'username': 'specialist1',
            'password': 'specialist123',
            'full_name': 'Иванов Иван Иванович',
            'email': 'ivanov@example.com',
            'services': [massaj_service]
        },
        {
            'username': 'specialist2',
            'password': 'specialist123',
            'full_name': 'Петрова Мария Сергеевна',
            'email': 'petrova@example.com',
            'services': [kosmet_service, facial_service]
        },
        {
            'username': 'specialist3',
            'password': 'specialist123',
            'full_name': 'Сидоров Петр Александрович',
            'email': 'sidorov@example.com',
            'services': [massaj_service]
        },
        {
            'username': 'specialist4',
            'password': 'specialist123',
            'full_name': 'Козлова Анна Владимировна',
            'email': 'kozlova@example.com',
            'services': [kosmet_service, facial_service]
        },
        {
            'username': 'specialist5',
            'password': 'specialist123',
            'full_name': 'VIP Мастер',
            'email': 'vip@example.com',
            'services': [vip_service, massaj_service]
        },
    ]
    
    for spec_data in specialists_data:
        user, created = User.objects.get_or_create(
            username=spec_data['username'],
            defaults={
                'email': spec_data['email']
            }
        )
        if created:
            user.set_password(spec_data['password'])
            user.save()
            user.groups.add(specialist_group)
            print(f"  ✓ Создан пользователь: {spec_data['username']}")
        
        profile, created = SpecialistProfile.objects.get_or_create(
            user=user,
            defaults={'full_name': spec_data['full_name']}
        )
        if created:
            for service in spec_data['services']:
                profile.services_can_perform.add(service)
            print(f"  ✓ Создан профиль: {spec_data['full_name']}")
        else:
            # Обновляем услуги если профиль уже существует
            for service in spec_data['services']:
                profile.services_can_perform.add(service)
        
        specialists.append(profile)
    
    return specialists


def create_schedules(specialists):
    """Создание графиков работы для специалистов"""
    schedule_data = [
        (0, '09:00', '18:00'),  # Понедельник
        (1, '09:00', '18:00'),  # Вторник
        (2, '09:00', '18:00'),  # Среда
        (3, '09:00', '18:00'),  # Четверг
        (4, '09:00', '18:00'),  # Пятница
        (5, '10:00', '16:00'),  # Суббота (некоторые специалисты)
    ]
    
    for specialist in specialists:
        for day, start, end in schedule_data:
            # Некоторые специалисты не работают в субботу
            if day == 5 and random.random() > 0.5:
                continue
            
            SpecialistSchedule.objects.get_or_create(
                specialist=specialist,
                day_of_week=day,
                defaults={
                    'start_time': parse_time(start),
                    'end_time': parse_time(end),
                }
            )


def create_bookings(specialists):
    """Создание тестовых бронирований"""
    
    # Получаем все услуги и варианты
    service_variants = list(ServiceVariant.objects.all())
    cabinets = list(Cabinet.objects.filter(is_active=True))
    
    if not service_variants or not cabinets:
        print("  ⚠ Нет услуг или кабинетов для создания бронирований")
        return
    
    # Получаем суперпользователя для created_by
    try:
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = User.objects.first()
    except:
        admin_user = None
    
    # Генерируем бронирования за последние 30 дней и на следующие 14 дней
    today = date.today()
    start_date = today - timedelta(days=30)
    end_date = today + timedelta(days=14)
    
    guest_names = [
        'Иванов Иван', 'Петрова Мария', 'Сидоров Петр', 'Козлова Анна',
        'Смирнов Алексей', 'Федорова Елена', 'Морозов Дмитрий', 'Новикова Ольга',
        'Волков Сергей', 'Лебедева Татьяна', 'Соколов Андрей', 'Павлова Юлия',
        'Попов Максим', 'Васильева Наталья', 'Семенов Игорь', 'Михайлова Екатерина',
        'Фролов Владимир', 'Николаева Светлана', 'Орлов Роман', 'Захарова Анастасия',
    ]
    
    room_numbers = ['101', '102', '103', '201', '202', '203', '301', '302', 'VIP-1', 'VIP-2']
    
    statuses = ['confirmed', 'completed', 'canceled']
    status_weights = [0.7, 0.2, 0.1]  # 70% confirmed, 20% completed, 10% canceled
    
    bookings_created = 0
    current_date = start_date
    
    while current_date <= end_date:
        # Пропускаем выходные (суббота и воскресенье)
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        
        # Генерируем 2-5 бронирований в день
        num_bookings = random.randint(2, 5)
        
        for _ in range(num_bookings):
            # Выбираем случайного специалиста
            specialist = random.choice(specialists)
            
            # Выбираем услугу, которую может выполнять специалист
            available_services = list(specialist.services_can_perform.all())
            if not available_services:
                continue
            
            service = random.choice(available_services)
            available_variants = [sv for sv in service_variants if sv.service == service]
            if not available_variants:
                continue
            
            service_variant = random.choice(available_variants)
            
            # Выбираем кабинет нужного типа
            required_types = list(service.required_cabinet_types.all())
            available_cabinets = [c for c in cabinets if c.cabinet_type in required_types]
            if not available_cabinets:
                continue
            
            cabinet = random.choice(available_cabinets)
            
            # Выбираем время (9:00 - 17:00)
            hour = random.randint(9, 17)
            minute = random.choice([0, 15, 30, 45])
            start_time_dt = timezone.make_aware(
                datetime.combine(current_date, time(hour, minute))
            )
            
            # Проверяем, не пересекается ли с существующими бронированиями
            duration = service_variant.duration_minutes
            settings = SystemSettings.get_solo()
            total_duration = duration + settings.buffer_time_minutes
            end_time_dt = start_time_dt + timedelta(minutes=total_duration)
            
            # Проверка конфликтов
            conflicting = Booking.objects.filter(
                specialist=specialist,
                start_time__lt=end_time_dt,
                end_time__gt=start_time_dt,
                status__in=['confirmed', 'completed']
            ).exists()
            
            if conflicting:
                continue
            
            # Выбираем статус в зависимости от даты
            if current_date < today:
                # Прошлые бронирования - большинство выполнены
                status = random.choices(statuses, weights=[0.2, 0.7, 0.1])[0]
            elif current_date == today:
                # Сегодня - все подтверждены
                status = 'confirmed'
            else:
                # Будущие - все подтверждены
                status = 'confirmed'
            
            # Создаем бронирование
            guest_name = random.choice(guest_names)
            guest_room = random.choice(room_numbers) if random.random() > 0.2 else ''
            
            booking = Booking.objects.create(
                guest_name=guest_name,
                guest_room_number=guest_room,
                service_variant=service_variant,
                specialist=specialist,
                cabinet=cabinet,
                start_time=start_time_dt,
                created_by=admin_user,
                status=status
            )
            
            bookings_created += 1
        
        current_date += timedelta(days=1)
    
    print(f"  ✓ Создано {bookings_created} бронирований")
    print(f"    - За период: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}")


if __name__ == '__main__':
    try:
        generate_test_data()
    except Exception as e:
        import traceback
        print(f"\n❌ Ошибка при генерации данных:")
        print(traceback.format_exc())


