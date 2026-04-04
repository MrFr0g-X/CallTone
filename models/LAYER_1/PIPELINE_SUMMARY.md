# LAYER_1 Complete Pipeline Summary

## Pipeline Features

The LAYER_1 pipeline processes audio files through multiple stages to produce rich transcriptions with:

1. **Audio Preprocessing** (Optional)
   - Denoising
   - Enhancement  
   - Or both

2. **Speaker Diarization**
   - Identifies who spoke when
   - Segments audio by speaker

3. **Transcription**
   - Converts speech to text using Whisper
   - Text emotion detection **DISABLED** (unreliable)

4. **Role Identification** ✨ NEW
   - Uses AI skill to identify speaker roles
   - Replaces generic SPEAKER_A/B with meaningful roles
   - Example: "Customer Service Agent", "Customer"

5. **Audio Emotion Detection** (Optional)
   - Uses NVIDIA Audio2Emotion-v3.0 model
   - Analyzes each segment for emotional tone
   - 6 emotions: anger, disgust, fear, joy, neutral, sadness

## Output Files

### Without Emotion Detection:
- `audio_diarized.txt` - Readable transcript with roles
- `audio_diarized.json` - Structured data with roles

### With Emotion Detection:
- `audio_diarized_with_emotions.txt` - Transcript with roles + emotions
- `audio_diarized_with_emotions.json` - Full data with roles + emotions

## Example Output

### Text Format (.txt)
```
════════════════════════════════════════════════════════════════════════════════
  TRANSCRIPTION WITH SPEAKER DIARIZATION + AUDIO EMOTION
  (Audio-based emotion detection using NVIDIA Audio2Emotion-v3.0)
  File     : call.wav
  Speakers : 2
════════════════════════════════════════════════════════════════════════════════

[00:06→00:08]  Customer Service Agent  [JOY:0.79]
    All pro vacuums, this is Tanya.

[00:09→00:13]  Customer  [ANGER:0.74]
    Hey, Tanya, I'm having a problem with my vacuum cleaner.

[00:18→00:20]  Customer Service Agent  [ANGER:0.51]
    Did you check underneath to see if anything is blocking it?
```

### JSON Format (.json)
```json
{
  "call_metadata": {
    "file": "call.wav",
    "duration_seconds": 90.75,
    "num_speakers": 2,
    "total_segments": 40,
    "roles_identified": true,
    "role_mapping": {
      "SPEAKER_A": "Customer Service Agent",
      "SPEAKER_B": "Customer"
    }
  },
  "speaker_summary": {
    "Customer Service Agent": {
      "talk_time_seconds": 19.79,
      "talk_time_pct": 21.8,
      "median_pitch_hz": null,
      "behavioral_signals": {
        "QUESTIONING": 4,
        "SATISFIED": 1
      },
      "role": "Customer Service Agent"
    },
    "Customer": {
      "talk_time_seconds": 70.96,
      "talk_time_pct": 78.2,
      "behavioral_signals": {
        "QUESTIONING": 1
      },
      "role": "Customer"
    }
  },
  "transcript": [
    {
      "id": 1,
      "start": 6.93,
      "end": 8.59,
      "speaker": "Customer Service Agent",
      "role": "Customer Service Agent",
      "emotion": "EMO_UNKNOWN",
      "event": "Speech",
      "signals": [],
      "text": "All pro vacuums, this is Tanya.",
      "audio_emotion": "joy",
      "audio_emotion_confidence": 0.79,
      "audio_emotion_scores": {
        "anger": 0.15,
        "disgust": 0.01,
        "fear": 0.03,
        "joy": 0.79,
        "neutral": 0.01,
        "sadness": 0.00
      }
    }
  ]
}
```

## Usage

### Interactive Mode
```bash
cd /home/mazen/grad_project/LAYER_1
conda run -n calltone python test_pipeline.py
```

Follow the prompts:
1. Enter audio file path
2. Choose preprocessing option (1-4)
3. Specify number of speakers (or auto-detect)
4. Enable role identification (y/n) - **recommended: yes**
5. Enable emotion detection (y/n)

### Programmatic Mode

```python
# Step 1: Transcribe + Diarize
os.system('python pipeline/transcribe_diarize.py audio.wav 2')

# Step 2: Identify Roles (optional but recommended)
os.system('python role_identification.py audio_diarized.json audio_diarized.txt')

# Step 3: Add Emotions (optional)
os.system('python emotion_integration.py audio.wav audio_diarized.json')
```

## Key Features

✅ **Fully Offline** - No internet or API tokens required
✅ **GPU Accelerated** - Uses CUDA when available
✅ **Role-Aware** - Meaningful speaker labels instead of A/B
✅ **Emotion-Enhanced** - Audio-based emotion detection
✅ **Behavioral Signals** - Detects questioning, frustration, satisfaction, etc.
✅ **Multiple Formats** - Both human-readable (TXT) and machine-readable (JSON)

## Models Used

1. **pyannote/segmentation-3.0** - Speaker diarization
2. **Whisper Large V3** - Speech transcription
3. **NVIDIA Audio2Emotion-v3.0** - Audio emotion detection (ONNX)
4. **Meta-Llama-3.1-8B-Instruct** - Role identification skill

## Files Structure

```
LAYER_1/
├── pipeline.py                              # Original pipeline
├── test_pipeline.py                         # Interactive test script
├── role_identification.py                   # Role identification module
├── emotion_integration.py                   # Emotion detection module
├── audio_emotion_detection_enhanced/        # Emotion detection system
│   ├── audio_emotion_detector.py
│   └── models/Audio2Emotion-v3.0/
├── pipeline/
│   ├── transcribe_diarize.py               # Main transcription module
│   └── SenseVoice/                          # (Unused - replaced with Whisper)
└── models/
    └── pyannote/
```

## Notes

- Role identification accuracy depends on clear role indicators in the transcript
- Emotion detection works best on segments > 0.6 seconds
- Audio preprocessing (denoise/enhance) can improve transcription quality
- All processing is done locally - no external API calls
