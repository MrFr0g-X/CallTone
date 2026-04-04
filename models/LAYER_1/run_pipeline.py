#!/usr/bin/env python3
"""
Non-interactive LAYER_1 pipeline runner.

Steps:
  1. Trim leading seconds from the audio
  2. Denoise (no enhancement)
  3. Transcription + diarization
  4. Role identification
  5. Emotion detection

Usage:
    conda run -n main python run_pipeline.py <audio_file> [trim_seconds] [num_speakers]

Example:
    conda run -n main python run_pipeline.py audio.mp3 11 2
"""

import os
os.environ["DS_BUILD_OPS"] = "0"

import sys
import shutil
from pathlib import Path

# Add resemble-enhance to path
sys.path.insert(0, str(Path(__file__).parent / "resemble-enhance"))
sys.path.insert(0, str(Path(__file__).parent / "pipeline"))
sys.path.insert(0, str(Path(__file__).parent))

import torch
import torch.nn.functional as F
import soundfile as sf
from torchaudio.functional import resample as torchaudio_resample


def trim_audio(input_path: str, trim_seconds: float) -> str:
    """Trim the first `trim_seconds` seconds from the audio and save as WAV."""
    print(f"\n{'='*80}")
    print("STEP 1: TRIMMING AUDIO")
    print(f"{'='*80}")
    print(f"Input:        {input_path}")
    print(f"Trim:         first {trim_seconds}s\n")

    data, sr = sf.read(input_path)
    trim_samples = int(trim_seconds * sr)
    trimmed = data[trim_samples:]

    base = os.path.splitext(input_path)[0]
    out_path = f"{base}_trimmed.wav"
    sf.write(out_path, trimmed, sr)
    duration = len(trimmed) / sr
    print(f"Trimmed duration: {duration:.1f}s")
    print(f"Saved to: {out_path}")
    return out_path


def denoise_audio(input_path: str) -> str:
    """Denoise (no enhancement) and save as WAV."""
    from resemble_enhance.enhancer.inference import denoise

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\n{'='*80}")
    print("STEP 2: DENOISING")
    print(f"{'='*80}")
    print(f"Input:  {input_path}")
    print(f"Device: {device}\n")

    dwav_np, sr = sf.read(input_path)
    original_length = len(dwav_np)
    dwav = torch.from_numpy(dwav_np).float()

    if dwav.dim() > 1:
        print("Converting to mono...")
        dwav = dwav.mean(dim=-1) if dwav.shape[-1] > 1 else dwav.squeeze()

    run_dir = Path(__file__).parent / "models" / "resemble-enhance" / "enhancer_stage2"
    print("Denoising...")
    processed_wav, new_sr = denoise(dwav, sr, device, run_dir=run_dir)

    if new_sr != sr:
        print(f"Resampling {new_sr} Hz -> {sr} Hz...")
        processed_wav = torchaudio_resample(processed_wav, orig_freq=new_sr, new_freq=sr)
        new_sr = sr

    current_length = processed_wav.shape[-1]
    if abs(current_length - original_length) > sr * 0.1:
        print(f"Adjusting length {current_length} -> {original_length} samples...")
        if current_length > original_length:
            processed_wav = processed_wav[:original_length]
        else:
            processed_wav = F.pad(processed_wav, (0, original_length - current_length))

    base = os.path.splitext(input_path)[0]
    out_path = f"{base}_denoised.wav"
    sf.write(out_path, processed_wav.cpu().numpy(), new_sr, subtype='PCM_16')
    print(f"Saved to: {out_path}")
    return out_path


def transcribe_diarize(audio_path: str, num_speakers: int | None) -> tuple[str, str]:
    """Run transcription + diarization. Returns (txt_path, json_path)."""
    print(f"\n{'='*80}")
    print("STEP 3: TRANSCRIPTION & DIARIZATION")
    print(f"{'='*80}")
    print(f"Input:    {audio_path}")
    print(f"Speakers: {num_speakers if num_speakers else 'auto-detect'}\n")

    import transcribe_diarize as td

    original_argv = sys.argv.copy()
    sys.argv = ["transcribe_diarize.py", audio_path]
    if num_speakers:
        sys.argv.append(str(num_speakers))
    try:
        td.main()
    finally:
        sys.argv = original_argv

    base = os.path.splitext(audio_path)[0]
    return f"{base}_diarized.txt", f"{base}_diarized.json"


def run_role_identification(json_path: str, txt_path: str) -> None:
    """Identify speaker roles and rewrite output files in place."""
    print(f"\n{'='*80}")
    print("STEP 4: ROLE IDENTIFICATION")
    print(f"{'='*80}\n")

    from role_identification import identify_speaker_roles, apply_roles_to_outputs
    role_map = identify_speaker_roles(json_path)
    if role_map:
        apply_roles_to_outputs(json_path, txt_path, role_map)
        print(f"Roles applied: {role_map}")
    else:
        print("Warning: no roles detected, keeping generic labels.")


def run_emotion_detection(audio_path: str, json_path: str) -> tuple[str, str]:
    """Add audio emotion to diarization output. Returns (txt_path, json_path)."""
    print(f"\n{'='*80}")
    print("STEP 5: EMOTION DETECTION")
    print(f"{'='*80}\n")

    from emotion_integration import enhance_diarization_with_emotions
    enhanced_json = enhance_diarization_with_emotions(audio_path, json_path)
    enhanced_txt = enhanced_json.replace('.json', '.txt')
    return enhanced_txt, enhanced_json


def organize_outputs(original_audio: str, files: list[str]) -> str:
    """Copy all result files into <audio_name>_results/ folder."""
    audio_name = os.path.splitext(os.path.basename(original_audio))[0]
    out_dir = os.path.join(os.path.dirname(original_audio), f"{audio_name}_results")
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n{'='*80}")
    print("ORGANIZING OUTPUTS")
    print(f"{'='*80}")
    print(f"Output dir: {out_dir}\n")

    for f in files:
        if f and os.path.exists(f):
            dst = os.path.join(out_dir, os.path.basename(f))
            shutil.copy2(f, dst)
            print(f"  Copied: {os.path.basename(f)}")

    return out_dir


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_pipeline.py <audio_file> [trim_seconds] [num_speakers]")
        print("Example: python run_pipeline.py call.mp3 11 2")
        sys.exit(1)

    audio_file   = sys.argv[1]
    trim_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    num_speakers = int(sys.argv[3])   if len(sys.argv) > 3 else None

    if not os.path.exists(audio_file):
        print(f"Error: file not found: {audio_file}")
        sys.exit(1)

    print(f"\n{'='*80}")
    print("LAYER 1 PIPELINE")
    print(f"{'='*80}")
    print(f"Audio:    {audio_file}")
    print(f"Trim:     {trim_seconds}s")
    print(f"Speakers: {num_speakers if num_speakers else 'auto'}")
    print(f"Denoise:  yes  |  Enhance: no  |  Roles: yes  |  Emotions: yes")

    try:
        # Step 1: Trim
        trimmed_path = trim_audio(audio_file, trim_seconds) if trim_seconds > 0 else audio_file

        # Step 2: Denoise
        denoised_path = denoise_audio(trimmed_path)

        # Step 3: Transcribe + diarize
        txt_path, json_path = transcribe_diarize(denoised_path, num_speakers)

        # Step 4: Role identification
        try:
            run_role_identification(json_path, txt_path)
        except Exception as e:
            print(f"Warning: role identification failed: {e}")

        # Step 5: Emotion detection
        try:
            txt_path, json_path = run_emotion_detection(denoised_path, json_path)
        except Exception as e:
            print(f"Warning: emotion detection failed: {e}")

        # Collect all generated files
        all_files = [trimmed_path, denoised_path, txt_path, json_path]

        # Organize into output folder
        out_dir = organize_outputs(audio_file, all_files)

        print(f"\n{'='*80}")
        print("PIPELINE COMPLETE")
        print(f"{'='*80}")
        print(f"Results saved in: {out_dir}\n")

    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
