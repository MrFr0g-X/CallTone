#!/usr/bin/env bash
set -Eeuo pipefail

DEST="${1:?destination user@host:path required}"
PORT="${2:?ssh port required}"
SSH_KEY="${3:?ssh private key secret required}"
SRC="${4:-backend/}"

if [ ! -d "${SRC}" ]; then
    echo "source directory does not exist: ${SRC}" >&2
    exit 1
fi

KEY_FILE="$(mktemp)"
cleanup() {
    rm -f "${KEY_FILE}"
}
trap cleanup EXIT

printf '%s\n' "${SSH_KEY}" > "${KEY_FILE}"
chmod 600 "${KEY_FILE}"

rsync -az --delete \
    -e "ssh -o StrictHostKeyChecking=no -p ${PORT} -i ${KEY_FILE}" \
    --exclude='.env' \
    --exclude='venv/' \
    --exclude='uploads/' \
    --exclude='data/' \
    --exclude='stress_runs/' \
    --exclude='calltone.db*' \
    --exclude='**/__pycache__/' \
    --exclude='**/.pytest_cache/' \
    --exclude='*.pyc' \
    "${SRC%/}/" \
    "${DEST}"
