#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

EXISTING_API_PIDS="$(lsof -tiTCP:8000 -sTCP:LISTEN || true)"
if [[ -n "$EXISTING_API_PIDS" ]]; then
  echo "Stopping existing backend process(es) on :8000: $EXISTING_API_PIDS"
  kill $EXISTING_API_PIDS >/dev/null 2>&1 || true
  sleep 1
fi

.venv/bin/python -m uvicorn finbert_site.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8000 \
  --reload-dir finbert_site \
  --reload-dir scripts \
  --reload-exclude ".next/*" \
  --reload-exclude "node_modules/*" \
  --reload-exclude "output/*" \
  --reload-exclude "public/*" &

API_PID="$!"
echo "Started backend (pid=$API_PID) on 127.0.0.1:8000."

for attempt in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
    echo "Backend health check passed."
    break
  fi
  if [[ "$attempt" -eq 40 ]]; then
    echo "Backend failed to become healthy."
    exit 1
  fi
  sleep 0.25
done

cleanup() {
  if [[ -n "${API_PID}" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

exec next dev --webpack
