"""
Утилиты для работы с именами гостей: нормализация, поиск похожих, объединение
"""
import re
from typing import List, Tuple, Dict
from django.db.models import Q, Count
from django.db import transaction
from .models import Guest, Booking


def normalize_guest_name(name: str) -> str:
    """
    Нормализует имя гостя для сравнения и поиска.
    
    Правила нормализации:
    - Удаление лишних пробелов
    - Правильная капитализация (каждое слово с заглавной буквы)
    - Удаление начальных/конечных пробелов
    
    Примеры:
    "ИВАН ИВАНОВ" -> "Иван Иванов"
    "иван  иванов" -> "Иван Иванов"
    "  Петрова Мария  " -> "Петрова Мария"
    """
    if not name:
        return ""
    
    # Удаляем лишние пробелы и нормализуем
    normalized = re.sub(r'\s+', ' ', name.strip())
    
    # Капитализация: каждое слово с заглавной буквы
    # Разбиваем по пробелам, капитализируем каждое слово
    words = normalized.split()
    capitalized_words = []
    
    for word in words:
        if word:
            # Первая буква заглавная, остальные строчные
            capitalized = word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper()
            capitalized_words.append(capitalized)
    
    return ' '.join(capitalized_words)


def calculate_similarity(name1: str, name2: str) -> float:
    """
    Вычисляет схожесть двух имен (0.0 - 1.0).
    Использует простой алгоритм на основе нормализации и расстояния Левенштейна.
    
    Args:
        name1: Первое имя
        name2: Второе имя
        
    Returns:
        Коэффициент схожести от 0.0 (совсем не похожи) до 1.0 (идентичны)
    """
    norm1 = normalize_guest_name(name1).lower()
    norm2 = normalize_guest_name(name2).lower()
    
    # Если после нормализации идентичны - 100% схожесть
    if norm1 == norm2:
        return 1.0
    
    # Простой алгоритм схожести на основе общих символов
    # Можно заменить на более продвинутый (fuzzywuzzy, difflib)
    if not norm1 or not norm2:
        return 0.0
    
    # Подсчет общих символов
    set1 = set(norm1.replace(' ', ''))
    set2 = set(norm2.replace(' ', ''))
    
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    if union == 0:
        return 0.0
    
    # Jaccard similarity для символов
    char_similarity = intersection / union
    
    # Учитываем порядок слов
    words1 = norm1.split()
    words2 = norm2.split()
    
    if not words1 or not words2:
        return char_similarity * 0.7
    
    # Проверка на перестановку слов (Иван Иванов vs Иванов Иван)
    if set(words1) == set(words2):
        return max(char_similarity, 0.85)  # Высокая схожесть при перестановке
    
    # Проверка на частичное совпадение слов
    common_words = set(words1) & set(words2)
    if common_words:
        word_similarity = len(common_words) / max(len(words1), len(words2))
        return max(char_similarity, word_similarity * 0.9)
    
    return char_similarity * 0.7


def find_similar_guests(name: str, threshold: float = 0.8, limit: int = 10) -> List[Guest]:
    """
    Находит похожих гостей по имени.
    
    Args:
        name: Имя для поиска
        threshold: Минимальный порог схожести (0.0 - 1.0)
        limit: Максимальное количество результатов
        
    Returns:
        Список объектов Guest, отсортированных по схожести
    """
    if not name:
        return []
    
    normalized = normalize_guest_name(name)
    
    # Сначала ищем точные совпадения по normalized_name
    exact_matches = Guest.objects.filter(normalized_name=normalized)
    
    # Затем ищем похожие (по началу имени или частичному совпадению)
    # Используем простой поиск по началу нормализованного имени
    similar_queryset = Guest.objects.exclude(normalized_name=normalized).filter(
        Q(normalized_name__icontains=normalized[:3]) |  # Первые 3 символа
        Q(display_name__icontains=name[:3])
    )
    
    # Вычисляем схожесть для каждого результата
    candidates = []
    for guest in similar_queryset:
        similarity = calculate_similarity(name, guest.display_name)
        if similarity >= threshold:
            candidates.append((similarity, guest))
    
    # Сортируем по схожести (убывание)
    candidates.sort(key=lambda x: x[0], reverse=True)
    
    # Возвращаем только гостей, без коэффициентов схожести
    result = [guest for _, guest in candidates[:limit]]
    
    # Добавляем точные совпадения в начало
    exact_list = list(exact_matches)
    for guest in exact_list:
        if guest not in result:
            result.insert(0, guest)
    
    return result


def find_duplicate_groups(threshold: float = 0.85) -> List[Dict]:
    """
    Находит группы потенциальных дублей среди всех гостей.
    
    Args:
        threshold: Минимальный порог схожести для группировки
        
    Returns:
        Список словарей с информацией о группах дублей:
        [
            {
                'primary': Guest,  # Основной гость (с наибольшим количеством бронирований)
                'duplicates': [Guest, ...],  # Похожие гости
                'similarity_scores': {guest_id: score},  # Оценки схожести
                'total_bookings': int,  # Общее количество бронирований в группе
            },
            ...
        ]
    """
    all_guests = Guest.objects.annotate(
        booking_count=Count('bookings')
    ).order_by('-booking_count')
    
    processed = set()
    groups = []
    
    for guest in all_guests:
        if guest.id in processed:
            continue
        
        # Ищем похожих гостей
        similar_guests = []
        similarity_scores = {}
        
        for other_guest in all_guests:
            if other_guest.id == guest.id or other_guest.id in processed:
                continue
            
            similarity = calculate_similarity(guest.display_name, other_guest.display_name)
            if similarity >= threshold:
                similar_guests.append(other_guest)
                similarity_scores[other_guest.id] = similarity
                processed.add(other_guest.id)
        
        if similar_guests:
            # Определяем основного гостя (с наибольшим количеством бронирований)
            all_in_group = [guest] + similar_guests
            primary = max(all_in_group, key=lambda g: g.booking_count)
            
            # Убираем основного из списка дублей
            duplicates = [g for g in all_in_group if g.id != primary.id]
            
            total_bookings = sum(g.booking_count for g in all_in_group)
            
            groups.append({
                'primary': primary,
                'duplicates': duplicates,
                'similarity_scores': similarity_scores,
                'total_bookings': total_bookings,
            })
            
            processed.add(guest.id)
    
    return groups


@transaction.atomic
def merge_guests(primary_guest: Guest, duplicate_guests: List[Guest], primary_display_name: str = None) -> int:
    """
    Объединяет дублирующихся гостей в одного основного.
    
    Все бронирования от duplicate_guests переносятся на primary_guest.
    После объединения duplicate_guests удаляются.
    
    Args:
        primary_guest: Основной гость, к которому будут перенесены бронирования
        duplicate_guests: Список гостей-дублей для объединения
        primary_display_name: Имя для отображения (если нужно изменить)
        
    Returns:
        Количество перенесенных бронирований
    """
    if not duplicate_guests:
        return 0
    
    # Обновляем display_name основного гостя, если указано
    if primary_display_name and primary_display_name.strip():
        primary_guest.display_name = primary_display_name.strip()
        primary_guest.save(update_fields=['display_name'])
    
    # Обновляем все бронирования: и guest, и guest_name
    bookings_updated = Booking.objects.filter(
        guest__in=duplicate_guests
    ).update(
        guest=primary_guest,
        guest_name=primary_guest.display_name  # Обновляем и старое поле для совместимости
    )
    
    # Также обновляем бронирования, которые еще используют старое поле guest_name
    # (для старых данных, где guest может быть null)
    all_duplicate_names = [g.display_name for g in duplicate_guests]
    Booking.objects.filter(
        guest__isnull=True,
        guest_name__in=all_duplicate_names
    ).update(guest_name=primary_guest.display_name)
    
    # Удаляем дублирующихся гостей
    guest_ids = [g.id for g in duplicate_guests]
    deleted_count = Guest.objects.filter(id__in=guest_ids).delete()[0]
    
    return bookings_updated
