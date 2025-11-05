# Инструкция по развертыванию Satva Wellness Booking System

## Оглавление
1. [Системные требования](#системные-требования)
2. [Установка зависимостей](#установка-зависимостей)
3. [Настройка PostgreSQL](#настройка-postgresql)
4. [Настройка Django проекта](#настройка-django-проекта)
5. [Настройка Gunicorn](#настройка-gunicorn)
6. [Настройка Nginx](#настройка-nginx)
7. [Запуск системы](#запуск-системы)
8. [Мониторинг и обслуживание](#мониторинг-и-обслуживание)

---

## Системные требования

- **ОС**: Ubuntu 22.04 LTS или аналогичная Linux-система
- **Python**: 3.12+
- **База данных**: PostgreSQL 14+
- **Веб-сервер**: Nginx
- **WSGI сервер**: Gunicorn

---

## Установка зависимостей

### 1. Обновление системы

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Установка Python и pip

```bash
sudo apt install python3.12 python3.12-venv python3-pip -y
```

### 3. Установка PostgreSQL

```bash
sudo apt install postgresql postgresql-contrib -y
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

---

## Настройка PostgreSQL

### 1. Создание базы данных и пользователя

```bash
sudo -u postgres psql
```

В консоли PostgreSQL выполните:

```sql
CREATE DATABASE satva_wellness_booking;
CREATE USER postgres WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE satva_wellness_booking TO postgres;
ALTER USER postgres CREATEDB;
\q
```

### 2. Настройка PostgreSQL для внешних подключений

Отредактируйте `/etc/postgresql/14/main/postgresql.conf`:

```conf
listen_addresses = 'localhost'
```

И `/etc/postgresql/14/main/pg_hba.conf`:

```conf
local   all             all                                     peer
host    all             all             127.0.0.1/32            md5
```

Перезапустите PostgreSQL:

```bash
sudo systemctl restart postgresql
```

---

## Настройка Django проекта

### 1. Клонирование проекта

```bash
cd /var/www
sudo git clone <your-repo-url> satva-wellness
sudo chown -R $USER:$USER satva-wellness
cd satva-wellness
```

### 2. Создание виртуального окружения

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```bash
nano .env
```

Добавьте:

```env
DJANGO_SECRET_KEY=your-super-secret-key-here-generate-with-openssl
DJANGO_DEBUG=False
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=satva_wellness_booking
DATABASE_USER=postgres
DATABASE_PASSWORD=your_secure_password
```

**ВНИМАНИЕ**: Сгенерируйте SECRET_KEY командой:
```bash
openssl rand -hex 32
```

### 4. Обновление settings.py

Убедитесь, что в `config/settings.py`:

- `DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'`
- `ALLOWED_HOSTS` содержит ваш домен
- `DATABASES` использует переменные окружения
- `STATIC_ROOT = BASE_DIR / 'staticfiles'`

Пример обновления settings.py:

```python
import os

DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

ALLOWED_HOSTS = ['your-domain.com', 'www.your-domain.com']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DATABASE_NAME', 'satva_wellness_booking'),
        'USER': os.environ.get('DATABASE_USER', 'postgres'),
        'PASSWORD': os.environ.get('DATABASE_PASSWORD', 'postgres'),
        'HOST': os.environ.get('DATABASE_HOST', 'localhost'),
        'PORT': os.environ.get('DATABASE_PORT', '5432'),
    }
}
```

### 5. Применение миграций

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Создание суперпользователя

```bash
python manage.py createsuperuser
```

### 7. Загрузка тестовых данных (опционально)

```bash
python manage.py shell < init_data.py
```

### 8. Сбор статических файлов

```bash
python manage.py collectstatic --noinput
```

---

## Настройка Gunicorn

### 1. Установка Gunicorn

```bash
pip install gunicorn
```

### 2. Создание systemd сервиса

Создайте файл `/etc/systemd/system/satva-wellness.service`:

```bash
sudo nano /etc/systemd/system/satva-wellness.service
```

Добавьте:

```ini
[Unit]
Description=Satva Wellness Booking Gunicorn Daemon
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/satva-wellness
Environment="PATH=/var/www/satva-wellness/venv/bin"
EnvironmentFile=/var/www/satva-wellness/.env
ExecStart=/var/www/satva-wellness/venv/bin/gunicorn \
    --access-logfile - \
    --workers 3 \
    --bind unix:/var/www/satva-wellness/satva-wellness.sock \
    config.wsgi:application

[Install]
WantedBy=multi-user.target
```

**ВАЖНО**: Замените пути на ваши актуальные!

### 3. Запуск и автозапуск Gunicorn

```bash
sudo systemctl daemon-reload
sudo systemctl start satva-wellness
sudo systemctl enable satva-wellness
sudo systemctl status satva-wellness
```

---

## Настройка Nginx

### 1. Установка Nginx

```bash
sudo apt install nginx -y
```

### 2. Создание конфигурации

Создайте файл `/etc/nginx/sites-available/satva-wellness`:

```bash
sudo nano /etc/nginx/sites-available/satva-wellness
```

Добавьте:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    client_max_body_size 10M;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /var/www/satva-wellness/staticfiles/;
    }

    location /media/ {
        alias /var/www/satva-wellness/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/satva-wellness/satva-wellness.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    error_page 500 502 503 504 /500.html;
    location = /500.html {
        root /var/www/satva-wellness/templates/;
    }
}
```

### 3. Активация конфигурации

```bash
sudo ln -s /etc/nginx/sites-available/satva-wellness /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 4. Настройка SSL (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

Certbot автоматически обновит конфигурацию Nginx для HTTPS.

---

## Запуск системы

### Проверка статуса всех сервисов

```bash
sudo systemctl status satva-wellness
sudo systemctl status nginx
sudo systemctl status postgresql
```

### Перезапуск после изменений

```bash
sudo systemctl restart satva-wellness
sudo systemctl restart nginx
```

---

## Мониторинг и обслуживание

### Логи

**Gunicorn логи**:
```bash
sudo journalctl -u satva-wellness -f
```

**Nginx логи**:
```bash
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

**Django логи** (если настроены):
```bash
tail -f /var/www/satva-wellness/logs/django.log
```

### Резервное копирование базы данных

Создайте скрипт `/usr/local/bin/backup-satva-db.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/backup/satva-wellness"
mkdir -p $BACKUP_DIR
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -U postgres satva_wellness_booking > $BACKUP_DIR/backup_$DATE.sql
find $BACKUP_DIR -name "backup_*.sql" -mtime +7 -delete
```

Добавьте в cron:
```bash
sudo crontab -e
```

Добавьте строку:
```
0 2 * * * /usr/local/bin/backup-satva-db.sh
```

### Обновление кода

```bash
cd /var/www/satva-wellness
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart satva-wellness
```

---

## Troubleshooting

### "502 Bad Gateway"

Проверьте:
1. Запущен ли Gunicorn: `sudo systemctl status satva-wellness`
2. Правильные ли права на socket: `ls -la /var/www/satva-wellness/satva-wellness.sock`
3. Пользователь Nginx может читать файлы: `sudo chown -R www-data:www-data /var/www/satva-wellness`

### "Permission denied"

```bash
sudo chown -R www-data:www-data /var/www/satva-wellness
sudo chmod -R 755 /var/www/satva-wellness
```

### Проблемы с базой данных

```bash
sudo -u postgres psql
\l  # список баз данных
\c satva_wellness_booking
\dt  # список таблиц
```

---

## Производительность

### Оптимизация PostgreSQL

Отредактируйте `/etc/postgresql/14/main/postgresql.conf`:

```conf
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 256MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 8MB
min_wal_size = 1GB
max_wal_size = 4GB
```

Перезапустите:
```bash
sudo systemctl restart postgresql
```

### Кэширование в Django

Добавьте в `settings.py`:

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

Установите Redis:
```bash
sudo apt install redis-server -y
sudo systemctl enable redis-server
```

---

## Безопасность

1. **Используйте HTTPS**: настройте SSL через Let's Encrypt
2. **Измените SECRET_KEY**: используйте сильный ключ из переменной окружения
3. **Ограничьте ALLOWED_HOSTS**: только ваши домены
4. **Настройте файрвол**:
```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```
5. **Регулярно обновляйте**: систему, Django, зависимости

---

## Запуск с Production настройками

Используйте `settings_production.py` для production окружения:

```bash
# Установите переменные окружения
export DJANGO_SETTINGS_MODULE=config.settings_production
export DJANGO_SECRET_KEY=$(openssl rand -hex 32)
export DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com
export DATABASE_NAME=satva_wellness_booking
export DATABASE_USER=postgres
export DATABASE_PASSWORD=your_secure_password
export DATABASE_HOST=localhost
export DATABASE_PORT=5432
export SENTRY_DSN=your_sentry_dsn_here  # Опционально

# Выполните миграции и соберите статические файлы
python manage.py migrate
python manage.py collectstatic --noinput

# Запустите с Gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

---

## API Аутентификация

Система поддерживает два метода аутентификации:
1. **Session Authentication** - для веб-интерфейса
2. **JWT Authentication** - для мобильных приложений и API клиентов

### Получение JWT токена

```bash
curl -X POST http://your-domain.com/api/v1/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "specialist_user", "password": "password"}'
```

Response:
```json
{
    "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

### Использование токена

```bash
curl http://your-domain.com/api/v1/my-schedule/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Обновление токена

```bash
curl -X POST http://your-domain.com/api/v1/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "YOUR_REFRESH_TOKEN"}'
```

### API Endpoints

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/api/v1/token/` | POST | Получение JWT токена |
| `/api/v1/token/refresh/` | POST | Обновление access токена |
| `/api/v1/my-schedule/` | GET | Список бронирований специалиста |

---

## Контакты и поддержка

При возникновении проблем:
1. Проверьте логи сервисов
2. Убедитесь, что все сервисы запущены
3. Проверьте права доступа к файлам и директориям
4. Проверьте конфигурацию Nginx и Gunicorn

