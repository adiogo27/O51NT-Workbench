#!/usr/bin/env bash
# O51NT — Etapa 7: fecha o SSH (sem root, sem senha). Executar com sudo SÓ depois de validar `ssh o51nt@VM` por chave.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "execute com sudo"; exit 1; }
[[ -s /home/o51nt/.ssh/authorized_keys ]] || { echo "o51nt sem authorized_keys — abortando"; exit 1; }
cat >/etc/ssh/sshd_config.d/90-o51nt.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AllowUsers o51nt
MaxAuthTries 4
LoginGraceTime 30
X11Forwarding no
EOF
sshd -t
systemctl reload ssh 2>/dev/null || systemctl reload sshd
echo "sshd: PermitRootLogin=$(sshd -T | awk '/^permitrootlogin/{print $2}') PasswordAuthentication=$(sshd -T | awk '/^passwordauthentication/{print $2}') AllowUsers=$(sshd -T | awk '/^allowusers/{print $2}')"
