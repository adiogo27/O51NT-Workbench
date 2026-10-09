#!/usr/bin/env bash
# O51NT — Etapa 4: Caddy com HTTPS automático + basic auth na frente do app. Idempotente. Executar com sudo.
# Gera (uma vez) usuário/senha em /root/o51nt-credenciais.txt (600) — entregue ao dono fora do repositório.
set -euo pipefail
APP=/opt/o51nt/app
CRED=/root/o51nt-credenciais.txt
log() { printf '[04] %s\n' "$*"; }
[[ $EUID -eq 0 ]] || { echo "execute com sudo"; exit 1; }

if [[ ! -f "$CRED" ]]; then
  USUARIO="o51nt"
  SENHA="$(python3 -c 'import secrets,string; a=string.ascii_letters+string.digits; print("".join(secrets.choice(a) for _ in range(20)))')"
  printf 'usuario=%s\nsenha=%s\nurl=https://o51nt.sentinela.api.br\ngerado=%s\n' "$USUARIO" "$SENHA" "$(date -Is)" >"$CRED"
  chmod 600 "$CRED"
  log "credenciais geradas em $CRED"
fi
USUARIO=$(awk -F= '/^usuario=/{print $2}' "$CRED")
SENHA=$(awk -F= '/^senha=/{print $2}' "$CRED")
HASH=$(caddy hash-password --plaintext "$SENHA")

sed -e "s|__USUARIO__|$USUARIO|" -e "s|__HASH__|$HASH|" "$APP/deploy/vps/Caddyfile" >/etc/caddy/Caddyfile.novo
caddy validate --config /etc/caddy/Caddyfile.novo --adapter caddyfile >/dev/null
mv /etc/caddy/Caddyfile.novo /etc/caddy/Caddyfile
caddy fmt --overwrite /etc/caddy/Caddyfile >/dev/null 2>&1 || true
# `caddy validate` como root cria o arquivo de log com dono root; devolve ao usuário do serviço.
install -d -m 750 -o caddy -g caddy /var/log/caddy
chown -R caddy:caddy /var/log/caddy
systemctl reload caddy || systemctl restart caddy

log "aguardando certificado…"
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 https://o51nt.sentinela.api.br/api/health || true)
  [[ "$code" == "401" ]] && break
  sleep 3
done
echo "  https sem senha → HTTP $code (esperado 401)"
echo "  https com senha → HTTP $(curl -s -o /dev/null -w '%{http_code}' --max-time 8 -u "$USUARIO:$SENHA" https://o51nt.sentinela.api.br/api/health) (esperado 200)"
echo "  http por IP     → HTTP $(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://162.35.16.238/ || true) (esperado 403)"
echo "  certificado: $(echo | openssl s_client -servername o51nt.sentinela.api.br -connect 127.0.0.1:443 2>/dev/null | openssl x509 -noout -issuer -enddate 2>/dev/null | tr '\n' ' ')"
