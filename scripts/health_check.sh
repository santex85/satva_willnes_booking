#!/bin/bash
#
# Скрипт проверки работоспособности приложения
# Использование: ./scripts/health_check.sh [--verbose]

set -euo pipefail

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Параметры
VERBOSE=false

for arg in "$@"; do
    case $arg in
        --verbose|-v)
            VERBOSE=true
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

# Счетчики
CHECKS_PASSED=0
CHECKS_FAILED=0

# Функция проверки
check() {
    local name="$1"
    local command="$2"
    
    echo -n "Проверка: $name... "
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC}"
        ((CHECKS_FAILED++))
        if [ "$VERBOSE" = true ]; then
            echo -e "${YELLOW}  Команда: $command${NC}"
        fi
        return 1
    fi
}

echo -e "${BLUE}Проверка работоспособности приложения...${NC}"
echo ""

# Проверка Docker
echo -e "${BLUE}=== Docker ===${NC}"
check "Docker доступен" "docker --version"
check "Docker Compose доступен" "docker compose version"

# Проверка контейнеров
echo ""
echo -e "${BLUE}=== Контейнеры ===${NC}"
check "Контейнер БД запущен" "docker compose ps db | grep -q Up"
check "Контейнер Web запущен" "docker compose ps web | grep -q Up"
check "Контейнер Nginx запущен" "docker compose ps nginx | grep -q Up"

# Проверка БД
echo ""
echo -e "${BLUE}=== База данных ===${NC}"
check "БД доступна" "docker compose exec -T db pg_isready -U postgres"
check "Подключение к БД работает" "docker compose exec -T web python manage.py check --database default 2>&1 | grep -q 'no issues'"

# Проверка миграций
echo ""
echo -e "${BLUE}=== Миграции ===${NC}"
if docker compose exec -T web python manage.py showmigrations --plan 2>/dev/null | grep -q "\[ \]"; then
    echo -e "${YELLOW}⚠ Есть непримененные миграции${NC}"
    ((CHECKS_FAILED++))
else
    echo -e "${GREEN}✓ Все миграции применены${NC}"
    ((CHECKS_PASSED++))
fi

# Проверка HTTP
echo ""
echo -e "${BLUE}=== HTTP ===${NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
    echo -e "${GREEN}✓ Веб-сервер доступен (HTTP $HTTP_CODE)${NC}"
    ((CHECKS_PASSED++))
else
    echo -e "${RED}✗ Веб-сервер недоступен (HTTP $HTTP_CODE)${NC}"
    ((CHECKS_FAILED++))
fi

# Проверка статических файлов
echo ""
echo -e "${BLUE}=== Статические файлы ===${NC}"
if docker compose exec -T web test -d /app/staticfiles 2>/dev/null; then
    STATIC_COUNT=$(docker compose exec -T web find /app/staticfiles -type f 2>/dev/null | wc -l | tr -d ' ' || echo "0")
    if [ "$STATIC_COUNT" -gt 0 ]; then
        echo -e "${GREEN}✓ Статические файлы собраны ($STATIC_COUNT файлов)${NC}"
        ((CHECKS_PASSED++))
    else
        echo -e "${YELLOW}⚠ Директория статических файлов пуста${NC}"
        ((CHECKS_FAILED++))
    fi
else
    echo -e "${RED}✗ Директория статических файлов не найдена${NC}"
    ((CHECKS_FAILED++))
fi

# Проверка логов на ошибки
echo ""
echo -e "${BLUE}=== Логи ===${NC}"
ERROR_COUNT=$(docker compose logs --tail=100 web 2>/dev/null | grep -i "error\|exception\|traceback" | wc -l | tr -d ' ' || echo "0")
if [ "$ERROR_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✓ Критических ошибок в логах не обнаружено${NC}"
    ((CHECKS_PASSED++))
else
    echo -e "${YELLOW}⚠ Обнаружено $ERROR_COUNT ошибок в последних 100 строках логов${NC}"
    if [ "$VERBOSE" = true ]; then
        echo -e "${YELLOW}Последние ошибки:${NC}"
        docker compose logs --tail=100 web 2>/dev/null | grep -i "error\|exception" | head -5
    fi
    ((CHECKS_FAILED++))
fi

# Итоги
echo ""
echo -e "${BLUE}=== Итоги ===${NC}"
echo -e "Пройдено: ${GREEN}$CHECKS_PASSED${NC}"
echo -e "Провалено: ${RED}$CHECKS_FAILED${NC}"

if [ $CHECKS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ Все проверки пройдены успешно${NC}"
    exit 0
else
    echo -e "${RED}✗ Обнаружены проблемы${NC}"
    exit 1
fi
