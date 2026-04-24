#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${REPO_DIR:-/root/calltone}"
VENV_DIR="${VENV_DIR:-/opt/calltone/venv}"
ENV_FILE="${ENV_FILE:-${REPO_DIR}/model_server/.env}"
LOG_FILE="${LOG_FILE:-/var/log/calltone-model.log}"
PID_FILE="${PID_FILE:-/var/run/calltone-model.pid}"
HOST="${MODEL_SERVER_HOST:-127.0.0.1}"
PORT="${MODEL_SERVER_PORT:-8081}"

if [[ ! -f "${REPO_DIR}/model_server/main.py" ]]; then
    echo "REPO_DIR does not contain model_server/main.py: ${REPO_DIR}" >&2
    exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing env file: ${ENV_FILE}" >&2
    exit 1
fi

if [[ ! -x "${VENV_DIR}/bin/uvicorn" ]]; then
    echo "Missing uvicorn in restored venv: ${VENV_DIR}/bin/uvicorn" >&2
    exit 1
fi

pkill -f "uvicorn model_server.main" 2>/dev/null || true
sleep 1

mkdir -p "$(dirname "${LOG_FILE}")" "$(dirname "${PID_FILE}")"

cd "${REPO_DIR}"
set -a
source "${ENV_FILE}"
set +a

nohup setsid "${VENV_DIR}/bin/uvicorn" model_server.main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers 1 \
    > "${LOG_FILE}" 2>&1 < /dev/null &

echo "$!" > "${PID_FILE}"
sleep 5

echo "started_pid=$(cat "${PID_FILE}")"
ss -tlnp | grep -E ":${PORT}\b" || true
curl -sS "http://127.0.0.1:${PORT}/v1/health" || true
echo
tail -80 "${LOG_FILE}" || true
