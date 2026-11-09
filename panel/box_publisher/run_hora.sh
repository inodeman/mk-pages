#!/bin/sh
# Cifra la última hora en el checkout de Pages. No hace commit, push ni reset.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
WRITE_DIR=${WRITE_DIR:-$ROOT}
if [ -z "${MK_PANEL_KEY:-}" ]; then
  echo "falta MK_PANEL_KEY en el entorno" >&2
  exit 2
fi
exec python3 "$ROOT/panel/publish_hora.py" \
  --sources "$ROOT/panel/hora_sources.json" \
  --write-dir "$WRITE_DIR"
