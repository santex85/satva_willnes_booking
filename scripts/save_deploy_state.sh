#!/bin/bash
#
# Скрипт для сохранения информации о деплое
# Использование: ./scripts/save_deploy_state.sh <previous_commit> <current_commit> <backup_file> <deploy_log>
#
# Вызывается из deploy_safe.sh после успешного деплоя

set -euo pipefail

# Параметры
PREVIOUS_COMMIT="${1:-}"
CURRENT_COMMIT="${2:-}"
BACKUP_FILE="${3:-}"
DEPLOY_LOG="${4:-}"

# Константы
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_FILE="$PROJECT_DIR/deploy_state.json"
STATES_DIR="$PROJECT_DIR/deploy_states"
MAX_STATES=5

# Создание директории для архивных состояний
mkdir -p "$STATES_DIR"

# Получение текущей даты
DEPLOY_DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Создание JSON с информацией о деплое
STATE_DATA=$(cat <<EOF
{
  "deploy_date": "$DEPLOY_DATE",
  "previous_commit": "$PREVIOUS_COMMIT",
  "current_commit": "$CURRENT_COMMIT",
  "backup_file": "$BACKUP_FILE",
  "deploy_log": "$DEPLOY_LOG"
}
EOF
)

# Сохранение текущего состояния
echo "$STATE_DATA" > "$STATE_FILE"

# Архивирование предыдущего состояния (если существует)
if [ -f "$STATE_FILE" ] && [ -n "$PREVIOUS_COMMIT" ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    ARCHIVE_FILE="$STATES_DIR/deploy_state_${TIMESTAMP}.json"
    
    # Копируем текущее состояние в архив перед перезаписью
    if [ -f "$STATE_FILE" ]; then
        cp "$STATE_FILE" "$ARCHIVE_FILE" 2>/dev/null || true
    fi
fi

# Удаление старых архивных состояний (оставляем только последние MAX_STATES)
if [ -d "$STATES_DIR" ]; then
    cd "$STATES_DIR"
    ls -t deploy_state_*.json 2>/dev/null | tail -n +$((MAX_STATES + 1)) | xargs rm -f 2>/dev/null || true
fi

# Вывод информации
echo "Состояние деплоя сохранено: $STATE_FILE"
if [ -n "$PREVIOUS_COMMIT" ]; then
    echo "  Previous commit: $PREVIOUS_COMMIT"
fi
if [ -n "$CURRENT_COMMIT" ]; then
    echo "  Current commit: $CURRENT_COMMIT"
fi
if [ -n "$BACKUP_FILE" ]; then
    echo "  Backup file: $BACKUP_FILE"
fi
