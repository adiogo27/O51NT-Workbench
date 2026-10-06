#!/usr/bin/env bash
# Suíte completa do O51NT Workbench num único comando (tudo local, sem `npm install -g`).
# Uso: ./test.sh            → pytest paralelo + sequencial, Vitest e Playwright E2E
#      ./test.sh --quick    → pula o E2E
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
[[ -x .venv/bin/pytest ]] || { echo "[o51nt] .venv ausente — rode ./run.sh uma vez (cria venv e deps)."; exit 1; }
[[ -d frontend/node_modules ]] || (cd frontend && npm install --no-audit --no-fund)
step() { printf '\n\033[1;34m[o51nt] %s\033[0m\n' "$*"; }
step "pytest -n auto (paralelo)";  .venv/bin/pytest -n auto -q -p no:warnings
step "pytest (sequencial)";        .venv/bin/pytest -q -p no:warnings
step "vitest (frontend unit)";     (cd frontend && npm run --silent test:unit)
step "typecheck (tsc)";            (cd frontend && npm run --silent typecheck)
if [[ "${1:-}" != "--quick" ]]; then
  step "build + playwright (E2E)"; (cd frontend && npm run --silent build >/dev/null && npm run --silent test:e2e)
fi
step "OK — todas as suítes passaram."
