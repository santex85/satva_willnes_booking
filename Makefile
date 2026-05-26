.PHONY: help build up down restart logs shell migrate createsuperuser collectstatic backup backup-safe restore restore-safe deploy deploy-full deploy-safe deploy-remote health-check dev dev-stop dev-logs dev-restart

help: ## Показать эту справку
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

dev: ## Полный перезапуск локальной разработки (DB + Django:8002 + Vite:5173)
	@chmod +x scripts/dev.sh
	@./scripts/dev.sh start

dev-stop: ## Остановить локальные dev-сервисы (Django + Vite)
	@chmod +x scripts/dev.sh
	@./scripts/dev.sh stop

dev-restart: ## Перезапустить dev-сервисы
	@chmod +x scripts/dev.sh
	@./scripts/dev.sh restart

dev-logs: ## Показать логи Django и Vite
	@tail -f .dev/django.log .dev/vite.log

build: ## Собрать Docker образы
	docker compose build

up: ## Запустить контейнеры в фоновом режиме
	docker compose up -d

down: ## Остановить и удалить контейнеры
	docker compose down

restart: ## Перезапустить контейнеры
	docker compose restart

logs: ## Показать логи всех контейнеров
	docker compose logs -f

logs-web: ## Показать логи веб-сервера
	docker compose logs -f web

logs-db: ## Показать логи базы данных
	docker compose logs -f db

logs-nginx: ## Показать логи Nginx
	docker compose logs -f nginx

shell: ## Войти в контейнер Django
	docker compose exec web bash

shell-db: ## Войти в контейнер PostgreSQL
	docker compose exec db psql -U postgres satva_wellness_booking

migrate: ## Применить миграции базы данных
	docker compose exec web python manage.py migrate

makemigrations: ## Создать новые миграции
	docker compose exec web python manage.py makemigrations

createsuperuser: ## Создать суперпользователя
	docker compose exec web python manage.py createsuperuser

collectstatic: ## Собрать статические файлы
	docker compose exec web python manage.py collectstatic --noinput

shell-django: ## Django shell
	docker compose exec web python manage.py shell

test: ## Запустить тесты
	docker compose exec web python manage.py test

status: ## Показать статус контейнеров
	docker compose ps

backup: ## Создать резервную копию базы данных
	@mkdir -p backups
	@docker compose exec -T db pg_dump -U postgres satva_wellness_booking | gzip > backups/db_$$(date +%Y%m%d_%H%M%S).sql.gz
	@echo "Backup created in backups/"

backup-safe: ## Создать резервную копию с проверкой целостности
	@./scripts/backup_db.sh --verify

restore: ## Восстановить базу данных из бэкапа (использовать: make restore FILE=backups/db_20240101_120000.sql.gz)
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make restore FILE=backups/db_YYYYMMDD_HHMMSS.sql.gz"; \
		exit 1; \
	fi
	@if [[ "$(FILE)" == *.gz ]]; then \
		gunzip -c $(FILE) | docker compose exec -T db psql -U postgres satva_wellness_booking; \
	else \
		docker compose exec -T db psql -U postgres satva_wellness_booking < $(FILE); \
	fi
	@echo "Database restored from $(FILE)"

restore-safe: ## Безопасное восстановление базы данных (использовать: make restore-safe FILE=backups/db_20240101_120000.sql.gz)
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make restore-safe FILE=backups/db_YYYYMMDD_HHMMSS.sql.gz"; \
		exit 1; \
	fi
	@./scripts/restore_db.sh $(FILE)

clean: ## Очистить неиспользуемые Docker ресурсы
	docker system prune -f

clean-all: ## Остановить контейнеры и удалить volumes (ОСТОРОЖНО: удалит данные!)
	docker compose down -v
	docker system prune -af

rebuild: ## Пересобрать образы без кэша и перезапустить
	docker compose build --no-cache
	docker compose up -d

update: ## Обновить код и перезапустить (git pull + rebuild)
	git pull origin main
	docker compose build
	docker compose up -d
	docker compose exec web python manage.py migrate
	docker compose exec web python manage.py collectstatic --noinput

deploy: ## Деплой: собрать web, миграции, статика, перезапуск и логи
	@echo "🚀 Начинаем деплой..."
	@echo "📦 Сборка образа web..."
	docker compose build web
	@echo "🗄️  Применение миграций..."
	docker compose exec web python manage.py migrate
	@echo "📁 Сборка статических файлов..."
	docker compose exec web python manage.py collectstatic --noinput
	@echo "🔄 Перезапуск контейнеров..."
	docker compose up -d
	@echo "📊 Статус контейнеров:"
	docker compose ps
	@echo "📋 Последние 50 строк логов web:"
	docker compose logs --tail=50 web
	@echo "✅ Деплой завершен!"

deploy-full: ## Полный деплой: git pull + deploy
	@echo "🔄 Обновление кода из git..."
	git pull origin main
	@echo "🚀 Начинаем деплой..."
	@echo "📦 Сборка образа web..."
	docker compose build web
	@echo "🗄️  Применение миграций..."
	docker compose exec web python manage.py migrate
	@echo "📁 Сборка статических файлов..."
	docker compose exec web python manage.py collectstatic --noinput
	@echo "🔄 Перезапуск контейнеров..."
	docker compose up -d
	@echo "📊 Статус контейнеров:"
	docker compose ps
	@echo "📋 Последние 50 строк логов web:"
	docker compose logs --tail=50 web
	@echo "✅ Деплой завершен!"

stats: ## Показать использование ресурсов контейнерами
	docker stats

deploy-safe: ## Безопасный деплой с автоматическим бэкапом и проверками
	@./scripts/deploy_safe.sh

deploy-safe-dry: ## Безопасный деплой в режиме проверки (без реальных изменений)
	@./scripts/deploy_safe.sh --dry-run

deploy-safe-interactive: ## Безопасный деплой с подтверждением каждого шага
	@./scripts/deploy_safe.sh --interactive

deploy-remote: ## Удаленный деплой на сервере через SSH (использовать: make deploy-remote SSH_KEY=~/.ssh/id_rsa SERVER=root@188.166.240.56)
	@if [ -z "$(SSH_KEY)" ] || [ -z "$(SERVER)" ]; then \
		echo "Usage: make deploy-remote SSH_KEY=~/.ssh/id_rsa SERVER=root@188.166.240.56"; \
		exit 1; \
	fi
	@./scripts/deploy_remote.sh $(SSH_KEY) $(SERVER)

health-check: ## Проверка работоспособности приложения
	@./scripts/health_check.sh

health-check-verbose: ## Проверка работоспособности с подробным выводом
	@./scripts/health_check.sh --verbose

test-deploy: ## Тестирование скриптов деплоя (безопасно, без изменений)
	@./scripts/test_deploy.sh

test-deploy-full: ## Полное тестирование скриптов деплоя (включая проверку функций)
	@./scripts/test_deploy.sh --full

rollback-quick: ## Быстрый откат к предыдущему состоянию (после деплоя)
	@./scripts/rollback_quick.sh

rollback-info: ## Показать информацию о последнем деплое
	@./scripts/rollback_quick.sh --info

