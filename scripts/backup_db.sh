#!/bin/bash
#
# Улучшенный скрипт создания резервной копии базы данных
# Использование: ./scripts/backup_db.sh [--verify] [--keep-days N]
#
# Опции:
#   --verify      - Проверить целостность бэкапа после создания
#   --keep-days N - Удалить бэкапы старше N дней (по умолчанию 30)

set -euo pipefail

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Параметры
VERIFY=false
KEEP_DAYS=30

for arg in "$@"; do
    case $arg in
        --verify)
            VERIFY=true
            shift
            ;;
        --keep-days=*)
            KEEP_DAYS="${arg#*=}"
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
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/db_${TIMESTAMP}.sql.gz"

# Создание директории
mkdir -p "$BACKUP_DIR"

echo -e "${BLUE}Создание резервной копии базы данных...${NC}"

# Проверка доступности БД
if ! docker compose ps db 2>/dev/null | grep -q "Up"; then
    echo -e "${RED}Ошибка: Контейнер БД не запущен${NC}"
    exit 1
fi

# Создание бэкапа
echo -e "${BLUE}Выполнение pg_dump...${NC}"
if docker compose exec -T db pg_dump -U postgres satva_wellness_booking 2>/dev/null | gzip > "$BACKUP_FILE"; then
    # Проверка размера файла
    if [ -f "$BACKUP_FILE" ] && [ -s "$BACKUP_FILE" ]; then
        local size=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
        echo -e "${GREEN}✓ Бэкап создан: $BACKUP_FILE${NC}"
        echo -e "${GREEN}  Размер: $(numfmt --to=iec-i --suffix=B $size 2>/dev/null || echo "${size}B")${NC}"
        
        # Проверка целостности
        if [ "$VERIFY" = true ]; then
            echo -e "${BLUE}Проверка целостности бэкапа...${NC}"
            if gunzip -t "$BACKUP_FILE" 2>/dev/null; then
                echo -e "${GREEN}✓ Бэкап корректен${NC}"
            else
                echo -e "${RED}✗ Ошибка: Бэкап поврежден${NC}"
                rm -f "$BACKUP_FILE"
                exit 1
            fi
        fi
        
        # Удаление старых бэкапов
        if [ "$KEEP_DAYS" -gt 0 ]; then
            echo -e "${BLUE}Удаление бэкапов старше $KEEP_DAYS дней...${NC}"
            find "$BACKUP_DIR" -name "db_*.sql.gz" -type f -mtime +$KEEP_DAYS -delete
            echo -e "${GREEN}✓ Очистка завершена${NC}"
        fi
        
        # Показ списка бэкапов
        echo -e "${BLUE}Текущие бэкапы:${NC}"
        ls -lh "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | tail -5 || echo "Нет других бэкапов"
        
        echo -e "${GREEN}✓ Резервная копия успешно создана${NC}"
        exit 0
    else
        echo -e "${RED}Ошибка: Бэкап не был создан или пуст${NC}"
        rm -f "$BACKUP_FILE"
        exit 1
    fi
else
    echo -e "${RED}Ошибка при создании бэкапа${NC}"
    exit 1
fi
