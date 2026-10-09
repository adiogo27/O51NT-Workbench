#!/usr/bin/env bash
# O51NT — Etapa 9: Cloudflare na frente do Caddy. Executar com sudo. Idempotente.
#   07_cloudflare.sh           → atualiza as faixas de IP da Cloudflare em /etc/caddy/confiaveis.caddy (IP real do visitante
#                                nos logs, no fail2ban e no app) e recarrega o Caddy. Seguro rodar antes de ativar o proxy.
#   07_cloudflare.sh --fechar  → além disso, restringe 80/443 no UFW às faixas da Cloudflare (ninguém fala com o servidor
#                                sem passar pelo WAF/Access). Só executa se o domínio JÁ resolve para a Cloudflare.
#   07_cloudflare.sh --abrir   → volta a aceitar 80/443 de qualquer origem (reverte o --fechar).
# Instala o timer semanal o51nt-cloudflare.timer, que reaplica o último estado (aberto/fechado) com faixas atualizadas.
set -euo pipefail
DOMINIO="${O51NT_DOMINIO:-o51nt.sentinela.api.br}"
ARQ=/etc/caddy/confiaveis.caddy
ESTADO=/etc/o51nt-cloudflare.estado
log() { printf '[07] %s\n' "$*"; }
[[ $EUID -eq 0 ]] || { echo "execute com sudo"; exit 1; }
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
MODO="${1:-}"
if [[ -z "$MODO" && -f $ESTADO ]]; then MODO="--$(cat "$ESTADO")"; fi

log "baixando faixas de IP da Cloudflare"
curl -fsS --max-time 20 https://www.cloudflare.com/ips-v4 -o "$TMP/v4"
curl -fsS --max-time 20 https://www.cloudflare.com/ips-v6 -o "$TMP/v6"
FAIXAS=$(cat "$TMP/v4" "$TMP/v6" | grep -E '^[0-9a-fA-F:.]+/[0-9]+$' | tr '\n' ' ')
[[ $(wc -w <<<"$FAIXAS") -ge 15 ]] || { echo "lista de IPs da Cloudflare suspeita: $FAIXAS"; exit 1; }

log "proxies confiáveis do Caddy → $ARQ"
cp -f "$ARQ" "$TMP/confiaveis.bak" 2>/dev/null || true
printf 'trusted_proxies static private_ranges %s\n' "$FAIXAS" >"$ARQ"
if ! caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>"$TMP/err"; then
  [[ -f "$TMP/confiaveis.bak" ]] && cp -f "$TMP/confiaveis.bak" "$ARQ"
  echo "Caddyfile inválido com as novas faixas — revertido:"; cat "$TMP/err"; exit 1
fi
systemctl reload caddy

proxied() { # o domínio resolve para IPs da Cloudflare?
  python3 - "$DOMINIO" "$FAIXAS" <<'PY'
import ipaddress, socket, sys
dom, faixas = sys.argv[1], [ipaddress.ip_network(f) for f in sys.argv[2].split()]
ips = {i[4][0] for i in socket.getaddrinfo(dom, 443)}
ok = ips and all(any(ipaddress.ip_address(ip) in f for f in faixas) for ip in ips)
print(" ".join(sorted(ips)))
sys.exit(0 if ok else 1)
PY
}
limpar_regras_cf() {
  while read -r n; do ufw --force delete "$n" >/dev/null; done < <(ufw status numbered | grep -F '# cloudflare' | sed -E 's/^\[ *([0-9]+)\].*/\1/' | sort -rn)
}

case "$MODO" in
  --fechar)
    if ! IPS=$(proxied); then
      echo "ABORTADO: $DOMINIO ainda não resolve para a Cloudflare ($IPS). Ative o proxy (nuvem laranja) e rode de novo."; exit 2
    fi
    log "restringindo 80/443 às faixas da Cloudflare (domínio → $IPS)"
    limpar_regras_cf
    for r in $FAIXAS; do ufw allow proto tcp from "$r" to any port 80,443 comment cloudflare >/dev/null; done
    ufw --force delete allow 80/tcp >/dev/null 2>&1 || true
    ufw --force delete allow 443/tcp >/dev/null 2>&1 || true
    echo fechar >"$ESTADO"
    ;;
  --abrir)
    log "reabrindo 80/443 para qualquer origem"
    limpar_regras_cf
    ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
    echo abrir >"$ESTADO"
    ;;
  "") : ;;
  *) echo "uso: $0 [--fechar|--abrir]"; exit 1 ;;
esac

# timer semanal: faixas novas + reaplica o estado
cat >/etc/systemd/system/o51nt-cloudflare.service <<EOF
[Unit]
Description=O51NT: atualiza faixas de IP da Cloudflare (Caddy trusted_proxies / UFW)
After=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/bin/bash /opt/o51nt/app/deploy/vps/07_cloudflare.sh
EOF
cat >/etc/systemd/system/o51nt-cloudflare.timer <<'EOF'
[Unit]
Description=O51NT: faixas da Cloudflare (semanal)
[Timer]
OnCalendar=weekly
RandomizedDelaySec=1h
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now o51nt-cloudflare.timer >/dev/null 2>&1

echo "  faixas: $(wc -w <<<"$FAIXAS") | estado do firewall: $(cat "$ESTADO" 2>/dev/null || echo aberto) | ufw 443: $(ufw status | grep -c '443')"
echo "  $DOMINIO → $(getent ahosts "$DOMINIO" | awk '{print $1}' | sort -u | tr '\n' ' ')"
