import re
from django.db import transaction
from django.contrib.auth.models import User, Group
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from config.models import Client, Domain

@api_view(['POST'])
@permission_classes([AllowAny])
def register_tenant(request):
    """
    Публичный эндпоинт для регистрации нового B2B объекта (салона).
    Создает изолированную схему бэкенда, домен, администратора и предустановленные ресурсы.
    """
    name = request.data.get('name', '').strip()
    subdomain = request.data.get('subdomain', '').strip().lower()
    email = request.data.get('email', '').strip()
    password = request.data.get('password', '')
    
    # Ресурсы из мастера онбординга
    cabinets_data = request.data.get('cabinets', [])
    services_data = request.data.get('services', [])

    if not name:
        return Response({'error': 'Название салона обязательно.'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not subdomain:
        return Response({'error': 'Поддомен обязателен.'}, status=status.HTTP_400_BAD_REQUEST)
        
    if not re.match(r'^[a-z0-9-]+$', subdomain):
        return Response({'error': 'Поддомен может содержать только строчные латинские буквы, цифры и дефис.'}, status=status.HTTP_400_BAD_REQUEST)
        
    if subdomain in ['public', 'admin', 'www', 'api', 'demo']:
        return Response({'error': 'Этот поддомен зарезервирован системой.'}, status=status.HTTP_400_BAD_REQUEST)
        
    if not email or not password:
        return Response({'error': 'Учетные данные администратора обязательны.'}, status=status.HTTP_400_BAD_REQUEST)
        
    if len(password) < 6:
        return Response({'error': 'Пароль администратора должен быть не менее 6 символов.'}, status=status.HTTP_400_BAD_REQUEST)

    # Проверка уникальности поддомена
    schema_name = subdomain.replace('-', '_')
    with schema_context('public'):
        if Client.objects.filter(schema_name=schema_name).exists():
            return Response({'error': 'Салон с таким поддоменом уже зарегистрирован.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with schema_context('public'):
            with transaction.atomic():
                # 1. Создаем арендатора (автоматически создает схему PostgreSQL и накатывает миграции)
                tenant = Client(schema_name=schema_name, name=name)
                tenant.save()
                
                # 2. Создаем доменное имя (поддомен)
                domain_name = f"{subdomain}.localhost"
                domain = Domain(domain=domain_name, tenant=tenant, is_primary=True)
                domain.save()
            
        # 3. Инициализируем данные внутри созданной изолированной схемы
        with schema_context(schema_name):
                # Импортируем модели лениво, так как они доступны только в tenant-контексте
                from booking.models import SystemSettings, CabinetType, Cabinet, Service, ServiceVariant, SpecialistProfile
                
                # Создаем группы пользователей
                superadmin_group, _ = Group.objects.get_or_create(name='SuperAdmin')
                admin_group, _ = Group.objects.get_or_create(name='Admin')
                specialist_group, _ = Group.objects.get_or_create(name='Specialist')
                
                # Создаем администратора
                username = email
                admin_user = User.objects.create_superuser(
                    username=username,
                    email=email,
                    password=password
                )
                admin_user.groups.add(superadmin_group, admin_group)
                
                # Создаем SpecialistProfile для администратора
                spec_profile = SpecialistProfile.objects.create(
                    user=admin_user,
                    full_name=name + " Администратор"
                )
                
                # Инициализируем системные настройки
                SystemSettings.objects.create(
                    spa_open_time='09:00',
                    spa_close_time='21:00',
                    buffer_time_minutes=15,
                    send_email_notifications=False
                )
                
                # Создаем типы кабинетов
                massaj_type, _ = CabinetType.objects.get_or_create(name='Массажный')
                kosmet_type, _ = CabinetType.objects.get_or_create(name='Косметологический')
                vip_type, _ = CabinetType.objects.get_or_create(name='VIP')
                
                # Создаем кабинеты из онбординга (или дефолтные)
                if not cabinets_data:
                    cabinets_data = ['Кабинет 1', 'VIP Комната']
                
                for i, cab_name in enumerate(cabinets_data):
                    cab_type = vip_type if 'vip' in cab_name.lower() else massaj_type
                    Cabinet.objects.create(name=cab_name, cabinet_type=cab_type, is_active=True)
                
                # Создаем стандартные услуги из онбординга
                if not services_data:
                    services_data = ['massage', 'facial']
                    
                if 'massage' in services_data:
                    massage_service = Service.objects.create(
                        name='Тайский массаж',
                        description='Классический оздоровительный массаж всего тела'
                    )
                    massage_service.required_cabinet_types.add(massaj_type)
                    spec_profile.services_can_perform.add(massage_service)
                    
                    # Варианты длительности тайского массажа
                    ServiceVariant.objects.create(service=massage_service, name_suffix='60 мин', duration_minutes=60, price=2000)
                    ServiceVariant.objects.create(service=massage_service, name_suffix='90 мин', duration_minutes=90, price=2800)
                    
                if 'facial' in services_data:
                    facial_service = Service.objects.create(
                        name='Уход за лицом',
                        description='Премиальный косметологический уход и очищение'
                    )
                    facial_service.required_cabinet_types.add(kosmet_type)
                    spec_profile.services_can_perform.add(facial_service)
                    
                    # Варианты длительности ухода за лицом
                    ServiceVariant.objects.create(service=facial_service, name_suffix='60 мин', duration_minutes=60, price=2500)
                    ServiceVariant.objects.create(service=facial_service, name_suffix='90 мин', duration_minutes=90, price=3500)

                if 'aromatherapy' in services_data:
                    aroma_service = Service.objects.create(
                        name='Ароматерапия',
                        description='Расслабляющий массаж с использованием эфирных масел'
                    )
                    aroma_service.required_cabinet_types.add(vip_type)
                    spec_profile.services_can_perform.add(aroma_service)
                    
                    # Варианты длительности ароматерапии
                    ServiceVariant.objects.create(service=aroma_service, name_suffix='60 мин', duration_minutes=60, price=3000)
                    ServiceVariant.objects.create(service=aroma_service, name_suffix='90 мин', duration_minutes=90, price=4000)
                    
        return Response({
            'success': True,
            'message': f'Салон «{name}» успешно зарегистрирован!',
            'subdomain': subdomain,
            'domain': domain_name,
            'admin_username': username,
        }, status=status.HTTP_201_CREATED)

    except Exception as exc:
        import logging
        logging.getLogger(__name__).error('Error during tenant registration: %s', exc, exc_info=True)
        return Response({
            'error': f'Внутренняя ошибка сервера при инициализации БД: {exc}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
