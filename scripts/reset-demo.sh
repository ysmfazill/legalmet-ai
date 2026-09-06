#!/usr/bin/env bash
# METRASIGHT SAFE DEMO RESET — wipes transactional demo activity (inspections,
# evidence, findings, reports, complaints, audit, stored files) while
# preserving login accounts, regulatory data, compliance rules and procedures,
# then re-seeds the single intentional demo inspection through the REAL
# pipeline (real intake + real local OCR + real evaluation + real review).
#
# Deterministic and idempotent: running it twice leaves the same state.
#
# Usage:
#   npm run reset:demo          (from the repo root)
#   bash scripts/reset-demo.sh
#
# The backend should ideally be STOPPED while resetting (the script also
# deletes stored image files). `bash scripts/demo.sh --reset` stops nothing
# but runs this before starting the servers fresh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$ROOT/services/api"

PY=""
if [ -f "$API/.venv/Scripts/python.exe" ]; then
  PY="$API/.venv/Scripts/python.exe"
elif [ -f "$API/.venv/bin/python" ]; then
  PY="$API/.venv/bin/python"
else
  echo "Backend virtualenv not found at $API/.venv — create it first (see README)." >&2
  exit 1
fi

(cd "$API" && exec "$PY" -m scripts.reset_demo)
