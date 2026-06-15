#!/usr/bin/env bash
# One-shot GPU bootstrap for the RTX 4090 container box (no systemd, Py3.12,
# CUDA 12.9, 8080=Jupyter). Seeds .env with the EXISTING backend token, patches
# the container bootstrap for the 4090 CUDA arch, exports nvcc+HF_TOKEN, runs it.
set -euo pipefail
cd /opt/calltone

export HF_TOKEN=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
export PATH=/usr/local/cuda/bin:$PATH
export CUDACXX=/usr/local/cuda/bin/nvcc
export MODEL_SERVER_PORT=8081

# ── 1. Seed model_server/.env (existing backend token => no backend change) ──
cat > model_server/.env <<'ENV'
MODEL_SERVER_TOKEN=aa386ac57743421fb6deb9543dfa16f51b30ebd5259ae0d0414c01ec04ce779a
ALLOWED_IPS=127.0.0.1
HF_TOKEN=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
CUDA_VISIBLE_DEVICES=0
MODEL_SERVER_DEBUG=0
ENV
chmod 600 model_server/.env

# ── 2. Patch container bootstrap: A100 arch 80 -> RTX 4090 arch 89 ──
C=model_server/setup_vast_container.sh
cp "$C" "$C.orig"
sed -i 's/-DCMAKE_CUDA_ARCHITECTURES=80/-DCMAKE_CUDA_ARCHITECTURES=89/g' "$C"

echo "=== verify arch patch ==="; grep -n "CMAKE_CUDA_ARCHITECTURES" "$C"
echo "=== nvcc ==="; nvcc --version | tail -1
echo "=== running setup_vast_container.sh (HF_TOKEN exported, port 8081) ==="
bash "$C"
