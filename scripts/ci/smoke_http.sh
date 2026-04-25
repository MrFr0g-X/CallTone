#!/usr/bin/env bash
set -Eeuo pipefail

FRONTEND_URL="${FRONTEND_URL:?FRONTEND_URL is required}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:?BACKEND_HEALTH_URL is required}"

fetch_with_retry() {
    local label="$1"
    local url="$2"
    local output_file="$3"
    local attempts="${SMOKE_RETRY_ATTEMPTS:-24}"
    local delay_seconds="${SMOKE_RETRY_DELAY_SECONDS:-5}"

    for attempt in $(seq 1 "${attempts}"); do
        echo "[smoke] ${label}: attempt ${attempt}/${attempts}: ${url}"
        if curl -fsS --max-time 30 "${url}" >"${output_file}"; then
            return 0
        fi

        if [[ "${attempt}" -lt "${attempts}" ]]; then
            sleep "${delay_seconds}"
        fi
    done

    echo "[smoke] ${label}: failed after ${attempts} attempts" >&2
    return 1
}

echo "[smoke] frontend: ${FRONTEND_URL}"
fetch_with_retry "frontend" "${FRONTEND_URL}" /tmp/calltone_frontend_smoke.html
grep -qi "calltone" /tmp/calltone_frontend_smoke.html || {
    echo "[smoke] frontend response did not contain CallTone marker" >&2
    exit 1
}

echo "[smoke] backend: ${BACKEND_HEALTH_URL}"
fetch_with_retry "backend" "${BACKEND_HEALTH_URL}" /tmp/calltone_backend_health.json
cat /tmp/calltone_backend_health.json

python - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("/tmp/calltone_backend_health.json").read_text())
text = json.dumps(payload).lower()
if '"status": "ok"' not in text and '"status":"ok"' not in text and '"ok": true' not in text and '"ok":true' not in text:
    raise SystemExit(f"health payload does not look healthy: {payload}")
print("[smoke] health payload accepted")
PY
