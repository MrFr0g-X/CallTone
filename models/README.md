# Grad Project — Audio Analysis Pipeline

An end-to-end pipeline for processing call-center audio: enhancement, transcription, speaker diarization, emotion detection, and role identification via LLM.

## Project Structure

```
grad_project/
├── LAYER_1/                    # Audio processing pipeline
│   ├── pipeline/               # Core pipeline (transcription + diarization)
│   ├── audio_emotion_detection_enhanced/  # Emotion detection from audio
│   ├── resemble-enhance/       # Audio enhancement (noise removal)
│   └── models/                 # Model weights (downloaded separately)
│
├── skill_implementation/       # LLM-based role identification
│   ├── skills/                 # Prompt-only skill definitions
│   ├── skill_runtime/          # Runtime framework
│   ├── runner/                 # CLI interface
│   └── models/                 # LLM weights (downloaded separately)
│
├── Test_audio/                 # Sample audio for testing
├── download_models.py          # Script to download all model weights
└── README.md
```

## Pipeline Overview

```
Raw Audio
   │
   ▼
[LAYER_1] Audio Enhancement (resemble-enhance)
   │
   ▼
[LAYER_1] Transcription + Speaker Diarization (Whisper + pyannote)
   │
   ▼
[LAYER_1] Emotion Detection per utterance (Audio2Emotion)
   │
   ▼
[skill_implementation] Role Identification (Llama 3.1 8B)
   │
   ▼
Structured Output (JSON)
```

## Quick Start

### 1. Install dependencies

```bash
# LAYER_1 dependencies
pip install -r LAYER_1/requirements_full.txt

# skill_implementation dependencies
pip install -r skill_implementation/requirements.txt
```

### 2. Download model weights (~12.5 GB total)

> Models are not included in this repo due to size. Use the download script:

```bash
# Install the downloader dependency first
pip install huggingface-hub

# See what will be downloaded
python download_models.py --list

# Download all models (except pyannote — requires token)
python download_models.py

# Download ALL models including pyannote (requires HuggingFace token)
# First accept terms at:
#   https://huggingface.co/pyannote/segmentation-3.0
#   https://huggingface.co/pyannote/speaker-diarization-3.1
python download_models.py --hf-token YOUR_HF_TOKEN

# Download a single model
python download_models.py --model llama
python download_models.py --model whisper
```

| Model Key             | Size      | Used by                        |
|-----------------------|-----------|-------------------------------|
| `llama`               | ~8.0 GB   | skill_implementation (LLM)    |
| `whisper`             | ~3.0 GB   | LAYER_1 transcription         |
| `resemble`            | ~681 MB   | LAYER_1 audio enhancement     |
| `audio2emotion`       | ~1.2 GB   | LAYER_1 emotion detection     |
| `pyannote-segmentation` | ~500 MB | LAYER_1 diarization (token)   |
| `pyannote-wespeaker`  | ~500 MB   | LAYER_1 diarization (token)   |

### 3. Run the pipeline

```bash
# Run the full LAYER_1 pipeline on an audio file
cd LAYER_1
python pipeline.py --input /path/to/audio.mp3

# Run role identification skill
cd skill_implementation
python runner/run_skill.py --skill identify-call-roles --file examples/sample_transcript.txt
```

## Components

### LAYER_1 — Audio Processing

Handles everything from raw audio to an annotated transcript with speaker labels and emotions.

- **Audio enhancement**: removes background noise using [resemble-enhance](https://github.com/resemble-ai/resemble-enhance)
- **Transcription**: speech-to-text via [Whisper](https://huggingface.co/openai/whisper-large-v3)
- **Diarization**: who spoke when via [pyannote.audio](https://github.com/pyannote/pyannote-audio)
- **Emotion detection**: per-utterance emotion from audio using [Audio2Emotion](https://huggingface.co/nvidia/Audio2Emotion-v3.0)

See [LAYER_1/LAYER_1_ARCHITECTURE.md](LAYER_1/LAYER_1_ARCHITECTURE.md) for a detailed architecture overview.

### skill_implementation — LLM Skills

A lightweight framework for deterministic, prompt-only LLM tasks using local models.

- **Model**: Meta-Llama-3.1-8B-Instruct (Q8 GGUF, runs on CPU/GPU)
- **Current skills**: `identify-call-roles` — labels speakers as Agent/Customer
- **Deterministic**: same input always produces same output (temperature=0)

See [skill_implementation/README.md](skill_implementation/README.md) for full documentation.

## Requirements

- Python 3.9+
- CUDA (optional, improves speed for LAYER_1 models)
- ~15 GB disk space for all models
- ~8 GB RAM minimum (16 GB recommended)

## HuggingFace Token

pyannote models require accepting usage terms and authenticating:

1. Create a free account at [huggingface.co](https://huggingface.co)
2. Accept terms at [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0) and [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
3. Generate a token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
4. Pass it via `python download_models.py --hf-token YOUR_TOKEN` or set `HF_TOKEN=YOUR_TOKEN`
