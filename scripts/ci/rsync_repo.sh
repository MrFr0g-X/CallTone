#!/usr/bin/env bash
set -Eeuo pipefail

DEST="${1:?destination user@host:path required}"
PORT="${2:?ssh port required}"
SSH_KEY="${3:?ssh private key secret required}"

KEY_FILE="$(mktemp)"
cleanup() {
    rm -f "${KEY_FILE}"
}
trap cleanup EXIT

printf '%s\n' "${SSH_KEY}" > "${KEY_FILE}"
chmod 600 "${KEY_FILE}"

rsync -az --delete \
    -e "ssh -o StrictHostKeyChecking=no -p ${PORT} -i ${KEY_FILE}" \
    --exclude='.git/' \
    --exclude='.github/' \
    --exclude='deployment/' \
    --exclude='**/__pycache__/' \
    --exclude='**/.pytest_cache/' \
    --exclude='**/node_modules/' \
    --exclude='calltone-UI/dist/' \
    --exclude='backend/.env' \
    --exclude='backend/uploads/' \
    --exclude='backend/calltone.db*' \
    --exclude='model_server/.env' \
    --exclude='*.gguf' \
    --exclude='*.onnx' \
    --exclude='*.safetensors' \
    --exclude='*.pt' \
    --exclude='*.pth' \
    --exclude='*.bin' \
    ./ \
    "${DEST}"
