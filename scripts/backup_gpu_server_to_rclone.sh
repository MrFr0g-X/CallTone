#!/usr/bin/env bash
set -Eeuo pipefail

# Stream the full GPU-server working state to an rclone remote.
#
# Default target:
#   gdrive:CallToneGPUBackups/<hostname>-YYYYmmdd-HHMMSS/
#
# Override with:
#   RCLONE_REMOTE=gdrive:CallToneGPUBackups \
#   BACKUP_NAME=my-backup \
#   bash scripts/backup_gpu_server_to_rclone.sh
#
# This script intentionally includes secrets and private material because the
# project owner asked for a full cold-restore backup. Protect the target
# storage account accordingly.

RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive:CallToneGPUBackups}"
BACKUP_NAME="${BACKUP_NAME:-$(hostname)-$(date +%Y%m%d-%H%M%S)}"
if [[ "${RCLONE_REMOTE}" == *: ]]; then
    REMOTE_PATH="${RCLONE_REMOTE}${BACKUP_NAME}"
else
    REMOTE_PATH="${RCLONE_REMOTE%/}/${BACKUP_NAME}"
fi
TMPDIR_ROOT="${TMPDIR:-/tmp}"
WORKDIR="$(mktemp -d "${TMPDIR_ROOT%/}/calltone-backup.XXXXXX")"

cleanup() {
    rm -rf "${WORKDIR}"
}
trap cleanup EXIT

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required command: $1" >&2
        exit 1
    }
}

need_cmd tar
need_cmd zstd
need_cmd sha256sum
need_cmd rclone

log() {
    printf '[backup] %s\n' "$*"
}

add_if_exists() {
    local list_file="$1"
    shift
    local path
    for path in "$@"; do
        if [ -e "${path}" ]; then
            printf '%s\n' "${path}" >> "${list_file}"
        fi
    done
}

write_metadata() {
    local out="${WORKDIR}/backup-metadata.txt"
    {
        echo "backup_name=${BACKUP_NAME}"
        echo "remote_path=${REMOTE_PATH}"
        echo "created_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "hostname=$(hostname)"
        echo "user=$(whoami)"
        echo "pwd=$(pwd)"
        echo
        echo "=== uname ==="
        uname -a || true
        echo
        echo "=== os-release ==="
        cat /etc/os-release 2>/dev/null || true
        echo
        echo "=== df -h ==="
        df -h || true
        echo
        echo "=== nvidia-smi ==="
        nvidia-smi || true
        echo
        echo "=== python ==="
        python --version 2>/dev/null || true
        /opt/calltone/venv/bin/python --version 2>/dev/null || true
        echo
        echo "=== du -sh ==="
        du -sh /root/calltone 2>/dev/null || true
        du -sh /root/.cache 2>/dev/null || true
        du -sh /opt/calltone 2>/dev/null || true
        du -sh /root/.ssh 2>/dev/null || true
        du -sh /root/.config/rclone 2>/dev/null || true
        echo
        echo "=== package snapshots ==="
        dpkg-query -W -f='${Package} ${Version}\n' 2>/dev/null || true
        echo
        echo "=== pip freeze (/opt/calltone/venv) ==="
        /opt/calltone/venv/bin/pip freeze 2>/dev/null || true
    } > "${out}"
}

stream_archive() {
    local archive_key="$1"
    local level="$2"
    local list_file="$3"

    if [ ! -s "${list_file}" ]; then
        log "skipping ${archive_key} (no paths found)"
        return 0
    fi

    local archive_name="${archive_key}.tar.zst"
    local remote_archive="${REMOTE_PATH}/${archive_name}"
    local remote_sha="${REMOTE_PATH}/${archive_name}.sha256"
    local remote_items="${REMOTE_PATH}/${archive_key}.items.txt"
    local sha_file="${WORKDIR}/${archive_name}.sha256"
    local items_file="${WORKDIR}/${archive_key}.items.txt"
    cp "${list_file}" "${items_file}"

    if rclone lsf "${REMOTE_PATH}" --files-only 2>/dev/null | grep -Fxq "${archive_name}"; then
        log "${archive_name} already exists remotely — resuming metadata/checksum only"
        if ! rclone lsf "${REMOTE_PATH}" --files-only 2>/dev/null | grep -Fxq "${archive_name}.sha256"; then
            log "computing remote checksum for existing ${archive_name}"
            rclone cat "${remote_archive}" | sha256sum | awk '{print $1}' > "${sha_file}"
        fi
    else
        log "uploading ${archive_name}"
        tar \
            --acls \
            --xattrs \
            --numeric-owner \
            --ignore-failed-read \
            --warning=no-file-changed \
            --verbatim-files-from \
            --preserve-permissions \
            --absolute-names \
            -T "${list_file}" \
            -cf - \
        | zstd "-${level}" -T0 \
        | tee >(sha256sum | awk '{print $1}' > "${sha_file}") \
        | rclone rcat "${remote_archive}" -P
    fi

    if [ ! -s "${sha_file}" ]; then
        for _ in $(seq 1 60); do
            [ -s "${sha_file}" ] && break
            sleep 1
        done
    fi
    if [ ! -s "${sha_file}" ]; then
        echo "checksum file was not created for ${archive_name}" >&2
        exit 1
    fi

    rclone copyto "${sha_file}" "${remote_sha}" -P
    rclone copyto "${items_file}" "${remote_items}" -P
}

write_restore_readme() {
    local out="${WORKDIR}/RESTORE.txt"
    cat > "${out}" <<EOF
Restore on a new GPU box:

  1. Install rclone, zstd, tar
  2. Configure the same rclone remote name used for this backup
  3. Copy the repo or at least scripts/restore_gpu_server_from_rclone.sh
  4. Run as root:

       RCLONE_REMOTE_PATH='${REMOTE_PATH}' \\
       bash scripts/restore_gpu_server_from_rclone.sh

This backup intentionally contains secrets, .env files, keys, model caches,
and venv state because the goal is a full operational restore.
EOF
}

main() {
    log "writing metadata"
    write_metadata
    write_restore_readme

    local list_root="${WORKDIR}/root-calltone.list"
    local list_cache="${WORKDIR}/root-cache.list"
    local list_venv="${WORKDIR}/opt-calltone.list"
    local list_ssh="${WORKDIR}/root-ssh.list"
    local list_system="${WORKDIR}/system-config.list"
    local list_tmp="${WORKDIR}/tmp-project-artifacts.list"

    : > "${list_root}"
    : > "${list_cache}"
    : > "${list_venv}"
    : > "${list_ssh}"
    : > "${list_system}"
    : > "${list_tmp}"

    add_if_exists "${list_root}" \
        /root/calltone

    add_if_exists "${list_cache}" \
        /root/.cache

    add_if_exists "${list_venv}" \
        /opt/calltone

    add_if_exists "${list_ssh}" \
        /root/.ssh

    add_if_exists "${list_system}" \
        /root/.bashrc \
        /root/.profile \
        /root/.config/rclone \
        /etc/environment \
        /etc/profile \
        /etc/bash.bashrc \
        /etc/ssh \
        /etc/systemd/system

    add_if_exists "${list_tmp}" \
        /tmp/calltone_job_3mmbwo4_ \
        /tmp/repro_out \
        /tmp/retest_layer2_fix

    # Add any remaining calltone temp job dirs dynamically.
    find /tmp -maxdepth 1 -type d \( -name 'calltone_job_*' -o -name 'calltone_*' -o -name 'repro*' \) -print 2>/dev/null \
        | while IFS= read -r p; do
            if [ -e "${p}" ] && ! grep -Fxq "${p}" "${list_tmp}"; then
                printf '%s\n' "${p}" >> "${list_tmp}"
            fi
        done

    log "creating remote path ${REMOTE_PATH}"
    rclone mkdir "${REMOTE_PATH}"

    stream_archive "01-root-calltone" 8 "${list_root}"
    stream_archive "02-root-cache" 4 "${list_cache}"
    stream_archive "03-opt-calltone" 3 "${list_venv}"
    stream_archive "04-root-ssh" 3 "${list_ssh}"
    stream_archive "05-system-config" 3 "${list_system}"
    stream_archive "06-tmp-project-artifacts" 1 "${list_tmp}"

    rclone copyto "${WORKDIR}/backup-metadata.txt" "${REMOTE_PATH}/backup-metadata.txt" -P
    rclone copyto "${WORKDIR}/RESTORE.txt" "${REMOTE_PATH}/RESTORE.txt" -P

    log "backup complete"
    log "remote path: ${REMOTE_PATH}"
}

main "$@"
