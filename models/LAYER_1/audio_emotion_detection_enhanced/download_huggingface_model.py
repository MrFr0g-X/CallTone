#!/usr/bin/env python3
"""
Download HuggingFace emotion model for fully offline operation.

This script downloads the wav2vec2 emotion recognition model and saves it locally
so you can use the emotion detector without internet connection.
"""

from pathlib import Path
import os
import sys

# Set HuggingFace cache directory to avoid path issues
CACHE_DIR = Path(__file__).parent / ".cache" / "huggingface"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ['HF_HOME'] = str(CACHE_DIR)
os.environ['TRANSFORMERS_CACHE'] = str(CACHE_DIR / "transformers")
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

# Target directory
LOCAL_MODEL_DIR = Path(__file__).parent / "models" / "wav2vec2-emotion"

print("=" * 70)
print("Downloading HuggingFace Emotion Model for Offline Use")
print("=" * 70)
print()

# Create directory
LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)

print(f"Target directory: {LOCAL_MODEL_DIR}")
print()

try:
    from transformers import Wav2Vec2ForSequenceClassification, AutoFeatureExtractor
    import torch
except ImportError:
    print("✗ Missing required packages: transformers and/or torch")
    print()
    print("Installing automatically...")
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "transformers", "torch", "torchaudio"])
    from transformers import Wav2Vec2ForSequenceClassification, AutoFeatureExtractor
    import torch
    print()

try:
    MODEL_NAME = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
    
    print(f"Downloading model: {MODEL_NAME}")
    print("This may take a few minutes (downloading ~1.2 GB)...")
    print()
    
    # Download feature extractor
    print("Step 1/2: Downloading feature extractor...")
    sys.stdout.flush()
    feature_extractor = AutoFeatureExtractor.from_pretrained(
        MODEL_NAME,
        cache_dir=str(CACHE_DIR)
    )
    feature_extractor.save_pretrained(str(LOCAL_MODEL_DIR))
    print("✓ Feature extractor downloaded and saved")
    print()
    
    # Download model
    print("Step 2/2: Downloading model weights (this is the large file)...")
    sys.stdout.flush()
    model = Wav2Vec2ForSequenceClassification.from_pretrained(
        MODEL_NAME,
        cache_dir=str(CACHE_DIR)
    )
    model.save_pretrained(str(LOCAL_MODEL_DIR))
    print("✓ Model weights downloaded and saved")
    
    print()
    print("=" * 70)
    print("✓ Download Complete!")
    print("=" * 70)
    print()
    print(f"Model saved to: {LOCAL_MODEL_DIR}")
    print()
    print("You can now use the emotion detector OFFLINE")
    print("The system will automatically use this local model.")
    
except ImportError as e:
    print(f"✗ Error: Failed to install required packages: {e}")
    print()
    print("Please install manually with:")
    print("  pip install transformers torch torchaudio")
    exit(1)
    
except Exception as e:
    print(f"✗ Error downloading model: {e}")
    print()
    print("Troubleshooting steps:")
    print("1. Check your internet connection")
    print("2. Try running with a HuggingFace token (see HuggingFace documentation)")
    print("3. Check if you have enough disk space (~1.5 GB needed)")
    import traceback
    print()
    print("Full error details:")
    traceback.print_exc()
    exit(1)
