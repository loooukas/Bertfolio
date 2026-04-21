#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

API_PID=""
if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Backend already running on 127.0.0.1:8000; reusing existing process."
else
  .venv/bin/python -m uvicorn finbert_site.main:app --reload --host 127.0.0.1 --port 8000 &
  API_PID="$!"
  echo "Started backend (pid=$API_PID) on 127.0.0.1:8000."
fi

cleanup() {
  if [[ -n "${API_PID}" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

exec next dev
