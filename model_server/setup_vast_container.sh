#!/usr/bin/env bash
# Container-mode bootstrap for Vast.ai instances that run as Docker
# containers (no systemd). Functionally equivalent to
# setup_vast_instance.sh but starts uvicorn via nohup and logs to
# /var/log/calltone-model.log.
#
# Required env:   HF_TOKEN
# Optional env:   CALLTONE_DIR (default /opt/calltone)
set -euo pipefail

CALLTONE_DIR="${CALLTONE_DIR:-/opt/calltone}"
VENV_DIR="${CALLTONE_DIR}/venv"
REPO_DIR="${REPO_DIR:-${CALLTONE_DIR}}"
ENV_FILE="${REPO_DIR}/model_server/.env"
LOG_FILE="/var/log/calltone-model.log"
PID_FILE="/var/run/calltone-model.pid"
LOG_PREFIX="[setup_vast_container]"

log() { echo "${LOG_PREFIX} $*"; }
err() { echo "${LOG_PREFIX} ERROR: $*" >&2; exit 1; }

[[ -f "${REPO_DIR}/model_server/main.py" ]] || err "REPO_DIR does not look right: ${REPO_DIR}"
[[ -n "${HF_TOKEN:-}" ]] || err "HF_TOKEN is required"

log "installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3.10 python3.10-venv python3-pip \
    ffmpeg git ca-certificates curl build-essential openssl \
    >/dev/null

if [[ ! -d "${VENV_DIR}" ]]; then
    log "creating venv at ${VENV_DIR}"
    python3.10 -m venv "${VENV_DIR}"
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip wheel setuptools >/dev/null

log "installing model_server deps"
pip install -r "${REPO_DIR}/model_server/requirements.txt" >/dev/null

log "installing torch cu121"
pip install \
    --extra-index-url https://download.pytorch.org/whl/cu121 \
    "torch==2.4.1+cu121" "torchaudio==2.4.1+cu121" >/dev/null

log "installing llama-cpp-python with CUDA"
CMAKE_ARGS="-DGGML_CUDA=on" pip install --no-binary=llama-cpp-python \
    "llama-cpp-python==0.3.2" >/dev/null

log "installing pyannote + funasr + onnxruntime-gpu"
pip install \
    "pyannote.audio==3.3.2" \
    "funasr==1.1.14" \
    "onnxruntime-gpu==1.19.2" >/dev/null

if ! python -c "import resemble_enhance" 2>/dev/null; then
    log "installing resemble-enhance"
    pip install "git+https://github.com/resemble-ai/resemble-enhance.git" >/dev/null
fi

log "downloading model weights (~12.5 GB; skipped if already present)"
python "${REPO_DIR}/models/download_models.py" --hf-token "${HF_TOKEN}"

if [[ ! -f "${ENV_FILE}" ]]; then
    cp "${REPO_DIR}/model_server/.env.example" "${ENV_FILE}"
fi
if ! grep -qE '^MODEL_SERVER_TOKEN=..+' "${ENV_FILE}"; then
    TOKEN=$(openssl rand -hex 32)
    if grep -qE '^MODEL_SERVER_TOKEN=' "${ENV_FILE}"; then
        sed -i "s|^MODEL_SERVER_TOKEN=.*$|MODEL_SERVER_TOKEN=${TOKEN}|" "${ENV_FILE}"
    else
        echo "MODEL_SERVER_TOKEN=${TOKEN}" >> "${ENV_FILE}"
    fi
    log "generated new MODEL_SERVER_TOKEN — copy this to the backend:"
    echo "${TOKEN}"
fi
chmod 600 "${ENV_FILE}"

if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    log "stopping existing uvicorn PID $(cat "${PID_FILE}")"
    kill "$(cat "${PID_FILE}")" || true
    sleep 2
fi

log "starting uvicorn via nohup (log: ${LOG_FILE})"
mkdir -p "$(dirname "${LOG_FILE}")" "$(dirname "${PID_FILE}")"
set -a; source "${ENV_FILE}"; set +a
cd "${REPO_DIR}"
nohup "${VENV_DIR}/bin/uvicorn" model_server.main:app \
    --host 0.0.0.0 --port 8080 --workers 1 \
    > "${LOG_FILE}" 2>&1 &
echo $! > "${PID_FILE}"

log "waiting up to 60s for /v1/health"
for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:8080/v1/health" >/dev/null; then
        log "model server healthy"
        curl -s "http://127.0.0.1:8080/v1/health" | python -m json.tool
        exit 0
    fi
    sleep 2
done

tail -n 50 "${LOG_FILE}" >&2
err "model server did not become healthy in 60 s"
