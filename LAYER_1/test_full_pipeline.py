#!/usr/bin/env python3
"""
Quick test of the complete LAYER_1 pipeline with role identification and emotion detection.
"""

import os
import sys
from pathlib import Path

# Add repo root for config import
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from config import LAYER_1_DIR, TEST_AUDIO_DIR

TEST_WAV = TEST_AUDIO_DIR / "full_test" / "test.wav"
TEST_JSON = TEST_AUDIO_DIR / "full_test" / "test_diarized.json"
TEST_TXT = TEST_AUDIO_DIR / "full_test" / "test_diarized.txt"

# Run transcription
print("=" * 80)
print("Step 1: Running transcription + diarization...")
print("=" * 80)
os.system(
    f'cd "{LAYER_1_DIR}" && conda run -n calltone python pipeline/transcribe_diarize.py'
    f' "{TEST_WAV}" 2'
)

# Run role identification
print("\n" + "=" * 80)
print("Step 2: Identifying speaker roles...")
print("=" * 80)
os.system(
    f'cd "{LAYER_1_DIR}" && conda run -n calltone python role_identification.py'
    f' "{TEST_JSON}" "{TEST_TXT}"'
)

# Run emotion detection
print("\n" + "=" * 80)
print("Step 3: Adding audio emotion detection...")
print("=" * 80)
os.system(
    f'cd "{LAYER_1_DIR}" && conda run -n calltone python emotion_integration.py'
    f' "{TEST_WAV}" "{TEST_JSON}"'
)

print("\n" + "=" * 80)
print("✓ COMPLETE PIPELINE TEST FINISHED!")
print("=" * 80)
print(f"\nCheck outputs in: {TEST_AUDIO_DIR / 'full_test'}")
