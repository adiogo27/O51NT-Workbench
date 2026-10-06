#!/usr/bin/env bash
# Encerra o backend do O51NT Workbench iniciado pelo run.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT/.run/uvicorn.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "[o51nt] Nenhum PID registrado; backend não está rodando via run.sh."
  exit 0
fi
PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  for _ in $(seq 1 20); do kill -0 "$PID" 2>/dev/null || break; sleep 0.25; done
  kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
  echo "[o51nt] Backend (PID $PID) encerrado."
else
  echo "[o51nt] Processo $PID já não existia."
fi
rm -f "$PID_FILE"
