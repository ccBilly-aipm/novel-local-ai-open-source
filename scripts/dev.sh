#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() {
  kill "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$ROOT_DIR/services/api"
if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Backend dependencies are missing. Follow README.md first."
  exit 1
fi
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
API_PID=$!

cd "$ROOT_DIR/apps/web"
npm run dev &
WEB_PID=$!

wait "$API_PID" "$WEB_PID"
