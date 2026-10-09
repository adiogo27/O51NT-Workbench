#!/usr/bin/env bash
# O51NT — grava as chaves na VM (sem passar por chat/repositório) e reinicia os serviços. Executar com sudo, interativo.
# Pergunta cada valor (digitação oculta); Enter em branco mantém o atual. Nada é impresso de volta.
set -euo pipefail
ENV_APP=/opt/o51nt/.env
OC=/home/openclaw/.openclaw
[[ $EUID -eq 0 ]] || { echo "execute com sudo"; exit 1; }
umask 077

ler() { # ler VAR "rótulo"  → define $VALOR (vazio = manter)
  local atual=""; atual=$(grep -E "^$1=" "$ENV_APP" 2>/dev/null | head -1 | cut -d= -f2- || true)
  printf '%s%s: ' "$2" "$([[ -n "$atual" ]] && echo ' [já definido; Enter mantém]' || echo '')"
  IFS= read -rs VALOR; echo
  [[ -n "$VALOR" ]] || VALOR="$atual"
}
gravar() { # gravar ARQUIVO VAR VALOR (substitui ou acrescenta)
  touch "$1"; grep -vE "^$2=" "$1" >"$1.tmp" || true; [[ -n "$3" ]] && printf '%s=%s\n' "$2" "$3" >>"$1.tmp"; mv "$1.tmp" "$1"
}

ler TELEGRAM_BOT_TOKEN "Token do bot do Telegram (@BotFather)"; TG="$VALOR"
ler ANTHROPIC_API_KEY  "Chave da API Anthropic (Claude)";        AN="$VALOR"
ler OPENAI_API_KEY     "Chave da API OpenAI";                    OA="$VALOR"

gravar "$ENV_APP" TELEGRAM_BOT_TOKEN "$TG"
gravar "$ENV_APP" TELEGRAM_CHAT_ID "${TELEGRAM_CHAT_ID:-371824016}"
gravar "$ENV_APP" ANTHROPIC_API_KEY "$AN"
gravar "$ENV_APP" OPENAI_API_KEY "$OA"
chown o51nt:o51nt "$ENV_APP"; chmod 600 "$ENV_APP"

if id openclaw >/dev/null 2>&1; then
  mkdir -p "$OC"
  gravar "$OC/secrets.env" ANTHROPIC_API_KEY "$AN"
  gravar "$OC/secrets.env" OPENAI_API_KEY "$OA"
  if [[ -n "$TG" ]]; then
    printf '%s' "$TG" >"$OC/telegram.token"
    sed -i 's/enabled: false,/enabled: true,/' "$OC/openclaw.json" 2>/dev/null || true
  fi
  chown -R openclaw:openclaw "$OC"; chmod 600 "$OC/secrets.env" "$OC/openclaw.json"; [[ -f "$OC/telegram.token" ]] && chmod 600 "$OC/telegram.token"
  UIDO=$(id -u openclaw)
  sudo -u openclaw env XDG_RUNTIME_DIR=/run/user/$UIDO DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$UIDO/bus systemctl --user restart openclaw-gateway.service || true
fi

systemctl restart o51nt.service
for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:8051/api/health >/dev/null 2>&1 && break; sleep 1; done
echo "O51NT: $(systemctl is-active o51nt) | Telegram: $(curl -fsS http://127.0.0.1:8051/api/settings/telegram)"
if [[ -n "$TG" ]]; then
  echo "teste: $(curl -fsS -X POST http://127.0.0.1:8051/api/settings/telegram/teste)"
fi
echo "concluído — nenhum valor foi exibido; chaves em $ENV_APP e $OC/{secrets.env,telegram.token}"
