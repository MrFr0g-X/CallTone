#!/usr/bin/env python3
"""
Download the Audio2Emotion-v3.0 model from HuggingFace.
"""

from huggingface_hub import snapshot_download
import os

MODEL_ID = "nvidia/Audio2Emotion-v3.0"
LOCAL_DIR = "/home/mazen/grad_project/audio_emotion_detection_enhanced/models/Audio2Emotion-v3.0"

print(f"Downloading {MODEL_ID}...")
print(f"Saving to: {LOCAL_DIR}")

snapshot_download(
    repo_id=MODEL_ID,
    local_dir=LOCAL_DIR,
    local_dir_use_symlinks=False,
)

print(f"\n✓ Model downloaded successfully to {LOCAL_DIR}")
