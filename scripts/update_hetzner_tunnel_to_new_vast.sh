#!/usr/bin/env bash
set -Eeuo pipefail

VAST_HOST="${VAST_HOST:-185.65.93.114}"
VAST_SSH_PORT="${VAST_SSH_PORT:-47993}"
VAST_MODEL_PORT="${VAST_MODEL_PORT:-8081}"
LOCAL_TUNNEL_PORT="${LOCAL_TUNNEL_PORT:-8090}"
KEY_PATH="${KEY_PATH:-/root/.ssh/calltone_vast_ed25519}"
UNIT_PATH="${UNIT_PATH:-/etc/systemd/system/calltone-tunnel.service}"

if [[ ! -f "${KEY_PATH}" ]]; then
    echo "Missing Vast SSH key on Hetzner: ${KEY_PATH}" >&2
    exit 1
fi

chmod 600 "${KEY_PATH}"

if [[ -f "${UNIT_PATH}" ]]; then
    cp "${UNIT_PATH}" "${UNIT_PATH}.bak-$(date +%Y%m%d%H%M%S)"
fi

cat > "${UNIT_PATH}" <<EOF
[Unit]
Description=CallTone SSH tunnel to Vast GPU model server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/autossh -M 0 -N \\
  -o ServerAliveInterval=15 \\
  -o ServerAliveCountMax=2 \\
  -o ExitOnForwardFailure=yes \\
  -o StrictHostKeyChecking=no \\
  -i ${KEY_PATH} \\
  -L ${LOCAL_TUNNEL_PORT}:localhost:${VAST_MODEL_PORT} \\
  -p ${VAST_SSH_PORT} root@${VAST_HOST}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable calltone-tunnel.service >/dev/null
systemctl restart calltone-tunnel.service
sleep 5

echo "=== tunnel status ==="
systemctl --no-pager --full status calltone-tunnel.service | sed -n '1,30p'

echo "=== local tunnel listener ==="
ss -tlnp | grep ":${LOCAL_TUNNEL_PORT}" || true

echo "=== model server health through tunnel ==="
curl -sS "http://127.0.0.1:${LOCAL_TUNNEL_PORT}/v1/health"
echo

echo "=== backend restart ==="
systemctl restart calltone-backend.service
sleep 3
systemctl --no-pager --full status calltone-backend.service | sed -n '1,25p'

echo "=== public health ==="
curl -sS https://api.calltone.tech/api/health
echo
curl -sS https://api.calltone.tech/api/health/detailed
echo
