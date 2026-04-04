#!/usr/bin/env python3
"""
Download HuggingFace emotion model for fully offline operation.

This script downloads the wav2vec2 emotion recognition model and saves it locally
so you can use the emotion detector without internet connection.
"""

from pathlib import Path
import os

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
    from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2Processor
    
    MODEL_NAME = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
    
    print(f"Downloading model: {MODEL_NAME}")
    print("This may take a few minutes...")
    print()
    
    # Download processor
    print("Downloading processor...")
    processor = Wav2Vec2Processor.from_pretrained(MODEL_NAME)
    processor.save_pretrained(str(LOCAL_MODEL_DIR))
    print("✓ Processor downloaded")
    
    # Download model
    print("Downloading model weights...")
    model = Wav2Vec2ForSequenceClassification.from_pretrained(MODEL_NAME)
    model.save_pretrained(str(LOCAL_MODEL_DIR))
    print("✓ Model weights downloaded")
    
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
    print(f"✗ Error: {e}")
    print()
    print("Please install transformers first:")
    print("  conda run -n calltone pip install transformers")
    exit(1)
    
except Exception as e:
    print(f"✗ Error downloading model: {e}")
    print()
    print("Please check your internet connection and try again.")
    exit(1)
