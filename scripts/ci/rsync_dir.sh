#!/usr/bin/env bash
set -Eeuo pipefail

SRC="${1:?source directory required}"
DEST="${2:?destination user@host:path required}"
PORT="${3:?ssh port required}"
SSH_KEY="${4:?ssh private key secret required}"

KEY_FILE="$(mktemp)"
cleanup() {
    rm -f "${KEY_FILE}"
}
trap cleanup EXIT

printf '%s\n' "${SSH_KEY}" > "${KEY_FILE}"
chmod 600 "${KEY_FILE}"

rsync -az --delete \
    -e "ssh -o StrictHostKeyChecking=no -p ${PORT} -i ${KEY_FILE}" \
    "${SRC}" \
    "${DEST}"
