#!/usr/bin/env bash
# Restart the model server on Vast. Idempotent.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")"/.. && pwd)}"
VENV_DIR="${VENV_DIR:-/opt/calltone/venv}"
ENV_FILE="${ENV_FILE:-${REPO_DIR}/model_server/.env}"
PID_FILE="${PID_FILE:-/var/run/calltone-model.pid}"
LOG="${LOG:-/var/log/calltone-model.log}"

if [[ -f "$PID_FILE" ]]; then
    OLD=$(cat "$PID_FILE" || echo)
    if [[ -n "${OLD:-}" ]] && kill -0 "$OLD" 2>/dev/null; then
        echo "killing PID $OLD"
        kill "$OLD" || true
        sleep 2
    fi
fi
pkill -f "uvicorn model_server.main" 2>/dev/null || true
sleep 1

cd "$REPO_DIR"
set -a
source "$ENV_FILE"
set +a

nohup setsid "${VENV_DIR}/bin/uvicorn" model_server.main:app \
    --host 127.0.0.1 --port 8081 --workers 1 \
    > "$LOG" 2>&1 < /dev/null &
NEW=$!
disown || true
echo "$NEW" > "$PID_FILE"
sleep 1
echo "started PID $NEW"
