#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")"/.. && pwd)}"
VENV_DIR="${VENV_DIR:-/opt/calltone/venv}"
ENV_FILE="${ENV_FILE:-${REPO_DIR}/model_server/.env}"

cd "$REPO_DIR"
set -a
. "$ENV_FILE"
set +a
exec "${VENV_DIR}/bin/uvicorn" model_server.main:app --host 127.0.0.1 --port 8081 --workers 1
