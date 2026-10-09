#!/usr/bin/env bash
# O51NT — Etapa 10: ferramentas OSINT (as do Kali) na VPS Ubuntu, em /opt/o51nt/ferramentas. Executar com sudo. Idempotente.
# Só OSINT passivo: whois, dig, dnsrecon, subfinder, theHarvester, sherlock, maigret, exiftool, yt-dlp e as sensíveis
# (holehe, h8mail, phoneinfoga — só rodam se "Ferramentas sensíveis" estiver ligado em Tema). Nada de nmap/masscan/
# nuclei/gobuster/wpscan/hydra/sqlmap: varredura e ataque não são OSINT público.
# O serviço o51nt tem ProtectHome=true, por isso os binários ficam em /opt/o51nt/ferramentas/bin (PATH do app).
set -euo pipefail
BASE=/opt/o51nt/ferramentas
BIN=$BASE/bin
log() { printf '[08] %s\n' "$*"; }
[[ $EUID -eq 0 ]] || { echo "execute com sudo"; exit 1; }
install -d -m 755 -o o51nt -g o51nt "$BASE" "$BIN"

log "pacotes do sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq whois dnsutils libimage-exiftool-perl pipx python3-venv curl unzip jq >/dev/null

log "pacotes Python isolados (pipx em $BASE/pipx)"
export PIPX_HOME=$BASE/pipx PIPX_BIN_DIR=$BIN
for pkg in dnsrecon sherlock-project maigret yt-dlp holehe h8mail; do
  if pipx list --short 2>/dev/null | grep -qi "^${pkg%%-*}"; then
    pipx upgrade "$pkg" >/dev/null 2>&1 || true
  else
    pipx install "$pkg" >/dev/null 2>&1 && log "  $pkg instalado" || log "  aviso: $pkg falhou (segue sem ele)"
  fi
done
# theHarvester: o pacote "theHarvester" do PyPI é um placeholder (0.0.1); o projeto real vem do GitHub (laramies)
rm -rf "$BASE/venv-theharvester"; [[ -f $BIN/theHarvester && ! -L $BIN/theHarvester ]] && grep -q venv-theharvester "$BIN/theHarvester" 2>/dev/null && rm -f "$BIN/theHarvester"
# a branch principal exige Python ≥ 3.14; a 4.11.1 é a última que roda no 3.12 do Ubuntu 24.04
if [[ ! -x $BIN/theHarvester ]]; then
  apt-get install -y -qq git >/dev/null 2>&1 || true
  ok=0
  for tag in 4.11.1 4.10.1 4.9.2; do
    if pipx install "git+https://github.com/laramies/theHarvester.git@$tag" >/dev/null 2>&1; then log "  theHarvester $tag instalado (GitHub)"; ok=1; break; fi
  done
  [[ $ok -eq 1 ]] || log "  aviso: theHarvester falhou (segue sem ele)"
fi

baixar_release() { # baixar_release repo padrao_asset destino_binario [arquivo_dentro_do_pacote]
  local repo=$1 padrao=$2 destino=$3 interno=${4:-}
  local url
  url=$(curl -fsSL --max-time 30 "https://api.github.com/repos/$repo/releases/latest" | jq -r --arg p "$padrao" '.assets[] | select(.name | test($p)) | .browser_download_url' | head -1)
  [[ -n "$url" && "$url" != "null" ]] || { log "  aviso: release de $repo não encontrada ($padrao)"; return 0; }
  local tmp; tmp=$(mktemp -d)
  curl -fsSL --max-time 120 "$url" -o "$tmp/pacote" || { log "  aviso: download de $repo falhou"; rm -rf "$tmp"; return 0; }
  case "$url" in
    *.zip) unzip -q -o "$tmp/pacote" -d "$tmp/x" ;;
    *.tar.gz|*.tgz) mkdir -p "$tmp/x" && tar -xzf "$tmp/pacote" -C "$tmp/x" ;;
    *) mkdir -p "$tmp/x" && cp "$tmp/pacote" "$tmp/x/$(basename "$destino")" ;;
  esac
  local bin; bin=$(find "$tmp/x" -type f -name "${interno:-$(basename "$destino")}" | head -1)
  [[ -n "$bin" ]] && install -m 755 "$bin" "$destino" && log "  $(basename "$destino") instalado ($url)" || log "  aviso: binário não encontrado no pacote de $repo"
  rm -rf "$tmp"
}

log "binários Go (releases oficiais do GitHub)"
baixar_release projectdiscovery/subfinder 'subfinder_.*_linux_amd64\.zip$' "$BIN/subfinder" subfinder
baixar_release sundowndev/phoneinfoga 'phoneinfoga_Linux_x86_64\.tar\.gz$' "$BIN/phoneinfoga" phoneinfoga

chown -R o51nt:o51nt "$BASE"
log "verificação"
for b in whois dig exiftool theHarvester dnsrecon sherlock maigret yt-dlp holehe h8mail subfinder phoneinfoga; do
  if PATH="$BIN:$PATH" command -v "$b" >/dev/null 2>&1; then printf '  %-12s ok\n' "$b"; else printf '  %-12s AUSENTE\n' "$b"; fi
done
echo "  pronto: o app lê $BIN (config O51NT_FERRAMENTAS_DIR, padrão); teste em Ferramentas → 'Ferramentas OSINT do servidor'"
