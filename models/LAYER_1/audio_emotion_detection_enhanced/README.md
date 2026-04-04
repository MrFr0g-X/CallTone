# Audio Emotion Detection Integration for LAYER_1 Pipeline

This module adds audio-based emotion recognition to the LAYER_1 audio processing pipeline using NVIDIA's Audio2Emotion-v3.0 model.

## Overview

After audio goes through denoising/enhancing and then diarization & transcription, this module runs emotion detection on each speaker segment to identify the emotional state during that time period.

## Features

- **Per-segment emotion detection**: Analyzes each speaker turn individually
- **Six emotion classes**: anger, disgust, fear, joy, neutral, sadness
- **Confidence scores**: Provides probability scores for all emotions
- **Enhanced reports**: Generates reports with both text-based and audio-based emotion

## Installation

### 1. Accept License on HuggingFace

The Audio2Emotion model requires accepting NVIDIA's license:

1. Go to: https://huggingface.co/nvidia/Audio2Emotion-v3.0
2. Log in to your HuggingFace account
3. Click "Agree and Access Repository"
4. Accept the license terms

### 2. Download the Model

After accepting the license, download the model:

```bash
cd /home/mazen/grad_project/audio_emotion_detection_enhanced

# Login to HuggingFace (you'll be prompted for your token)
conda run -n calltone huggingface-cli login

# Download the model
conda run -n calltone python download_model.py
```

Alternative manual download:
```bash
cd models
conda run -n calltone huggingface-cli download nvidia/Audio2Emotion-v3.0 --local-dir Audio2Emotion-v3.0
```

### 3. Install Dependencies

The model requires NeMo framework:

```bash
conda run -n calltone pip install nemo_toolkit['all']
```

Or install specific dependencies:
```bash
conda run -n calltone pip install nemo_toolkit torch torchaudio librosa
```

## Usage

### Integrated with LAYER_1 Pipeline

Run the enhanced test pipeline:

```bash
cd /home/mazen/grad_project/LAYER_1
conda run -n calltone python test_pipeline.py
```

When prompted:
1. Choose audio file
2. Select audio preprocessing option (1-4)
3. Enter number of speakers (or auto-detect)
4. **Answer 'y' for emotion detection** when asked: "Do you want to add audio-based emotion detection?"

### Standalone Usage

Process an existing diarization JSON:

```bash
cd /home/mazen/grad_project/LAYER_1
conda run -n calltone python emotion_integration.py <audio_file.wav> <diarized.json>
```

Example:
```bash
conda run -n calltone python emotion_integration.py \
  ../Test_audio/bad_cs_denoised.wav \
  ../Test_audio/bad_cs_results/bad_cs_denoised_diarized.json
```

## Output Files

When emotion detection is enabled, you get:

1. `*_diarized_with_emotions.json` - Enhanced JSON with audio emotion data
2. `*_diarized_with_emotions.txt` - Enhanced text report showing both text and audio emotions

### JSON Structure

Each segment in the JSON will contain:

```json
{
  "start": 18.0,
  "end": 20.0,
  "speaker": "SPEAKER_A",
  "text": "Did you check underneath...",
  "emotion": "QUESTIONING",  // From text analysis
  "audio_emotion": "neutral",  // From Audio2Emotion model
  "audio_emotion_confidence": 0.85,
  "audio_emotion_scores": {
    "anger": 0.02,
    "disgust": 0.01,
    "fear": 0.03,
    "joy": 0.05,
    "neutral": 0.85,
    "sadness": 0.04
  }
}
```

### Text Report Format

```
[00:18→00:20]  SPEAKER_A  [TEXT:QUESTIONING]  [AUDIO:NEUTRAL:0.85]
    Did you check underneath to see if anything is blocking it?
```

## Model Details

- **Model**: nvidia/Audio2Emotion-v3.0
- **Architecture**: Wav2Vec2-based transformer
- **Input**: Raw audio waveforms
- **Output**: 6 emotion classes (anger, disgust, fear, joy, neutral, sadness)
- **Framework**: NeMo (NVIDIA Neural Modules)
- **License**: NVIDIA Audio2Emotion License (commercial use allowed with restrictions)

## Important Notes

### License Restrictions

Per NVIDIA's license:
- ✅ Allowed: Use with Audio2Face project and 3D character animation
- ✅ Allowed: Commercial and non-commercial use within scope
- ❌ Prohibited: General-purpose emotion recognition systems
- ❌ Prohibited: Use outside the Audio2Face project scope

**For your call center use case**, you should verify compliance or consider alternative emotion models like:
- `ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition`
- `superb/wav2vec2-base-superb-er`
- `emo-net` models

### Performance Considerations

- Processing adds ~0.5-2 seconds per segment depending on segment length
- GPU recommended for faster processing
- Processes segments in sequence (not parallelized by default)

## Troubleshooting

### "Model directory not found"
- Ensure you've downloaded the model to the correct location
- Check: `/home/mazen/grad_project/audio_emotion_detection_enhanced/models/Audio2Emotion-v3.0/`

### "License not accepted"
- You must accept the license on HuggingFace before downloading
- Login with: `conda run -n calltone huggingface-cli login`

### "NeMo not installed"
- Install: `conda run -n calltone pip install nemo_toolkit['all']`

### "CUDA out of memory"
- Process shorter audio files
- Use CPU instead: The detector will auto-detect and fallback to CPU

## Alternative Emotion Models

If you prefer a more permissive emotion recognition model:

```python
# In audio_emotion_detector.py, replace with Hugging Face model:
from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2Processor

model_name = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
processor = Wav2Vec2Processor.from_pretrained(model_name)
model = Wav2Vec2ForSequenceClassification.from_pretrained(model_name)
```

## Architecture

```
Pipeline Flow:
1. Audio Input
2. Denoising/Enhancing (optional)
3. Diarization (who spoke when)
4. Transcription (what was said)
5. Text Emotion Detection (existing)
6. ➡️ Audio Emotion Detection (NEW) ⬅️
7. Combined Report Generation
```

## Example Output

Before (text emotions only):
```
[00:18→00:20]  SPEAKER_A  [QUESTIONING]
    Did you check underneath to see if anything is blocking it?
```

After (with audio emotions):
```
[00:18→00:20]  SPEAKER_A  [TEXT:QUESTIONING]  [AUDIO:NEUTRAL:0.85]
    Did you check underneath to see if anything is blocking it?
```

This gives you both perspectives:
- **Text emotion**: What the words suggest
- **Audio emotion**: What the voice tone reveals

## Support

For issues or questions:
1. Check HuggingFace model page: https://huggingface.co/nvidia/Audio2Emotion-v3.0
2. Review NeMo documentation: https://docs.nvidia.com/deeplearning/nemo/user-guide/docs/en/main/
3. Check the Audio2Face project: https://docs.omniverse.nvidia.com/audio2face/
