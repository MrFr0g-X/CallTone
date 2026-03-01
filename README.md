# CallTone — AI-Powered QA for Customer Service Calls

Automated quality assurance system that processes call recordings end-to-end: raw audio in, structured QA report out. Replaces manual QA (2-5% coverage) with 100% call analysis. Fully offline — no cloud APIs.

## Architecture

```
Raw Audio (MP3/WAV)
    |
    v
LAYER 1 — Audio Intelligence Pipeline
  Enhancement -> Diarization -> Transcription -> Role ID -> Emotion Detection
  Output: JSON with speakers, roles, emotions, behavioral signals
    |
    v
LAYER 2 — QA Scoring Engine
  Scores calls on 4 dimensions using LLM skill (Llama 3.1 8B)
  Output: qa_report.json with scores, confidence, evidence
    |
    v
LAYER 3 — REST API (FastAPI)
  11 endpoints serving dashboards + call detail data
    |
    v
calltone-UI — React Frontend
  QA Dashboard, Agent Dashboard, Admin Panel
```

## Project Structure

```
CallTone/
├── LAYER_1/                          # Audio processing pipeline
│   ├── pipeline.py                   # Main entry point
│   ├── pipeline/transcribe_diarize.py
│   ├── role_identification.py
│   ├── emotion_integration.py
│   └── audio_emotion_detection_enhanced/
├── LAYER_2/                          # QA scoring engine
│   ├── qa_scorer.py                  # Scores calls using LLM skill
│   └── test_determinism.py
├── LAYER_3/                          # REST API
│   └── api/
│       ├── main.py                   # FastAPI — 11 endpoints under /api
│       ├── demo_data.py              # Mock data + real L1 transformer
│       └── models.py                 # Pydantic schemas
├── skill_implementation/             # LLM skills framework
│   ├── skills/
│   │   ├── identify-call-roles/      # Speaker role identification
│   │   └── score-call-quality/       # QA scoring (4 dimensions)
│   └── skill_runtime/                # Framework runtime
├── calltone-UI/                      # React frontend
│   ├── src/pages/                    # QA, Agent, Admin dashboards
│   ├── src/services/api.ts           # API client
│   └── src/contexts/AuthContext.tsx   # Role-based auth
├── Test_audio/                       # Sample audio + pipeline outputs
├── config.py                         # Portable path resolution
└── download_models.py                # Downloads all models (~12.5 GB)
```

## Quick Start

### 1. Download models

```bash
pip install huggingface-hub
python download_models.py --list
python download_models.py
```

### 2. Run the full pipeline

```bash
cd LAYER_1
python pipeline.py --input /path/to/call.mp3
```

### 3. Run QA scoring

```bash
python LAYER_2/qa_scorer.py Test_audio/bad_cs_results/bad_cs_denoised_diarized_with_emotions.json
```

### 4. Start the API + UI

```bash
# Terminal 1 — API (port 8000)
cd LAYER_3/api
pip install -r requirements.txt
uvicorn main:app --reload

# Terminal 2 — UI (port 8080)
cd calltone-UI
npm install
npm run dev
```

Open `http://localhost:8080` and login:
- `qa@calltone.tech` — QA Dashboard
- `agent@calltone.tech` — Agent Dashboard
- `admin@calltone.tech` — Admin Panel

## QA Dimensions

| Dimension | Weight | Scale | Good Score |
|-----------|--------|-------|------------|
| Politeness & Tone | 15% | 1-5 | 4+ |
| Empathy | 10% | 1-5 | 4+ |
| Conflict Detection | 15% | 0 or 1 | 0 (no conflict) |
| Issue Resolution | 5% | 0 or 1 | 1 (resolved) |

Overall score normalized to 0-100. Calls flagged when any dimension confidence < 0.7.

## Models

| Model | Size | Purpose |
|-------|------|---------|
| Meta-Llama-3.1-8B-Instruct | ~8 GB | Role ID + QA scoring (GGUF) |
| SenseVoiceSmall | ~893 MB | Transcription |
| resemble-enhance | ~681 MB | Audio denoising |
| Audio2Emotion-v3.0 | ~1.2 GB | Emotion detection (ONNX) |
| pyannote segmentation + wespeaker | ~1 GB | Speaker diarization |

## Requirements

- Python 3.9+
- Node.js 18+ (for UI)
- CUDA optional (recommended for speed)
- ~15 GB disk for models
- 8 GB RAM minimum, 16 GB recommended

---

Graduation project — CSAI 498/499, Zewail City of Science and Technology
