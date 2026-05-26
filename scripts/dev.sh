#!/usr/bin/env bash
# Локальная разработка: PostgreSQL + Django (8002) + Vite (5173)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DEV_DIR="$ROOT/.dev"
DJANGO_PID="$DEV_DIR/django.pid"
VITE_PID="$DEV_DIR/vite.pid"
DJANGO_LOG="$DEV_DIR/django.log"
VITE_LOG="$DEV_DIR/vite.log"
VENV="$ROOT/venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

DJANGO_PORT="${DJANGO_PORT:-8002}"
VITE_PORT="${VITE_PORT:-5173}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}▶${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
err() { echo -e "${RED}✗${NC} $*" >&2; }

kill_pid_file() {
  local pidfile="$1"
  local name="$2"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      log "Останавливаю $name (PID $pid)..."
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  fi
}

kill_port() {
  local port="$1"
  local pids
  pids="$(lsof -ti:"$port" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    log "Освобождаю порт $port..."
    echo "$pids" | xargs kill -9 2>/dev/null || true
  fi
}

stop_dev() {
  log "Останавливаю dev-сервисы..."
  kill_pid_file "$DJANGO_PID" "Django"
  kill_pid_file "$VITE_PID" "Vite"
  kill_port "$DJANGO_PORT"
  kill_port "$VITE_PORT"
  log "Dev-сервисы остановлены."
}

ensure_env() {
  if [[ ! -f "$ROOT/.env" ]]; then
    warn ".env не найден — копирую из .env.example"
    cp "$ROOT/.env.example" "$ROOT/.env"
    warn "Отредактируйте .env при необходимости (DATABASE_PASSWORD и т.д.)"
  fi
}

ensure_venv() {
  if [[ ! -d "$VENV" ]]; then
    log "Создаю виртуальное окружение..."
    python3 -m venv "$VENV"
  fi
  log "Устанавливаю Python-зависимости..."
  "$PIP" install -q -r "$ROOT/requirements.txt"
}

ensure_frontend() {
  if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
    log "Устанавливаю npm-зависимости..."
    npm --prefix "$ROOT/frontend" install
  else
    npm --prefix "$ROOT/frontend" install --prefer-offline 2>/dev/null || npm --prefix "$ROOT/frontend" install
  fi
}

ensure_postgres() {
  local db_host="${DATABASE_HOST:-localhost}"
  local db_port="${DATABASE_PORT:-5432}"

  if command -v pg_isready >/dev/null 2>&1; then
    if pg_isready -h "$db_host" -p "$db_port" >/dev/null 2>&1; then
      log "PostgreSQL доступен ($db_host:$db_port)"
      return 0
    fi
  fi

  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    log "Запускаю PostgreSQL через Docker..."
    docker compose up -d db
    local i
    for i in $(seq 1 30); do
      if docker compose exec -T db pg_isready -U "${DATABASE_USER:-postgres}" >/dev/null 2>&1; then
        log "PostgreSQL в Docker готов"
        return 0
      fi
      sleep 1
    done
    err "PostgreSQL не запустился за 30 секунд"
    exit 1
  fi

  err "PostgreSQL недоступен на $db_host:$db_port. Установите PostgreSQL или запустите Docker."
  exit 1
}

run_migrations() {
  log "Применяю миграции (shared + tenant schemas)..."
  "$PYTHON" "$ROOT/manage.py" migrate_schemas --shared --noinput
  "$PYTHON" "$ROOT/manage.py" migrate_schemas --tenant --noinput
}

start_django() {
  log "Запускаю Django на порту $DJANGO_PORT..."
  nohup "$PYTHON" "$ROOT/manage.py" runserver "0.0.0.0:$DJANGO_PORT" \
    >"$DJANGO_LOG" 2>&1 &
  echo $! >"$DJANGO_PID"
  sleep 2
  if ! kill -0 "$(cat "$DJANGO_PID")" 2>/dev/null; then
    err "Django не запустился. Смотрите $DJANGO_LOG"
    tail -20 "$DJANGO_LOG" >&2 || true
    exit 1
  fi
}

start_vite() {
  log "Запускаю Vite на порту $VITE_PORT..."
  nohup npm --prefix "$ROOT/frontend" run dev -- --host 0.0.0.0 --port "$VITE_PORT" \
    >"$VITE_LOG" 2>&1 &
  echo $! >"$VITE_PID"
  sleep 2
  if ! kill -0 "$(cat "$VITE_PID")" 2>/dev/null; then
    err "Vite не запустился. Смотрите $VITE_LOG"
    tail -20 "$VITE_LOG" >&2 || true
    exit 1
  fi
}

wait_for_http() {
  local url="$1"
  local name="$2"
  local extra_curl_args="${3:-}"
  local i code
  for i in $(seq 1 20); do
    code="$(curl -s -o /dev/null -w "%{http_code}" $extra_curl_args "$url" 2>/dev/null || echo "000")"
    if [[ "$code" != "000" ]]; then
      return 0
    fi
    sleep 1
  done
  warn "$name ещё не отвечает на $url (может потребоваться ещё несколько секунд)"
}

print_status() {
  echo ""
  echo -e "${GREEN}══════════════════════════════════════════════${NC}"
  echo -e "${GREEN}  Satva Wellness — dev окружение запущено${NC}"
  echo -e "${GREEN}══════════════════════════════════════════════${NC}"
  echo ""
  echo "  Frontend (React):  http://localhost:$VITE_PORT/"
  echo "  Backend API:       http://demo.localhost:$DJANGO_PORT/api/v1/"
  echo "  Django Admin:      http://demo.localhost:$DJANGO_PORT/admin/"
  echo "  SPA (production):  http://demo.localhost:$DJANGO_PORT/"
  echo ""
  echo "  Логи:  make dev-logs"
  echo "  Стоп:  make dev-stop"
  echo ""
  echo -e "${YELLOW}  Логин: admin / admin12345 (tenant demo)${NC}"
  echo ""
}

start_dev() {
  mkdir -p "$DEV_DIR"

  # Подгружаем .env для проверки PostgreSQL
  if [[ -f "$ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/.env"
    set +a
  fi

  stop_dev
  ensure_env
  ensure_venv
  ensure_frontend
  ensure_postgres
  run_migrations
  start_django
  start_vite

  wait_for_http "http://127.0.0.1:$VITE_PORT/" "Vite" || true
  wait_for_http "http://127.0.0.1:$DJANGO_PORT/" "Django" "-H Host:demo.localhost" || true

  print_status
}

case "${1:-start}" in
  stop)
    stop_dev
    ;;
  restart|start|"")
    start_dev
    ;;
  *)
    echo "Usage: $0 [start|stop|restart]"
    exit 1
    ;;
esac
