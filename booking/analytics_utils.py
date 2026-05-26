"""
Утилиты аналитики: фильтры периода, форматирование, агрегации для отчётов.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Iterator, Optional, Tuple

from django.utils import timezone
from django.db.models import Count, Max, Min, QuerySet, Sum
from rest_framework.exceptions import ValidationError

from .models import Booking, Guest


def format_duration(minutes: int) -> str:
    """Форматирует минуты в человекочитаемый вид («X ч Y мин»)."""
    minutes = int(minutes or 0)
    if minutes >= 60:
        hours = minutes // 60
        remaining = minutes % 60
        if remaining:
            return f'{hours} ч {remaining} мин'
        return f'{hours} ч'
    return f'{minutes} мин'


def parse_date_range(request) -> Tuple[date, date]:
    """Парсит start_date и end_date из query-параметров запроса."""
    start_raw = request.query_params.get('start_date', '').strip()
    end_raw = request.query_params.get('end_date', '').strip()

    if not start_raw or not end_raw:
        raise ValidationError({'detail': 'Параметры start_date и end_date обязательны (YYYY-MM-DD).'})

    try:
        start = datetime.strptime(start_raw, '%Y-%m-%d').date()
        end = datetime.strptime(end_raw, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValidationError({'detail': 'Неверный формат даты. Используйте YYYY-MM-DD.'}) from exc

    if start > end:
        raise ValidationError({'detail': 'start_date не может быть позже end_date.'})

    return start, end


def parse_specialist_id(request) -> Optional[int]:
    """Опциональный фильтр по specialist_id."""
    raw = request.query_params.get('specialist_id', '').strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValidationError({'detail': 'specialist_id должен быть целым числом.'}) from exc


def build_bookings_filter(
    start: date,
    end: date,
    specialist_id: Optional[int] = None,
) -> QuerySet:
    """Базовый queryset бронирований за период (без отменённых)."""
    qs = Booking.objects.filter(
        start_time__date__range=[start, end],
    ).exclude(status='canceled')

    if specialist_id is not None:
        qs = qs.filter(specialist_id=specialist_id)

    return qs


def get_service_popularity(bookings_filter: QuerySet) -> list:
    """Популярность услуг за период."""
    rows = bookings_filter.values('service_variant__service__name').annotate(
        count=Count('id'),
    ).order_by('-count')

    return [
        {
            'service_name': row['service_variant__service__name'] or 'Без названия',
            'count': row['count'],
        }
        for row in rows
    ]


def get_specialist_load(bookings_filter: QuerySet) -> list:
    """Нагрузка специалистов за период."""
    rows = bookings_filter.values('specialist__full_name').annotate(
        total_minutes=Sum('service_variant__duration_minutes'),
    ).order_by('-total_minutes')

    result = []
    for row in rows:
        minutes = int(row.get('total_minutes') or 0)
        result.append({
            'specialist_name': row['specialist__full_name'] or 'Не указан',
            'total_minutes': minutes,
            'total_display': format_duration(minutes),
        })
    return result


def get_guest_statistics(bookings_filter: QuerySet) -> list:
    """
    CRM-статистика по гостям: нормализованные Guest + legacy guest_name.
    Логика перенесена из booking/views.py reports_view.
    """
    bookings_with_guest = bookings_filter.filter(guest__isnull=False)
    bookings_without_guest = bookings_filter.filter(guest__isnull=True)

    guest_stats_with_guest = bookings_with_guest.values('guest').annotate(
        visit_count=Count('id'),
        total_amount=Sum('service_variant__price'),
        total_duration=Sum('service_variant__duration_minutes'),
        first_visit=Min('start_time'),
        last_visit=Max('start_time'),
        room_number=Max('guest_room_number'),
    ).order_by('-total_amount')

    guest_stats_without_guest = bookings_without_guest.values('guest_name').annotate(
        visit_count=Count('id'),
        total_amount=Sum('service_variant__price'),
        total_duration=Sum('service_variant__duration_minutes'),
        first_visit=Min('start_time'),
        last_visit=Max('start_time'),
        room_number=Max('guest_room_number'),
    ).order_by('-total_amount')

    guest_ids = [item['guest'] for item in guest_stats_with_guest]
    guests_dict = {
        g.id: g for g in Guest.objects.filter(id__in=guest_ids)
    }

    services_per_guest: dict = defaultdict(list)
    for booking in bookings_filter.select_related('guest', 'service_variant__service'):
        if booking.guest:
            guest_key = booking.guest.id
        else:
            guest_key = f'name_{booking.guest_name}'

        service_name = (
            booking.service_variant.service.name
            if booking.service_variant and booking.service_variant.service
            else None
        )
        if service_name and service_name not in services_per_guest[guest_key]:
            services_per_guest[guest_key].append(service_name)

    guest_statistics = []

    for item in guest_stats_with_guest:
        guest_id = item['guest']
        guest_obj = guests_dict.get(guest_id)
        if not guest_obj:
            continue

        minutes = int(item.get('total_duration') or 0)
        total = item.get('total_amount') or Decimal('0')
        count = item.get('visit_count') or 0
        avg_check = (total / count) if count else Decimal('0')

        first = item.get('first_visit')
        last = item.get('last_visit')

        name_variants = set(
            bookings_filter.filter(guest=guest_obj)
            .values_list('guest_name', flat=True)
            .distinct()
        )
        name_variants.add(guest_obj.display_name)
        name_variants = {n for n in name_variants if n}

        guest_statistics.append({
            'guest_id': guest_id,
            'guest_name': guest_obj.display_name,
            'room_number': (item.get('room_number') or '').strip() or None,
            'visit_count': count,
            'total_amount': str(total),
            'avg_check': str(avg_check.quantize(Decimal('0.01'))),
            'total_duration_minutes': minutes,
            'total_duration_display': format_duration(minutes),
            'first_visit': timezone.localtime(first).isoformat() if first else None,
            'last_visit': timezone.localtime(last).isoformat() if last else None,
            'services': sorted(services_per_guest.get(guest_id, [])),
            'name_variants': sorted(name_variants) if len(name_variants) > 1 else None,
            'is_merged': len(name_variants) > 1,
        })

    for item in guest_stats_without_guest:
        minutes = int(item.get('total_duration') or 0)
        total = item.get('total_amount') or Decimal('0')
        count = item.get('visit_count') or 0
        avg_check = (total / count) if count else Decimal('0')

        first = item.get('first_visit')
        last = item.get('last_visit')
        guest_name = item.get('guest_name') or 'Без имени'
        guest_key = f'name_{guest_name}'

        guest_statistics.append({
            'guest_id': None,
            'guest_name': guest_name,
            'room_number': (item.get('room_number') or '').strip() or None,
            'visit_count': count,
            'total_amount': str(total),
            'avg_check': str(avg_check.quantize(Decimal('0.01'))),
            'total_duration_minutes': minutes,
            'total_duration_display': format_duration(minutes),
            'first_visit': timezone.localtime(first).isoformat() if first else None,
            'last_visit': timezone.localtime(last).isoformat() if last else None,
            'services': sorted(services_per_guest.get(guest_key, [])),
            'name_variants': None,
            'is_merged': False,
        })

    guest_statistics.sort(
        key=lambda x: Decimal(x['total_amount']),
        reverse=True,
    )
    return guest_statistics


def iter_csv_report_rows(bookings_query: QuerySet) -> Iterator[list]:
    """Генератор строк CSV-отчёта по бронированиям."""
    headers = [
        'Дата',
        'Время начала',
        'Время окончания',
        'Гость',
        'Номер комнаты',
        'Процедура',
        'Длительность (мин)',
        'Стоимость',
        'Специалист',
        'Кабинет',
        'Статус',
    ]
    yield headers

    total_cost = Decimal('0')
    for booking in bookings_query:
        local_start = timezone.localtime(booking.start_time)
        local_end = timezone.localtime(booking.end_time)
        cost = booking.service_variant.price
        total_cost += cost

        guest_label = (
            booking.guest.display_name
            if booking.guest
            else booking.guest_name
        )

        yield [
            local_start.strftime('%d.%m.%Y'),
            local_start.strftime('%H:%M'),
            local_end.strftime('%H:%M'),
            guest_label,
            booking.guest_room_number or '',
            str(booking.service_variant),
            booking.service_variant.duration_minutes,
            str(cost).replace('.', ','),
            booking.specialist.full_name,
            booking.cabinet.name,
            booking.get_status_display(),
        ]

    yield []
    yield ['ИТОГО:', '', '', '', '', '', '', str(total_cost).replace('.', ','), '', '', '']


def build_csv_stream(bookings_query: QuerySet) -> io.StringIO:
    """Строит CSV в StringIO с UTF-8 BOM для Excel."""
    buffer = io.StringIO()
    buffer.write('\ufeff')
    writer = csv.writer(buffer, delimiter=';')
    for row in iter_csv_report_rows(bookings_query):
        writer.writerow(row)
    buffer.seek(0)
    return buffer
