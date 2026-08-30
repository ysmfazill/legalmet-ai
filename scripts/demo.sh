#!/usr/bin/env bash
# METRASIGHT one-command localhost demo (Prompt 10, Phase 2).
#
# Installs what is missing, starts the backend (FastAPI) and the frontend
# (Vite) together, and shuts both down on Ctrl+C. This is a LOCALHOST demo
# runner — it never deploys anything, never needs the network after the
# one-time OCR model download, and never touches a remote database.
#
# Usage:
#   bash scripts/demo.sh            # start (or reuse) the local demo
#   bash scripts/demo.sh --fresh    # ALSO wipe the local demo database first
#                                   # (legalmet.db + storage/) — first boot then
#                                   # re-seeds, paying the real-OCR cost (~2 min)
#
# Everything the script does is documented step by step in README.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$ROOT/services/api"
FRONTEND_URL="http://localhost:5173"
BACKEND_URL="http://localhost:8000"

FRESH=0
[ "${1:-}" = "--fresh" ] && FRESH=1

step() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }

# --- 1. Frontend / shared packages ------------------------------------------
step "Frontend dependencies (skipped when already installed)"
if [ ! -d "$ROOT/node_modules" ]; then
  (cd "$ROOT" && npm install)
else
  echo "node_modules present — skipping npm install"
fi

# --- 2. Backend virtualenv ---------------------------------------------------
step "Backend virtualenv (skipped when already installed)"
if [ ! -d "$API/.venv" ]; then
  echo "Creating .venv (first run only)..."
  (cd "$API" && python -m venv .venv)
  "$API/.venv/Scripts/python.exe" -m pip install --quiet -r "$API/requirements.txt" -r "$API/requirements-dev.txt" ||
    "$API/.venv/bin/python" -m pip install --quiet -r "$API/requirements.txt" -r "$API/requirements-dev.txt"
  echo "NOTE: for real OCR also run:"
  echo '  pip install "paddlepaddle==3.0.0" "paddleocr==3.1.0" "paddlex==3.1.0"'
  echo "  (without it the app still runs; perception reports AI_SERVICE_UNAVAILABLE honestly)"
else
  echo ".venv present — skipping pip install"
fi

# --- 3. Optional fresh demo database ----------------------------------------
if [ "$FRESH" = "1" ]; then
  step "Fresh database requested — removing legalmet.db and storage/"
  rm -f "$API/legalmet.db"
  rm -rf "$API/storage"
  echo "First boot will re-seed through the real services (~2 minutes, real OCR)."
fi

# --- 4. Start backend + frontend, stop both on exit -------------------------
step "Starting backend ($BACKEND_URL) and frontend ($FRONTEND_URL)"
PIDS=()
cleanup() {
  echo ""
  step "Stopping demo servers..."
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(cd "$API" && exec .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000) &
PIDS+=($!)
(cd "$ROOT" && exec npm run dev:web) &
PIDS+=($!)

echo ""
echo "  Frontend : $FRONTEND_URL   (login: inspector@legalmet.local / changeme-inspector)"
echo "  Backend  : $BACKEND_URL/api/v1/health"
echo "  First boot with a fresh DB seeds 4 demo inspections via real OCR (~2 min);"
echo "  later boots take ~2 s. Ctrl+C stops both servers."
echo ""

wait
