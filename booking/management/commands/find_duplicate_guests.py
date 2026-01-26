"""
Команда для поиска потенциальных дублей среди гостей.

Использование:
    python manage.py find_duplicate_guests
    python manage.py find_duplicate_guests --threshold 0.9
    python manage.py find_duplicate_guests --output duplicates.json
"""
import json
from django.core.management.base import BaseCommand
from django.db.models import Count
from booking.models import Guest
from booking.guest_utils import find_duplicate_groups, calculate_similarity


class Command(BaseCommand):
    help = 'Находит потенциальные дубли среди гостей'

    def add_arguments(self, parser):
        parser.add_argument(
            '--threshold',
            type=float,
            default=0.85,
            help='Минимальный порог схожести (0.0 - 1.0). По умолчанию: 0.85'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Путь к JSON файлу для сохранения результатов'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Подробный вывод'
        )

    def handle(self, *args, **options):
        threshold = options['threshold']
        output_file = options.get('output')
        verbose = options.get('verbose', False)
        
        self.stdout.write(self.style.SUCCESS('Поиск дублей среди гостей...'))
        self.stdout.write(f'Порог схожести: {threshold}')
        self.stdout.write('')
        
        # Получаем статистику
        total_guests = Guest.objects.count()
        self.stdout.write(f'Всего гостей в базе: {total_guests}')
        
        if total_guests == 0:
            self.stdout.write(self.style.WARNING('В базе нет гостей'))
            return
        
        # Ищем группы дублей
        duplicate_groups = find_duplicate_groups(threshold=threshold)
        
        if not duplicate_groups:
            self.stdout.write(self.style.SUCCESS('Дублей не найдено!'))
            return
        
        # Выводим результаты
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(f'Найдено групп дублей: {len(duplicate_groups)}'))
        self.stdout.write('')
        
        total_duplicates = 0
        total_bookings_in_duplicates = 0
        results = []
        
        for idx, group in enumerate(duplicate_groups, 1):
            primary = group['primary']
            duplicates = group['duplicates']
            total_bookings = group['total_bookings']
            
            total_duplicates += len(duplicates)
            total_bookings_in_duplicates += total_bookings
            
            self.stdout.write(self.style.WARNING(f'Группа {idx}:'))
            self.stdout.write(f'  Основной: {primary.display_name} (ID: {primary.id})')
            self.stdout.write(f'    Нормализованное: {primary.normalized_name}')
            self.stdout.write(f'    Бронирований: {primary.booking_count}')
            
            for dup in duplicates:
                similarity = calculate_similarity(primary.display_name, dup.display_name)
                self.stdout.write(f'  Дубль: {dup.display_name} (ID: {dup.id})')
                self.stdout.write(f'    Нормализованное: {dup.normalized_name}')
                self.stdout.write(f'    Бронирований: {dup.booking_count}')
                self.stdout.write(f'    Схожесть: {similarity:.2%}')
            
            self.stdout.write(f'  Всего бронирований в группе: {total_bookings}')
            self.stdout.write('')
            
            # Сохраняем для JSON
            results.append({
                'primary': {
                    'id': primary.id,
                    'display_name': primary.display_name,
                    'normalized_name': primary.normalized_name,
                    'booking_count': primary.booking_count,
                },
                'duplicates': [
                    {
                        'id': dup.id,
                        'display_name': dup.display_name,
                        'normalized_name': dup.normalized_name,
                        'booking_count': dup.booking_count,
                        'similarity': calculate_similarity(primary.display_name, dup.display_name),
                    }
                    for dup in duplicates
                ],
                'total_bookings': total_bookings,
            })
        
        # Итоговая статистика
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Итоговая статистика:'))
        self.stdout.write(f'  Всего гостей: {total_guests}')
        self.stdout.write(f'  Групп дублей: {len(duplicate_groups)}')
        self.stdout.write(f'  Гостей-дублей: {total_duplicates}')
        self.stdout.write(f'  Бронирований в дублях: {total_bookings_in_duplicates}')
        self.stdout.write('')
        
        # Сохраняем в JSON, если указан файл
        if output_file:
            output_data = {
                'threshold': threshold,
                'total_guests': total_guests,
                'duplicate_groups_count': len(duplicate_groups),
                'total_duplicates': total_duplicates,
                'groups': results,
            }
            
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)
                self.stdout.write(self.style.SUCCESS(f'Результаты сохранены в: {output_file}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Ошибка при сохранении: {e}'))
        
        if verbose:
            self.stdout.write('')
            self.stdout.write('Для объединения дублей используйте админ-панель:')
            self.stdout.write('  /admin/booking/guest/merge-duplicates/')
