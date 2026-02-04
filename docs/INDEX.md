# Индекс документации проекта

## Все документы

| Файл | Назначение |
|------|------------|
| [README.md](../README.md) | Описание проекта, установка, первичная настройка, API |
| [DEPLOYMENT.md](../DEPLOYMENT.md) | Развертывание: Docker, безопасный деплой, откат, SSL, бэкапы, сбор информации |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Участие в проекте, окружение, стиль кода, коммиты |
| [TESTING.md](../TESTING.md) | Тестирование скриптов деплоя (dry-run, бэкапы, health-check) |
| [MIGRATION_RISK_ANALYSIS.md](../MIGRATION_RISK_ANALYSIS.md) | Риски и рекомендации по миграции Guest Model |
| [scripts/SERVER_INFO_COLLECTION.md](../scripts/SERVER_INFO_COLLECTION.md) | Детали работы скрипта сбора информации с сервера |

## Быстрый доступ

- **Начало работы:** [README.md](../README.md), [CONTRIBUTING.md](../CONTRIBUTING.md)
- **Деплой и операции:** [DEPLOYMENT.md](../DEPLOYMENT.md)
- **Тестирование деплоя:** [TESTING.md](../TESTING.md)
- **Миграция Guest:** [MIGRATION_RISK_ANALYSIS.md](../MIGRATION_RISK_ANALYSIS.md)
- **Сбор информации с сервера:** [DEPLOYMENT.md](../DEPLOYMENT.md#сбор-информации-с-сервера), [scripts/SERVER_INFO_COLLECTION.md](../scripts/SERVER_INFO_COLLECTION.md)

## Рекомендуемый порядок

**Деплой на production:** DEPLOYMENT.md → при первом использовании скриптов TESTING.md → при миграции Guest MIGRATION_RISK_ANALYSIS.md.

**Поиск по темам:** деплой, Docker, бэкапы, откат, SSL — DEPLOYMENT.md; тесты деплоя — TESTING.md; миграция Guest — MIGRATION_RISK_ANALYSIS.md.

## Обновление документации

При добавлении или изменении функциональности деплоя, миграций или скриптов обновите соответствующий раздел в DEPLOYMENT.md или TESTING.md и при необходимости этот индекс.
