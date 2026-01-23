#!/bin/bash
#
# Скрипт для сбора информации о текущей конфигурации проекта на production сервере
# Использование: ./scripts/collect_server_info.sh [SSH_KEY_PATH] [SERVER_USER@SERVER_IP]
#
# Пример: ./scripts/collect_server_info.sh ~/.ssh/id_rsa root@188.166.240.56

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры
SSH_KEY="${1:-~/.ssh/id_rsa}"
SERVER="${2:-root@188.166.240.56}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="server_info_${TIMESTAMP}.md"

# Функция для выполнения команд на сервере
ssh_exec() {
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$SERVER" "$@"
}

# Функция для маскировки чувствительных данных
mask_sensitive() {
    sed -E 's/(SECRET_KEY|PASSWORD|PASS|KEY|TOKEN)=[^[:space:]]+/&_MASKED/g' | \
    sed -E 's/(password|secret|key|token)[[:space:]]*[:=][[:space:]]*[^[:space:]]+/&_MASKED/gi'
}

echo -e "${GREEN}Начинаю сбор информации с сервера ${SERVER}...${NC}"

# Проверка подключения
echo -e "${YELLOW}Проверка подключения к серверу...${NC}"
if ! ssh_exec "echo 'Connection OK'" > /dev/null 2>&1; then
    echo -e "${RED}Ошибка: Не удалось подключиться к серверу${NC}"
    echo "Проверьте:"
    echo "  1. SSH ключ: $SSH_KEY"
    echo "  2. Адрес сервера: $SERVER"
    echo "  3. Доступность сервера"
    exit 1
fi

echo -e "${GREEN}Подключение установлено${NC}"

# Создание временного файла на сервере для сбора информации
TEMP_FILE="/tmp/server_info_${TIMESTAMP}.txt"
ssh_exec "cat > $TEMP_FILE << 'EOFMARKER'
=== СИСТЕМНАЯ ИНФОРМАЦИЯ ===
OS: \$(lsb_release -d 2>/dev/null | cut -f2 || uname -a)
Kernel: \$(uname -r)
Uptime: \$(uptime)
Date: \$(date)

=== ВЕРСИИ ПО ===
Docker: \$(docker --version 2>/dev/null || echo 'Not installed')
Docker Compose: \$(docker compose version 2>/dev/null || echo 'Not installed')
Python: \$(python3 --version 2>/dev/null || echo 'Not installed')
PostgreSQL: \$(docker compose exec -T db psql --version 2>/dev/null || echo 'Not available')

=== ИСПОЛЬЗОВАНИЕ РЕСУРСОВ ===
Disk Usage:
\$(df -h | grep -E '^/dev/')

Memory:
\$(free -h)

CPU Info:
\$(lscpu | grep -E '^CPU\(s\)|^Model name|^Architecture' || echo 'N/A')

=== ПУТЬ К ПРОЕКТУ ===
\$(pwd 2>/dev/null || echo 'N/A')
EOFMARKER
" > /dev/null

# Поиск проекта на сервере
echo -e "${YELLOW}Поиск проекта на сервере...${NC}"
PROJECT_PATH=$(ssh_exec "find /opt /var/www /home -type d -name '*satva*' -o -name '*wellness*' -o -name '*booking*' 2>/dev/null | head -1" || echo "")
if [ -z "$PROJECT_PATH" ]; then
    # Попробуем найти через docker-compose
    PROJECT_PATH=$(ssh_exec "docker compose ps 2>/dev/null | head -1 | awk '{print \$NF}' | xargs -I {} docker inspect {} --format '{{.Config.Labels.com.docker.compose.project.working_dir}}' 2>/dev/null | head -1" || echo "")
fi

if [ -z "$PROJECT_PATH" ]; then
    echo -e "${YELLOW}Проект не найден автоматически. Используем текущую директорию.${NC}"
    PROJECT_PATH="."
else
    echo -e "${GREEN}Найден проект: $PROJECT_PATH${NC}"
fi

# Сбор информации о проекте
echo -e "${YELLOW}Сбор информации о проекте...${NC}"
ssh_exec "cd $PROJECT_PATH 2>/dev/null || cd /opt 2>/dev/null || cd ~; cat >> $TEMP_FILE << 'EOFMARKER'

=== ИНФОРМАЦИЯ О ПРОЕКТЕ ===
Project Path: \$(pwd)
Git Status:
\$(git status --short 2>/dev/null || echo 'Not a git repository')
Git Branch: \$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'N/A')
Git Commit: \$(git rev-parse HEAD 2>/dev/null || echo 'N/A')
Git Last Commit Date: \$(git log -1 --format='%cd' 2>/dev/null || echo 'N/A')

Project Structure (top level):
\$(ls -la 2>/dev/null | head -20)
EOFMARKER
" > /dev/null

# Сбор информации о Docker
echo -e "${YELLOW}Сбор информации о Docker...${NC}"
ssh_exec "cd $PROJECT_PATH 2>/dev/null || cd /opt 2>/dev/null || cd ~; cat >> $TEMP_FILE << 'EOFMARKER'

=== DOCKER КОНФИГУРАЦИЯ ===
Docker Containers Status:
\$(docker compose ps 2>/dev/null || docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || echo 'Docker not available')

Docker Volumes:
\$(docker volume ls 2>/dev/null || echo 'N/A')

Docker Networks:
\$(docker network ls 2>/dev/null || echo 'N/A')

Docker Compose File (if exists):
\$(if [ -f docker-compose.yml ]; then cat docker-compose.yml; else echo 'docker-compose.yml not found'; fi)

Docker Compose Environment Variables (names only):
\$(if [ -f docker-compose.yml ]; then grep -E '^\s*[A-Z_]+:' docker-compose.yml | head -20 || echo 'N/A'; fi)
EOFMARKER
" > /dev/null

# Сбор информации о .env файле (без значений)
echo -e "${YELLOW}Сбор информации о переменных окружения...${NC}"
ssh_exec "cd $PROJECT_PATH 2>/dev/null || cd /opt 2>/dev/null || cd ~; cat >> $TEMP_FILE << 'EOFMARKER'

=== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
.env file exists: \$(if [ -f .env ]; then echo 'Yes'; else echo 'No'; fi)
.env variables (names only):
\$(if [ -f .env ]; then grep -v '^#' .env | grep -v '^$' | cut -d'=' -f1 | sort || echo 'N/A'; fi)
EOFMARKER
" > /dev/null

# Сбор информации о Nginx
echo -e "${YELLOW}Сбор информации о Nginx...${NC}"
ssh_exec "cd $PROJECT_PATH 2>/dev/null || cd /opt 2>/dev/null || cd ~; cat >> $TEMP_FILE << 'EOFMARKER'

=== NGINX КОНФИГУРАЦИЯ ===
Nginx Config (if exists):
\$(if [ -f nginx/nginx.conf ]; then cat nginx/nginx.conf; elif [ -f nginx.conf ]; then cat nginx.conf; else echo 'nginx.conf not found in project'; fi)

Nginx Container Logs (last 20 lines):
\$(docker compose logs --tail=20 nginx 2>/dev/null || docker logs satva_wellness_nginx --tail=20 2>/dev/null || echo 'Nginx logs not available')
EOFMARKER
" > /dev/null

# Сбор информации о базе данных
echo -e "${YELLOW}Сбор информации о базе данных...${NC}"
ssh_exec "cd $PROJECT_PATH 2>/dev/null || cd /opt 2>/dev/null || cd ~; cat >> $TEMP_FILE << 'EOFMARKER'

=== БАЗА ДАННЫХ ===
PostgreSQL Version:
\$(docker compose exec -T db psql --version 2>/dev/null || echo 'Database container not available')

Database Size:
\$(docker compose exec -T db psql -U postgres -c \"SELECT pg_size_pretty(pg_database_size('satva_wellness_booking'));\" 2>/dev/null | grep -v 'row' | grep -v '^$' || echo 'N/A')

Database Tables Count:
\$(docker compose exec -T db psql -U postgres -d satva_wellness_booking -c \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';\" 2>/dev/null | grep -E '^[[:space:]]*[0-9]+' || echo 'N/A')

Last Migrations (last 10):
\$(docker compose exec -T web python manage.py showmigrations --plan 2>/dev/null | tail -10 || echo 'N/A')
EOFMARKER
" > /dev/null

# Сбор информации о SSL
echo -e "${YELLOW}Сбор информации о SSL сертификатах...${NC}"
ssh_exec "cat >> $TEMP_FILE << 'EOFMARKER'

=== SSL СЕРТИФИКАТЫ ===
Let's Encrypt Certificates:
\$(if [ -d /etc/letsencrypt/live ]; then ls -la /etc/letsencrypt/live/ 2>/dev/null || echo 'No certificates found'; else echo 'Let\\'s Encrypt directory not found'; fi)

Certificate Expiry (if available):
\$(if [ -f /etc/letsencrypt/live/*/fullchain.pem ]; then openssl x509 -enddate -noout -in /etc/letsencrypt/live/*/fullchain.pem 2>/dev/null | head -1 || echo 'N/A'; else echo 'Certificate file not found'; fi)
EOFMARKER
" > /dev/null

# Сбор информации о логах
echo -e "${YELLOW}Сбор информации о логах...${NC}"
ssh_exec "cd $PROJECT_PATH 2>/dev/null || cd /opt 2>/dev/null || cd ~; cat >> $TEMP_FILE << 'EOFMARKER'

=== ЛОГИ И МОНИТОРИНГ ===
Django Logs (last 30 lines, errors only):
\$(docker compose logs --tail=50 web 2>/dev/null | grep -i error | tail -10 || echo 'No errors found or logs not available')

Web Container Status:
\$(docker compose ps web 2>/dev/null || docker ps --filter 'name=web' --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || echo 'N/A')

Container Resource Usage:
\$(docker stats --no-stream --format 'table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}' 2>/dev/null | head -5 || echo 'N/A')
EOFMARKER
" > /dev/null

# Сбор информации о бэкапах
echo -e "${YELLOW}Сбор информации о резервных копиях...${NC}"
ssh_exec "cat >> $TEMP_FILE << 'EOFMARKER'

=== РЕЗЕРВНЫЕ КОПИИ ===
Backup Directories:
\$(find /opt /var /home -type d -name '*backup*' -o -name '*backup*' 2>/dev/null | head -5 || echo 'No backup directories found')

Recent Backups:
\$(find /opt /var /home -type f -name '*backup*.sql*' -o -name '*backup*.gz' 2>/dev/null | head -5 | xargs -I {} ls -lh {} 2>/dev/null || echo 'No backup files found')

Cron Jobs:
\$(crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$' || echo 'No cron jobs found')
EOFMARKER
" > /dev/null

# Сбор дополнительной информации
echo -e "${YELLOW}Сбор дополнительной информации...${NC}"
ssh_exec "cat >> $TEMP_FILE << 'EOFMARKER'

=== ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ ===
Firewall Status:
\$(ufw status 2>/dev/null || iptables -L -n 2>/dev/null | head -10 || echo 'Firewall info not available')

Active Network Connections:
\$(netstat -tuln 2>/dev/null | grep -E ':(80|443|5432|8000|8001)' || ss -tuln 2>/dev/null | grep -E ':(80|443|5432|8000|8001)' || echo 'N/A')

System Services:
\$(systemctl list-units --type=service --state=running 2>/dev/null | grep -E 'docker|nginx|postgres' || echo 'N/A')
EOFMARKER
" > /dev/null

# Копирование собранной информации
echo -e "${YELLOW}Копирование информации с сервера...${NC}"
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER:$TEMP_FILE" "$OUTPUT_FILE" > /dev/null 2>&1

# Удаление временного файла с сервера
ssh_exec "rm -f $TEMP_FILE" > /dev/null 2>&1

# Обработка и форматирование информации
echo -e "${YELLOW}Обработка информации...${NC}"

# Создание markdown отчета
{
    echo "# Информация о сервере: $SERVER"
    echo ""
    echo "**Дата сбора:** $(date '+%Y-%m-%d %H:%M:%S')"
    echo "**Сервер:** $SERVER"
    echo ""
    echo "---"
    echo ""
    cat "$OUTPUT_FILE" | mask_sensitive
} > "${OUTPUT_FILE}.md"

# Удаление временного файла
rm -f "$OUTPUT_FILE"

echo -e "${GREEN}✓ Информация успешно собрана!${NC}"
echo -e "${GREEN}Отчет сохранен в: ${OUTPUT_FILE}.md${NC}"
echo ""
echo "Следующие шаги:"
echo "  1. Проверьте файл ${OUTPUT_FILE}.md"
echo "  2. Убедитесь, что все критичные настройки задокументированы"
echo "  3. Используйте эту информацию для безопасного деплоя"
