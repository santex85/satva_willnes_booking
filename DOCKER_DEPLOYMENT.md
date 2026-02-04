# Инструкция по развертыванию на Digital Ocean с Docker

## Оглавление
1. [Локальное тестирование Docker](#локальное-тестирование-docker) ⭐
2. [Подготовка Digital Ocean Droplet](#подготовка-digital-ocean-droplet)
3. [Установка Docker и Docker Compose](#установка-docker-и-docker-compose)
4. [Настройка проекта на сервере](#настройка-проекта-на-сервере)
5. [Настройка переменных окружения](#настройка-переменных-окружения)
6. [Запуск контейнеров](#запуск-контейнеров)
7. [Настройка домена и SSL](#настройка-домена-и-ssl)
8. [Мониторинг и обслуживание](#мониторинг-и-обслуживание)
9. [Бэкапы](#бэкапы)

---

## Локальное тестирование Docker

Перед развертыванием на production сервере рекомендуется протестировать Docker-окружение локально на вашем компьютере.

### Предварительные требования

1. **Установлен Docker Desktop** (macOS/Windows) или **Docker Engine + Docker Compose** (Linux)
   - Проверьте установку:
     ```bash
     docker --version
     docker compose version
     ```
   - Если не установлен, скачайте с [docker.com](https://www.docker.com/products/docker-desktop)

2. **Освобожденные порты**:
   - `80` - для Nginx (или измените на другой, например `8080`)
   - `5432` - для PostgreSQL (или измените на другой, например `5433`)

### Быстрый старт

#### 1. Подготовка окружения

```bash
# Перейдите в директорию проекта
cd "/Users/alex/projects/Satva willnes booking"

# Создайте .env файл из примера
cp .env.example .env

# Откройте .env для редактирования
# (используйте ваш редактор: nano, vim, или IDE)
```

#### 2. Настройка .env файла для локального тестирования

Минимальная конфигурация для локального теста:

```env
# Django Settings
DJANGO_SECRET_KEY=test-secret-key-for-local-development-change-in-production
DEBUG=False

# Database Settings (для Docker используйте 'db' как host)
DATABASE_NAME=satva_wellness_booking
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
DATABASE_HOST=db
DATABASE_PORT=5432

# Allowed Hosts (для локального тестирования)
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Email Settings (можно оставить пустым или использовать консольный backend)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=noreply@localhost

# SSL Settings (для локального тестирования - False)
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False

# Sentry (опционально, можно оставить пустым)
SENTRY_DSN=
```

**Примечание**: Для генерации безопасного `DJANGO_SECRET_KEY`:
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

#### 3. Сборка и запуск контейнеров

**Вариант A: Используя Makefile (рекомендуется)**

```bash
# Показать все доступные команды
make help

# Собрать Docker образы
make build

# Запустить контейнеры в фоновом режиме
make up

# Просмотреть логи
make logs
```

**Вариант B: Используя docker compose напрямую**

```bash
# Сборка образов
docker compose build

# Запуск контейнеров в фоновом режиме
docker compose up -d

# Просмотр статуса
docker compose ps
```

#### 4. Проверка работы

**Проверка статуса контейнеров:**
```bash
docker compose ps
```

Должны быть запущены 3 контейнера:
- ✅ `satva_wellness_db` - PostgreSQL (статус: Up)
- ✅ `satva_wellness_web` - Django приложение (статус: Up)
- ✅ `satva_wellness_nginx` - Nginx (статус: Up)

**Просмотр логов:**
```bash
# Все логи в реальном времени
docker compose logs -f

# Логи конкретного сервиса
docker compose logs -f web
docker compose logs -f db
docker compose logs -f nginx

# Последние 50 строк логов
docker compose logs --tail=50 web
```

**Откройте в браузере:**
- 🌐 **http://localhost/** - через Nginx (рекомендуется)
- 🌐 **http://localhost:8000/** - напрямую Django (если пробросить порт в docker-compose.yml)

#### 5. Создание суперпользователя

```bash
# Используя Makefile
make createsuperuser

# Или напрямую
docker compose exec web python manage.py createsuperuser
```

Следуйте инструкциям в терминале для создания пользователя.

#### 6. Проверка работы приложения

После создания суперпользователя:

1. Откройте http://localhost/ в браузере
2. Войдите с созданными учетными данными
3. Проверьте работу основных функций:
   - Календарь
   - Создание бронирований
   - Просмотр расписания
   - API endpoints (если используется)

### Полезные команды для локального тестирования

#### Работа с контейнерами

```bash
# Вход в контейнер Django
docker compose exec web bash

# Или используя Makefile
make shell

# Выполнение команд Django внутри контейнера
docker compose exec web python manage.py migrate
docker compose exec web python manage.py check
docker compose exec web python manage.py shell

# Проверка подключения к БД
docker compose exec web python manage.py dbshell
```

#### Управление контейнерами

```bash
# Остановка контейнеров
docker compose down

# Остановка и удаление volumes (ОСТОРОЖНО: удалит данные БД!)
docker compose down -v

# Перезапуск конкретного сервиса
docker compose restart web
docker compose restart nginx

# Просмотр использования ресурсов
docker stats
```

#### Отладка

```bash
# Проверка конфигурации docker-compose
docker compose config

# Пересборка без кэша
docker compose build --no-cache

# Просмотр переменных окружения в контейнере
docker compose exec web env

# Проверка сетевых подключений
docker network inspect satva_willnes_booking_satva_network
```

### Решение проблем при локальном тестировании

#### Проблема: Порт 80 уже занят

**Решение**: Измените порт в `docker-compose.yml`:

```yaml
nginx:
  ports:
    - "8080:80"  # вместо "80:80"
```

Затем откройте http://localhost:8080/

#### Проблема: Порт 5432 уже занят (локальный PostgreSQL)

**Решение**: Измените порт в `docker-compose.yml`:

```yaml
db:
  ports:
    - "5433:5432"  # вместо "5432:5432"
```

#### Проблема: Ошибки при сборке образа

**Решение**:
```bash
# Очистить кэш Docker
docker system prune -a

# Пересобрать без кэша
docker compose build --no-cache
```

#### Проблема: Контейнер web не запускается

**Проверьте**:
```bash
# Логи контейнера
docker compose logs web

# Проверьте, что база данных готова
docker compose logs db

# Проверьте переменные окружения
docker compose exec web env | grep DATABASE
```

#### Проблема: Статические файлы не загружаются

**Решение**:
```bash
# Пересобрать статику
docker compose exec web python manage.py collectstatic --noinput

# Перезапустить nginx
docker compose restart nginx
```

#### Проблема: Ошибки миграций

**Решение**:
```bash
# Проверить статус миграций
docker compose exec web python manage.py showmigrations

# Применить миграции
docker compose exec web python manage.py migrate

# Если нужно откатить
docker compose exec web python manage.py migrate app_name zero
```

### Полная очистка и повторный запуск

Если нужно начать с чистого листа:

```bash
# Остановить и удалить все
docker compose down -v

# Удалить образы
docker compose rm -f

# Очистить систему Docker
docker system prune -a

# Пересобрать и запустить заново
docker compose build --no-cache
docker compose up -d
```

### Проверка перед деплоем на production

Перед развертыванием на сервер убедитесь, что:

- ✅ Все контейнеры запускаются без ошибок
- ✅ Приложение доступно через Nginx
- ✅ База данных работает и миграции применены
- ✅ Статические файлы загружаются
- ✅ Создан суперпользователь и можно войти
- ✅ Основные функции работают (календарь, бронирования)
- ✅ Логи не содержат критических ошибок

### Следующий шаг

После успешного локального тестирования переходите к разделу [Подготовка Digital Ocean Droplet](#подготовка-digital-ocean-droplet) для развертывания на production сервере.

---

## Подготовка Digital Ocean Droplet

### 1. Создание Droplet

1. Войдите в панель управления Digital Ocean
2. Создайте новый Droplet:
   - **Образ**: Ubuntu 22.04 LTS
   - **Размер**: Минимум 2GB RAM, 1 vCPU (рекомендуется 4GB RAM для production)
   - **Регион**: Выберите ближайший к вашим пользователям
   - **Аутентификация**: SSH ключ (рекомендуется) или пароль
3. Дождитесь создания Droplet и запишите IP адрес

### 2. Подключение к серверу

```bash
ssh root@YOUR_SERVER_IP
```

Или если используете пользователя:

```bash
ssh your_user@YOUR_SERVER_IP
```

---

## Установка Docker и Docker Compose

### 1. Обновление системы

```bash
apt update && apt upgrade -y
```

### 2. Установка Docker

```bash
# Установка зависимостей
apt install -y apt-transport-https ca-certificates curl gnupg lsb-release

# Добавление официального GPG ключа Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Добавление репозитория Docker
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установка Docker
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Проверка установки
docker --version
docker compose version
```

### 3. Настройка пользователя (опционально)

Если работаете не от root:

```bash
# Добавление пользователя в группу docker
usermod -aG docker $USER

# Перезагрузка сессии
newgrp docker
```

---

## Настройка проекта на сервере

### 1. Клонирование репозитория

```bash
# Установка Git (если еще не установлен)
apt install -y git

# Клонирование репозитория
cd /opt
git clone https://github.com/santex85/satva_willnes_booking.git
cd satva_willnes_booking
```

### 2. Создание необходимых директорий

```bash
mkdir -p nginx/ssl
mkdir -p logs
```

---

## Настройка переменных окружения

### 1. Создание .env файла

```bash
cp .env.example .env
nano .env
```

### 2. Заполнение переменных окружения

```env
# Django Settings
DJANGO_SECRET_KEY=your-very-secure-secret-key-here-generate-with-openssl-rand-hex-32
DEBUG=False

# Database Settings (используются имена сервисов из docker-compose)
DATABASE_NAME=satva_wellness_booking
DATABASE_USER=postgres
DATABASE_PASSWORD=your-strong-database-password
DATABASE_HOST=db
DATABASE_PORT=5432

# Allowed Hosts (укажите ваш домен)
DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com,YOUR_SERVER_IP

# Email Settings
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com

# SSL Settings (установить в True после настройки SSL)
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False

# Sentry (опционально)
SENTRY_DSN=your-sentry-dsn-if-using
```

### 3. Генерация SECRET_KEY

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Или с помощью OpenSSL:

```bash
openssl rand -hex 32
```

---

## Запуск контейнеров

### 1. Сборка и запуск

```bash
# Сборка образов
docker compose build

# Запуск контейнеров в фоновом режиме
docker compose up -d

# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs -f
```

### 2. Создание суперпользователя

```bash
docker compose exec web python manage.py createsuperuser
```

### 3. Инициализация данных (опционально)

```bash
# Если есть скрипт инициализации
docker compose exec web python manage.py shell < init_data.py
```

---

## Настройка домена и SSL

### 1. Настройка DNS

В панели управления вашего регистратора домена:
- Создайте A-запись, указывающую на IP вашего Droplet
- Для www создайте CNAME запись или еще одну A-запись

### 2. Установка Certbot для Let's Encrypt

```bash
# Установка Certbot
apt install -y certbot python3-certbot-nginx

# Получение сертификата (если Nginx на хосте)
certbot --nginx -d your-domain.com -d www.your-domain.com
```

### 3. Настройка SSL в Docker

Для работы с SSL в Docker есть два варианта:

#### Вариант A: Certbot в контейнере Nginx

1. Обновите `docker-compose.yml`, добавив volume для сертификатов
2. Используйте certbot в контейнере для получения сертификатов
3. Обновите `nginx/nginx.conf`, раскомментировав HTTPS блок

#### Вариант B: Certbot на хосте (рекомендуется)

1. Получите сертификаты на хосте:

```bash
certbot certonly --standalone -d your-domain.com -d www.your-domain.com
```

2. Скопируйте сертификаты в директорию проекта:

```bash
mkdir -p nginx/ssl
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/
chmod 644 nginx/ssl/fullchain.pem
chmod 600 nginx/ssl/privkey.pem
```

3. Обновите `.env`:

```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

4. Обновите `nginx/nginx.conf`, раскомментировав HTTPS блок и указав правильный домен

5. Перезапустите контейнеры:

```bash
docker compose restart nginx
```

### 4. Автоматическое обновление сертификатов

При использовании Certbot в режиме `standalone` (получение сертификата с хоста) порт 80 должен быть свободен во время обновления. Добавьте cron задачу, которая останавливает nginx, обновляет сертификат и снова запускает nginx:

```bash
crontab -e
```

Добавьте (замените `/opt/satva_willnes_booking` на путь к проекту на сервере):

```cron
0 3 * * * cd /opt/satva_willnes_booking && docker compose stop nginx && certbot renew --quiet --non-interactive && docker compose start nginx
```

---

## Мониторинг и обслуживание

### Просмотр логов

```bash
# Все логи
docker compose logs -f

# Логи конкретного сервиса
docker compose logs -f web
docker compose logs -f db
docker compose logs -f nginx

# Последние 100 строк
docker compose logs --tail=100 web
```

### Проверка статуса контейнеров

```bash
docker compose ps
docker stats
```

### Обновление приложения

```bash
# Остановка контейнеров
docker compose down

# Обновление кода
git pull origin main

# Пересборка образов
docker compose build

# Запуск с миграциями
docker compose up -d

# Применение миграций
docker compose exec web python manage.py migrate
```

**Важно: Миграция Guest Model**

При обновлении до версии с моделью Guest будет применена миграция `0011_add_guest_model.py`. 

**Особенности:**
- Миграция может занять несколько минут на больших БД (зависит от количества бронирований)
- Скрипт `deploy_safe.sh` автоматически создает бэкап перед применением миграций
- Рекомендуется использовать `make deploy-safe` для безопасного деплоя

**Проверка результатов миграции через Docker:**

```bash
# Вход в Django shell
docker compose exec web python manage.py shell
```

В Django shell:

```python
from booking.models import Guest, Booking

# Проверка количества созданных гостей
print(f"Guests: {Guest.objects.count()}")

# Проверка связей
print(f"Bookings with guest: {Booking.objects.filter(guest__isnull=False).count()}")
print(f"Bookings without guest: {Booking.objects.filter(guest__isnull=True).count()}")

# Примеры гостей
for guest in Guest.objects.all()[:5]:
    print(f"  - {guest.display_name}")
```

Подробнее о миграции: [MIGRATION_RISK_ANALYSIS.md](../MIGRATION_RISK_ANALYSIS.md)

### Создание резервных копий БД

```bash
# Ручной бэкап
docker compose exec db pg_dump -U postgres satva_wellness_booking > backup_$(date +%Y%m%d_%H%M%S).sql

# Восстановление из бэкапа
docker compose exec -T db psql -U postgres satva_wellness_booking < backup_file.sql
```

---

## Бэкапы

### Автоматические бэкапы БД

Создайте скрипт `/opt/backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/opt/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Бэкап базы данных
docker compose exec -T db pg_dump -U postgres satva_wellness_booking | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Удаление старых бэкапов (старше 30 дней)
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +30 -delete

echo "Backup completed: db_$DATE.sql.gz"
```

Сделайте скрипт исполняемым:

```bash
chmod +x /opt/backup.sh
```

Добавьте в cron:

```bash
crontab -e
```

```cron
0 2 * * * /opt/backup.sh
```

### Рекомендации

- Настройте мониторинг (например, Uptime Robot)
- Настройте алерты при падении сервисов
- Регулярно обновляйте Docker образы
- Настройте ротацию логов
- Используйте firewall (ufw):

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

---

## Troubleshooting

### Контейнеры не запускаются

```bash
# Проверка логов
docker compose logs

# Проверка конфигурации
docker compose config
```

### Проблемы с базой данных

```bash
# Проверка подключения
docker compose exec web python manage.py dbshell

# Проверка статуса БД
docker compose exec db pg_isready -U postgres
```

### Проблемы со статическими файлами

```bash
# Пересборка статики
docker compose exec web python manage.py collectstatic --noinput
```

### Очистка и пересборка

```bash
# Остановка и удаление контейнеров
docker compose down

# Удаление volumes (ОСТОРОЖНО: удалит данные БД!)
docker compose down -v

# Пересборка без кэша
docker compose build --no-cache
docker compose up -d
```

---

## Полезные команды

```bash
# Вход в контейнер Django
docker compose exec web bash

# Выполнение команд Django
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py collectstatic

# Перезапуск сервисов
docker compose restart web
docker compose restart nginx

# Просмотр использования ресурсов
docker stats

# Очистка неиспользуемых образов
docker system prune -a
```

