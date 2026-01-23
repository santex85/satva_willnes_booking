#!/bin/bash
#
# Улучшенный скрипт восстановления базы данных из бэкапа
# Использование: ./scripts/restore_db.sh <backup_file> [--confirm]
#
# Опции:
#   --confirm - Пропустить подтверждение (опасно!)

set -euo pipefail

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Параметры
CONFIRM=false
BACKUP_FILE=""

for arg in "$@"; do
    case $arg in
        --confirm)
            CONFIRM=true
            shift
            ;;
        *)
            if [ -z "$BACKUP_FILE" ]; then
                BACKUP_FILE="$arg"
            fi
            shift
            ;;
    esac
done

# Проверка параметров
if [ -z "$BACKUP_FILE" ]; then
    echo -e "${RED}Ошибка: Укажите файл бэкапа${NC}"
    echo "Использование: $0 <backup_file> [--confirm]"
    exit 1
fi

# Константы
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"

# Проверка существования файла
if [ ! -f "$BACKUP_FILE" ]; then
    # Попробуем найти в директории backups
    if [ -f "$BACKUP_DIR/$BACKUP_FILE" ]; then
        BACKUP_FILE="$BACKUP_DIR/$BACKUP_FILE"
    else
        echo -e "${RED}Ошибка: Файл бэкапа не найден: $BACKUP_FILE${NC}"
        exit 1
    fi
fi

echo -e "${YELLOW}⚠️  ВНИМАНИЕ: Восстановление базы данных удалит все текущие данные!${NC}"
echo -e "${BLUE}Файл бэкапа: $BACKUP_FILE${NC}"

# Проверка целостности бэкапа
echo -e "${BLUE}Проверка целостности бэкапа...${NC}"
if [[ "$BACKUP_FILE" == *.gz ]]; then
    if ! gunzip -t "$BACKUP_FILE" 2>/dev/null; then
        echo -e "${RED}Ошибка: Бэкап поврежден${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Бэкап корректен${NC}"
else
    echo -e "${YELLOW}Предупреждение: Файл не сжат, проверка целостности пропущена${NC}"
fi

# Подтверждение
if [ "$CONFIRM" != true ]; then
    read -p "Продолжить восстановление? (yes/no): " -r
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo -e "${YELLOW}Восстановление отменено${NC}"
        exit 0
    fi
fi

# Проверка доступности БД
if ! docker compose ps db 2>/dev/null | grep -q "Up"; then
    echo -e "${RED}Ошибка: Контейнер БД не запущен${NC}"
    exit 1
fi

# Создание бэкапа перед восстановлением
echo -e "${BLUE}Создание бэкапа текущего состояния БД...${NC}"
PRE_RESTORE_BACKUP="$BACKUP_DIR/pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
if docker compose exec -T db pg_dump -U postgres satva_wellness_booking 2>/dev/null | gzip > "$PRE_RESTORE_BACKUP"; then
    echo -e "${GREEN}✓ Бэкап текущего состояния создан: $PRE_RESTORE_BACKUP${NC}"
else
    echo -e "${YELLOW}⚠️  Не удалось создать бэкап текущего состояния${NC}"
    if [ "$CONFIRM" != true ]; then
        read -p "Продолжить без бэкапа? (yes/no): " -r
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            echo -e "${YELLOW}Восстановление отменено${NC}"
            exit 0
        fi
    fi
fi

# Восстановление
echo -e "${BLUE}Восстановление базы данных...${NC}"

# Очистка текущей БД (опционально, можно заменить на DROP DATABASE)
echo -e "${BLUE}Очистка текущей базы данных...${NC}"
docker compose exec -T db psql -U postgres -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" satva_wellness_booking 2>/dev/null || true

# Восстановление из бэкапа
if [[ "$BACKUP_FILE" == *.gz ]]; then
    if gunzip -c "$BACKUP_FILE" | docker compose exec -T db psql -U postgres satva_wellness_booking > /dev/null 2>&1; then
        echo -e "${GREEN}✓ База данных восстановлена${NC}"
    else
        echo -e "${RED}Ошибка при восстановлении базы данных${NC}"
        echo -e "${YELLOW}Попытка восстановить из pre-restore бэкапа...${NC}"
        if [ -f "$PRE_RESTORE_BACKUP" ]; then
            gunzip -c "$PRE_RESTORE_BACKUP" | docker compose exec -T db psql -U postgres satva_wellness_booking > /dev/null 2>&1 || true
        fi
        exit 1
    fi
else
    if docker compose exec -T db psql -U postgres satva_wellness_booking < "$BACKUP_FILE" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ База данных восстановлена${NC}"
    else
        echo -e "${RED}Ошибка при восстановлении базы данных${NC}"
        exit 1
    fi
fi

# Проверка восстановления
echo -e "${BLUE}Проверка восстановления...${NC}"
TABLE_COUNT=$(docker compose exec -T db psql -U postgres -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" satva_wellness_booking 2>/dev/null | tr -d ' ' || echo "0")
if [ "$TABLE_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ База данных восстановлена успешно (таблиц: $TABLE_COUNT)${NC}"
else
    echo -e "${RED}Ошибка: База данных пуста после восстановления${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Восстановление завершено успешно${NC}"
