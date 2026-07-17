"""
Бэкфилл нормализованных гостей из legacy-поля guest_name.

Находит все бронирования без привязки к Guest (guest IS NULL), но с заполненным
текстовым guest_name, создаёт (или переиспользует) записи Guest по
нормализованному имени и привязывает к ним бронирования. После этого слияние
дублей (эндпоинт /api/v1/guests/merge/ и страница отчётов) начинает работать
для таких записей.

Использование:

    python manage.py backfill_guests --dry-run   # предпросмотр без записи
    python manage.py backfill_guests             # применить
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from booking.models import Booking, Guest
from booking.guest_utils import normalize_guest_name


class Command(BaseCommand):
    help = 'Создаёт Guest из legacy guest_name и привязывает к ним бронирования'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать, что будет сделано, без записи в БД',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)

        legacy = (
            Booking.objects
            .filter(guest__isnull=True)
            .exclude(guest_name__isnull=True)
            .exclude(guest_name__exact='')
        )

        total_legacy = legacy.count()
        self.stdout.write(self.style.SUCCESS('Бэкфилл нормализованных гостей'))
        if dry_run:
            self.stdout.write(self.style.WARNING('РЕЖИМ DRY-RUN: изменения не сохраняются'))
        self.stdout.write(f'Legacy-бронирований без Guest: {total_legacy}')

        if total_legacy == 0:
            self.stdout.write(self.style.SUCCESS('Нечего бэкфиллить.'))
            return

        # Группируем уникальные имена -> нормализованное имя
        raw_names = (
            legacy.values_list('guest_name', flat=True).distinct()
        )

        # normalized -> {display_name, count_names}
        normalized_map = {}
        for raw in raw_names:
            normalized = normalize_guest_name(raw)
            if not normalized:
                continue
            # Первый встреченный display оставляем как отображаемое имя
            normalized_map.setdefault(normalized, raw.strip())

        self.stdout.write(f'Уникальных имён (после нормализации): {len(normalized_map)}')
        self.stdout.write('')

        created_guests = 0
        reused_guests = 0
        linked_bookings = 0

        try:
            with transaction.atomic():
                for normalized, display in normalized_map.items():
                    if dry_run:
                        exists = Guest.objects.filter(normalized_name=normalized).exists()
                        affected = legacy.filter(
                            guest_name__in=self._names_for(normalized, raw_names)
                        ).count()
                        action = 'переиспользуем' if exists else 'создаём'
                        self.stdout.write(
                            f'  [{action}] «{display}» (norm: {normalized}) '
                            f'-> {affected} бронирований'
                        )
                        if exists:
                            reused_guests += 1
                        else:
                            created_guests += 1
                        linked_bookings += affected
                        continue

                    guest, created = Guest.objects.get_or_create(
                        normalized_name=normalized,
                        defaults={'display_name': display},
                    )
                    if created:
                        created_guests += 1
                    else:
                        reused_guests += 1

                    matching_names = self._names_for(normalized, raw_names)
                    affected = legacy.filter(
                        guest__isnull=True,
                        guest_name__in=matching_names,
                    ).update(guest=guest)
                    linked_bookings += affected

                    self.stdout.write(
                        f'  {"+" if created else "="} «{guest.display_name}» '
                        f'(ID {guest.id}) -> {affected} бронирований'
                    )

                if dry_run:
                    raise _Rollback()
        except _Rollback:
            pass

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Итог:'))
        self.stdout.write(f'  Создано гостей: {created_guests}')
        self.stdout.write(f'  Переиспользовано существующих: {reused_guests}')
        self.stdout.write(f'  Привязано бронирований: {linked_bookings}')
        if dry_run:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Это был DRY-RUN. Запустите без --dry-run, чтобы применить.'
            ))

    @staticmethod
    def _names_for(normalized, raw_names):
        """Все исходные варианты guest_name, которые нормализуются в normalized."""
        return [
            raw for raw in raw_names
            if normalize_guest_name(raw) == normalized
        ]


class _Rollback(Exception):
    """Служебное исключение для отката транзакции в dry-run."""
