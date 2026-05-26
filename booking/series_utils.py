"""Утилиты для работы с сериями бронирований (вынесены из legacy views)."""
from .utils import check_booking_conflicts


def detect_occurrence_conflicts(occurrences, service_variant, specialist, cabinet, exclude_ids=None):
    """Проверяет конфликты для списка дат."""
    issues = []
    for index, start_dt in enumerate(occurrences, start=1):
        exclude_id = None
        if exclude_ids and index - 1 < len(exclude_ids):
            exclude_id = exclude_ids[index - 1]
        conflicts = check_booking_conflicts(
            start_time=start_dt,
            service_variant=service_variant,
            specialist=specialist,
            cabinet=cabinet,
            exclude_booking_id=exclude_id,
        )
        if conflicts:
            issues.append((index, start_dt, conflicts))
    return issues
