"""
Portable path configuration for CallTone.

All paths are resolved relative to this file's directory,
with optional override via CALLTONE_ROOT environment variable.
"""

import os
from pathlib import Path

# Root of the repository
REPO_ROOT = Path(os.environ.get("CALLTONE_ROOT", str(Path(__file__).parent.resolve())))

# Model paths
MODEL_PATHS = {
    "llama_gguf": REPO_ROOT
    / "skill_implementation"
    / "models"
    / "Meta-Llama-3.1-8B-Instruct-Q8_0.gguf",
    "whisper": REPO_ROOT / "LAYER_1" / "models" / "whisper" / "openai" / "whisper-large-v3",
    "resemble_enhance": REPO_ROOT / "LAYER_1" / "models" / "resemble-enhance",
    "audio2emotion": REPO_ROOT
    / "LAYER_1"
    / "audio_emotion_detection_enhanced"
    / "models"
    / "Audio2Emotion-v3.0",
    "pyannote_segmentation": REPO_ROOT
    / "LAYER_1"
    / "models"
    / "pyannote"
    / "segmentation-3.0",
    "pyannote_wespeaker": REPO_ROOT
    / "LAYER_1"
    / "models"
    / "pyannote"
    / "wespeaker-voxceleb-resnet34-LM",
}

# Directory paths
LAYER_1_DIR = REPO_ROOT / "LAYER_1"
LAYER_2_DIR = REPO_ROOT / "LAYER_2"
LAYER_3_DIR = REPO_ROOT / "LAYER_3"
SKILL_DIR = REPO_ROOT / "skill_implementation"
TEST_AUDIO_DIR = REPO_ROOT / "Test_audio"
