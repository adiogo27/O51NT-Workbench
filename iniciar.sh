#!/usr/bin/env bash
# O51NT Workbench — inicializador.
# Sobe o backend (via run.sh, sem perguntas) e abre uma aba no navegador padrão com o sistema rodando.
#
# Uso:
#   ./iniciar.sh                abre o sistema (sobe o backend antes, se ele não estiver no ar)
#   ./iniciar.sh --atalho       (re)gera o lançador "O51NT Workbench.desktop" nesta pasta
#   ./iniciar.sh --instalar     instala o lançador no menu de aplicativos e na área de trabalho
#   ./iniciar.sh --desinstalar  remove o lançador do menu e da área de trabalho
#
# Navegador: preferencias.navegadorPadrao de data/settings.json (aba Tema), quando definido;
# com "auto" ou sem configuração, usa o navegador padrão do sistema (xdg-open).
# Variáveis de ambiente: O51NT_HOST / O51NT_PORT (as mesmas do run.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
HOST="${O51NT_HOST:-127.0.0.1}"
PORT="${O51NT_PORT:-8051}"
URL="http://$HOST:$PORT/"
LOG="$ROOT/data/logs/iniciar.log"
LOCK="$ROOT/.run/iniciar.lock"
ICON="$ROOT/deploy/o51nt.svg"
LAUNCHER="$ROOT/O51NT Workbench.desktop"
APP_ID="o51nt-workbench.desktop"

log() { printf '[o51nt] %s\n' "$*"; }

# O lançador roda sem terminal: avisos também vão como notificação da área de trabalho.
avisar() {  # avisar <low|normal|critical> <mensagem>
  log "$2"
  command -v notify-send >/dev/null 2>&1 || return 0
  notify-send -a "O51NT Workbench" -u "$1" -i "$ICON" "O51NT Workbench" "$2" >/dev/null 2>&1 || true
}

backend_ok() { curl -fsS --max-time 3 "${URL}api/health" >/dev/null 2>&1; }

preferencia_navegador() {
  [[ -f "$ROOT/data/settings.json" ]] || return 0
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("preferencias",{}).get("navegadorPadrao",""))' \
    "$ROOT/data/settings.json" 2>/dev/null || true
}

# Só executa nomes de navegadores conhecidos (mesma lista do run.sh), nunca um comando arbitrário do JSON.
NAVEGADORES=(firefox firefox-esr chromium chromium-browser google-chrome google-chrome-stable brave-browser brave microsoft-edge opera vivaldi)

navegador_conhecido() {
  local b
  for b in "${NAVEGADORES[@]}"; do [[ "$1" == "$b" ]] && return 0; done
  return 1
}

abrir_aba() {
  local pref cmd=()
  pref="$(preferencia_navegador)"
  if [[ -n "$pref" ]] && navegador_conhecido "$pref" && command -v "$pref" >/dev/null 2>&1; then
    case "$pref" in
      firefox*) cmd=("$pref" --new-tab "$URL") ;;
      *) cmd=("$pref" "$URL") ;;  # Chrome/Chromium/Brave/Edge/Opera/Vivaldi abrem aba na janela existente
    esac
  elif command -v xdg-open >/dev/null 2>&1; then
    cmd=(xdg-open "$URL")  # navegador padrão do sistema
  else
    cmd=(python3 -m webbrowser -t "$URL")
  fi
  log "Abrindo $URL em ${cmd[0]}…"
  # processo destacado: o navegador não fica preso ao inicializador nem herda descritores dele
  if command -v setsid >/dev/null 2>&1; then
    setsid -f "${cmd[@]}" >/dev/null 2>&1 </dev/null
  else
    nohup "${cmd[@]}" >/dev/null 2>&1 </dev/null &
  fi
}

iniciar() {
  mkdir -p "$ROOT/data/logs" "$ROOT/.run"
  # Um inicializador por vez: cliques repetidos esperam o primeiro terminar, sem subir dois backends.
  exec 9>"$LOCK"
  flock -w 900 9 || { avisar critical "Outro inicializador está preso há 15 min. Veja $LOG"; exit 1; }

  if backend_ok; then
    log "Backend já está no ar em $URL"
  else
    avisar normal "Iniciando… (a primeira execução instala dependências e pode levar alguns minutos)"
    printf '\n==== %s ====\n' "$(date '+%F %T')" >>"$LOG"
    # 9>&- : o uvicorn (filho do run.sh) não pode herdar o lock, senão ele nunca seria liberado
    if ! "$ROOT/run.sh" --no-browser 9>&- </dev/null 2>&1 | tee -a "$LOG"; then
      avisar critical "Falha ao subir o backend. Detalhes em $LOG"
      exit 1
    fi
    backend_ok || { avisar critical "O backend não respondeu em $URL. Detalhes em $LOG"; exit 1; }
  fi
  exec 9>&-  # libera o lock antes de abrir o navegador
  abrir_aba
}

# Marca o lançador como confiável: GNOME (extensão DING) e Thunar/XFCE. Sem gio, o primeiro
# duplo clique apenas pede confirmação.
confiar() {
  command -v gio >/dev/null 2>&1 || return 0
  gio set "$1" metadata::trusted true >/dev/null 2>&1 || true
  gio set -t string "$1" metadata::xfce-exe-checksum "$(sha256sum "$1" | cut -d' ' -f1)" >/dev/null 2>&1 || true
}

gerar_atalho() {
  python3 - "$ROOT" "$LAUNCHER" <<'PY'
import sys

root, destino = sys.argv[1], sys.argv[2]


def exec_arg(caminho: str) -> str:
    # Desktop Entry Spec: argumento entre aspas, escapando " ` $ \ (regra do Exec) e depois \ (regra de string)
    esc = "".join("\\" + c if c in '"`$\\' else c for c in caminho)
    return '"' + esc.replace("\\", "\\\\") + '"'


def valor(s: str) -> str:
    return s.replace("\\", "\\\\")


with open(destino, "w", encoding="utf-8") as fh:
    fh.write(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.5\n"
        "Name=O51NT Workbench\n"
        "GenericName=Workbench OSINT\n"
        "Comment=Sobe o backend local e abre o O51NT Workbench no navegador padrão\n"
        f"Exec={exec_arg(root + '/iniciar.sh')}\n"
        f"Path={valor(root)}\n"
        f"Icon={valor(root + '/deploy/o51nt.svg')}\n"
        "Terminal=false\n"
        "StartupNotify=false\n"
        "Categories=Network;\n"
        "Keywords=OSINT;Google;Dorks;PRF;Evidências;\n"
    )
PY
  chmod +x "$LAUNCHER"
  confiar "$LAUNCHER"
  log "Lançador gerado: $LAUNCHER"
}

dir_area_de_trabalho() {
  local d
  d="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
  [[ -n "$d" && "$d" != "$HOME" && -d "$d" ]] && printf '%s\n' "$d"
  return 0
}

instalar() {
  gerar_atalho
  local apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications" desk
  mkdir -p "$apps"
  cp "$LAUNCHER" "$apps/$APP_ID"
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$apps" 2>/dev/null || true
  log "Menu de aplicativos: $apps/$APP_ID"
  desk="$(dir_area_de_trabalho)"
  if [[ -n "$desk" ]]; then
    cp "$LAUNCHER" "$desk/$APP_ID"
    chmod +x "$desk/$APP_ID"
    confiar "$desk/$APP_ID"
    log "Área de trabalho: $desk/$APP_ID"
  fi
}

desinstalar() {
  local apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications" desk
  rm -f "$apps/$APP_ID"
  desk="$(dir_area_de_trabalho)"
  [[ -n "$desk" ]] && rm -f "$desk/$APP_ID"
  log "Lançador removido do menu e da área de trabalho (o desta pasta foi mantido)."
}

case "${1:-}" in
  "") iniciar ;;
  --atalho) gerar_atalho ;;
  --instalar) instalar ;;
  --desinstalar) desinstalar ;;
  -h|--help) sed -n '2,13p' "$0" ;;
  *) log "Opção desconhecida: $1 (use --help)"; exit 2 ;;
esac
