#!/usr/bin/env bash
# ============================================================
# CallTone - Vast.ai B200 GPU Quick-Start Script
# Run this on a fresh vast.ai instance with /workspace partition
# Tested on: CUDA 12.9, Ubuntu 22.04, NVIDIA B200 (sm_100)
# Branch: server
# ============================================================
set -euo pipefail

WORKSPACE=/workspace
REPO_URL=https://github.com/MrFr0g-X/CallTone.git
APP_DIR="$WORKSPACE/calltone"
VENV="$WORKSPACE/venv"
HF_TOKEN="${HF_TOKEN:-}"  # Set via: export HF_TOKEN=hf_xxx before running

echo "======================================================"
echo "  CallTone Vast.ai Quick-Start"
echo "======================================================"

# ── Phase 1: Clone repo ──────────────────────────────────
echo ""
echo "[1/9] Cloning repo (server branch)..."
git clone -b server "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

# ── Phase 2: Build frontend ──────────────────────────────
echo ""
echo "[2/9] Building React frontend..."
cd "$APP_DIR/calltone-UI"
npm ci
VITE_API_BASE_URL=/api npm run build
mkdir -p "$APP_DIR/backend/static"
cp -r dist/* "$APP_DIR/backend/static/"
cd "$APP_DIR"

# ── Phase 3: Create Python venv ──────────────────────────
echo ""
echo "[3/9] Creating Python virtual environment..."
python3.11 -m venv "$VENV" || python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip setuptools wheel

# ── Phase 4: Fix missing cuBLAS headers (CUDA 12.9 issue) ─
echo ""
echo "[4/9] Fixing cuBLAS headers for CUDA compile..."
CUBLAS_SRC="/usr/local/cuda-12.8/targets/x86_64-linux/include"
if [ -n "$CUBLAS_SRC" ] && [ -d "$CUBLAS_SRC" ]; then
    cp "$CUBLAS_SRC"/cublas*.h /usr/local/cuda/targets/x86_64-linux/include/ 2>/dev/null || true
    echo "  cuBLAS headers copied from cuda-12.8"
else
    echo "  cuda-12.8 not found, skipping (headers may already be present)"
fi

# ── Phase 5: Install PyTorch cu128 (B200/sm_100 support) ─
echo ""
echo "[5/9] Installing PyTorch 2.11 + cu128 (B200 support)..."
pip install torch==2.11.0 torchaudio==2.11.0 \
    --index-url https://download.pytorch.org/whl/cu128

# ── Phase 6: Install Python dependencies ─────────────────
echo ""
echo "[6/9] Installing backend + ML dependencies..."
pip install -r "$APP_DIR/backend/requirements.txt"
pip install \
    transformers accelerate pyannote.audio lightning-fabric \
    huggingface_hub sentencepiece \
    soundfile librosa scipy numpy resampy \
    omegaconf rich tabulate tqdm \
    onnxruntime-gpu \
    jinja2 pyyaml \
    openai-whisper

# ── Phase 7: Build llama-cpp-python with CUDA (sm_100) ───
echo ""
echo "[7/9] Building llama-cpp-python with CUDA (sm_100)..."
export CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=100"
export FORCE_CMAKE=1
pip install "llama-cpp-python>=0.3.0" --no-cache-dir
# Remove torchcodec — it requires libnvrtc.so.13 (CUDA 13) which doesnt exist
pip uninstall torchcodec -y 2>/dev/null || true
echo "  torchcodec removed (CUDA 13 incompatibility workaround)"

# ── Phase 8: Download model weights ──────────────────────
echo ""
echo "[8/9] Downloading model weights (~16 GB)..."
cd "$APP_DIR"
if [ -n "$HF_TOKEN" ]; then
    python3 download_models.py --hf-token "$HF_TOKEN"
else
    echo "  WARNING: HF_TOKEN not set — pyannote models will be skipped!"
    python3 download_models.py
fi

# ── Phase 9: Create model symlinks ───────────────────────
# download_models.py saves to LAYER_1/models/ and skill_implementation/models/
# but the backend expects models at models/LAYER_1/models/ and models/skill_implementation/models/
echo ""
echo "[9/9] Creating model symlinks..."
mkdir -p "$APP_DIR/models/LAYER_1"
mkdir -p "$APP_DIR/models/skill_implementation"
mkdir -p "$APP_DIR/models/LAYER_2/company_context/contexts"

# Core model dirs
ln -sfn "$APP_DIR/LAYER_1/models" "$APP_DIR/models/LAYER_1/models"
ln -sfn "$APP_DIR/skill_implementation/models" "$APP_DIR/models/skill_implementation/models"

# resemble-enhance
mkdir -p "$APP_DIR/models/LAYER_1/resemble-enhance"
ln -sfn "$APP_DIR/LAYER_1/models/resemble-enhance/enhancer_stage2" \
    "$APP_DIR/models/LAYER_1/resemble-enhance/enhancer_stage2"

# Audio2Emotion ONNX model
mkdir -p "$APP_DIR/models/LAYER_1/audio_emotion_detection_enhanced/models/Audio2Emotion-v3.0"
ln -sfn "$APP_DIR/LAYER_1/audio_emotion_detection_enhanced/models/Audio2Emotion-v3.0/network.onnx" \
    "$APP_DIR/models/LAYER_1/audio_emotion_detection_enhanced/models/Audio2Emotion-v3.0/network.onnx" \
    2>/dev/null || true

echo ""
echo "======================================================"
echo "  Setup complete! Starting CallTone..."
echo "======================================================"

# ── Launch ────────────────────────────────────────────────
# Kill JupyterLab if it grabbed port 8080 (common on vast.ai)
fuser -k 8080/tcp 2>/dev/null || true

cd "$APP_DIR/backend"
python3 -m app.seed_data 2>/dev/null || true

exec python3 -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8080 \
    --workers 1 \
    --timeout-keep-alive 300
