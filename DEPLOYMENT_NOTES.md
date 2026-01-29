# Краткие заметки по деплою

## Быстрые команды

### Безопасный деплой (рекомендуется)

```bash
# Автоматический деплой с бэкапом и проверками
make deploy-safe

# С подтверждением каждого шага
make deploy-safe-interactive

# Проверка без реального деплоя
make deploy-safe-dry
```

### Удаленный деплой на сервер

```bash
# Деплой на production сервер
make deploy-remote SSH_KEY=~/.ssh/id_rsa SERVER=root@188.166.240.56
```

### Проверка работоспособности

```bash
# Базовая проверка
make health-check

# Подробная проверка
make health-check-verbose
```

### Откат

```bash
# Быстрый откат к предыдущему состоянию
make rollback-quick

# Информация о последнем деплое
make rollback-info
```

## Чек-лист перед деплоем

### Обязательные проверки

- [ ] Создан бэкап БД (скрипт `deploy_safe.sh` делает это автоматически)
- [ ] Проверены переменные окружения (`.env` файл)
- [ ] Проверена доступность БД
- [ ] Проверено свободное место на диске (минимум 1GB)
- [ ] Все контейнеры запущены и работают

### Рекомендуемые проверки

- [ ] Протестирован деплой в dry-run режиме: `make deploy-safe-dry`
- [ ] Проверены логи на наличие ошибок: `docker compose logs`
- [ ] Проверена работоспособность приложения: `make health-check`

## Важные замечания

### Миграция Guest Model (0011_add_guest_model.py)

Миграция уже включена в код и будет автоматически применена при `python manage.py migrate`.

**Особенности:**
- Время выполнения зависит от количества бронирований (может занять несколько минут)
- Скрипт `deploy_safe.sh` автоматически создает бэкап перед применением миграций
- Миграция обратно совместима - поле `guest_name` остается для совместимости

**Подробнее:** [MIGRATION_RISK_ANALYSIS.md](MIGRATION_RISK_ANALYSIS.md)

## Полезные команды

### Работа с БД

```bash
# Бэкап
make backup-safe

# Восстановление
make restore-safe FILE=backups/db_YYYYMMDD_HHMMSS.sql.gz

# Миграции
make migrate
```

### Проверка статуса

```bash
# Статус контейнеров
docker compose ps

# Логи
docker compose logs -f web
```

## Документация

- [DEPLOYMENT.md](DEPLOYMENT.md) - Общая инструкция по развертыванию
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) - Деплой с Docker
- [DEPLOY_SAFE.md](DEPLOY_SAFE.md) - Безопасный деплой с бэкапами
- [MIGRATION_RISK_ANALYSIS.md](MIGRATION_RISK_ANALYSIS.md) - Анализ рисков миграции Guest
- [ROLLBACK_QUICK.md](ROLLBACK_QUICK.md) - Быстрый откат
- [TESTING.md](TESTING.md) - Руководство по тестированию

## Troubleshooting

### Миграция Guest не применяется

```bash
# Проверка статуса миграций
docker compose exec web python manage.py showmigrations

# Принудительное применение
docker compose exec web python manage.py migrate --run-syncdb
```

### Ошибки при деплое

1. Проверьте логи: `docker compose logs web`
2. Проверьте статус контейнеров: `docker compose ps`
3. Выполните откат: `make rollback-quick`
4. Проверьте бэкап: `ls -lth backups/`

### Проблемы с БД

```bash
# Проверка подключения
docker compose exec web python manage.py dbshell

# Проверка статуса БД
docker compose exec db pg_isready -U postgres
```
