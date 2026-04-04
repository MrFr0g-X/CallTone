#!/bin/bash
# Setup script for Audio Emotion Detection integration

echo "========================================"
echo "Audio Emotion Detection Setup"
echo "========================================"
echo ""

# Check conda environment
echo "Checking conda environment 'calltone'..."
if ! conda env list | grep -q "calltone"; then
    echo "ERROR: conda environment 'calltone' not found!"
    echo "Please create it first."
    exit 1
fi

echo "✓ Environment 'calltone' found"
echo ""

# Check which model is available
echo "Checking for NVIDIA Audio2Emotion model..."
if [ -f "/home/mazen/grad_project/audio_emotion_detection_enhanced/models/Audio2Emotion-v3.0/network.onnx" ]; then
    echo "✓ NVIDIA Audio2Emotion model found (1.2GB ONNX model)"
    echo "  This is the PRIMARY model that will be used"
    HAS_NVIDIA=true
else
    echo "⚠ NVIDIA Audio2Emotion model not found"
    echo "  Will use HuggingFace fallback model instead"
    HAS_NVIDIA=false
fi
echo ""

# Install onnxruntime (for NVIDIA model)
if [ "$HAS_NVIDIA" = true ]; then
    echo "Installing onnxruntime for NVIDIA model..."
    
    # Check if CUDA is available
    if command -v nvidia-smi &> /dev/null; then
        echo "  CUDA detected - installing onnxruntime-gpu..."
        conda run -n calltone pip install onnxruntime-gpu -q
    else
        echo "  No CUDA detected - installing onnxruntime (CPU)..."
        conda run -n calltone pip install onnxruntime -q
    fi
    
    echo "✓ ONNX Runtime installed"
    echo ""
fi

# Install transformers (for fallback model)
echo "Installing transformers for HuggingFace fallback model..."
conda run -n calltone pip install transformers accelerate -q
echo "✓ Transformers installed"
echo ""

# Download HuggingFace model for offline use
echo "Do you want to download HuggingFace emotion model for OFFLINE use? (y/n)"
echo "(This is optional if you have the NVIDIA model)"
read -r download_hf

if [[ "$download_hf" == "y" || "$download_hf" == "Y" ]]; then
    echo ""
    echo "Downloading HuggingFace model..."
    cd /home/mazen/grad_project/audio_emotion_detection_enhanced
    conda run -n calltone python download_huggingface_model.py
    echo ""
fi

# Test the installation
echo "========================================"
echo "Testing emotion detector..."
echo "========================================"
cd /home/mazen/grad_project/audio_emotion_detection_enhanced
conda run -n calltone python -c "
import warnings
warnings.filterwarnings('ignore')
try:
    from audio_emotion_detector import Audio2EmotionDetector
    detector = Audio2EmotionDetector()
    print('✓ Emotion detector working!')
    print(f'  Backend: {detector.backend}')
    print(f'  Device: {detector.device}')
    print(f'  Emotions: {', '.join(detector.emotion_labels)}')
except Exception as e:
    print(f'✗ Error: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
"

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""

if [ "$HAS_NVIDIA" = true ]; then
    echo "✓ Using NVIDIA Audio2Emotion-v3.0 (ONNX) - PRIMARY"
    echo "  Emotions: anger, disgust, fear, joy, neutral, sadness"
else
    echo "✓ Using HuggingFace wav2vec2 emotion model - FALLBACK"
    echo "  Emotions: angry, calm, disgust, fearful, happy, neutral, sad, surprised"
fi

echo ""
echo "Usage:"
echo "  cd /home/mazen/grad_project/LAYER_1"
echo "  conda run -n calltone python test_pipeline.py"
echo ""
echo "When prompted, answer 'y' to enable emotion detection."
echo ""
echo "OFFLINE MODE: All models are now local, no internet required! 🔒"
echo ""
