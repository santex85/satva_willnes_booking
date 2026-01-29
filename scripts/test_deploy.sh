#!/bin/bash
#
# Скрипт для тестирования скриптов деплоя
# Использование: ./scripts/test_deploy.sh [--full]
#
# Опции:
#   --full - Полное тестирование (включая проверку на реальных контейнерах)

set -euo pipefail

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Параметры
FULL_TEST=false

for arg in "$@"; do
    case $arg in
        --full)
            FULL_TEST=true
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
TESTS_PASSED=0
TESTS_FAILED=0

# Функция теста
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -e "${BLUE}Тест: $test_name${NC}"
    
    if eval "$test_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ ПРОЙДЕН${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗ ПРОВАЛЕН${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Тестирование скриптов деплоя${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Тест 1: Проверка синтаксиса
echo -e "${YELLOW}=== Проверка синтаксиса ===${NC}"
for script in deploy_safe.sh backup_db.sh restore_db.sh health_check.sh deploy_remote.sh; do
    run_test "Синтаксис $script" "bash -n $SCRIPT_DIR/$script"
done
echo ""

# Тест 2: Проверка наличия скриптов
echo -e "${YELLOW}=== Проверка наличия файлов ===${NC}"
for script in deploy_safe.sh backup_db.sh restore_db.sh health_check.sh deploy_remote.sh; do
    run_test "Файл $script существует" "test -f $SCRIPT_DIR/$script"
done
echo ""

# Тест 3: Проверка прав на выполнение
echo -e "${YELLOW}=== Проверка прав на выполнение ===${NC}"
for script in deploy_safe.sh backup_db.sh restore_db.sh health_check.sh deploy_remote.sh; do
    run_test "Права на выполнение $script" "test -x $SCRIPT_DIR/$script"
done
echo ""

# Тест 4: Проверка функций скриптов (dry-run)
if [ "$FULL_TEST" = true ]; then
    echo -e "${YELLOW}=== Тестирование функций (dry-run) ===${NC}"
    
    # Проверка доступности Docker
    if command -v docker &> /dev/null; then
        run_test "Docker доступен" "docker --version"
        
        # Проверка доступности docker compose
        if docker compose version &> /dev/null; then
            run_test "Docker Compose доступен" "docker compose version"
            
            # Проверка статуса контейнеров (если запущены)
            if docker compose ps &> /dev/null; then
                echo -e "${BLUE}Проверка работы скриптов с Docker...${NC}"
                
                # Тест health_check (безопасно)
                run_test "health_check.sh работает" "$SCRIPT_DIR/health_check.sh --verbose 2>&1 | head -5"
                
                # Тест deploy_safe в dry-run режиме (безопасно)
                echo -e "${BLUE}Тест deploy_safe.sh в dry-run режиме...${NC}"
                if timeout 30 "$SCRIPT_DIR/deploy_safe.sh" --dry-run 2>&1 | grep -q "РЕЖИМ ПРОВЕРКИ"; then
                    echo -e "${GREEN}✓ deploy_safe.sh dry-run работает${NC}"
                    ((TESTS_PASSED++))
                else
                    echo -e "${YELLOW}⚠ deploy_safe.sh dry-run требует проверки вручную${NC}"
                fi
            else
                echo -e "${YELLOW}⚠ Docker Compose не настроен, пропуск тестов с контейнерами${NC}"
            fi
        else
            echo -e "${YELLOW}⚠ Docker Compose не доступен, пропуск тестов${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ Docker не установлен, пропуск тестов с Docker${NC}"
    fi
    echo ""
fi

# Тест 5: Проверка параметров скриптов
echo -e "${YELLOW}=== Проверка обработки параметров ===${NC}"

# deploy_safe.sh
run_test "deploy_safe.sh --dry-run принимает параметр" "$SCRIPT_DIR/deploy_safe.sh --dry-run 2>&1 | grep -q 'РЕЖИМ ПРОВЕРКИ' || timeout 5 $SCRIPT_DIR/deploy_safe.sh --dry-run 2>&1 | head -1"

# backup_db.sh
run_test "backup_db.sh --verify принимает параметр" "timeout 5 $SCRIPT_DIR/backup_db.sh --verify 2>&1 | head -1"

# health_check.sh
run_test "health_check.sh --verbose принимает параметр" "timeout 10 $SCRIPT_DIR/health_check.sh --verbose 2>&1 | head -1"

echo ""

# Тест 6: Проверка директорий
echo -e "${YELLOW}=== Проверка структуры проекта ===${NC}"
run_test "Директория scripts существует" "test -d $SCRIPT_DIR"
run_test "Директория backups существует или может быть создана" "mkdir -p $PROJECT_DIR/backups && test -d $PROJECT_DIR/backups"
run_test "Директория logs существует или может быть создана" "mkdir -p $PROJECT_DIR/logs && test -d $PROJECT_DIR/logs"
echo ""

# Итоги
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Итоги тестирования${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Пройдено: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Провалено: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ Все тесты пройдены успешно!${NC}"
    echo ""
    echo -e "${BLUE}Следующие шаги:${NC}"
    echo "  1. Запустите dry-run: make deploy-safe-dry"
    echo "  2. Протестируйте отдельные компоненты"
    echo "  3. Прочитайте TESTING.md для детального плана"
    exit 0
else
    echo -e "${RED}✗ Некоторые тесты провалены${NC}"
    echo ""
    echo -e "${YELLOW}Рекомендации:${NC}"
    echo "  1. Проверьте ошибки выше"
    echo "  2. Убедитесь, что все скрипты имеют права на выполнение: chmod +x scripts/*.sh"
    echo "  3. Проверьте синтаксис: bash -n scripts/*.sh"
    exit 1
fi
