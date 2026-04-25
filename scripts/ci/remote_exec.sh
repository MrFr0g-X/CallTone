#!/usr/bin/env bash
set -Eeuo pipefail

TARGET="${1:?target user@host required}"
PORT="${2:?ssh port required}"
SSH_KEY="${3:?ssh private key secret required}"
COMMAND="${4:?remote command required}"

KEY_FILE="$(mktemp)"
cleanup() {
    rm -f "${KEY_FILE}"
}
trap cleanup EXIT

printf '%s\n' "${SSH_KEY}" > "${KEY_FILE}"
chmod 600 "${KEY_FILE}"

ssh -o StrictHostKeyChecking=no -p "${PORT}" -i "${KEY_FILE}" "${TARGET}" "${COMMAND}"
