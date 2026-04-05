"""
Integration module to add Audio2Emotion detection to LAYER_1 pipeline.

This module enhances the transcribe_diarize results with audio-based emotion detection.
"""

import sys
import json
from pathlib import Path

# Add audio_emotion_detection_enhanced to path
sys.path.insert(0, str(Path(__file__).parent / "audio_emotion_detection_enhanced"))

from audio_emotion_detector import Audio2EmotionDetector

# Module-level cache — loaded once, reused across pipeline calls
_DETECTOR_CACHE: dict = {}


def enhance_diarization_with_emotions(
    audio_path: str,
    json_output_path: str,
    model_dir: str = None
) -> str:
    """
    Add audio-based emotion detection to existing diarization JSON output.
    
    Args:
        audio_path: Path to the audio file
        json_output_path: Path to the _diarized.json file
        model_dir: Optional custom model directory
        
    Returns:
        Path to the enhanced JSON file
    """
    print("\n" + "="*80)
    print("AUDIO EMOTION DETECTION")
    print("="*80)
    print(f"Audio: {audio_path}")
    print(f"JSON:  {json_output_path}\n")
    
    # Load existing diarization results
    with open(json_output_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Handle both 'segments' and 'transcript' keys
    segments = data.get('segments', data.get('transcript', []))
    
    if not segments:
        print("Warning: No segments found in JSON file")
        return json_output_path
    
    # Initialize emotion detector (cached — loads 1.18 GB ONNX model only once)
    cache_key = str(model_dir)
    if cache_key not in _DETECTOR_CACHE:
        _DETECTOR_CACHE[cache_key] = Audio2EmotionDetector(model_dir=model_dir)
    else:
        print("  Audio2Emotion model already loaded — reusing cached model.")
    detector = _DETECTOR_CACHE[cache_key]
    
    # Batch-process all segments in a single GPU forward pass
    enriched_segments = detector.process_diarization_segments(audio_path, segments)
    print()
    
    # Update data with enriched segments (preserve original key name)
    segments_key = 'transcript' if 'transcript' in data else 'segments'
    data[segments_key] = enriched_segments
    
    # Add metadata about emotion detection
    if 'metadata' not in data:
        data['metadata'] = {}
    data['metadata']['audio_emotion_model'] = 'nvidia/Audio2Emotion-v3.0'
    data['metadata']['audio_emotion_processed'] = True
    
    # Save enhanced JSON
    enhanced_json_path = json_output_path.replace('.json', '_with_emotions.json')
    with open(enhanced_json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Enhanced JSON saved to: {enhanced_json_path}")
    
    # Also generate an enhanced text report
    generate_enhanced_text_report(data, enhanced_json_path.replace('.json', '.txt'))
    
    return enhanced_json_path


def generate_enhanced_text_report(data: dict, output_path: str):
    """
    Generate a text report with audio emotion information.
    
    Args:
        data: Enhanced diarization data with emotions
        output_path: Path to save the text report
    """
    lines = []
    W = 80
    
    lines.append("═" * W)
    lines.append("  TRANSCRIPTION WITH SPEAKER DIARIZATION + AUDIO EMOTION")
    lines.append("  (Audio-based emotion detection using NVIDIA Audio2Emotion-v3.0)")
    
    # Handle different JSON structures
    if 'call_metadata' in data:
        lines.append(f"  File     : {data['call_metadata'].get('file', 'unknown')}")
        lines.append(f"  Speakers : {data['call_metadata'].get('num_speakers', 'unknown')}")
    else:
        lines.append(f"  File     : {data.get('audio_file', 'unknown')}")
        lines.append(f"  Speakers : {data.get('total_speakers', 'unknown')}")
    
    lines.append("═" * W)
    lines.append("")
    
    # Handle both 'segments' and 'transcript' keys
    segments = data.get('segments', data.get('transcript', []))
    
    # Process segments
    for segment in segments:
        start = segment['start']
        end = segment['end']
        speaker = segment['speaker']
        text = segment.get('text', '')
        
        # Get emotions
        transcript_emotion = segment.get('emotion', '')
        audio_emotion = segment.get('audio_emotion', '')
        audio_confidence = segment.get('audio_emotion_confidence', 0.0)
        
        # Format timestamp
        time_str = f"[{int(start//60):02d}:{int(start%60):02d}→{int(end//60):02d}:{int(end%60):02d}]"
        
        # Format header with audio emotion only (text emotion disabled)
        header = f"{time_str}  {speaker}"
        
        if audio_emotion:
            header += f"  [{audio_emotion.upper()}:{audio_confidence:.2f}]"
        
        lines.append(header)
        
        # Add text if present
        if text:
            # Wrap text to fit width
            text_lines = []
            current_line = "    "
            words = text.split()
            for word in words:
                if len(current_line) + len(word) + 1 <= W - 4:
                    current_line += word + " "
                else:
                    text_lines.append(current_line.rstrip())
                    current_line = "    " + word + " "
            if current_line.strip():
                text_lines.append(current_line.rstrip())
            
            lines.extend(text_lines)
        
        lines.append("")
    
    # Add summary
    lines.append("─" * W)
    lines.append("  EMOTION ANALYSIS SUMMARY")
    lines.append("─" * W)
    
    # Count audio emotions per speaker
    from collections import defaultdict, Counter
    
    # Get segments (handle both keys)
    segments = data.get('segments', data.get('transcript', []))
    
    speaker_audio_emotions = defaultdict(list)
    for seg in segments:
        if 'audio_emotion' in seg:
            speaker_audio_emotions[seg['speaker']].append(seg['audio_emotion'])
    
    for speaker in sorted(speaker_audio_emotions.keys()):
        emotions = speaker_audio_emotions[speaker]
        emotion_counts = Counter(emotions)
        lines.append(f"\n  {speaker}")
        lines.append(f"    Audio emotions detected: {len(emotions)} segments")
        for emotion, count in emotion_counts.most_common():
            pct = (count / len(emotions)) * 100
            lines.append(f"      {emotion}: {count} ({pct:.1f}%)")
    
    lines.append("")
    lines.append("═" * W)
    
    # Write report
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"Enhanced text report saved to: {output_path}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python emotion_integration.py <audio_file> <diarized_json>")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    json_file = sys.argv[2]
    
    enhance_diarization_with_emotions(audio_file, json_file)
