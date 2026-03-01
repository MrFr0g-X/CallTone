#!/usr/bin/env python3
"""
Download the Audio2Emotion-v3.0 model from HuggingFace.
"""

import sys
from pathlib import Path

# Add repo root to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))

from config import MODEL_PATHS
from huggingface_hub import snapshot_download

MODEL_ID = "nvidia/Audio2Emotion-v3.0"
LOCAL_DIR = str(MODEL_PATHS["audio2emotion"])

print(f"Downloading {MODEL_ID}...")
print(f"Saving to: {LOCAL_DIR}")

snapshot_download(
    repo_id=MODEL_ID,
    local_dir=LOCAL_DIR,
    local_dir_use_symlinks=False,
)

print(f"\n✓ Model downloaded successfully to {LOCAL_DIR}")
