#!/usr/bin/env bash
# O51NT — chave de deploy para o GitHub Actions (job `deploy` em .github/workflows/ci.yml). Idempotente.
# Executar na VM como root (sudo). Gera um par de chaves ed25519 exclusivo para o deploy, instala a chave pública em
# /home/o51nt/.ssh/authorized_keys RESTRITA a um único comando (git pull + 03_o51nt.sh) e imprime o que colar nos
# segredos do repositório (Settings → Secrets and variables → Actions):
#   VPS_HOST        162.35.16.238 (ou o domínio)
#   VPS_USER        o51nt
#   VPS_SSH_KEY     a chave PRIVADA impressa abaixo (inteira, com as linhas BEGIN/END)
#   VPS_KNOWN_HOSTS a linha de `ssh-keyscan` impressa abaixo (fixa a identidade da VM; evita aceitar host desconhecido)
# A chave privada NÃO fica na VM depois de impressa (só a pública). Rode de novo para gerar outra e revogar a anterior.
set -euo pipefail
U=o51nt
HOME_U=$(getent passwd "$U" | cut -d: -f6)
[[ -n "$HOME_U" ]] || { echo "usuário $U não existe (rode 01_endurecer.sh antes)"; exit 1; }
HOST="${VPS_HOST:-$(hostname -I | awk '{print $1}')}"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
ssh-keygen -q -t ed25519 -N "" -C "o51nt-deploy-github-actions" -f "$TMP/chave"
PUB=$(cat "$TMP/chave.pub")

install -d -m 700 -o "$U" -g "$U" "$HOME_U/.ssh"
AK="$HOME_U/.ssh/authorized_keys"
touch "$AK"; chown "$U:$U" "$AK"; chmod 600 "$AK"
# remove chaves de deploy anteriores (mesmo comentário) e instala a nova, restrita ao comando de atualização
grep -v 'o51nt-deploy-github-actions' "$AK" >"$TMP/ak" || true
echo "command=\"cd /opt/o51nt/app && git pull -q --ff-only && bash deploy/vps/03_o51nt.sh\",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty $PUB" >>"$TMP/ak"
install -m 600 -o "$U" -g "$U" "$TMP/ak" "$AK"

echo "=============================================================="
echo "Segredos do repositório (GitHub → Settings → Secrets → Actions)"
echo "=============================================================="
echo "VPS_HOST=$HOST"
echo "VPS_USER=$U"
echo "VPS_KNOWN_HOSTS="
ssh-keyscan -t ed25519 -H "$HOST" 2>/dev/null || ssh-keyscan -t ed25519 -H 127.0.0.1 2>/dev/null | sed "s/^[^ ]*/$HOST/"
echo "VPS_SSH_KEY= (chave privada; copie TUDO, inclusive BEGIN/END)"
cat "$TMP/chave"
echo "=============================================================="
echo "Chave pública instalada em $AK, restrita a: cd /opt/o51nt/app && git pull && bash deploy/vps/03_o51nt.sh"
echo "Teste de fora (após gravar os segredos): o job 'deploy' roda sozinho no próximo merge na main."
