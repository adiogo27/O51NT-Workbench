#!/usr/bin/env bash
# Backup diário do O51NT: cópia consistente do SQLite (API .backup) + tar de data/ (evidências, settings, alertas).
# Mantém os últimos 7. Rode como o usuário o51nt (systemd timer o51nt-backup).
set -euo pipefail
BASE=/opt/o51nt
DATA=$BASE/data
DEST=$BASE/backups
STAMP=$(date +%Y%m%d_%H%M%S)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$DEST"
if [[ -f "$DATA/o51nt.db" ]]; then
  sqlite3 "$DATA/o51nt.db" ".backup '$TMP/o51nt.db'"
fi
tar -czf "$DEST/o51nt_$STAMP.tgz" -C "$TMP" . -C "$DATA" --exclude='./models' --exclude='./logs' --exclude='./searxng' .
ls -1t "$DEST"/o51nt_*.tgz | tail -n +8 | xargs -r rm -f
echo "backup: $DEST/o51nt_$STAMP.tgz ($(du -h "$DEST/o51nt_$STAMP.tgz" | cut -f1))"
