#!/bin/bash
# Full CallTone setup for vast.ai B200 server
# Installs everything to /workspace (75 GB dedicated XFS partition)

export HF_TOKEN="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"
export TMPDIR=/dev/shm   # pip downloads go to 141G tmpfs, not workspace
export TOKENIZERS_PARALLELISM=false
export DS_BUILD_OPS=0

log() { echo "[$(date +%H:%M:%S)] $*"; }
free_ws() { df /workspace | awk 'NR==2{printf "/workspace: %.1fG free\n", $4/1024/1024}'; }

log "=== CallTone Full Setup ==="
log "Workspace: $(df /workspace | awk 'NR==2{print $4/1024/1024"G free"}')"

# ─── 1. Extract app ──────────────────────────────────────────────────────
log "=== 1/9 Extracting app ==="
cd /workspace
tar -xzf calltone_app.tar.gz && rm calltone_app.tar.gz
log "App extracted"; free_ws

# ─── 2. Build frontend ───────────────────────────────────────────────────
log "=== 2/9 Building frontend ==="
export NVM_DIR=/opt/nvm
export PATH=$NVM_DIR/versions/node/v24.14.1/bin:$PATH
cd /workspace/calltone/calltone-UI
npm ci --ignore-scripts 2>&1 | tail -2
VITE_API_BASE_URL=/api npm run build 2>&1 | tail -5
mkdir -p /workspace/calltone/backend/static
cp -r dist/* /workspace/calltone/backend/static/
rm -rf node_modules
log "Frontend built and copied"; free_ws

# ─── 3. Python venv ──────────────────────────────────────────────────────
log "=== 3/9 Creating Python venv ==="
python3 -m venv /workspace/venv
/workspace/venv/bin/pip install --upgrade pip setuptools wheel --no-cache-dir -q
log "Venv: $(/workspace/venv/bin/python --version)"; free_ws

# ─── 4. Backend deps ─────────────────────────────────────────────────────
log "=== 4/9 Backend deps ==="
/workspace/venv/bin/pip install --no-cache-dir -q \
  fastapi "uvicorn[standard]" sqlalchemy psycopg2-binary \
  pydantic pydantic-settings "python-jose[cryptography]" \
  "passlib[bcrypt]" "bcrypt==4.0.1" email-validator \
  python-multipart aiofiles
log "Backend deps done"; free_ws

# ─── 5. PyTorch CUDA ─────────────────────────────────────────────────────
log "=== 5/9 PyTorch CUDA (downloads to /dev/shm) ==="
/workspace/venv/bin/pip install --no-cache-dir \
  torch torchaudio \
  --index-url https://download.pytorch.org/whl/cu126
/workspace/venv/bin/python -c "import torch; print(f'  torch {torch.__version__} | CUDA: {torch.cuda.is_available()}')"
free_ws

# ─── 6. Core ML deps ─────────────────────────────────────────────────────
log "=== 6/9 Core ML deps ==="
/workspace/venv/bin/pip install --no-cache-dir \
  transformers accelerate huggingface_hub sentencepiece \
  soundfile librosa scipy resampy \
  omegaconf rich tabulate tqdm jinja2 pyyaml
log "Core ML done"; free_ws

# ─── 7. pyannote + onnxruntime + funasr ──────────────────────────────────
log "=== 7/9 pyannote + onnxruntime + funasr ==="
/workspace/venv/bin/pip install --no-cache-dir \
  "pyannote.audio" lightning-fabric onnxruntime-gpu funasr
log "pyannote/onnx/funasr done"; free_ws

# ─── 8. llama-cpp-python with CUDA ───────────────────────────────────────
log "=== 8/9 llama-cpp-python with CUDA (compiling ~10-15 min) ==="
export CMAKE_ARGS="-DGGML_CUDA=on"
export FORCE_CMAKE=1
/workspace/venv/bin/pip install --no-cache-dir "llama-cpp-python>=0.3.0"
/workspace/venv/bin/python -c "import llama_cpp; print('  llama_cpp OK')"
free_ws

# ─── 9. Download models ──────────────────────────────────────────────────
log "=== 9/9 Downloading model weights to /workspace/models ==="
mkdir -p /workspace/models

# Set HuggingFace home to workspace (persistent)
export HF_HOME=/workspace/.hf_home
export HUGGINGFACE_HUB_VERBOSITY=info

/workspace/venv/bin/python - << 'PYEOF'
import os, sys
os.environ["HF_TOKEN"] = os.environ.get("HF_TOKEN", "")
os.environ["HF_HOME"] = "/workspace/.hf_home"
from huggingface_hub import snapshot_download, hf_hub_download
from pathlib import Path

token = os.environ["HF_TOKEN"]
base = Path("/workspace/models")

models = [
    # (repo_id, local_subdir, requires_token, is_file, filename)
    ("bartowski/Meta-Llama-3.1-8B-Instruct-GGUF", "skill_implementation/models", False, True, "Meta-Llama-3.1-8B-Instruct-Q8_0.gguf"),
    ("openai/whisper-large-v3", "LAYER_1/models/whisper/openai/whisper-large-v3", False, False, None),
    ("iic/SenseVoiceSmall", "LAYER_1/models/sensevoice/iic/SenseVoiceSmall", False, False, None),
    ("resemble-enhance/resemble-enhance", "LAYER_1/models/resemble-enhance/enhancer_stage2", False, False, None),
    ("nvidia/Audio2Emotion-v3.0", "LAYER_1/models/Audio2Emotion-v3.0", False, False, None),
    ("pyannote/segmentation-3.0", "LAYER_1/models/pyannote/segmentation-3.0", True, False, None),
    ("pyannote/wespeaker-voxceleb-resnet34-LM", "LAYER_1/models/pyannote/wespeaker-voxceleb-resnet34-LM", True, False, None),
    ("pyannote/speaker-diarization-3.1", "LAYER_1/models/pyannote/speaker-diarization-3.1", True, False, None),
]

for repo_id, subdir, needs_tok, is_file, fname in models:
    dest = base / subdir
    dest.mkdir(parents=True, exist_ok=True)
    tok = token if needs_tok else None
    print(f"\n[Downloading] {repo_id} → {subdir}")
    try:
        if is_file:
            hf_hub_download(repo_id=repo_id, filename=fname, local_dir=str(dest), token=tok)
        else:
            snapshot_download(repo_id=repo_id, local_dir=str(dest), token=tok,
                              ignore_patterns=["*.msgpack", "flax_model*", "tf_model*", "rust_model*"])
        print(f"  ✓ Done")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
print("\nAll downloads attempted.")
PYEOF

free_ws

# ─── Configure symlinks so pipeline finds models ──────────────────────────
log "=== Linking models into pipeline paths ==="
# Pipeline code is at /workspace/calltone/models/ and expects models/ subdirs
# Create symlinks from code paths to /workspace/models/
mkdir -p /workspace/calltone/models/LAYER_1/models
mkdir -p /workspace/calltone/models/skill_implementation/models

# Link model dirs
for dir in whisper sensevoice pyannote Audio2Emotion-v3.0; do
  src="/workspace/models/LAYER_1/models/$dir"
  dst="/workspace/calltone/models/LAYER_1/models/$dir"
  [ -d "$src" ] && [ ! -e "$dst" ] && ln -s "$src" "$dst" && echo "  linked: $dir"
done

# resemble-enhance
src="/workspace/models/LAYER_1/models/resemble-enhance"
dst="/workspace/calltone/models/LAYER_1/resemble-enhance"
[ -d "$src" ] && [ ! -e "$dst" ] && ln -s "$src" "$dst" && echo "  linked: resemble-enhance"

# skill_implementation models
src="/workspace/models/skill_implementation/models"
dst="/workspace/calltone/models/skill_implementation/models"
[ -d "$src" ] && [ ! -e "$dst" ] && ln -s "$src" "$dst" && echo "  linked: skill_implementation/models"

free_ws

# ─── Start backend ────────────────────────────────────────────────────────
log "=== Starting backend ==="
cd /workspace/calltone/backend
export SECRET_KEY=$(openssl rand -hex 32)
export CORS_ORIGINS="*"
export HF_HUB_OFFLINE=1  # Use downloaded models only
export HF_HOME=/workspace/.hf_home
export PYTHONPATH=/workspace/calltone/models:/workspace/calltone/models/LAYER_1/resemble-enhance:/workspace/calltone/models/LAYER_1/pipeline:/workspace/calltone/models/LAYER_1

# Seed DB
/workspace/venv/bin/python -m app.seed_data 2>/dev/null && log "DB seeded"

# Start uvicorn
nohup /workspace/venv/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8080 --workers 1 \
  --timeout-keep-alive 300 \
  > /workspace/uvicorn.log 2>&1 &
echo $! > /workspace/uvicorn.pid
log "uvicorn started (PID $(cat /workspace/uvicorn.pid))"
sleep 3
curl -sf http://localhost:8080/ > /dev/null && log "✓ HTTP OK" || log "✗ HTTP check failed"

log "=== SETUP COMPLETE ==="
free_ws
echo ""
echo "Access: http://<server-ip>:8080"
echo "Logs:   tail -f /workspace/uvicorn.log"
