#!/usr/bin/env bash
# O51NT — Etapa 3: instala/atualiza o O51NT Workbench em /opt/o51nt como serviço systemd. Idempotente.
# Executar como o usuário `o51nt` (usa sudo só para systemd). Reexecutar = atualizar (git pull + build + restart).
set -euo pipefail
BASE=/opt/o51nt
APP=$BASE/app
VENV=$BASE/venv
REPO="${O51NT_REPO:-https://github.com/adiogo27/O51NT-Workbench.git}"
RAMO="${O51NT_BRANCH:-main}"
log() { printf '[03] %s\n' "$*"; }

[[ "$(id -un)" == "o51nt" ]] || { echo "execute como o usuário o51nt"; exit 1; }
mkdir -p "$BASE/data" "$BASE/backups"
chmod 750 "$BASE/data"

if [[ -d "$APP/.git" ]]; then
  log "atualizando código ($RAMO)"
  git -C "$APP" fetch -q origin "$RAMO" && git -C "$APP" reset -q --hard "origin/$RAMO"
else
  log "clonando $REPO"
  git clone -q --branch "$RAMO" "$REPO" "$APP"
fi
log "versão: $(git -C "$APP" log --oneline -1)"

log "venv + dependências Python"
[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP/requirements.txt"
# Chromium do Playwright (scraper com JS: OneMillionTweetMap/Convocações). Falha não é fatal.
if [[ ! -d "$HOME/.cache/ms-playwright" ]]; then
  log "Chromium do Playwright (uma vez)"
  "$VENV/bin/python" -m playwright install --with-deps chromium >/dev/null 2>&1 || "$VENV/bin/python" -m playwright install chromium >/dev/null 2>&1 || log "aviso: Chromium do Playwright não instalado"
fi

log "frontend (npm ci + build)"
( cd "$APP/frontend" && npm ci --no-audit --no-fund --silent && npm run --silent build )

log "SearXNG (Docker, 127.0.0.1:8080) — opcional"
if docker info >/dev/null 2>&1; then
  mkdir -p "$APP/data/searxng"
  if [[ ! -f "$APP/data/searxng/settings.yml" ]]; then
    sed "s/__SECRET__/$(python3 -c 'import secrets; print(secrets.token_hex(32))')/" "$APP/deploy/searxng/settings.yml" >"$APP/data/searxng/settings.yml"
  fi
  ( cd "$APP" && docker compose up -d searxng >/dev/null 2>&1 ) && log "SearXNG no ar" || log "aviso: SearXNG não subiu (segue sem ele)"
else
  log "sem acesso ao Docker nesta sessão (relogar para o grupo docker valer); SearXNG fica para depois"
fi

log ".env"
touch "$BASE/.env" && chmod 600 "$BASE/.env"
grep -q '^O51NT_SEARXNG_URL=' "$BASE/.env" || echo 'O51NT_SEARXNG_URL=http://127.0.0.1:8080' >>"$BASE/.env"
if ! grep -q '^TELEGRAM_BOT_TOKEN=' "$BASE/.env"; then
  log "AVISO: TELEGRAM_BOT_TOKEN ausente em $BASE/.env (canal Telegram ficará desativado até ser definido)"
fi
grep -q '^TELEGRAM_CHAT_ID=' "$BASE/.env" || echo 'TELEGRAM_CHAT_ID=371824016' >>"$BASE/.env"

log "serviço systemd + backup diário"
sudo install -m 644 "$APP/deploy/vps/o51nt.service" /etc/systemd/system/o51nt.service
sudo install -m 644 "$APP/deploy/vps/o51nt-backup.service" /etc/systemd/system/o51nt-backup.service
sudo install -m 644 "$APP/deploy/vps/o51nt-backup.timer" /etc/systemd/system/o51nt-backup.timer
sudo install -m 755 "$APP/deploy/vps/backup.sh" "$BASE/backup.sh"
sudo systemctl daemon-reload
sudo systemctl enable o51nt.service o51nt-backup.timer >/dev/null
sudo systemctl restart o51nt.service
sudo systemctl start o51nt-backup.timer

for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:8051/api/health >/dev/null 2>&1 && break; sleep 1; done
echo "  health: $(curl -fsS http://127.0.0.1:8051/api/health || echo FALHOU)"
echo "  serviço: $(systemctl is-active o51nt) | watchdog: $(systemctl show -p WatchdogUSec --value o51nt) | timer backup: $(systemctl is-active o51nt-backup.timer)"
