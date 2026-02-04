# Развертывание Satva Wellness Booking

Единая инструкция по развертыванию: Docker (рекомендуется), безопасный деплой, откат и сбор информации с сервера.

## Оглавление

1. [Быстрые команды и чек-лист](#быстрые-команды-и-чек-лист)
2. [Локальное тестирование Docker](#локальное-тестирование-docker)
3. [Подготовка сервера](#подготовка-сервера)
4. [Настройка проекта и переменных окружения](#настройка-проекта-и-переменных-окружения)
5. [Запуск контейнеров](#запуск-контейнеров)
6. [Домен и SSL](#домен-и-ssl)
7. [Безопасный деплой](#безопасный-деплой)
8. [Откат](#откат)
9. [Сбор информации с сервера](#сбор-информации-с-сервера)
10. [Мониторинг и бэкапы](#мониторинг-и-бэкапы)
11. [Troubleshooting](#troubleshooting)
12. [Миграция Guest Model](#миграция-guest-model)
13. [API](#api)
14. [Развертывание без Docker (альтернатива)](#развертывание-без-docker-альтернатива)

---

## Быстрые команды и чек-лист

### Команды

```bash
# Безопасный деплой (рекомендуется)
make deploy-safe
make deploy-safe-interactive   # с подтверждением каждого шага
make deploy-safe-dry          # проверка без деплоя

# Удаленный деплой
make deploy-remote SSH_KEY=~/.ssh/id_ed25519 SERVER=root@YOUR_SERVER_IP

# Проверка и откат
make health-check
make health-check-verbose
make rollback-info
make rollback-quick           # откат к состоянию до последнего деплоя

# БД
make backup-safe
make restore-safe FILE=backups/db_YYYYMMDD_HHMMSS.sql.gz
```

### Чек-лист перед деплоем

- [ ] Бэкап БД (делается автоматически в `deploy_safe.sh`)
- [ ] Проверен `.env`, доступность БД, свободное место (≥1GB)
- [ ] Все контейнеры запущены
- [ ] По возможности: `make deploy-safe-dry` и `make health-check`

---

## Локальное тестирование Docker

**Требования:** Docker и Docker Compose. Порты 80 и 5432 свободны (или изменены в `docker-compose.yml`).

```bash
cp .env.example .env
# Отредактируйте .env: DATABASE_HOST=db, DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

make build && make up
make createsuperuser
# Откройте http://localhost/
```

**.env для локального теста (минимум):** `DJANGO_SECRET_KEY`, `DEBUG=False`, `DATABASE_*` (host=db), `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1`, при необходимости пустые `EMAIL_*` и `SENTRY_DSN`.

**Полезные команды:** `docker compose ps`, `docker compose logs -f web`, `make shell`, `docker compose exec web python manage.py migrate`.

**Проблемы:** порт 80 занят — в `docker-compose.yml` у nginx задать `"8080:80"`; порт 5432 занят — у db задать `"5433:5432"`.

---

## Подготовка сервера

### Digital Ocean Droplet

- Образ: Ubuntu 22.04 LTS
- Размер: минимум 2GB RAM, 1 vCPU
- Аутентификация: SSH-ключ

### Установка Docker

```bash
apt update && apt upgrade -y
apt install -y apt-transport-https ca-certificates curl gnupg lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt update && apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
docker --version && docker compose version
```

### Клонирование проекта

```bash
cd /opt
git clone https://github.com/santex85/satva_willnes_booking.git
cd satva_willnes_booking
mkdir -p nginx/ssl logs
```

---

## Настройка проекта и переменных окружения

```bash
cp .env.example .env
nano .env
```

Основные переменные для production:

- `DJANGO_SECRET_KEY` — сгенерировать: `openssl rand -hex 32`
- `DEBUG=False`
- `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_HOST=db`, `DATABASE_PORT=5432`
- `DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com,SERVER_IP`
- `EMAIL_*`, `DEFAULT_FROM_EMAIL`
- После настройки SSL: `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`
- По желанию: `SENTRY_DSN`

---

## Запуск контейнеров

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose exec web python manage.py createsuperuser
# Опционально: docker compose exec web python manage.py shell < init_data.py
```

Ожидаются контейнеры: `satva_wellness_db`, `satva_wellness_web`, `satva_wellness_nginx`.

---

## Домен и SSL

### DNS

A-запись домена и www на IP сервера.

### Let's Encrypt (Certbot на хосте)

Сертификаты получают на хосте; nginx в Docker монтирует `/etc/letsencrypt`. Перед первым получением остановите nginx (чтобы порт 80 был свободен):

```bash
cd /opt/satva_willnes_booking   # или ваш путь к проекту
docker compose stop nginx
certbot certonly --standalone -d your-domain.com -d www.your-domain.com
docker compose start nginx
```

В `nginx/nginx.conf` должны быть указаны пути к сертификатам (например `/etc/letsencrypt/live/your-domain.com/fullchain.pem` и `privkey.pem`).

### Автообновление сертификатов

При использовании Certbot в режиме `standalone` порт 80 должен быть свободен во время обновления. Cron (от root):

```bash
crontab -e
```

Добавить (путь к проекту заменить при необходимости):

```cron
0 3 * * * cd /opt/satva_willnes_booking && docker compose stop nginx && certbot renew --quiet --non-interactive && docker compose start nginx
```

---

## Безопасный деплой

Используйте `make deploy-safe` для production: автоматический бэкап БД, проверки до/после, откат при ошибках.

### Фазы скрипта `scripts/deploy_safe.sh`

1. **Подготовка:** проверка Docker, Git, места на диске, контейнеров, .env.
2. **Бэкап:** pg_dump в `backups/db_*.sql.gz`, проверка целостности.
3. **Деплой:** git pull, build web, migrate, collectstatic, docker compose up -d.
4. **Проверка:** статус контейнеров, HTTP health check, БД, миграции, логи.
5. **Откат при сбое:** восстановление БД из бэкапа, откат кода, перезапуск контейнеров.

### Опции

```bash
./scripts/deploy_safe.sh [--dry-run] [--interactive] [--skip-backup]
```

### Вспомогательные скрипты

- **Бэкап:** `./scripts/backup_db.sh` (опции: `--verify`, `--keep-days=30`).
- **Восстановление:** `./scripts/restore_db.sh backups/db_YYYYMMDD_HHMMSS.sql.gz` (по умолчанию с подтверждением).
- **Проверка:** `./scripts/health_check.sh` и `./scripts/health_check.sh --verbose`.
- **Удаленный деплой:** `./scripts/deploy_remote.sh SSH_KEY SERVER` (с опциями `--dry-run`, `--interactive`).

Логи деплоя: `logs/deploy_YYYYMMDD_HHMMSS.log`.

---

## Откат

После успешного деплоя состояние сохраняется в `deploy_state.json`. Быстрый откат к состоянию до последнего деплоя:

```bash
make rollback-info    # информация о последнем деплое
make rollback-quick   # откат с подтверждением
./scripts/rollback_quick.sh --dry-run
./scripts/rollback_quick.sh --confirm   # без подтверждения (опасно)
```

Откат: бэкап текущей БД → checkout предыдущего commit → восстановление БД из бэкапа деплоя → перезапуск контейнеров. Работает только если деплой выполнялся через `deploy_safe.sh`.

---

## Сбор информации с сервера

Перед деплоем можно сохранить конфигурацию сервера (только чтение, ничего не меняется):

```bash
./scripts/collect_server_info.sh ~/.ssh/id_ed25519 root@YOUR_SERVER_IP
```

В корне проекта появится `server_info_YYYYMMDD_HHMMSS.md` с переменными окружения (имена без значений), docker-compose, nginx, БД, SSL, commit, cron, firewall. Отчеты не коммитить — могут содержать чувствительные данные. Подробности: [scripts/SERVER_INFO_COLLECTION.md](scripts/SERVER_INFO_COLLECTION.md).

---

## Мониторинг и бэкапы

### Логи

```bash
docker compose logs -f
docker compose logs -f web
docker compose logs --tail=100 web
```

### Бэкапы БД

Ручной бэкап:

```bash
docker compose exec db pg_dump -U postgres satva_wellness_booking | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

Автоматические бэкапы: скрипт в `/opt/backup.sh` (или аналог) с вызовом pg_dump через `docker compose exec -T db`, затем добавить в cron, например `0 2 * * * /opt/backup.sh`.

### Рекомендации

- Мониторинг доступности (например Uptime Robot).
- Firewall: `ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable`.

---

## Troubleshooting

**Бэкап не создается:** проверить `docker compose ps db`, `df -h`, права на `backups/`.

**Ошибки миграций:** `docker compose logs web`, `docker compose exec web python manage.py showmigrations`; при необходимости откат.

**Контейнеры не запускаются:** `docker compose logs`, `docker compose config`; откат через скрипт при сбое деплоя.

**HTTP health check не проходит:** `docker compose ps nginx`, `docker compose logs nginx`, `docker compose exec nginx nginx -t`.

**502 Bad Gateway:** проверить, что web и nginx запущены, конфиг nginx корректен.

**БД:** `docker compose exec web python manage.py dbshell`, `docker compose exec db pg_isready -U postgres`.

**Статика:** `docker compose exec web python manage.py collectstatic --noinput` и перезапуск nginx.

**Полная пересборка:** `docker compose down -v`, затем `docker compose build --no-cache && docker compose up -d` (осторожно: `-v` удалит данные БД).

---

## Миграция Guest Model

При первом применении миграций после обновления кода выполняется миграция `0011_add_guest_model.py`: создается таблица гостей, данные переносятся из `guest_name`. Время выполнения зависит от количества бронирований. `deploy_safe.sh` создает бэкап перед миграциями. Подробности и риски: [MIGRATION_RISK_ANALYSIS.md](MIGRATION_RISK_ANALYSIS.md).

---

## API

- **JWT:** `POST /api/v1/token/` с `username`, `password`; заголовок `Authorization: Bearer <access>`.
- **Refresh:** `POST /api/v1/token/refresh/` с `refresh`.
- **Расписание специалиста:** `GET /api/v1/my-schedule/` с Bearer-токеном.

---

## Развертывание без Docker (альтернатива)

Вариант без контейнеров: Ubuntu 22.04, Python 3.12+, PostgreSQL 14+, Nginx, Gunicorn.

Кратко: клонирование в `/var/www`, venv, `.env`, миграции, collectstatic, Gunicorn (unix socket), systemd-юнит для Gunicorn, Nginx как reverse proxy к сокету, статика и media через alias. SSL: `certbot --nginx -d domain`. Обновление: `git pull`, `pip install -r requirements.txt`, `migrate`, `collectstatic`, `systemctl restart satva-wellness nginx`.

Детали (PostgreSQL, Gunicorn, Nginx, бэкапы, производительность) при необходимости можно восстановить из истории репозитория; для нового развертывания рекомендуется Docker и разделы выше.
