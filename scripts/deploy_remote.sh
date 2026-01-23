#!/bin/bash
#
# Скрипт для удаленного деплоя на сервере через SSH
# Использование: ./scripts/deploy_remote.sh [SSH_KEY] [SERVER] [--dry-run] [--interactive]
#
# Пример: ./scripts/deploy_remote.sh ~/.ssh/id_rsa root@188.166.240.56

set -euo pipefail

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Параметры
SSH_KEY="${1:-~/.ssh/id_rsa}"
SERVER="${2:-root@188.166.240.56}"
DRY_RUN=false
INTERACTIVE=false

# Обработка дополнительных параметров
shift 2 2>/dev/null || true
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
        *)
            echo -e "${RED}Неизвестный параметр: $arg${NC}"
            exit 1
            ;;
    esac
done

# Функция выполнения команд на сервере
ssh_exec() {
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$SERVER" "$@"
}

# Функция копирования файлов
scp_copy() {
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no "$1" "$SERVER:$2"
}

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

# Проверка подключения
log INFO "Проверка подключения к серверу $SERVER..."
if ! ssh_exec "echo 'Connection OK'" > /dev/null 2>&1; then
    log ERROR "Не удалось подключиться к серверу"
    echo "Проверьте:"
    echo "  1. SSH ключ: $SSH_KEY"
    echo "  2. Адрес сервера: $SERVER"
    echo "  3. Доступность сервера"
    exit 1
fi
log SUCCESS "Подключение установлено"

# Поиск проекта на сервере
log INFO "Поиск проекта на сервере..."
PROJECT_PATH=$(ssh_exec "find /opt /var/www /home -type d -name '*satva*' -o -name '*wellness*' -o -name '*booking*' 2>/dev/null | head -1" || echo "")
if [ -z "$PROJECT_PATH" ]; then
    PROJECT_PATH=$(ssh_exec "docker compose ps 2>/dev/null | head -1 | awk '{print \$NF}' | xargs -I {} docker inspect {} --format '{{.Config.Labels.com.docker.compose.project.working_dir}}' 2>/dev/null | head -1" || echo "")
fi

if [ -z "$PROJECT_PATH" ]; then
    log WARNING "Проект не найден автоматически"
    read -p "Введите путь к проекту на сервере: " PROJECT_PATH
    if [ -z "$PROJECT_PATH" ]; then
        log ERROR "Путь к проекту не указан"
        exit 1
    fi
else
    log SUCCESS "Найден проект: $PROJECT_PATH"
fi

# Проверка наличия скрипта деплоя на сервере
log INFO "Проверка наличия скрипта деплоя на сервере..."
if ! ssh_exec "test -f $PROJECT_PATH/scripts/deploy_safe.sh" 2>/dev/null; then
    log WARNING "Скрипт deploy_safe.sh не найден на сервере"
    log INFO "Копирование скрипта на сервер..."
    
    if [ "$DRY_RUN" = true ]; then
        log INFO "[DRY-RUN] Скрипт будет скопирован"
    else
        # Создание директории scripts на сервере
        ssh_exec "mkdir -p $PROJECT_PATH/scripts"
        
        # Копирование скрипта
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        scp_copy "$SCRIPT_DIR/deploy_safe.sh" "$PROJECT_PATH/scripts/deploy_safe.sh"
        ssh_exec "chmod +x $PROJECT_PATH/scripts/deploy_safe.sh"
        
        log SUCCESS "Скрипт скопирован на сервер"
    fi
else
    log SUCCESS "Скрипт deploy_safe.sh найден на сервере"
fi

# Подготовка параметров для деплоя
DEPLOY_ARGS=""
if [ "$DRY_RUN" = true ]; then
    DEPLOY_ARGS="--dry-run"
fi
if [ "$INTERACTIVE" = true ]; then
    DEPLOY_ARGS="$DEPLOY_ARGS --interactive"
fi

# Выполнение деплоя
log INFO "Запуск безопасного деплоя на сервере..."
log INFO "Команда: cd $PROJECT_PATH && ./scripts/deploy_safe.sh $DEPLOY_ARGS"

if [ "$DRY_RUN" = true ]; then
    log INFO "[DRY-RUN] Деплой будет выполнен"
    ssh_exec "cd $PROJECT_PATH && ./scripts/deploy_safe.sh $DEPLOY_ARGS" || true
else
    if ssh_exec "cd $PROJECT_PATH && ./scripts/deploy_safe.sh $DEPLOY_ARGS"; then
        log SUCCESS "Деплой успешно завершен"
    else
        log ERROR "Ошибка при выполнении деплоя"
        exit 1
    fi
fi

# Проверка работоспособности
log INFO "Проверка работоспособности после деплоя..."
if ssh_exec "cd $PROJECT_PATH && test -f scripts/health_check.sh && ./scripts/health_check.sh" 2>/dev/null; then
    log SUCCESS "Все проверки пройдены"
else
    log WARNING "Некоторые проверки не пройдены (возможно скрипт health_check.sh отсутствует)"
fi

log SUCCESS "Удаленный деплой завершен"
