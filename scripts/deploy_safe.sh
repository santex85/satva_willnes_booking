#!/bin/bash
#
# Скрипт безопасного деплоя с автоматическим бэкапом БД
# Использование: ./scripts/deploy_safe.sh [--dry-run] [--interactive] [--skip-backup]
#
# Опции:
#   --dry-run       - Проверка без реального деплоя
#   --interactive   - Подтверждение каждого шага
#   --skip-backup   - Пропустить создание бэкапа (не рекомендуется)

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Флаги
DRY_RUN=false
INTERACTIVE=false
SKIP_BACKUP=false

# Параметры
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --interactive)
            INTERACTIVE=true
            shift
            ;;
        --skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        *)
            echo -e "${RED}Неизвестный параметр: $arg${NC}"
            exit 1
            ;;
    esac
done

# Константы
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
LOG_DIR="$PROJECT_DIR/logs"
DEPLOY_LOG="$LOG_DIR/deploy_$(date +%Y%m%d_%H%M%S).log"
BACKUP_FILE=""
PREVIOUS_COMMIT=""
CURRENT_COMMIT=""
ROLLBACK_NEEDED=false

# Создание директорий
mkdir -p "$BACKUP_DIR" "$LOG_DIR"

# Функция логирования
log_action() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$DEPLOY_LOG"
    
    case $level in
        ERROR)
            echo -e "${RED}[ERROR]${NC} $message" >&2
            ;;
        WARNING)
            echo -e "${YELLOW}[WARNING]${NC} $message"
            ;;
        SUCCESS)
            echo -e "${GREEN}[SUCCESS]${NC} $message"
            ;;
        INFO)
            echo -e "${BLUE}[INFO]${NC} $message"
            ;;
    esac
}

# Функция подтверждения
confirm() {
    if [ "$INTERACTIVE" = true ]; then
        read -p "$1 (y/N): " -n 1 -r
        echo
        [[ $REPLY =~ ^[Yy]$ ]]
    else
        return 0
    fi
}

# Функция проверки команды
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_action ERROR "Команда $1 не найдена"
        return 1
    fi
    return 0
}

# Функция проверки контейнера
check_container() {
    local container="$1"
    if docker compose ps "$container" 2>/dev/null | grep -q "Up"; then
        return 0
    else
        return 1
    fi
}

# Функция создания бэкапа БД
create_backup() {
    log_action INFO "Создание резервной копии базы данных..."
    
    if [ "$SKIP_BACKUP" = true ]; then
        log_action WARNING "Создание бэкапа пропущено (--skip-backup)"
        return 0
    fi
    
    BACKUP_FILE="$BACKUP_DIR/db_$(date +%Y%m%d_%H%M%S).sql.gz"
    
    if [ "$DRY_RUN" = true ]; then
        log_action INFO "[DRY-RUN] Бэкап будет создан: $BACKUP_FILE"
        return 0
    fi
    
    # Проверка доступности БД
    if ! check_container db; then
        log_action ERROR "Контейнер БД не запущен"
        return 1
    fi
    
    # Создание бэкапа
    if docker compose exec -T db pg_dump -U postgres satva_wellness_booking 2>/dev/null | gzip > "$BACKUP_FILE"; then
        # Проверка целостности
        if [ -f "$BACKUP_FILE" ] && [ -s "$BACKUP_FILE" ]; then
            local size=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
            if [ "$size" -gt 1000 ]; then
                log_action SUCCESS "Бэкап создан: $BACKUP_FILE (размер: $(numfmt --to=iec-i --suffix=B $size 2>/dev/null || echo "${size}B"))"
                return 0
            else
                log_action ERROR "Бэкап слишком маленький, возможно ошибка"
                rm -f "$BACKUP_FILE"
                return 1
            fi
        else
            log_action ERROR "Бэкап не был создан"
            return 1
        fi
    else
        log_action ERROR "Ошибка при создании бэкапа"
        return 1
    fi
}

# Функция проверки перед деплоем
pre_deployment_checks() {
    log_action INFO "Выполнение проверок перед деплоем..."
    
    local errors=0
    
    # Проверка команд
    for cmd in docker git; do
        if ! check_command "$cmd"; then
            ((errors++))
        fi
    done
    
    # Проверка docker compose
    if ! docker compose version &>/dev/null; then
        log_action ERROR "Docker Compose не доступен"
        ((errors++))
    fi
    
    # Проверка свободного места
    local available_space=$(df "$PROJECT_DIR" | tail -1 | awk '{print $4}')
    if [ "$available_space" -lt 1048576 ]; then  # Меньше 1GB
        log_action WARNING "Мало свободного места: ${available_space}KB"
    fi
    
    # Проверка статуса контейнеров
    if ! check_container db; then
        log_action ERROR "Контейнер БД не запущен"
        ((errors++))
    fi
    
    # Проверка git
    cd "$PROJECT_DIR"
    if [ -d .git ]; then
        PREVIOUS_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "")
        CURRENT_COMMIT=$(git rev-parse origin/main 2>/dev/null || echo "")
        
        if [ -n "$CURRENT_COMMIT" ] && [ "$PREVIOUS_COMMIT" != "$CURRENT_COMMIT" ]; then
            log_action INFO "Обнаружены изменения в git: $PREVIOUS_COMMIT -> $CURRENT_COMMIT"
        else
            log_action WARNING "Нет новых изменений в git"
        fi
    fi
    
    # Проверка переменных окружения
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        log_action WARNING "Файл .env не найден"
    fi
    
    if [ $errors -gt 0 ]; then
        log_action ERROR "Обнаружено $errors ошибок при проверке"
        return 1
    fi
    
    log_action SUCCESS "Все проверки пройдены"
    return 0
}

# Функция деплоя приложения
deploy_application() {
    log_action INFO "Начало деплоя приложения..."
    
    if [ "$DRY_RUN" = true ]; then
        log_action INFO "[DRY-RUN] Деплой будет выполнен"
        return 0
    fi
    
    cd "$PROJECT_DIR"
    
    # Обновление кода из git
    if [ -d .git ]; then
        log_action INFO "Обновление кода из git..."
        
        # Проверка на конфликтующие неотслеживаемые файлы
        log_action INFO "Проверка на конфликтующие файлы..."
        CONFLICTING_FILES=$(git status --porcelain 2>/dev/null | grep '^??' | awk '{print $2}' | grep -E '^scripts/(deploy_safe|rollback_quick|save_deploy_state|backup_db|restore_db|health_check|deploy_remote|collect_server_info|test_deploy)\.sh$' || true)
        
        if [ -n "$CONFLICTING_FILES" ]; then
            log_action WARNING "Обнаружены конфликтующие файлы, удаление перед git pull..."
            echo "$CONFLICTING_FILES" | xargs rm -f 2>/dev/null || true
        fi
        
        if ! git pull origin main; then
            log_action ERROR "Ошибка при обновлении кода из git"
            return 1
        fi
        CURRENT_COMMIT=$(git rev-parse HEAD)
        log_action SUCCESS "Код обновлен до commit: $CURRENT_COMMIT"
    fi
    
    # Сборка образа
    log_action INFO "Сборка Docker образа..."
    if ! docker compose build web; then
        log_action ERROR "Ошибка при сборке образа"
        ROLLBACK_NEEDED=true
        return 1
    fi
    
    # Применение миграций
    log_action INFO "Применение миграций базы данных..."
    if ! docker compose exec web python manage.py migrate --noinput; then
        log_action ERROR "Ошибка при применении миграций"
        ROLLBACK_NEEDED=true
        return 1
    fi
    
    # Сбор статических файлов
    log_action INFO "Сбор статических файлов..."
    if ! docker compose exec web python manage.py collectstatic --noinput --clear; then
        log_action WARNING "Ошибка при сборе статических файлов (не критично)"
    fi
    
    # Перезапуск контейнеров
    log_action INFO "Перезапуск контейнеров..."
    if ! docker compose up -d; then
        log_action ERROR "Ошибка при перезапуске контейнеров"
        ROLLBACK_NEEDED=true
        return 1
    fi
    
    # Ожидание готовности сервисов
    log_action INFO "Ожидание готовности сервисов..."
    sleep 5
    
    log_action SUCCESS "Деплой выполнен успешно"
    return 0
}

# Функция проверки после деплоя
post_deployment_checks() {
    log_action INFO "Выполнение проверок после деплоя..."
    
    local errors=0
    
    # Проверка статуса контейнеров
    log_action INFO "Проверка статуса контейнеров..."
    for container in db web nginx; do
        if check_container "$container"; then
            log_action SUCCESS "Контейнер $container запущен"
        else
            log_action ERROR "Контейнер $container не запущен"
            ((errors++))
        fi
    done
    
    # HTTP health check
    log_action INFO "Проверка доступности веб-сервера..."
    sleep 3
    if curl -f -s -o /dev/null -w "%{http_code}" http://localhost/ > /dev/null 2>&1; then
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null || echo "000")
        if [ "$http_code" = "200" ] || [ "$http_code" = "301" ] || [ "$http_code" = "302" ]; then
            log_action SUCCESS "Веб-сервер доступен (HTTP $http_code)"
        else
            log_action WARNING "Веб-сервер вернул код: $http_code"
        fi
    else
        log_action WARNING "Не удалось проверить доступность веб-сервера"
    fi
    
    # Проверка подключения к БД
    log_action INFO "Проверка подключения к базе данных..."
    if docker compose exec -T web python manage.py check --database default 2>/dev/null | grep -q "System check identified no issues"; then
        log_action SUCCESS "Подключение к БД работает"
    else
        log_action WARNING "Проблемы с проверкой БД (возможно не критично)"
    fi
    
    # Проверка миграций
    log_action INFO "Проверка статуса миграций..."
    if docker compose exec -T web python manage.py showmigrations --plan 2>/dev/null | grep -q "\[ \]"; then
        log_action WARNING "Есть непримененные миграции"
    else
        log_action SUCCESS "Все миграции применены"
    fi
    
    # Проверка логов на ошибки
    log_action INFO "Проверка логов на ошибки..."
    local error_count=$(docker compose logs --tail=100 web 2>/dev/null | grep -i "error\|exception\|traceback" | wc -l || echo "0")
    if [ "$error_count" -gt 0 ]; then
        log_action WARNING "Обнаружено $error_count ошибок в логах (последние 100 строк)"
        docker compose logs --tail=50 web | grep -i "error\|exception" | head -5
    else
        log_action SUCCESS "Критических ошибок в логах не обнаружено"
    fi
    
    if [ $errors -gt 0 ]; then
        log_action ERROR "Обнаружено $errors критических ошибок после деплоя"
        return 1
    fi
    
    log_action SUCCESS "Все проверки после деплоя пройдены"
    return 0
}

# Функция отката
rollback_deployment() {
    log_action WARNING "Начало отката деплоя..."
    
    if [ "$DRY_RUN" = true ]; then
        log_action INFO "[DRY-RUN] Откат будет выполнен"
        return 0
    fi
    
    cd "$PROJECT_DIR"
    
    # Откат кода
    if [ -n "$PREVIOUS_COMMIT" ] && [ -d .git ]; then
        log_action INFO "Откат кода к предыдущему commit: $PREVIOUS_COMMIT"
        if git checkout "$PREVIOUS_COMMIT" 2>/dev/null; then
            log_action SUCCESS "Код откачен"
        else
            log_action WARNING "Не удалось откатить код через git"
        fi
    fi
    
    # Восстановление БД из бэкапа
    if [ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ]; then
        log_action INFO "Восстановление базы данных из бэкапа: $BACKUP_FILE"
        if confirm "Восстановить базу данных из бэкапа?"; then
            if gunzip -c "$BACKUP_FILE" | docker compose exec -T db psql -U postgres satva_wellness_booking > /dev/null 2>&1; then
                log_action SUCCESS "База данных восстановлена"
            else
                log_action ERROR "Ошибка при восстановлении базы данных"
            fi
        fi
    fi
    
    # Перезапуск контейнеров
    log_action INFO "Перезапуск контейнеров..."
    docker compose up -d
    
    log_action WARNING "Откат завершен"
}

# Главная функция
main() {
    log_action INFO "========================================="
    log_action INFO "Начало безопасного деплоя"
    log_action INFO "Лог файл: $DEPLOY_LOG"
    if [ "$DRY_RUN" = true ]; then
        log_action INFO "РЕЖИМ ПРОВЕРКИ (dry-run) - изменения не будут применены"
    fi
    log_action INFO "========================================="
    
    # Фаза 1: Подготовка
    if ! pre_deployment_checks; then
        log_action ERROR "Проверки перед деплоем не пройдены"
        exit 1
    fi
    
    if ! confirm "Продолжить деплой?"; then
        log_action INFO "Деплой отменен пользователем"
        exit 0
    fi
    
    # Фаза 2: Создание бэкапа
    if ! create_backup; then
        log_action ERROR "Не удалось создать бэкап"
        if ! confirm "Продолжить без бэкапа? (НЕ РЕКОМЕНДУЕТСЯ)"; then
            log_action INFO "Деплой отменен"
            exit 1
        fi
    fi
    
    # Фаза 3: Деплой
    if ! deploy_application; then
        log_action ERROR "Ошибка при деплое"
        if [ "$ROLLBACK_NEEDED" = true ]; then
            if confirm "Выполнить автоматический откат?"; then
                rollback_deployment
            fi
        fi
        exit 1
    fi
    
    # Фаза 4: Проверка после деплоя
    if ! post_deployment_checks; then
        log_action ERROR "Проверки после деплоя не пройдены"
        if confirm "Выполнить откат?"; then
            rollback_deployment
        fi
        exit 1
    fi
    
    # Успешное завершение
    log_action SUCCESS "========================================="
    log_action SUCCESS "Деплой успешно завершен!"
    log_action SUCCESS "Бэкап: $BACKUP_FILE"
    log_action SUCCESS "Commit: $CURRENT_COMMIT"
    log_action SUCCESS "Лог: $DEPLOY_LOG"
    log_action SUCCESS "========================================="
    
    # Сохранение состояния деплоя для быстрого отката
    if [ "$DRY_RUN" != true ] && [ -n "$PREVIOUS_COMMIT" ] && [ -n "$CURRENT_COMMIT" ]; then
        log_action INFO "Сохранение состояния деплоя для быстрого отката..."
        if [ -f "$SCRIPT_DIR/save_deploy_state.sh" ]; then
            if "$SCRIPT_DIR/save_deploy_state.sh" "$PREVIOUS_COMMIT" "$CURRENT_COMMIT" "$BACKUP_FILE" "$DEPLOY_LOG" > /dev/null 2>&1; then
                log_action SUCCESS "Состояние деплоя сохранено (для быстрого отката используйте: make rollback-quick)"
            else
                log_action WARNING "Не удалось сохранить состояние деплоя (не критично)"
            fi
        fi
    fi
}

# Обработка ошибок
trap 'log_action ERROR "Критическая ошибка на строке $LINENO"; exit 1' ERR

# Запуск
main "$@"
