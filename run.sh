#!/usr/bin/env bash
# O51NT Workbench — startup.
# Uso: ./run.sh [--browser NOME] [--no-browser] [--port N] [--rebuild] [--no-searxng] [--reset-db] [--dry-run] [--list-browsers]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
RUN_DIR="$ROOT/.run"
PID_FILE="$RUN_DIR/uvicorn.pid"
DATA="$ROOT/data"
DB="$DATA/o51nt.db"
SETTINGS="$DATA/settings.json"
LOG_FILE="$DATA/logs/uvicorn.log"
HOST="${O51NT_HOST:-127.0.0.1}"
PORT="${O51NT_PORT:-8051}"
SEARXNG_URL="${O51NT_SEARXNG_URL:-http://127.0.0.1:8080}"
SEARXNG_IMAGE="searxng/searxng:2026.10.4-d48c4b555"  # manter igual ao docker-compose.yml
BROWSER_CHOICE=""
OPEN_BROWSER=1
REBUILD=0
DRY_RUN=0
USE_SEARXNG=1
RESET_DB=0

BROWSERS=(firefox firefox-esr chromium chromium-browser google-chrome google-chrome-stable brave-browser brave microsoft-edge opera vivaldi)

log() { printf '\033[1;34m[o51nt]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[o51nt]\033[0m %s\n' "$*" >&2; }

detect_browsers() {
  local b
  for b in "${BROWSERS[@]}"; do command -v "$b" >/dev/null 2>&1 && echo "$b"; done
  return 0
}

preferred_from_settings() {
  [[ -f "$SETTINGS" ]] || return 0
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("preferencias",{}).get("navegadorPadrao",""))' "$SETTINGS" 2>/dev/null || true
}

# Grava preferencias.navegadorPadrao em data/settings.json (merge + escrita atômica).
persist_browser() {
  local b="$1"
  mkdir -p "$DATA"
  python3 - "$SETTINGS" "$b" <<'PY'
import json, os, sys, tempfile
path, browser = sys.argv[1], sys.argv[2]
try:
    cfg = json.load(open(path, encoding="utf-8"))
except (OSError, ValueError):
    cfg = {}
cfg.setdefault("preferencias", {})["navegadorPadrao"] = browser
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False, indent=2)
os.replace(tmp, path)
PY
}

# Ecoa o navegador escolhido. Escolhas explícitas (--browser ou menu) são persistidas.
choose_browser() {
  mapfile -t found < <(detect_browsers)
  if [[ -n "$BROWSER_CHOICE" ]] && command -v "$BROWSER_CHOICE" >/dev/null 2>&1; then echo "$BROWSER_CHOICE"; return; fi
  local pref; pref="$(preferred_from_settings)"
  if [[ -n "$pref" && "$pref" != "auto" ]] && command -v "$pref" >/dev/null 2>&1; then echo "$pref"; return; fi
  if (( ${#found[@]} == 0 )); then echo "xdg-open"; return; fi
  if (( ${#found[@]} == 1 )) || [[ ! -t 0 ]] || (( DRY_RUN )); then echo "${found[0]}"; return; fi
  echo "Navegadores disponíveis:" >&2
  local i; for i in "${!found[@]}"; do echo "  $((i + 1))) ${found[$i]}" >&2; done
  local opt; read -r -t 15 -p "Escolha [1-${#found[@]}] (Enter = 1; a escolha será lembrada): " opt >&2 || true
  local escolhido="${found[0]}"
  [[ "$opt" =~ ^[0-9]+$ ]] && (( opt >= 1 && opt <= ${#found[@]} )) && escolhido="${found[$((opt - 1))]}"
  persist_browser "$escolhido"
  echo "$escolhido"
}

backend_running() { [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; }

# Backup consistente (API de backup do SQLite) e remoção; o backend recria o banco vazio.
reset_db() {
  if [[ ! -f "$DB" ]]; then log "Nenhum banco em $DB — nada a resetar."; return; fi
  if [[ -t 0 ]]; then
    local ok; read -r -p "Resetar o banco? Um backup será criado antes. [s/N] " ok
    [[ "$ok" =~ ^[sSyY]$ ]] || { log "Reset cancelado."; exit 0; }
  fi
  if backend_running; then log "Parando backend para o reset…"; "$ROOT/stop.sh"; fi
  local bak; bak="$DB.bak.$(date +%Y%m%d_%H%M%S)"
  python3 -c 'import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()' "$DB" "$bak"
  rm -f "$DB" "$DB-wal" "$DB-shm"
  log "Backup salvo em $bak — banco removido; será recriado no próximo start."
  log "Arquivos de evidência e data/evidence/manifest.jsonl foram preservados."
}

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then echo "docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then echo "docker-compose"
  fi
}

# Sobe o SearXNG local. Nunca é fatal: sem ele, os módulos funcionam por deeplinks.
start_searxng() {
  if curl -fsS "$SEARXNG_URL/healthz" >/dev/null 2>&1; then log "SearXNG já disponível em $SEARXNG_URL."; return; fi
  if ! command -v docker >/dev/null 2>&1; then err "Docker ausente — SearXNG desativado (scraping de busca indisponível)."; return; fi
  if ! docker info >/dev/null 2>&1; then
    err "Docker sem acesso ao daemon (serviço parado ou usuário fora do grupo 'docker')."
    err "  Para habilitar: sudo systemctl start docker && sudo usermod -aG docker \$USER (relogar). Seguindo sem SearXNG."
    return
  fi
  mkdir -p "$DATA/searxng"
  if [[ ! -f "$DATA/searxng/settings.yml" ]]; then
    local secret; secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    sed "s/__SECRET__/$secret/" "$ROOT/deploy/searxng/settings.yml" >"$DATA/searxng/settings.yml"
  fi
  local cc; cc="$(compose_cmd)"
  log "Subindo SearXNG (${cc:-docker run})…"
  if [[ -n "$cc" ]]; then
    ( cd "$ROOT" && $cc up -d searxng ) || { err "Falha ao subir SearXNG via compose."; return; }
  else
    docker rm -f o51nt-searxng >/dev/null 2>&1 || true
    docker run -d --name o51nt-searxng --restart unless-stopped -p 127.0.0.1:8080:8080 \
      -v "$DATA/searxng:/etc/searxng:rw" -e SEARXNG_BASE_URL=http://127.0.0.1:8080/ \
      --cap-drop ALL --cap-add CHOWN --cap-add SETGID --cap-add SETUID ${SEARXNG_IMAGE} >/dev/null \
      || { err "Falha ao subir SearXNG via docker run."; return; }
  fi
  for _ in $(seq 1 30); do curl -fsS "$SEARXNG_URL/healthz" >/dev/null 2>&1 && { log "SearXNG OK em $SEARXNG_URL."; return; }; sleep 1; done
  err "SearXNG não respondeu em 30 s (veja: docker logs o51nt-searxng)."
}

while (( $# )); do
  case "$1" in
    --browser) BROWSER_CHOICE="${2:-}"; shift ;;
    --no-browser) OPEN_BROWSER=0 ;;
    --port) PORT="${2:-8051}"; shift ;;
    --rebuild) REBUILD=1 ;;
    --no-searxng) USE_SEARXNG=0 ;;
    --reset-db) RESET_DB=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --list-browsers) detect_browsers; exit 0 ;;
    -h|--help) sed -n '2,3p' "$0"; exit 0 ;;
    *) err "Opção desconhecida: $1"; exit 2 ;;
  esac
  shift
done

URL="http://$HOST:$PORT/"

if [[ -n "$BROWSER_CHOICE" ]]; then
  if ! command -v "$BROWSER_CHOICE" >/dev/null 2>&1; then
    err "Navegador '$BROWSER_CHOICE' não encontrado; disponíveis: $(detect_browsers | tr '\n' ' ')"
    BROWSER_CHOICE=""
  elif (( ! DRY_RUN )); then
    persist_browser "$BROWSER_CHOICE"
    log "Navegador '$BROWSER_CHOICE' salvo como padrão em data/settings.json."
  fi
fi

if (( DRY_RUN )); then
  log "DRY-RUN — nada será instalado/iniciado."
  log "Python: $(command -v python3 || echo 'AUSENTE') $(python3 --version 2>&1 || true)"
  log "Node:   $(command -v node || echo 'AUSENTE (necessário só para build do frontend)')"
  log "Navegadores detectados: $(detect_browsers | tr '\n' ' ')"
  log "Navegador escolhido: $(choose_browser) (preferência salva: $(preferred_from_settings || true))"
  if command -v docker >/dev/null 2>&1; then
    log "Docker: $(docker info >/dev/null 2>&1 && echo 'daemon OK' || echo 'sem acesso ao daemon') · compose: $(compose_cmd || true)"
  else
    log "Docker: ausente"
  fi
  log "SearXNG: $SEARXNG_URL ($(curl -fsS "$SEARXNG_URL/healthz" >/dev/null 2>&1 && echo disponível || echo indisponível))"
  (( RESET_DB )) && log "--reset-db: faria backup de $DB e o removeria."
  log "URL: $URL"
  exit 0
fi

mkdir -p "$RUN_DIR" "$DATA/logs" "$DATA/evidence" "$DATA/alerts"

(( RESET_DB )) && reset_db
(( USE_SEARXNG )) && start_searxng

if backend_running; then
  log "Backend já em execução (PID $(cat "$PID_FILE"))."
else
  # 1) venv + dependências Python
  command -v python3 >/dev/null || { err "python3 não encontrado"; exit 1; }
  if [[ ! -x "$VENV/bin/python" ]]; then
    log "Criando venv em .venv…"
    python3 -m venv "$VENV"
  fi
  STAMP="$VENV/.deps-installed"
  if [[ ! -f "$STAMP" || "$ROOT/requirements.txt" -nt "$STAMP" ]]; then
    log "Instalando dependências Python…"
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"
    touch "$STAMP"
  fi
  # Chromium do Playwright é opcional: se faltar, o scraper usa o Chromium do sistema.
  if [[ ! -d "$HOME/.cache/ms-playwright" ]] && ! command -v chromium >/dev/null && ! command -v google-chrome >/dev/null; then
    log "Instalando Chromium do Playwright (uma vez)…"
    "$VENV/bin/python" -m playwright install chromium || err "Falha ao instalar Chromium; scraping com JS ficará indisponível."
  fi

  # 2) build do frontend se necessário
  if (( REBUILD )) || [[ ! -f "$ROOT/backend/static/index.html" ]] || \
     [[ -n "$(find "$ROOT/frontend/src" "$ROOT/frontend/index.html" -newer "$ROOT/backend/static/index.html" -print -quit 2>/dev/null)" ]]; then
    if command -v npm >/dev/null; then
      log "Buildando frontend…"
      ( cd "$ROOT/frontend" && { [[ -d node_modules ]] || npm install --no-audit --no-fund; } && npm run build )
    elif [[ -f "$ROOT/backend/static/index.html" ]]; then
      err "npm ausente; usando build existente."
    else
      err "npm ausente e frontend não buildado. Instale Node.js 18+."; exit 1
    fi
  fi

  # 3) uvicorn em background
  log "Subindo backend em $URL…"
  # `cd` separado do `&`: assim $! é o PID do próprio uvicorn (não de um subshell) e o stop.sh o encerra.
  (
    cd "$ROOT/backend" || exit 1
    O51NT_DATA_DIR="$DATA" O51NT_PORT="$PORT" O51NT_SEARXNG_URL="$SEARXNG_URL" \
      nohup "$VENV/bin/python" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --log-level warning \
      >>"$LOG_FILE" 2>&1 </dev/null &
    echo $! >"$PID_FILE"
  )
  for _ in $(seq 1 40); do
    if curl -fsS "${URL}api/health" >/dev/null 2>&1; then break; fi
    if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then err "Backend morreu. Veja $LOG_FILE"; tail -20 "$LOG_FILE" >&2; exit 1; fi
    sleep 0.5
  done
  curl -fsS "${URL}api/health" >/dev/null 2>&1 || { err "Backend não respondeu. Veja $LOG_FILE"; exit 1; }
  log "Backend OK (PID $(cat "$PID_FILE")). Logs: $LOG_FILE"
fi

# 4) navegador
if (( OPEN_BROWSER )); then
  B="$(choose_browser)"
  log "Abrindo $URL em $B…"
  nohup "$B" "$URL" >/dev/null 2>&1 &
fi
log "Para encerrar: ./stop.sh (o SearXNG continua; pare com: docker stop o51nt-searxng)"
