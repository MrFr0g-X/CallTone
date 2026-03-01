# Quick Start: Audio Emotion Detection

This guide will get you up and running with audio emotion detection in the LAYER_1 pipeline.

## Setup (One-Time)

### Option 1: Automatic Setup (Recommended)

```bash
cd /home/mazen/grad_project/audio_emotion_detection_enhanced
./setup.sh
```

This will:
- Install transformers and dependencies
- Optionally install NeMo for NVIDIA model
- Test the installation

### Option 2: Manual Setup

```bash
# Install HuggingFace model support (recommended, works out-of-the-box)
conda run -n calltone pip install transformers accelerate

# Optional: For NVIDIA Audio2Emotion model
conda run -n calltone pip install nemo_toolkit['all']
```

## Usage

### Run the Enhanced Pipeline

```bash
cd /home/mazen/grad_project/LAYER_1
conda run -n calltone python test_pipeline.py
```

Interactive prompts:
```
Enter path of audio file: ../Test_audio/bad_cs.mp3

How do you want to process the audio file?
  1. Input as is (no preprocessing)
  2. Only denoised
  3. Only enhanced
  4. Denoised and enhanced

Enter your choice (1-4): 2

Number of speakers (press Enter to auto-detect): 2

Do you want to add audio-based emotion detection? (y/n, default: n): y
```

That's it! The pipeline will:
1. Denoise the audio (or your chosen preprocessing)
2. Perform speaker diarization
3. Transcribe the speech
4. Detect text-based emotions
5. **Detect audio-based emotions for each segment** ← NEW!
6. Generate enhanced reports

## Output

You'll get two types of output files:

### 1. Enhanced JSON (`*_diarized_with_emotions.json`)

```json
{
  "segments": [
    {
      "start": 18.0,
      "end": 20.0,
      "speaker": "SPEAKER_A",
      "text": "Did you check underneath...",
      "emotion": "QUESTIONING",
      "audio_emotion": "neutral",
      "audio_emotion_confidence": 0.87,
      "audio_emotion_scores": {
        "angry": 0.02,
        "calm": 0.03,
        "disgust": 0.01,
        "fearful": 0.02,
        "happy": 0.03,
        "neutral": 0.87,
        "sad": 0.01,
        "surprised": 0.01
      }
    }
  ]
}
```

### 2. Enhanced Text Report (`*_diarized_with_emotions.txt`)

```
═══════════════════════════════════════════════════════════════════
  TRANSCRIPTION WITH SPEAKER DIARIZATION + AUDIO EMOTION
  File     : bad_cs_denoised.wav
  Speakers : 2
═══════════════════════════════════════════════════════════════════

[00:18→00:20]  SPEAKER_A  [TEXT:QUESTIONING]  [AUDIO:NEUTRAL:0.87]
    Did you check underneath to see if anything is blocking it?

[00:22→00:25]  SPEAKER_B  [TEXT:NEUTRAL]  [AUDIO:CALM:0.91]
    Well yeah, of course I did, that was one of the first things
    that I did.
```

## What's the Difference?

**Text Emotion** (from words):
- Analyzes what was said
- Based on word choice, phrasing
- Detects: QUESTIONING, CONFUSED, FRUSTRATED, APOLOGETIC, etc.

**Audio Emotion** (from voice):
- Analyzes how it was said
- Based on voice tone, pitch, rhythm
- Detects: angry, calm, disgust, fearful, happy, neutral, sad, surprised

Both perspectives together give you a more complete picture!

## Example: Text vs Audio Emotions

```
[00:51→00:54]  SPEAKER_B  [TEXT:NEUTRAL]  [AUDIO:FRUSTRATED:0.82]
    I'm trying to explain that what I was doing.
```

Here:
- **Text**: Words are neutral (just explaining)
- **Audio**: Voice shows frustration (tone reveals true emotion)

This discrepancy can be valuable for call quality analysis!

## Troubleshooting

### "Model not found" or "Cannot load model"

The system will automatically use the HuggingFace fallback model. No action needed!

If you see this message:
```
Could not load NeMo model: ... Falling back to HuggingFace...
✓ HuggingFace emotion model loaded successfully
```

You're fine! The system is using the open-source emotion model.

### Want to use NVIDIA Audio2Emotion instead?

1. Visit https://huggingface.co/nvidia/Audio2Emotion-v3.0
2. Accept license
3. Login: `conda run -n calltone huggingface-cli login`
4. Download: `cd /home/mazen/grad_project/audio_emotion_detection_enhanced && conda run -n calltone python download_model.py`

### Processing is slow

- Normal: ~0.5-2 seconds per segment
- Use GPU for faster processing (auto-detected)
- Or skip emotion detection for quick tests

## Advanced: Process Existing Results

Already have diarization results? Add emotions to them:

```bash
cd /home/mazen/grad_project/LAYER_1

conda run -n calltone python emotion_integration.py \
  /path/to/audio.wav \
  /path/to/audio_diarized.json
```

This creates:
- `audio_diarized_with_emotions.json`
- `audio_diarized_with_emotions.txt`

## Next Steps

- Process your call center recordings
- Compare text vs audio emotions
- Identify emotional patterns
- Improve customer service training
- Detect agent stress or customer frustration

Happy emotion detecting! 🎭
