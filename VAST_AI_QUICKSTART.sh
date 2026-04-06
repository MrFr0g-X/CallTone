#!/usr/bin/env bash
# ============================================================
# CallTone - Vast.ai B200 GPU Quick-Start Script
# Run this on a fresh vast.ai instance with /workspace partition
# Tested on: CUDA 12.9, Ubuntu 22.04, NVIDIA B200 (sm_100)
# ============================================================
set -e

WORKSPACE=/workspace
REPO_URL=https://github.com/MrFr0g-X/CallTone.git
HF_TOKEN=${HF_TOKEN:-}  # Set via: export HF_TOKEN=hf_xxx

echo '======================================================'
echo '  CallTone Vast.ai Quick-Start'
echo '======================================================'

# Phase 1: Clone repo
echo ''
echo '[1/8] Cloning repo...'
git clone $REPO_URL $WORKSPACE/calltone
cd $WORKSPACE/calltone

# Phase 2: Build frontend
echo ''
echo '[2/8] Building React frontend...'
if ! command -v node &>/dev/null; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
    export NVM_DIR=$HOME/.nvm
    source $NVM_DIR/nvm.sh
    nvm install 24
fi
cd calltone-UI
npm ci
VITE_API_BASE_URL=/api npm run build
mkdir -p ../backend/static
cp -r dist/* ../backend/static/
cd ..

# Phase 3: Python venv
echo ''
echo '[3/8] Setting up Python environment...'
python3.11 -m venv $WORKSPACE/venv 2>/dev/null || python3 -m venv $WORKSPACE/venv
source $WORKSPACE/venv/bin/activate

# Phase 4: Fix cublas headers for CUDA 12.9 (missing in runtime-only install)
echo ''
echo '[4/8] Fixing CUDA cuBLAS headers...'
CUBLAS_SRC=$(find /usr/local -name 'cublas_v2.h' 2>/dev/null | head -1)
if [ -n $CUBLAS_SRC ]; then
    CUDA_INC=$(dirname $CUBLAS_SRC)
    TARGET_INC=/usr/local/cuda/targets/x86_64-linux/include
    for header in $CUDA_INC/cublas*.h; do
        [ -f $TARGET_INC/$(basename $header) ] || cp $header $TARGET_INC/
    done
    echo 'cuBLAS headers copied'
else
    apt-get install -y libcublas-dev-12-8 2>/dev/null || true
fi

# Phase 5: PyTorch cu128 (B200 sm_100 support)
echo ''
echo '[5/8] Installing PyTorch for B200 GPU (cu128)...'
export TMPDIR=/dev/shm
pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu128

# Phase 6: Backend and ML dependencies
echo ''
echo '[6/8] Installing backend + ML dependencies...'
pip install --no-cache-dir -r backend/requirements.txt
pip install --no-cache-dir     transformers accelerate pyannote.audio lightning-fabric     huggingface_hub sentencepiece     soundfile librosa scipy numpy resampy     omegaconf rich tabulate tqdm     onnxruntime-gpu     jinja2 pyyaml funasr

# Phase 7: llama-cpp-python with CUDA for B200 (sm_100 only)
echo ''
echo '[7/8] Building llama-cpp-python for B200 (sm_100)...'
CMAKE_ARGS='-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=100'     FORCE_CMAKE=1     pip install --no-cache-dir 'llama-cpp-python>=0.3.0'

# Remove torchcodec (incompatible with PyTorch 2.11+cu128)
pip uninstall torchcodec -y 2>/dev/null || true

# Phase 8: Download model weights
echo ''
echo '[8/8] Downloading model weights (~16 GB)...'
mkdir -p $WORKSPACE/models
pip install huggingface_hub -q

if [ -n $HF_TOKEN ]; then
    python3 download_models.py --hf-token $HF_TOKEN --target-dir $WORKSPACE/models
else
    python3 download_models.py --target-dir $WORKSPACE/models
fi

# Set up model symlinks
ln -sfn $WORKSPACE/models/LAYER_1/models models/LAYER_1/models
ln -sfn $WORKSPACE/models/skill_implementation/models models/skill_implementation/models
ln -sfn $WORKSPACE/models/LAYER_1/resemble-enhance/enhancer_stage2     models/LAYER_1/resemble-enhance/enhancer_stage2
# Fix Audio2Emotion ONNX path
mkdir -p models/LAYER_1/audio_emotion_detection_enhanced/models/Audio2Emotion-v3.0
ln -sfn $WORKSPACE/models/LAYER_1/models/Audio2Emotion-v3.0/network.onnx     models/LAYER_1/audio_emotion_detection_enhanced/models/Audio2Emotion-v3.0/network.onnx

# Start the app
echo ''
echo '======================================================'
echo '  Starting CallTone on port 8080...'
echo '======================================================'
fuser -k 8080/tcp 2>/dev/null || true
cd backend
HF_TOKEN=$HF_TOKEN $WORKSPACE/venv/bin/python3 -m app.seed_data 2>/dev/null
exec $WORKSPACE/venv/bin/python3 -m uvicorn app.main:app     --host 0.0.0.0 --port 8080 --workers 1
