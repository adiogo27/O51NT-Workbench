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

ler_visivel() { # ler_visivel VAR "rótulo" "padrão" → $VALOR (Enter = atual ou padrão)
  local atual=""; atual=$(grep -E "^$1=" "$ENV_APP" 2>/dev/null | head -1 | cut -d= -f2- || true)
  printf '%s [%s]: ' "$2" "${atual:-$3}"; IFS= read -r VALOR
  [[ -n "$VALOR" ]] || VALOR="${atual:-$3}"
}

ler TELEGRAM_BOT_TOKEN "Token do bot do Telegram (@BotFather)"; TG="$VALOR"
ler ANTHROPIC_API_KEY  "Chave da API Anthropic (Claude)";        AN="$VALOR"
ler OPENAI_API_KEY     "Chave da API OpenAI";                    OA="$VALOR"
echo "    Chave Anthropic de organização (sem escopo de workspace) exige o ID do workspace (console → Settings → Workspaces, 'wrkspc_…')."
ler_visivel ANTHROPIC_WORKSPACE_ID "ID do workspace Anthropic (Enter se a chave já for de workspace)" ""; AW="$VALOR"
echo "--- E-mail de login do painel (SMTP). Gmail: ative a verificação em 2 etapas e crie uma 'senha de app' em myaccount.google.com/apppasswords"
echo "    Atenção: aqui vai o SERVIDOR (ex.: smtp.gmail.com); a senha de app é pedida mais abaixo."
ler_visivel SMTP_HOST "Servidor SMTP" "smtp.gmail.com";      SH="$VALOR"
[[ "$SH" == *.* && "$SH" != *" "* ]] || { echo "    valor inválido para servidor; usando smtp.gmail.com"; SH="smtp.gmail.com"; }
ler_visivel SMTP_PORT "Porta SMTP (587 STARTTLS)" "587";     SP="$VALOR"
ler_visivel SMTP_USER "Usuário SMTP (e-mail remetente)" "adiogo27@gmail.com"; SU="$VALOR"
ler SMTP_PASSWORD     "Senha SMTP / senha de app";           SS="$VALOR"
ler_visivel SMTP_FROM "Remetente (From, um e-mail)" "$SU";   SF="$VALOR"
[[ "$SF" == *@* ]] || SF="$SU"

gravar "$ENV_APP" TELEGRAM_BOT_TOKEN "$TG"
gravar "$ENV_APP" TELEGRAM_CHAT_ID "${TELEGRAM_CHAT_ID:-371824016}"
gravar "$ENV_APP" ANTHROPIC_API_KEY "$AN"
gravar "$ENV_APP" OPENAI_API_KEY "$OA"
gravar "$ENV_APP" ANTHROPIC_WORKSPACE_ID "$AW"
gravar "$ENV_APP" SMTP_HOST "$SH"; gravar "$ENV_APP" SMTP_PORT "$SP"; gravar "$ENV_APP" SMTP_USER "$SU"
gravar "$ENV_APP" SMTP_PASSWORD "$SS"; gravar "$ENV_APP" SMTP_FROM "$SF"
grep -q '^O51NT_ADMIN_EMAIL=' "$ENV_APP" || gravar "$ENV_APP" O51NT_ADMIN_EMAIL "adiogo27@gmail.com"
chown o51nt:o51nt "$ENV_APP"; chmod 600 "$ENV_APP"

if id openclaw >/dev/null 2>&1; then
  mkdir -p "$OC"
  gravar "$OC/secrets.env" ANTHROPIC_API_KEY "$AN"
  gravar "$OC/secrets.env" OPENAI_API_KEY "$OA"
  gravar "$OC/secrets.env" ANTHROPIC_WORKSPACE_ID "$AW"
  if [[ -n "$TG" ]]; then
    printf '%s' "$TG" >"$OC/telegram.token"
    # o OpenClaw reescreve o config em JSON; usar a CLI em vez de sed
    UIDO=$(id -u openclaw)
    sudo -u openclaw env XDG_RUNTIME_DIR=/run/user/$UIDO HOME=/home/openclaw bash -c 'cd ~ && openclaw config set channels.telegram.enabled true' >/dev/null 2>&1 || true
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
echo "login do painel: $(curl -fsS http://127.0.0.1:8051/api/auth/estado) (canal=email significa SMTP ativo)"
echo "concluído — nenhum valor foi exibido; chaves em $ENV_APP e $OC/{secrets.env,telegram.token}"
