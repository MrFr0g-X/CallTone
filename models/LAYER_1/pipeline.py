#!/usr/bin/env python3
"""
Complete Audio Processing Pipeline:
1. Audio Enhancement (resemble-enhance)
2. Speaker Diarization & Transcription (transcribe_diarize.py)

Usage:
    conda run -n calltone python pipeline.py <input_audio> [num_speakers]

Example:
    conda run -n calltone python pipeline.py test/2077589677_final_stereo.wav 2
"""

import os
os.environ["DS_BUILD_OPS"] = "0"

import sys
import subprocess
from pathlib import Path

# Add resemble-enhance to path
sys.path.insert(0, str(Path(__file__).parent / "resemble-enhance"))

import torch
import soundfile as sf

from resemble_enhance.enhancer.inference import denoise, enhance


def enhance_audio_stage(input_path, output_path, device="cuda" if torch.cuda.is_available() else "cpu"):
    """Stage 1: Enhance audio using resemble-enhance."""
    print("\n" + "="*80)
    print("STAGE 1: AUDIO ENHANCEMENT")
    print("="*80)
    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print(f"Device: {device}\n")
    
    # Load audio using soundfile
    print("Loading audio...")
    dwav_np, sr = sf.read(input_path)
    dwav = torch.from_numpy(dwav_np).float()
    
    # Convert to mono if stereo
    if dwav.dim() > 1 and dwav.shape[-1] > 1:
        print("Converting stereo to mono...")
        dwav = dwav.mean(dim=-1)
    elif dwav.dim() > 1:
        dwav = dwav.squeeze()
    
    print(f"Audio shape: {dwav.shape}, Sample rate: {sr}")
    
    # Point to local model weights in LAYER_1/models/resemble-enhance/
    run_dir = Path(__file__).parent / "models" / "resemble-enhance" / "enhancer_stage2"

    # Denoise and enhance
    print("\nStep 1/2: Denoising...")
    denoised_wav, new_sr = denoise(dwav, sr, device, run_dir=run_dir)

    print("Step 2/2: Enhancing (using denoised audio)...")
    # Use denoised audio for enhancement with lighter denoising (lambd=0.1)
    enhanced_wav, new_sr = enhance(denoised_wav, new_sr, device, nfe=64, solver="midpoint", lambd=0.1, tau=0.5, run_dir=run_dir)
    
    # Save enhanced audio
    print(f"\nSaving enhanced audio to: {output_path}")
    sf.write(output_path, enhanced_wav.cpu().numpy(), new_sr)
    
    print("✓ Enhancement complete!\n")
    return output_path


def transcribe_diarize_stage(audio_path, num_speakers=None):
    """Stage 2: Transcribe and diarize using transcribe_diarize.py."""
    print("\n" + "="*80)
    print("STAGE 2: TRANSCRIPTION & DIARIZATION")
    print("="*80)
    print(f"Input: {audio_path}")
    if num_speakers:
        print(f"Expected speakers: {num_speakers}\n")
    else:
        print("Speakers: Auto-detect\n")
    
    # Build command
    script_path = Path(__file__).parent / "pipeline" / "transcribe_diarize.py"
    cmd = ["conda", "run", "-n", "calltone", "python", str(script_path), audio_path]
    if num_speakers:
        cmd.append(str(num_speakers))
    
    # Run transcription
    print("Running transcription & diarization...\n")
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    if result.returncode == 0:
        print("\n✓ Transcription complete!")
        # Output files are automatically saved by transcribe_diarize.py
        base = os.path.splitext(audio_path)[0]
        print(f"\nOutput files:")
        print(f"  - {base}_diarized.txt")
        print(f"  - {base}_diarized.json")
    else:
        print(f"\n✗ Transcription failed with code {result.returncode}")
        sys.exit(result.returncode)


def main():
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <input_audio> [num_speakers]")
        print("\nExample:")
        print("  python pipeline.py test/2077589677_final_stereo.wav 2")
        sys.exit(1)
    
    input_audio = sys.argv[1]
    num_speakers = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    if not os.path.exists(input_audio):
        print(f"Error: Input file not found: {input_audio}")
        sys.exit(1)
    
    print("\n" + "="*80)
    print("AUDIO PROCESSING PIPELINE")
    print("="*80)
    print(f"Input file: {input_audio}")
    print(f"Speakers: {num_speakers if num_speakers else 'Auto-detect'}")
    
    # Generate enhanced output path
    base, ext = os.path.splitext(input_audio)
    enhanced_audio = f"{base}_enhanced{ext}"
    
    try:
        # STAGE 1: Enhancement
        enhance_audio_stage(input_audio, enhanced_audio)
        
        # STAGE 2: Transcription & Diarization
        transcribe_diarize_stage(enhanced_audio, num_speakers)
        
        print("\n" + "="*80)
        print("✓ PIPELINE COMPLETE!")
        print("="*80)
        print(f"\nFinal outputs:")
        base_enhanced = os.path.splitext(enhanced_audio)[0]
        print(f"  1. Enhanced audio: {enhanced_audio}")
        print(f"  2. Transcription:  {base_enhanced}_diarized.txt")
        print(f"  3. JSON data:      {base_enhanced}_diarized.json")
        print()
        
    except KeyboardInterrupt:
        print("\n\n✗ Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
