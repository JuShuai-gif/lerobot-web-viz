#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
DATASET_PATH="${1:-${LEROBOT_DATASET_PATH:-}}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
HOST="${HOST:-0.0.0.0}"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
  python3 -m venv "$BACKEND_DIR/.venv"
fi

source "$BACKEND_DIR/.venv/bin/activate"
pip install -r "$BACKEND_DIR/requirements.txt"
deactivate

cd "$FRONTEND_DIR"
npm install

if [[ -n "$DATASET_PATH" ]]; then
  export LEROBOT_DATASET_PATH="$DATASET_PATH"
fi
export LEROBOT_BROWSE_ROOTS="${LEROBOT_BROWSE_ROOTS:-${DATASET_PATH:-/data:/home}}"

cd "$BACKEND_DIR"
"$BACKEND_DIR/.venv/bin/uvicorn" app.main:app --host "$HOST" --port "$BACKEND_PORT" &
BACKEND_PID=$!

cd "$FRONTEND_DIR"
VITE_API_BASE="${VITE_API_BASE:-}" npm run dev -- --host "$HOST" --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

cat <<EOF

lerobot-web-viz is running.
Backend:  http://localhost:$BACKEND_PORT
Frontend: http://localhost:$FRONTEND_PORT

Open the frontend and click Browse to choose a server directory, or start with:
  ./start.sh /path/to/dataset

Press Ctrl-C to stop both services.
EOF

wait -n "$BACKEND_PID" "$FRONTEND_PID"
