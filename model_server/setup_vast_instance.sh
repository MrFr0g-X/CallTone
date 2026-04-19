#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# CallTone — Vast.ai bootstrap (one-shot, idempotent).
#
# After SSH-ing into a fresh Vast instance:
#     bash model_server/setup_vast_instance.sh
#
# What this does (in order):
#   1. System deps (ffmpeg, git, build tools) if missing.
#   2. Python venv at /opt/calltone/venv.
#   3. pip install the model_server "server" + "ml" groups.
#   4. Download models via models/download_models.py (uses HF_TOKEN).
#   5. Generate MODEL_SERVER_TOKEN if not already present.
#   6. Write /etc/systemd/system/calltone-model.service.
#   7. Enable + start the systemd unit.
#   8. Verify /v1/health responds 200.
#
# Re-run safe: every step checks for prior state before acting.
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

CALLTONE_DIR="${CALLTONE_DIR:-/opt/calltone}"
VENV_DIR="${CALLTONE_DIR}/venv"
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")"/.. && pwd)}"
ENV_FILE="${REPO_DIR}/model_server/.env"
SERVICE_NAME="calltone-model"
LOG_PREFIX="[setup_vast]"

log() { echo "${LOG_PREFIX} $*"; }
err() { echo "${LOG_PREFIX} ERROR: $*" >&2; exit 1; }

# ── 0. Preflight ──────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || err "must run as root (Vast's default user is root)"
[[ -f "${REPO_DIR}/model_server/main.py" ]] || err "REPO_DIR does not look like the grad-project repo: ${REPO_DIR}"

# ── 1. System deps ────────────────────────────────────────────────────────
log "installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3.10 python3.10-venv python3-pip \
    ffmpeg git ca-certificates curl build-essential \
    >/dev/null

# ── 2. Virtualenv ─────────────────────────────────────────────────────────
if [[ ! -d "${VENV_DIR}" ]]; then
    log "creating venv at ${VENV_DIR}"
    python3.10 -m venv "${VENV_DIR}"
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip wheel setuptools >/dev/null

# ── 3. Python deps ────────────────────────────────────────────────────────
log "installing model_server (server group)"
pip install -r "${REPO_DIR}/model_server/requirements.txt" >/dev/null

log "installing ML group (torch+cu121, llama-cpp-python[cuda], pyannote, funasr)"
# torch must be installed from its index URL to get the CUDA wheel.
pip install \
    --extra-index-url https://download.pytorch.org/whl/cu121 \
    "torch==2.4.1+cu121" "torchaudio==2.4.1+cu121" >/dev/null

CMAKE_ARGS="-DGGML_CUDA=on" pip install --no-binary=llama-cpp-python \
    "llama-cpp-python==0.3.2" >/dev/null

pip install \
    "pyannote.audio==3.3.2" \
    "funasr==1.1.14" \
    "onnxruntime-gpu==1.19.2" >/dev/null

# resemble-enhance is fetched from Git — pinned commit lives next to the LAYER_1 code.
if ! python -c "import resemble_enhance" 2>/dev/null; then
    log "installing resemble-enhance"
    pip install "git+https://github.com/resemble-ai/resemble-enhance.git" >/dev/null
fi

# ── 4. Model weights ──────────────────────────────────────────────────────
if [[ -z "${HF_TOKEN:-}" && -f "${ENV_FILE}" ]]; then
    # pick up HF_TOKEN from .env if the operator set it there
    # shellcheck disable=SC1090
    set -a; source "${ENV_FILE}"; set +a
fi

if [[ -z "${HF_TOKEN:-}" ]]; then
    err "HF_TOKEN is not set — required for pyannote downloads. Set it in ${ENV_FILE} or export it."
fi

log "downloading model weights (~12.5 GB; skipped if already present)"
python "${REPO_DIR}/models/download_models.py" --hf-token "${HF_TOKEN}"

# ── 5. MODEL_SERVER_TOKEN ─────────────────────────────────────────────────
if [[ ! -f "${ENV_FILE}" ]]; then
    log "seeding .env from .env.example"
    cp "${REPO_DIR}/model_server/.env.example" "${ENV_FILE}"
fi

# Generate a token if the file has an empty assignment.
if ! grep -qE '^MODEL_SERVER_TOKEN=..+' "${ENV_FILE}"; then
    TOKEN=$(openssl rand -hex 32)
    # Replace blank MODEL_SERVER_TOKEN= line in-place.
    if grep -qE '^MODEL_SERVER_TOKEN=' "${ENV_FILE}"; then
        sed -i "s|^MODEL_SERVER_TOKEN=.*$|MODEL_SERVER_TOKEN=${TOKEN}|" "${ENV_FILE}"
    else
        echo "MODEL_SERVER_TOKEN=${TOKEN}" >> "${ENV_FILE}"
    fi
    log "generated new MODEL_SERVER_TOKEN — copy this to the backend:"
    echo "${TOKEN}"
fi

chmod 600 "${ENV_FILE}"  # secrets at rest

# ── 6. systemd unit ───────────────────────────────────────────────────────
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
log "writing ${UNIT_PATH}"
cat > "${UNIT_PATH}" <<EOF
[Unit]
Description=CallTone Model Server (Tier 3)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/uvicorn model_server.main:app --host 0.0.0.0 --port 8080 --workers 1
Restart=on-failure
RestartSec=10
# Fail fast if CUDA is broken; don't keep restarting forever.
StartLimitInterval=600
StartLimitBurst=5
# Log to journald — inspect with ``journalctl -u calltone-model -f``.
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── 7. Start ──────────────────────────────────────────────────────────────
log "enabling + starting ${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}" >/dev/null
systemctl restart "${SERVICE_NAME}"

# ── 8. Health check ───────────────────────────────────────────────────────
log "waiting up to 60s for /v1/health"
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:8080/v1/health" >/dev/null; then
        log "model server healthy ✓"
        curl -s "http://127.0.0.1:8080/v1/health" | python -m json.tool
        exit 0
    fi
    sleep 2
done

journalctl -u "${SERVICE_NAME}" --no-pager -n 50 >&2
err "model server did not become healthy in 60 s"
