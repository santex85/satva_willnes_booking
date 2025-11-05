# Многоступенчатый Dockerfile для Django приложения
FROM python:3.12-slim as builder

# Установка системных зависимостей для сборки
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Создание рабочей директории
WORKDIR /app

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Финальный образ
FROM python:3.12-slim

# Установка только runtime зависимостей
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Создание пользователя без прав root
RUN useradd -m -u 1000 django && \
    mkdir -p /app /app/staticfiles /app/logs && \
    chown -R django:django /app

# Копирование установленных пакетов из builder
COPY --from=builder /root/.local /home/django/.local

# Настройка пути для Python
ENV PATH=/home/django/.local/bin:$PATH

# Установка рабочей директории
WORKDIR /app

# Копирование кода приложения
COPY --chown=django:django . .

# Установка netcat для проверки доступности БД в entrypoint
USER root
RUN apt-get update && apt-get install -y netcat-openbsd && rm -rf /var/lib/apt/lists/*
USER django

# Создание директорий для логов
RUN mkdir -p logs

# Переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings_production

# Порт для Gunicorn
EXPOSE 8000

# Entrypoint скрипт будет запускать миграции и collectstatic
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# Запуск Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "config.wsgi:application"]

