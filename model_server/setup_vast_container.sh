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
MODEL_SERVER_HOST="${MODEL_SERVER_HOST:-127.0.0.1}"
MODEL_SERVER_PORT="${MODEL_SERVER_PORT:-8081}"
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
    "llama-cpp-python==0.3.20" >/dev/null

log "installing pyannote + funasr + faster-whisper + onnxruntime-gpu"
pip install \
    "huggingface_hub==0.25.2" \
    "pyannote.audio==3.3.2" \
    "funasr==1.1.14" \
    "faster-whisper>=1.0.3" \
    "onnxruntime-gpu==1.19.2" >/dev/null

# Some transitive deps pull in CPU-only ``onnxruntime``, which shadows the GPU
# wheel and makes Audio2Emotion run on CPU for long calls. Remove it
# aggressively, then force-reinstall the GPU wheel and verify CUDA is visible.
pip uninstall -y onnxruntime >/dev/null 2>&1 || true
pip install --force-reinstall "onnxruntime-gpu==1.19.2" >/dev/null
python - <<'PY'
import onnxruntime as ort
providers = set(ort.get_available_providers())
assert "CUDAExecutionProvider" in providers, (
    f"onnxruntime-gpu installed but CUDAExecutionProvider missing; "
    f"providers={sorted(providers)}"
)
print("onnxruntime providers:", sorted(providers))
PY

if ! python -c "import resemble_enhance" 2>/dev/null; then
    log "installing resemble-enhance"
    pip install "git+https://github.com/resemble-ai/resemble-enhance.git" >/dev/null
fi

log "downloading model weights (~12.5 GB; skipped if already present)"
python "${REPO_DIR}/models/download_models.py" --hf-token "${HF_TOKEN}"

# transformers + accelerate are pulled in here, not in the model_server
# requirements (which only need the FastAPI side). Without them LAYER 1
# step 2 fails with ModuleNotFoundError: No module named 'transformers'.
log "installing layer-1 ML deps (transformers, accelerate)"
pip install "transformers>=4.44.0,<4.50" "accelerate>=0.33.0" >/dev/null

# Pyannote ships its sub-model paths in speaker-diarization-3.1/config.yaml
# as absolute paths. The committed copy may carry Windows paths, and
# pyannote.Pipeline.from_pretrained needs file paths (not directories) for
# offline use. Rewrite both: any baked-in dev path → /opt/calltone, and
# embedding/segmentation directory → its pytorch_model.bin.
PYANNOTE_CFG="${REPO_DIR}/models/LAYER_1/models/pyannote/speaker-diarization-3.1/config.yaml"
if [[ -f "${PYANNOTE_CFG}" ]]; then
    log "rewriting pyannote config.yaml for local Linux paths"
    sed -i \
        -e "s|D:/[^[:space:]]*/grad-project-main|/opt/calltone|g" \
        -e "s|C:/[^[:space:]]*/grad-project-main|/opt/calltone|g" \
        -e "s|\(embedding: /opt/calltone/models/LAYER_1/models/pyannote/wespeaker-voxceleb-resnet34-LM\)\$|\1/pytorch_model.bin|" \
        -e "s|\(segmentation: /opt/calltone/models/LAYER_1/models/pyannote/segmentation-3.0\)\$|\1/pytorch_model.bin|" \
        "${PYANNOTE_CFG}"
fi

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
    --host "${MODEL_SERVER_HOST}" --port "${MODEL_SERVER_PORT}" --workers 1 \
    > "${LOG_FILE}" 2>&1 &
echo $! > "${PID_FILE}"

log "waiting up to 60s for /v1/health"
for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${MODEL_SERVER_PORT}/v1/health" >/dev/null; then
        log "model server healthy"
        curl -s "http://127.0.0.1:${MODEL_SERVER_PORT}/v1/health" | python -m json.tool
        exit 0
    fi
    sleep 2
done

tail -n 50 "${LOG_FILE}" >&2
err "model server did not become healthy in 60 s"
