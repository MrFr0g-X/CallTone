#!/usr/bin/env python3
"""
Interactive Audio Processing Pipeline Test Script

This script allows you to test the audio processing pipeline with different
preprocessing options (no processing, denoise only, enhance only, or both).

Usage:
    conda run -n calltone python test_pipeline.py
"""

import os
os.environ["DS_BUILD_OPS"] = "0"

import sys
import shutil
from pathlib import Path

# Add resemble-enhance to path
sys.path.insert(0, str(Path(__file__).parent / "resemble-enhance"))

import torch
import torch.nn.functional as F
import soundfile as sf
from torchaudio.functional import resample as torchaudio_resample

from resemble_enhance.enhancer.inference import denoise, enhance


def clear_screen():
    """Clear the terminal screen."""
    os.system('clear' if os.name != 'nt' else 'cls')


def print_header():
    """Print the script header."""
    print("\n" + "="*80)
    print(" " * 20 + "AUDIO PROCESSING PIPELINE TEST")
    print("="*80 + "\n")


def get_audio_path():
    """Get audio file path from user."""
    while True:
        audio_path = input("Enter path of audio file: ").strip()
        
        # Remove quotes if user wrapped path in quotes
        audio_path = audio_path.strip('"').strip("'")
        
        if not audio_path:
            print("❌ Error: Please provide a valid path.\n")
            continue
            
        if not os.path.exists(audio_path):
            print(f"❌ Error: File not found: {audio_path}\n")
            continue
            
        # Check if it's a valid audio file
        ext = os.path.splitext(audio_path)[1].lower()
        if ext not in ['.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac']:
            print(f"❌ Error: Unsupported audio format: {ext}")
            print("   Supported formats: .wav, .mp3, .flac, .ogg, .m4a, .aac\n")
            continue
            
        return audio_path


def get_processing_option():
    """Get user's choice for audio processing."""
    print("\nHow do you want to process the audio file?")
    print("  1. Input as is (no preprocessing)")
    print("  2. Only denoised")
    print("  3. Only enhanced")
    print("  4. Denoised and enhanced")
    
    while True:
        choice = input("\nEnter your choice (1-4): ").strip()
        if choice in ['1', '2', '3', '4']:
            return int(choice)
        print("❌ Invalid choice. Please enter 1, 2, 3, or 4.")


def process_audio(input_path, option, device="cuda" if torch.cuda.is_available() else "cpu"):
    """
    Process audio based on user's choice.
    
    Returns:
        processed_audio_path: Path to the processed audio file
    """
    print("\n" + "-"*80)
    print("AUDIO PREPROCESSING")
    print("-"*80)
    print(f"Input:  {input_path}")
    print(f"Option: {option}")
    print(f"Device: {device}\n")
    
    if option == 1:
        # No processing - just return original path
        print("✓ Using input audio as is (no preprocessing)\n")
        return input_path
    
    # Load audio using soundfile
    print("Loading audio...")
    dwav_np, sr = sf.read(input_path)
    original_length = len(dwav_np)
    dwav = torch.from_numpy(dwav_np).float()
    
    # Convert to mono if stereo
    if dwav.dim() > 1 and dwav.shape[-1] > 1:
        print("Converting stereo to mono...")
        dwav = dwav.mean(dim=-1)
    elif dwav.dim() > 1:
        dwav = dwav.squeeze()
    
    print(f"Audio shape: {dwav.shape}, Sample rate: {sr}")
    
    # Process based on option
    base, ext = os.path.splitext(input_path)
    run_dir = Path(__file__).parent / "models" / "resemble-enhance" / "enhancer_stage2"

    if option == 2:
        # Only denoise
        print("\nDenoising audio...")
        processed_wav, new_sr = denoise(dwav, sr, device, run_dir=run_dir)
        output_path = f"{base}_denoised.wav"
        suffix = "denoised"

    elif option == 3:
        # Only enhance
        print("\nEnhancing audio (without prior denoising)...")
        processed_wav, new_sr = enhance(dwav, sr, device, nfe=64, solver="midpoint", lambd=0.5, tau=0.5, run_dir=run_dir)
        output_path = f"{base}_enhanced.wav"
        suffix = "enhanced"

    elif option == 4:
        # Denoise then enhance
        print("\nStep 1/2: Denoising...")
        denoised_wav, new_sr = denoise(dwav, sr, device, run_dir=run_dir)

        print("Step 2/2: Enhancing (using denoised audio)...")
        processed_wav, new_sr = enhance(denoised_wav, new_sr, device, nfe=64, solver="midpoint", lambd=0.1, tau=0.5, run_dir=run_dir)
        output_path = f"{base}_denoised_enhanced.wav"
        suffix = "denoised_enhanced"
    
    # Ensure processed audio has consistent length and sample rate
    # Resample back to original sample rate if it changed
    if new_sr != sr:
        print(f"Resampling from {new_sr} Hz back to {sr} Hz...")
        processed_wav = torchaudio_resample(processed_wav, orig_freq=new_sr, new_freq=sr)
        new_sr = sr
    
    # Trim or pad to match original length approximately
    current_length = processed_wav.shape[-1]
    if abs(current_length - original_length) > sr * 0.1:  # More than 0.1 second difference
        print(f"Adjusting audio length from {current_length} to {original_length} samples...")
        if current_length > original_length:
            processed_wav = processed_wav[:original_length]
        else:
            processed_wav = F.pad(processed_wav, (0, original_length - current_length))
    
    # Save processed audio as WAV with explicit format
    print(f"\nSaving processed audio to: {output_path}")
    sf.write(output_path, processed_wav.cpu().numpy(), new_sr, subtype='PCM_16')
    
    print(f"✓ Audio preprocessing complete!\n")
    return output_path


def run_transcription_diarization(audio_path, num_speakers=None):
    """
    Run transcription and diarization on the audio file.
    
    Returns:
        output_dir: Directory containing the results
    """
    print("\n" + "-"*80)
    print("TRANSCRIPTION & DIARIZATION")
    print("-"*80)
    print(f"Input: {audio_path}")
    if num_speakers:
        print(f"Expected speakers: {num_speakers}\n")
    else:
        print("Speakers: Auto-detect\n")
    
    # Import and run transcription
    script_dir = Path(__file__).parent
    transcribe_script = script_dir / "pipeline" / "transcribe_diarize.py"
    
    # Import the transcribe_diarize module
    sys.path.insert(0, str(script_dir / "pipeline"))
    import transcribe_diarize
    
    # Save original sys.argv
    original_argv = sys.argv.copy()
    
    # Set sys.argv for the transcribe_diarize script
    sys.argv = ["transcribe_diarize.py", audio_path]
    if num_speakers:
        sys.argv.append(str(num_speakers))
    
    try:
        # Run the main function
        transcribe_diarize.main()
        
        # Get output paths
        base = os.path.splitext(audio_path)[0]
        txt_output = f"{base}_diarized.txt"
        json_output = f"{base}_diarized.json"
        
        return txt_output, json_output
        
    finally:
        # Restore original sys.argv
        sys.argv = original_argv


def organize_outputs(audio_path, processed_audio_path, txt_output, json_output):
    """
    Organize outputs into a folder named after the original audio file.
    
    Returns:
        output_dir: Path to the output directory
    """
    print("\n" + "-"*80)
    print("ORGANIZING OUTPUT FILES")
    print("-"*80)
    
    # Create output directory based on original audio file name
    audio_name = os.path.splitext(os.path.basename(audio_path))[0]
    output_dir = os.path.join(os.path.dirname(audio_path), f"{audio_name}_results")
    
    # Create directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Copy/move files to output directory
    files_to_copy = []
    
    # Add processed audio if different from original
    if processed_audio_path != audio_path:
        files_to_copy.append((processed_audio_path, os.path.join(output_dir, os.path.basename(processed_audio_path))))
    
    # Add output files
    files_to_copy.append((txt_output, os.path.join(output_dir, os.path.basename(txt_output))))
    files_to_copy.append((json_output, os.path.join(output_dir, os.path.basename(json_output))))
    
    print(f"\nOutput directory: {output_dir}\n")
    print("Copying files:")
    for src, dst in files_to_copy:
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  ✓ {os.path.basename(dst)}")
    
    print(f"\n✓ All outputs saved to: {output_dir}\n")
    return output_dir


def main():
    """Main function to run the interactive pipeline."""
    try:
        clear_screen()
        print_header()
        
        # Step 1: Get audio file path
        audio_path = get_audio_path()
        
        # Step 2: Get processing option
        option = get_processing_option()
        
        # Optional: Ask for number of speakers
        print("\nNumber of speakers (press Enter to auto-detect): ", end="")
        num_speakers_input = input().strip()
        num_speakers = int(num_speakers_input) if num_speakers_input else None
        
        # Optional: Ask for role identification
        print("\nDo you want to identify speaker roles? (y/n, default: y): ", end="")
        role_identification = input().strip().lower() not in ['n', 'no']
        
        # Optional: Ask for emotion detection
        print("\nDo you want to add audio-based emotion detection? (y/n, default: n): ", end="")
        emotion_detection = input().strip().lower() in ['y', 'yes']
        
        print("\n" + "="*80)
        print("STARTING PIPELINE")
        print("="*80)
        
        # Step 3: Process audio based on option
        processed_audio_path = process_audio(audio_path, option)
        
        # Step 4: Run transcription and diarization
        txt_output, json_output = run_transcription_diarization(processed_audio_path, num_speakers)
        
        # Step 5 (Optional): Identify speaker roles
        if role_identification:
            try:
                from role_identification import identify_speaker_roles, apply_roles_to_outputs
                role_map = identify_speaker_roles(json_output)
                if role_map:
                    apply_roles_to_outputs(json_output, txt_output, role_map)
            except Exception as e:
                print(f"\n⚠ Warning: Role identification failed: {e}")
                print("Continuing with original speaker labels...\n")
        
        # Step 6 (Optional): Add emotion detection
        if emotion_detection:
            try:
                from emotion_integration import enhance_diarization_with_emotions
                enhanced_json = enhance_diarization_with_emotions(processed_audio_path, json_output)
                # Update outputs to include enhanced versions
                enhanced_txt = enhanced_json.replace('.json', '.txt')
                if os.path.exists(enhanced_txt):
                    txt_output = enhanced_txt
                    json_output = enhanced_json
            except Exception as e:
                print(f"\n⚠ Warning: Emotion detection failed: {e}")
                print("Continuing with original outputs...\n")
        
        # Step 7: Organize outputs
        output_dir = organize_outputs(audio_path, processed_audio_path, txt_output, json_output)
        
        # Final summary
        print("\n" + "="*80)
        print("✓ PIPELINE COMPLETE!")
        print("="*80)
        print(f"\nAll results are saved in: {output_dir}")
        print("\nOutput files:")
        print(f"  📝 Text transcription: {os.path.basename(txt_output)}")
        print(f"  📊 JSON data: {os.path.basename(json_output)}")
        if processed_audio_path != audio_path:
            print(f"  🔊 Processed audio: {os.path.basename(processed_audio_path)}")
        print("\nPipeline features:")
        if role_identification:
            print(f"  👥 Role identification: Enabled")
        if emotion_detection:
            print(f"  🎭 Emotion detection: Enabled")
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
