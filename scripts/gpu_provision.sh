#!/usr/bin/env bash
# One-shot GPU bootstrap for an RTX 4090 container box (no systemd, Py3.12,
# CUDA 12.x, 8080=Jupyter). Patches the container bootstrap for the 4090 CUDA
# arch, seeds model_server/.env, exports nvcc, runs it.
#
# Secrets are read from the environment (NEVER hardcode them here):
#   HF_TOKEN            HuggingFace token (gated pyannote downloads)
#   MODEL_SERVER_TOKEN  shared bearer the backend already uses (so backend needs no change)
# Supply them out-of-band, e.g.:
#   HF_TOKEN=hf_xxx MODEL_SERVER_TOKEN=xxx bash scripts/gpu_provision.sh
set -euo pipefail
cd /opt/calltone

: "${HF_TOKEN:?set HF_TOKEN in the environment before running}"
: "${MODEL_SERVER_TOKEN:?set MODEL_SERVER_TOKEN in the environment before running}"
export HF_TOKEN MODEL_SERVER_TOKEN
export PATH=/usr/local/cuda/bin:$PATH
export CUDACXX=/usr/local/cuda/bin/nvcc
export MODEL_SERVER_PORT=8081

# ── 1. Seed model_server/.env (restrictive perms from creation; no chmod race) ──
( umask 077; cat > model_server/.env <<ENV
MODEL_SERVER_TOKEN=${MODEL_SERVER_TOKEN}
ALLOWED_IPS=127.0.0.1
HF_TOKEN=${HF_TOKEN}
CUDA_VISIBLE_DEVICES=0
MODEL_SERVER_DEBUG=0
ENV
)

# ── 2. Patch container bootstrap: A100 arch 80 -> RTX 4090 arch 89 ──
C=model_server/setup_vast_container.sh
cp "$C" "$C.orig"
sed -i 's/-DCMAKE_CUDA_ARCHITECTURES=80/-DCMAKE_CUDA_ARCHITECTURES=89/g' "$C"

echo "=== verify arch patch ==="; grep -n "CMAKE_CUDA_ARCHITECTURES" "$C"
echo "=== nvcc ==="; nvcc --version | tail -1
echo "=== running setup_vast_container.sh (HF_TOKEN exported, port 8081) ==="
bash "$C"
