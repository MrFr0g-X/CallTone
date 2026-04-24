#!/usr/bin/env bash
set -Eeuo pipefail

# Restore a backup created by scripts/backup_gpu_server_to_rclone.sh.
#
# Usage:
#   RCLONE_REMOTE_PATH='gdrive:CallToneGPUBackups/host-YYYYmmdd-HHMMSS' \
#   bash scripts/restore_gpu_server_from_rclone.sh

RCLONE_REMOTE_PATH="${RCLONE_REMOTE_PATH:-${1:-}}"

if [ -z "${RCLONE_REMOTE_PATH}" ]; then
    echo "Usage: RCLONE_REMOTE_PATH='remote:path/to/backup' bash scripts/restore_gpu_server_from_rclone.sh" >&2
    exit 1
fi

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required command: $1" >&2
        exit 1
    }
}

need_cmd rclone
need_cmd zstd
need_cmd tar

log() {
    printf '[restore] %s\n' "$*"
}

have_remote_file() {
    local name="$1"
    rclone size "${RCLONE_REMOTE_PATH}/${name}" >/dev/null 2>&1
}

restore_archive() {
    local archive_name="$1"

    if ! have_remote_file "${archive_name}"; then
        log "skipping ${archive_name} (not present in backup)"
        return 0
    fi

    log "restoring ${archive_name}"
    rclone cat --stats 30s --stats-one-line "${RCLONE_REMOTE_PATH}/${archive_name}" \
        | zstd -d \
        | tar -xpf - -C /
}

main() {
    log "remote path: ${RCLONE_REMOTE_PATH}"

    restore_archive "01-root-calltone.tar.zst"
    restore_archive "02-root-cache.tar.zst"
    restore_archive "03-opt-calltone.tar.zst"
    restore_archive "04-root-ssh.tar.zst"
    restore_archive "05-system-config.tar.zst"
    restore_archive "06-tmp-project-artifacts.tar.zst"

    if [ -d /root/.ssh ]; then
        chmod 700 /root/.ssh || true
        find /root/.ssh -type f -exec chmod 600 {} \; || true
        find /root/.ssh -type f -name '*.pub' -exec chmod 644 {} \; || true
    fi

    log "restore complete"
    log "recommended next steps:"
    log "  1. source /root/calltone/model_server/.env if you launch manually"
    log "  2. verify rclone: rclone listremotes"
    log "  3. verify GPU: nvidia-smi"
    log "  4. verify model server health after startup"
}

main "$@"
