#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export APP_ENV="${APP_ENV:-demo}"
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM
node node_modules/vite/bin/vite.js --host 0.0.0.0 &
WEB_PID=$!
trap 'kill "$API_PID" "$WEB_PID" 2>/dev/null || true' EXIT INT TERM
wait -n "$API_PID" "$WEB_PID"
