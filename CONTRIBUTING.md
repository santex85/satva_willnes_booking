# Руководство по участию в проекте

## Подготовка окружения

1. Клонируйте репозиторий.
2. Создайте виртуальное окружение: `python3 -m venv venv`
3. Активируйте: `source venv/bin/activate` (Windows: `venv\Scripts\activate`)
4. Установите зависимости: `pip install -r requirements.txt`
5. Скопируйте `.env.example` в `.env` и заполните настройки.
6. Выполните миграции: `python manage.py migrate`
7. Создайте суперпользователя: `python manage.py createsuperuser`

Подробная установка и развертывание: [README.md](README.md), [DEPLOYMENT.md](DEPLOYMENT.md).

## Структура проекта

- `booking/` — основное приложение Django
- `config/` — настройки (settings, urls)
- `templates/` — HTML-шаблоны
- `static/` — исходные статические файлы; `staticfiles/` — результат `collectstatic`
- `scripts/` — скрипты деплоя и бэкапов

## Стиль кода

- Следуйте PEP 8.
- Комментируйте неочевидную логику.
- Используйте осмысленные имена переменных и функций.

## Коммиты

- Пишите понятные сообщения коммитов.
- Группируйте связанные изменения в один коммит.
- Не коммитьте чувствительные данные (`.env`, пароли, `server_info_*.md`).

## Документация

При изменении функциональности деплоя, миграций или скриптов обновите соответствующий раздел в [DEPLOYMENT.md](DEPLOYMENT.md) или [TESTING.md](TESTING.md). Индекс документации: [docs/INDEX.md](docs/INDEX.md).

