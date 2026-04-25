#!/usr/bin/env bash
# CallTone Vast.ai model-server bootstrap.
#
# Purpose:
#   Bring up only Tier 3 (GPU model server) on a fresh Vast container.
#   Tier 1 frontend and Tier 2 backend stay on Hetzner; do not run them here.
#
# Required:
#   export HF_TOKEN=...                  # Hugging Face token with pyannote access
#
# Optional:
#   export CALLTONE_BRANCH=main          # branch or tag to deploy
#   export CALLTONE_DIR=/opt/calltone
#   export MODEL_SERVER_PORT=8081
#   export MODEL_SERVER_HOST=127.0.0.1
#
# After this succeeds, update the Hetzner autossh tunnel to:
#   -L 8090:localhost:${MODEL_SERVER_PORT} -p <vast-ssh-port> root@<vast-ip>
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/MrFr0g-X/CallTone.git}"
CALLTONE_BRANCH="${CALLTONE_BRANCH:-main}"
CALLTONE_DIR="${CALLTONE_DIR:-/opt/calltone}"
MODEL_SERVER_PORT="${MODEL_SERVER_PORT:-8081}"
MODEL_SERVER_HOST="${MODEL_SERVER_HOST:-127.0.0.1}"

log() {
    printf '[vast-quickstart] %s\n' "$*"
}

die() {
    printf '[vast-quickstart] ERROR: %s\n' "$*" >&2
    exit 1
}

[[ -n "${HF_TOKEN:-}" ]] || die "HF_TOKEN is required. Set it in the shell; do not hardcode it in this script."

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends git ca-certificates curl openssh-client >/dev/null

if [[ -d "${CALLTONE_DIR}/.git" ]]; then
    log "updating existing checkout at ${CALLTONE_DIR}"
    git -C "${CALLTONE_DIR}" fetch --prune origin
    git -C "${CALLTONE_DIR}" checkout --quiet "${CALLTONE_BRANCH}"
    git -C "${CALLTONE_DIR}" pull --ff-only origin "${CALLTONE_BRANCH}" || true
else
    log "cloning ${REPO_URL} (${CALLTONE_BRANCH}) into ${CALLTONE_DIR}"
    rm -rf "${CALLTONE_DIR}"
    git clone --depth 1 --branch "${CALLTONE_BRANCH}" "${REPO_URL}" "${CALLTONE_DIR}"
fi

log "starting model-server setup on ${MODEL_SERVER_HOST}:${MODEL_SERVER_PORT}"
export CALLTONE_DIR
export REPO_DIR="${CALLTONE_DIR}"
export MODEL_SERVER_HOST
export MODEL_SERVER_PORT
bash "${CALLTONE_DIR}/model_server/setup_vast_container.sh"

log "health check"
curl -fsS "http://127.0.0.1:${MODEL_SERVER_PORT}/v1/health"
echo

log "capacity check"
if [[ -f "${CALLTONE_DIR}/model_server/.env" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${CALLTONE_DIR}/model_server/.env"
    set +a
    curl -fsS -H "Authorization: Bearer ${MODEL_SERVER_TOKEN}" \
        "http://127.0.0.1:${MODEL_SERVER_PORT}/v1/capacity" || true
    echo
fi

log "done. Keep this instance alive and point Hetzner tunnel to port ${MODEL_SERVER_PORT}."
