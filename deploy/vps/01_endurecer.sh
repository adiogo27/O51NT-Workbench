#!/usr/bin/env bash
# O51NT — Etapa 1: endurecimento básico da VPS (Ubuntu 24.04). Idempotente. Executar como root.
# NÃO altera o sshd (root/senha): isso é a etapa 7, só depois de validar o login do usuário `o51nt`.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
USUARIO="${O51NT_USER:-o51nt}"
TZ_ALVO="America/Sao_Paulo"
log() { printf '[01] %s\n' "$*"; }

log "atualizando pacotes…"
apt-get update -qq
apt-get -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" upgrade -qq
apt-get -y install -qq ufw fail2ban unattended-upgrades apt-listchanges curl ca-certificates gnupg git jq \
  python3-venv python3-pip build-essential sqlite3 htop rsync logrotate

log "timezone → $TZ_ALVO"
timedatectl set-timezone "$TZ_ALVO"

log "usuário $USUARIO (sudo sem senha, chave do root copiada)"
if ! id "$USUARIO" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "O51NT Workbench" "$USUARIO"
fi
usermod -aG sudo "$USUARIO"
echo "$USUARIO ALL=(ALL) NOPASSWD:ALL" >/etc/sudoers.d/90-"$USUARIO"
chmod 440 /etc/sudoers.d/90-"$USUARIO"
install -d -m 700 -o "$USUARIO" -g "$USUARIO" "/home/$USUARIO/.ssh"
install -m 600 -o "$USUARIO" -g "$USUARIO" /root/.ssh/authorized_keys "/home/$USUARIO/.ssh/authorized_keys"

log "firewall UFW: 22/80/443"
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

log "fail2ban (sshd)"
cat >/etc/fail2ban/jail.d/o51nt.local <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd

[sshd]
enabled = true
EOF
systemctl enable --now fail2ban >/dev/null
systemctl restart fail2ban

log "atualizações automáticas de segurança"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
sed -i 's|^//\s*"\${distro_id}:\${distro_codename}-security";|        "${distro_id}:${distro_codename}-security";|' /etc/apt/apt.conf.d/50unattended-upgrades || true
systemctl enable --now unattended-upgrades >/dev/null

log "diretórios do O51NT"
install -d -m 750 -o "$USUARIO" -g "$USUARIO" /opt/o51nt
install -d -m 750 -o "$USUARIO" -g "$USUARIO" /opt/o51nt/backups
touch /opt/o51nt/.env && chown "$USUARIO:$USUARIO" /opt/o51nt/.env && chmod 600 /opt/o51nt/.env

log "resumo"
echo "  tz: $(timedatectl show -p Timezone --value) | ufw: $(ufw status | head -1) | fail2ban: $(systemctl is-active fail2ban) | unattended: $(systemctl is-active unattended-upgrades)"
echo "  usuário: $(id "$USUARIO") | chaves: $(wc -l < /home/$USUARIO/.ssh/authorized_keys)"
echo "  reboot necessário: $([ -f /var/run/reboot-required ] && echo sim || echo não)"
