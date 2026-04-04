# LAYER_1 Simple Flow Diagram

## Visual Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         LAYER 1: AUDIO PROCESSING                       │
└─────────────────────────────────────────────────────────────────────────┘

INPUT:
  📁 audio_file.mp3/wav/flac
     ↓

┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: PREPROCESSING (Optional)                                      │
│                                                                         │
│  Model: Resemble-Enhance                                               │
│  Options:                                                               │
│    [1] As-is (no processing)                                           │
│    [2] Denoise only                                                    │
│    [3] Enhance only                                                    │
│    [4] Denoise + Enhance                                               │
│                                                                         │
│  Output: 🔊 audio_processed.wav (16kHz, Mono)                         │
└─────────────────────────────────────────────────────────────────────────┘
     ↓

┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: SPEAKER DIARIZATION                                           │
│                                                                         │
│  Models:                                                                │
│    • pyannote/segmentation-3.0 (speaker change detection)             │
│    • wespeaker-resnet34-LM (speaker embedding)                        │
│                                                                         │
│  Process:                                                               │
│    Audio → Voice Activity Detection → Speaker Segmentation             │
│         → Speaker Clustering → Timeline                                │
│                                                                         │
│  Output:                                                                │
│    ┌────────────────────────────────────────┐                         │
│    │ SPEAKER_A: [0.0s → 5.2s]              │                         │
│    │ SPEAKER_B: [5.5s → 8.3s]              │                         │
│    │ SPEAKER_A: [8.7s → 12.1s]             │                         │
│    │ ...                                     │                         │
│    └────────────────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────┘
     ↓

┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: SPEECH TRANSCRIPTION                                          │
│                                                                         │
│  Model: Whisper (openai/whisper-large-v3)                              │
│                                                                         │
│  Process:                                                               │
│    Audio Segments → Speech Recognition → Text + Events                │
│                  → Behavioral Signal Detection                         │
│                                                                         │
│  Output:                                                                │
│    ┌────────────────────────────────────────┐                         │
│    │ SPEAKER_A: "Hello, how can I help?"   │                         │
│    │   signals: [QUESTIONING]               │                         │
│    │                                         │                         │
│    │ SPEAKER_B: "I have a problem."        │                         │
│    │   signals: [FRUSTRATED]                │                         │
│    └────────────────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────┘
     ↓

┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 4: ROLE IDENTIFICATION (Optional, Default: ON)                   │
│                                                                         │
│  Model: Meta-Llama-3.1-8B-Instruct (GGUF, 8-bit)                      │
│  Skill: identify-call-roles                                            │
│                                                                         │
│  Process:                                                               │
│    Transcript → AI Analysis → Role Classification                      │
│                                                                         │
│  Analyzes:                                                              │
│    • Professional language patterns                                    │
│    • Greeting/closing styles                                           │
│    • Problem description vs solution offering                          │
│    • Question patterns                                                  │
│                                                                         │
│  Output:                                                                │
│    ┌────────────────────────────────────────┐                         │
│    │ SPEAKER_A → "Customer Service Agent"  │                         │
│    │ SPEAKER_B → "Customer"                │                         │
│    │ Confidence: 0.95                       │                         │
│    └────────────────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────┘
     ↓

┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 5: AUDIO EMOTION DETECTION (Optional, Default: OFF)              │
│                                                                         │
│  Model: NVIDIA Audio2Emotion-v3.0 (ONNX)                              │
│  Size: 1.18 GB                                                         │
│  Backend: ONNX Runtime (GPU accelerated)                               │
│                                                                         │
│  Process:                                                               │
│    For each segment:                                                   │
│      Audio → Resample (16kHz) → Pad (min 10k samples)                │
│           → Neural Network → 6 Emotion Scores                          │
│                                                                         │
│  Emotions Detected:                                                     │
│    • anger                                                              │
│    • disgust                                                            │
│    • fear                                                               │
│    • joy                                                                │
│    • neutral                                                            │
│    • sadness                                                            │
│                                                                         │
│  Output per segment:                                                    │
│    ┌────────────────────────────────────────┐                         │
│    │ Dominant: "anger"                      │                         │
│    │ Confidence: 0.74                       │                         │
│    │ Scores: {                              │                         │
│    │   anger: 0.74, joy: 0.12,             │                         │
│    │   neutral: 0.09, fear: 0.01, ...      │                         │
│    │ }                                       │                         │
│    └────────────────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────┘
     ↓

┌─────────────────────────────────────────────────────────────────────────┐
│ FINAL OUTPUT                                                            │
│                                                                         │
│  📄 audio_diarized.txt                                                 │
│  📊 audio_diarized.json                                                │
│                                                                         │
│  IF emotion detection enabled:                                         │
│  📄 audio_diarized_with_emotions.txt                                   │
│  📊 audio_diarized_with_emotions.json                                  │
│                                                                         │
│  Contents:                                                              │
│    ✓ Speaker roles (Agent/Customer/etc.)                              │
│    ✓ Timestamped transcript                                            │
│    ✓ Behavioral signals (questioning, frustrated, etc.)                │
│    ✓ Audio emotions (if enabled)                                       │
│    ✓ Speaker statistics (talk time, pitch, etc.)                      │
│    ✓ Conversation summary                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Transformation Flow

```
┌──────────────────┐
│  Raw Audio File  │  5 MB MP3
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Preprocessed    │  13 MB WAV (16kHz Mono)
│  Audio           │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Speaker         │  Segments with timestamps
│  Timeline        │  [
└────────┬─────────┘    {"speaker": "A", "start": 0, "end": 5},
         │              {"speaker": "B", "start": 5, "end": 8}
         │            ]
         ▼
┌──────────────────┐
│  Transcript      │  [
│  with            │    {"speaker": "A", "text": "Hello...", "signals": [...]},
│  Signals         │    {"speaker": "B", "text": "I need...", "signals": [...]}
└────────┬─────────┘  ]
         │  
         ▼
┌──────────────────┐
│  Role-Labeled    │  [
│  Transcript      │    {"speaker": "Agent", "role": "Customer Service Agent", ...},
└────────┬─────────┘    {"speaker": "Customer", "role": "Customer", ...}
         │            ]
         ▼
┌──────────────────┐
│  Emotion-        │  [
│  Enhanced        │    {"speaker": "Agent", "text": "...", 
│  Transcript      │     "audio_emotion": "joy", "confidence": 0.79, ...},
└────────┬─────────┘    {"speaker": "Customer", "text": "...",
         │                "audio_emotion": "anger", "confidence": 0.74, ...}
         │            ]
         ▼
┌──────────────────┐
│  Final Files     │  • audio_diarized_with_emotions.txt (5 KB)
│  TXT + JSON      │  • audio_diarized_with_emotions.json (30 KB)
└──────────────────┘
```

## Model Files Location Map

```
LAYER_1/
│
├── 🎙️ PREPROCESSING
│   └── resemble-enhance/
│       └── resemble_enhance/
│           ├── denoiser/       (Background noise removal)
│           └── enhancer/       (Audio quality improvement)
│
├── 👥 DIARIZATION
│   └── models/pyannote/
│       ├── segmentation-3.0/
│       │   └── pytorch_model.bin         (345 MB)
│       └── wespeaker-voxceleb-resnet34-LM/
│           └── pytorch_model.bin         (89 MB)
│
├── 🗣️ TRANSCRIPTION
│   └── models/whisper/openai/whisper-large-v3/
│       └── model.safetensors             (3.0 GB)
│
├── 🎭 ROLE IDENTIFICATION
│   └── ../skill_implementation/models/
│       └── Meta-Llama-3.1-8B-Instruct-Q8_0.gguf  (8.5 GB)
│
└── 😊 EMOTION DETECTION
    └── audio_emotion_detection_enhanced/models/
        └── Audio2Emotion-v3.0/
            └── network.onnx              (1.18 GB)

Total Model Size: ~11.3 GB
```

## Processing Timeline (2-minute audio)

```
Time      Stage                           Status
───────────────────────────────────────────────────────────────
00:00     📁 Load audio file              ████████████████ 100%
00:02     🎙️ Preprocessing (if enabled)   ████████████████ 100%
00:07     👥 Diarization                  ████████████████ 100%
00:37     🗣️ Transcription                ████████████████ 100%
00:47     🎭 Role identification          ████████████████ 100%
01:27     😊 Emotion detection            ████████████████ 100%
01:30     💾 Save final outputs           ████████████████ 100%
───────────────────────────────────────────────────────────────
Total: ~90 seconds
```

## Configuration Summary

| Component | Device | Memory | Precision |
|-----------|--------|--------|-----------|
| Resemble-Enhance | GPU | 2 GB | FP32 |
| Pyannote Diarization | GPU | 3 GB | FP32 |
| Whisper | GPU | 6 GB | FP16 |
| Llama-3.1 | GPU/CPU | 8 GB | INT8 |
| Audio2Emotion | GPU/CPU | 2 GB | FP32 |

**Environment:** Conda (calltone)  
**Python:** 3.11  
**CUDA:** Required for GPU acceleration  
**Total Peak Memory:** ~8 GB GPU + ~4 GB RAM
