#!/bin/bash
#
# Скрипт быстрого отката к предыдущему состоянию production
# Использование: ./scripts/rollback_quick.sh [--confirm] [--dry-run] [--info] [--to-state=FILE]
#
# Опции:
#   --confirm      - Пропустить подтверждение (опасно!)
#   --dry-run      - Показать что будет сделано без реального отката
#   --info         - Показать информацию о последнем деплое
#   --to-state=FILE - Откат к конкретному состоянию

set -euo pipefail

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Параметры
CONFIRM=false
DRY_RUN=false
SHOW_INFO=false
STATE_FILE=""

for arg in "$@"; do
    case $arg in
        --confirm)
            CONFIRM=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --info)
            SHOW_INFO=true
            shift
            ;;
        --to-state=*)
            STATE_FILE="${arg#*=}"
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
STATE_FILE_DEFAULT="$PROJECT_DIR/deploy_state.json"
BACKUP_DIR="$PROJECT_DIR/backups"

# Функция логирования
log() {
    local level="$1"
    shift
    local message="$*"
    local color="$NC"
    
    case $level in
        ERROR) color="$RED" ;;
        SUCCESS) color="$GREEN" ;;
        WARNING) color="$YELLOW" ;;
        INFO) color="$BLUE" ;;
    esac
    
    echo -e "${color}[$level]${NC} $message"
}

# Функция проверки JSON файла
check_json_file() {
    local file="$1"
    if [ ! -f "$file" ]; then
        log ERROR "Файл состояния не найден: $file"
        return 1
    fi
    
    # Проверка что это валидный JSON (базовая проверка)
    if ! grep -q "previous_commit\|current_commit" "$file" 2>/dev/null; then
        log ERROR "Файл состояния поврежден или имеет неверный формат: $file"
        return 1
    fi
    
    return 0
}

# Функция чтения состояния из JSON
read_state() {
    local file="$1"
    
    # Используем Python для парсинга JSON (если доступен)
    if command -v python3 &> /dev/null; then
        PREVIOUS_COMMIT=$(python3 -c "import json, sys; data = json.load(open('$file')); print(data.get('previous_commit', ''))" 2>/dev/null || echo "")
        CURRENT_COMMIT=$(python3 -c "import json, sys; data = json.load(open('$file')); print(data.get('current_commit', ''))" 2>/dev/null || echo "")
        BACKUP_FILE=$(python3 -c "import json, sys; data = json.load(open('$file')); print(data.get('backup_file', ''))" 2>/dev/null || echo "")
        DEPLOY_DATE=$(python3 -c "import json, sys; data = json.load(open('$file')); print(data.get('deploy_date', ''))" 2>/dev/null || echo "")
        DEPLOY_LOG=$(python3 -c "import json, sys; data = json.load(open('$file')); print(data.get('deploy_log', ''))" 2>/dev/null || echo "")
    else
        # Fallback: простой парсинг через grep/sed
        PREVIOUS_COMMIT=$(grep -o '"previous_commit": "[^"]*"' "$file" | sed 's/.*: "\(.*\)".*/\1/' || echo "")
        CURRENT_COMMIT=$(grep -o '"current_commit": "[^"]*"' "$file" | sed 's/.*: "\(.*\)".*/\1/' || echo "")
        BACKUP_FILE=$(grep -o '"backup_file": "[^"]*"' "$file" | sed 's/.*: "\(.*\)".*/\1/' || echo "")
        DEPLOY_DATE=$(grep -o '"deploy_date": "[^"]*"' "$file" | sed 's/.*: "\(.*\)".*/\1/' || echo "")
        DEPLOY_LOG=$(grep -o '"deploy_log": "[^"]*"' "$file" | sed 's/.*: "\(.*\)".*/\1/' || echo "")
    fi
}

# Показать информацию о деплое
show_info() {
    local file="${1:-$STATE_FILE_DEFAULT}"
    
    if ! check_json_file "$file"; then
        log ERROR "Не удалось прочитать информацию о деплое"
        log INFO "Проверьте наличие файла: $file"
        exit 1
    fi
    
    read_state "$file"
    
    echo -e "${BLUE}=== Информация о последнем деплое ===${NC}"
    echo "Файл состояния: $file"
    echo ""
    if [ -n "$DEPLOY_DATE" ]; then
        echo "Дата деплоя: $DEPLOY_DATE"
    fi
    if [ -n "$PREVIOUS_COMMIT" ]; then
        echo "Previous commit: $PREVIOUS_COMMIT"
    fi
    if [ -n "$CURRENT_COMMIT" ]; then
        echo "Current commit: $CURRENT_COMMIT"
    fi
    if [ -n "$BACKUP_FILE" ]; then
        echo "Backup file: $BACKUP_FILE"
        if [ -f "$PROJECT_DIR/$BACKUP_FILE" ]; then
            local size=$(stat -f%z "$PROJECT_DIR/$BACKUP_FILE" 2>/dev/null || stat -c%s "$PROJECT_DIR/$BACKUP_FILE" 2>/dev/null || echo "0")
            echo "  Размер: $(numfmt --to=iec-i --suffix=B $size 2>/dev/null || echo "${size}B")"
            echo "  Существует: Да"
        else
            echo "  Существует: Нет"
        fi
    fi
    if [ -n "$DEPLOY_LOG" ]; then
        echo "Deploy log: $DEPLOY_LOG"
        if [ -f "$PROJECT_DIR/$DEPLOY_LOG" ]; then
            echo "  Существует: Да"
        else
            echo "  Существует: Нет"
        fi
    fi
    echo ""
    
    # Проверка commit в git
    if [ -d "$PROJECT_DIR/.git" ] && [ -n "$PREVIOUS_COMMIT" ]; then
        cd "$PROJECT_DIR"
        if git cat-file -e "$PREVIOUS_COMMIT" 2>/dev/null; then
            echo -e "${GREEN}✓ Previous commit существует в git${NC}"
        else
            echo -e "${RED}✗ Previous commit не найден в git${NC}"
        fi
    fi
}

# Основная функция отката
rollback() {
    local file="${1:-$STATE_FILE_DEFAULT}"
    
    log INFO "Начало быстрого отката..."
    
    if [ "$DRY_RUN" = true ]; then
        log INFO "[DRY-RUN] Откат будет выполнен"
        show_info "$file"
        return 0
    fi
    
    # Проверка файла состояния
    if ! check_json_file "$file"; then
        log ERROR "Не удалось прочитать состояние деплоя"
        exit 1
    fi
    
    # Чтение состояния
    read_state "$file"
    
    # Проверка наличия необходимых данных
    if [ -z "$PREVIOUS_COMMIT" ]; then
        log ERROR "Previous commit не указан в файле состояния"
        exit 1
    fi
    
    if [ -z "$BACKUP_FILE" ]; then
        log WARNING "Backup file не указан в файле состояния"
        log WARNING "Будет выполнен только откат кода"
    fi
    
    # Показ информации о том, что будет сделано
    log INFO "Информация об откате:"
    echo "  Previous commit: $PREVIOUS_COMMIT"
    if [ -n "$BACKUP_FILE" ]; then
        echo "  Backup file: $BACKUP_FILE"
    fi
    echo ""
    
    # Подтверждение
    if [ "$CONFIRM" != true ]; then
        echo -e "${YELLOW}⚠️  ВНИМАНИЕ: Откат вернет систему к предыдущему состоянию!${NC}"
        read -p "Продолжить откат? (yes/no): " -r
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            log INFO "Откат отменен пользователем"
            exit 0
        fi
    fi
    
    cd "$PROJECT_DIR"
    
    # Создание бэкапа текущего состояния перед откатом
    log INFO "Создание бэкапа текущего состояния БД перед откатом..."
    PRE_ROLLBACK_BACKUP="$BACKUP_DIR/pre_rollback_$(date +%Y%m%d_%H%M%S).sql.gz"
    if docker compose exec -T db pg_dump -U postgres satva_wellness_booking 2>/dev/null | gzip > "$PRE_ROLLBACK_BACKUP"; then
        log SUCCESS "Бэкап текущего состояния создан: $PRE_ROLLBACK_BACKUP"
    else
        log WARNING "Не удалось создать бэкап текущего состояния"
        if [ "$CONFIRM" != true ]; then
            read -p "Продолжить без бэкапа? (yes/no): " -r
            if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
                log INFO "Откат отменен"
                exit 0
            fi
        fi
    fi
    
    # Откат кода
    if [ -d .git ] && [ -n "$PREVIOUS_COMMIT" ]; then
        log INFO "Откат кода к commit: $PREVIOUS_COMMIT"
        if git checkout "$PREVIOUS_COMMIT" 2>/dev/null; then
            log SUCCESS "Код откачен"
        else
            log ERROR "Не удалось откатить код через git"
            exit 1
        fi
    else
        log WARNING "Не удалось откатить код (git не доступен или commit не указан)"
    fi
    
    # Восстановление БД из бэкапа
    if [ -n "$BACKUP_FILE" ] && [ -f "$PROJECT_DIR/$BACKUP_FILE" ]; then
        log INFO "Восстановление базы данных из бэкапа: $BACKUP_FILE"
        
        # Проверка целостности бэкапа
        if [[ "$BACKUP_FILE" == *.gz ]]; then
            if ! gunzip -t "$PROJECT_DIR/$BACKUP_FILE" 2>/dev/null; then
                log ERROR "Бэкап поврежден: $BACKUP_FILE"
                exit 1
            fi
        fi
        
        # Восстановление
        if [[ "$BACKUP_FILE" == *.gz ]]; then
            if gunzip -c "$PROJECT_DIR/$BACKUP_FILE" | docker compose exec -T db psql -U postgres satva_wellness_booking > /dev/null 2>&1; then
                log SUCCESS "База данных восстановлена"
            else
                log ERROR "Ошибка при восстановлении базы данных"
                # Попытка восстановить из pre-rollback бэкапа
                if [ -f "$PRE_ROLLBACK_BACKUP" ]; then
                    log WARNING "Попытка восстановить из pre-rollback бэкапа..."
                    gunzip -c "$PRE_ROLLBACK_BACKUP" | docker compose exec -T db psql -U postgres satva_wellness_booking > /dev/null 2>&1 || true
                fi
                exit 1
            fi
        else
            if docker compose exec -T db psql -U postgres satva_wellness_booking < "$PROJECT_DIR/$BACKUP_FILE" > /dev/null 2>&1; then
                log SUCCESS "База данных восстановлена"
            else
                log ERROR "Ошибка при восстановлении базы данных"
                exit 1
            fi
        fi
    else
        log WARNING "Файл бэкапа не найден: $BACKUP_FILE"
        log WARNING "БД не будет восстановлена"
    fi
    
    # Перезапуск контейнеров
    log INFO "Перезапуск контейнеров..."
    if docker compose up -d; then
        log SUCCESS "Контейнеры перезапущены"
    else
        log ERROR "Ошибка при перезапуске контейнеров"
        exit 1
    fi
    
    # Ожидание готовности
    log INFO "Ожидание готовности сервисов..."
    sleep 5
    
    # Проверка работоспособности
    log INFO "Проверка работоспособности после отката..."
    if [ -f "$SCRIPT_DIR/health_check.sh" ]; then
        if "$SCRIPT_DIR/health_check.sh" > /dev/null 2>&1; then
            log SUCCESS "Проверка работоспособности пройдена"
        else
            log WARNING "Некоторые проверки не пройдены (проверьте вручную)"
        fi
    fi
    
    log SUCCESS "========================================="
    log SUCCESS "Откат успешно завершен!"
    log SUCCESS "Система возвращена к предыдущему состоянию"
    if [ -f "$PRE_ROLLBACK_BACKUP" ]; then
        log SUCCESS "Бэкап текущего состояния: $PRE_ROLLBACK_BACKUP"
    fi
    log SUCCESS "========================================="
}

# Главная логика
main() {
    if [ "$SHOW_INFO" = true ]; then
        show_info "${STATE_FILE:-$STATE_FILE_DEFAULT}"
        exit 0
    fi
    
    # Определение файла состояния
    if [ -z "$STATE_FILE" ]; then
        STATE_FILE="$STATE_FILE_DEFAULT"
    fi
    
    # Выполнение отката
    rollback "$STATE_FILE"
}

# Запуск
main "$@"