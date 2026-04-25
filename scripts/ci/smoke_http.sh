#!/usr/bin/env bash
set -Eeuo pipefail

FRONTEND_URL="${FRONTEND_URL:?FRONTEND_URL is required}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:?BACKEND_HEALTH_URL is required}"

echo "[smoke] frontend: ${FRONTEND_URL}"
curl -fsS --max-time 20 "${FRONTEND_URL}" >/tmp/calltone_frontend_smoke.html
grep -qi "calltone" /tmp/calltone_frontend_smoke.html || {
    echo "[smoke] frontend response did not contain CallTone marker" >&2
    exit 1
}

echo "[smoke] backend: ${BACKEND_HEALTH_URL}"
curl -fsS --max-time 30 "${BACKEND_HEALTH_URL}" | tee /tmp/calltone_backend_health.json

python - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("/tmp/calltone_backend_health.json").read_text())
text = json.dumps(payload).lower()
if '"status": "ok"' not in text and '"status":"ok"' not in text and '"ok": true' not in text and '"ok":true' not in text:
    raise SystemExit(f"health payload does not look healthy: {payload}")
print("[smoke] health payload accepted")
PY
