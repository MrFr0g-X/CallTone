#!/usr/bin/env python3
"""
Quick test of the complete LAYER_1 pipeline with role identification and emotion detection.
"""

import os
import sys
sys.path.insert(0, 'pipeline')

# Run transcription
print("="*80)
print("Step 1: Running transcription + diarization...")
print("="*80)
os.system('cd /home/mazen/grad_project/LAYER_1 && conda run -n calltone python pipeline/transcribe_diarize.py /home/mazen/grad_project/Test_audio/full_test/test.wav 2')

# Run role identification
print("\n" + "="*80)
print("Step 2: Identifying speaker roles...")
print("="*80)
os.system('cd /home/mazen/grad_project/LAYER_1 && conda run -n calltone python role_identification.py /home/mazen/grad_project/Test_audio/full_test/test_diarized.json /home/mazen/grad_project/Test_audio/full_test/test_diarized.txt')

# Run emotion detection
print("\n" + "="*80)
print("Step 3: Adding audio emotion detection...")
print("="*80)
os.system('cd /home/mazen/grad_project/LAYER_1 && conda run -n calltone python emotion_integration.py /home/mazen/grad_project/Test_audio/full_test/test.wav /home/mazen/grad_project/Test_audio/full_test/test_diarized.json')

print("\n" + "="*80)
print("✓ COMPLETE PIPELINE TEST FINISHED!")
print("="*80)
print("\nCheck outputs in: /home/mazen/grad_project/Test_audio/full_test/")
print("\nFiles created:")
os.system('ls -lh /home/mazen/grad_project/Test_audio/full_test/*.{txt,json} 2>/dev/null')
