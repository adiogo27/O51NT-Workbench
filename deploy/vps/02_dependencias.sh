#!/usr/bin/env bash
# O51NT — Etapa 2: dependências da VPS. Idempotente. Executar como root (ou via sudo).
# Node 24 (NodeSource; OpenClaw exige >= 24.16), Docker CE (SearXNG), Caddy (HTTPS + proxy).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
USUARIO="${O51NT_USER:-o51nt}"
log() { printf '[02] %s\n' "$*"; }
install -d -m 755 /etc/apt/keyrings

if ! command -v node >/dev/null 2>&1 || [[ "$(node -v | cut -d. -f1 | tr -d v)" -lt 24 ]]; then
  log "Node.js 24 (NodeSource)"
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main" >/etc/apt/sources.list.d/nodesource.list
  apt-get update -qq && apt-get install -y -qq nodejs
fi

if ! command -v docker >/dev/null 2>&1; then
  log "Docker CE (repositório oficial)"
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" >/etc/apt/sources.list.d/docker.list
  apt-get update -qq && apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
systemctl enable --now docker >/dev/null
usermod -aG docker "$USUARIO"
# Docker publica portas direto no iptables, contornando o UFW; o SearXNG só publica em 127.0.0.1, mas deixamos explícito:
install -d -m 755 /etc/docker
if [[ ! -f /etc/docker/daemon.json ]]; then
  echo '{ "ip": "127.0.0.1", "log-driver": "json-file", "log-opts": { "max-size": "5m", "max-file": "2" } }' >/etc/docker/daemon.json
  systemctl restart docker
fi

if ! command -v caddy >/dev/null 2>&1; then
  log "Caddy (repositório oficial)"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /etc/apt/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' >/etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy
fi
systemctl enable caddy >/dev/null

log "resumo"
echo "  node $(node -v) | npm $(npm -v) | docker $(docker --version | awk '{print $3}' | tr -d ,) | compose $(docker compose version --short) | caddy $(caddy version | awk '{print $1}')"
echo "  grupos de $USUARIO: $(id -nG "$USUARIO")"
