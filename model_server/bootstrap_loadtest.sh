#!/usr/bin/env bash
# Token-free bootstrap for the dual-4090 load/ceiling test.
# Builds the env + downloads the NON-gated models. Pyannote (gated) is left
# for a follow-up step once HF_TOKEN is supplied. Does NOT start the server.
set -uo pipefail
REPO=/opt/calltone
VENV=$REPO/.venv
export CUDA_HOME=/usr/local/cuda-12.9
export PATH="$CUDA_HOME/bin:$PATH"
log(){ echo "[$(date +%H:%M:%S)] $*"; }
cd "$REPO"

log "PHASE 1: venv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip wheel setuptools 2>&1 | tail -1

log "PHASE 2: model_server requirements"
"$VENV/bin/pip" install -q -r "$REPO/model_server/requirements.txt" 2>&1 | tail -2

log "PHASE 3: torch (cu121 wheels, forward-compatible with driver)"
"$VENV/bin/pip" install -q --extra-index-url https://download.pytorch.org/whl/cu121 \
    torch torchaudio 2>&1 | tail -2

log "PHASE 4: build llama-cpp-python for RTX 4090 (arch 89)"
CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=89" \
    "$VENV/bin/pip" install -q --no-cache-dir --no-binary=llama-cpp-python \
    "llama-cpp-python==0.3.20" 2>&1 | tail -3

log "PHASE 5: aux libs (hf_hub, onnxruntime-gpu, transformers, accelerate)"
"$VENV/bin/pip" install -q "huggingface_hub==0.25.2" 2>&1 | tail -1
"$VENV/bin/pip" install -q --force-reinstall "onnxruntime-gpu==1.19.2" 2>&1 | tail -1
"$VENV/bin/pip" install -q "transformers>=4.44.0,<4.50" "accelerate>=0.33.0" 2>&1 | tail -1
"$VENV/bin/pip" install -q "git+https://github.com/resemble-ai/resemble-enhance.git" 2>&1 | tail -1 || log "resemble-enhance pip install skipped/failed (non-fatal)"

log "PHASE 6: verify CUDA visible to onnxruntime + torch"
"$VENV/bin/python" -c "import onnxruntime as o; print('onnx providers:', [p for p in o.get_available_providers()])" 2>&1 | tail -1
"$VENV/bin/python" -c "import torch; print('torch cuda:', torch.cuda.is_available(), torch.cuda.device_count())" 2>&1 | tail -1

log "PHASE 7: download NON-gated models (qwen3, whisper, resemble, emotion)"
for m in qwen3 whisper resemble emotion; do
  log "  downloading $m"
  "$VENV/bin/python" "$REPO/models/download_models.py" --model "$m" 2>&1 | tail -2
done

log "BOOTSTRAP DONE (token-free). Pyannote still needed for full pipeline."
touch "$REPO/.bootstrap_done"
