.PHONY: help build up down restart logs shell migrate createsuperuser collectstatic backup

help: ## Показать эту справку
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

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

restore: ## Восстановить базу данных из бэкапа (использовать: make restore FILE=backups/db_20240101_120000.sql.gz)
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make restore FILE=backups/db_YYYYMMDD_HHMMSS.sql.gz"; \
		exit 1; \
	fi
	@docker compose exec -T db psql -U postgres satva_wellness_booking < $(FILE)
	@echo "Database restored from $(FILE)"

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

stats: ## Показать использование ресурсов контейнерами
	docker stats

