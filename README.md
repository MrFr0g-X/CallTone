# CallTone

AI-powered quality assurance for customer service calls. Takes a raw call recording and produces a scored QA report grounded in the company's own written policies. Fully offline, no cloud APIs.

Built as a graduation project for CSAI 498/499 at Zewail City of Science and Technology, Spring 2026.

## What It Does

A QA manager writes their company's call handling policies in plain text. CallTone handles the rest:

1. Processes the audio (denoising, transcription, speaker identification, emotion detection)
2. Scans the transcript for prompt injection attacks
3. Rates the call on 7 criteria using the company's policies as ground truth
4. Generates a professional report explaining every score

Manual QA typically covers 2-5% of calls. This system handles 100%.

## Architecture

```
Raw Audio (MP3/WAV/FLAC)
        |
  [ LAYER 1 ]  Audio Processing
  resemble-enhance -> pyannote diarization -> SenseVoice transcription
  -> Llama role identification -> Audio2Emotion detection
        |
  Structured Transcript JSON
  (speaker roles, emotions, behavioral signals)
        |
  [ Security Gate ]  Prompt Injection Scan
  (static regex + LLM sandbox detector)
        |
  [ LAYER 2 ]  Call Rating
  7 criteria scored against company policy via context graph
        |
  [ LAYER 3 ]  Report Generation
  LaTeX reports (simple score table + narrative explanations)
        |
  [ Backend ]  FastAPI REST API + PostgreSQL
  24 endpoints, JWT auth, role-based access
        |
  [ Frontend ]  React + TypeScript
  QA Dashboard, Agent Dashboard, Admin Panel, Upload page
```

## Project Structure

```
CallTone/
├── models/
│   ├── run_full_pipeline.py              # End-to-end: L1 -> L2 -> L3
│   ├── LAYER_1/                          # Audio processing pipeline
│   │   ├── pipeline/transcribe_diarize.py
│   │   ├── role_identification.py
│   │   ├── emotion_integration.py
│   │   └── models/                       # Downloaded model weights
│   ├── LAYER_2/                          # QA scoring engine
│   │   ├── pipeline.py                   # Rating pipeline (7 criteria)
│   │   ├── company_context/              # Company policy storage
│   │   ├── context_graph/                # Zettelkasten-style knowledge graph
│   │   ├── consensus/                    # Deterministic scoring runner
│   │   ├── security/                     # Injection scanner
│   │   └── change_management/            # Policy update tracking
│   ├── LAYER_3/                          # Report generation
│   │   ├── pipeline.py
│   │   └── renderers/                    # LaTeX simple + narrative
│   └── skill_implementation/             # LLM skills framework
│       ├── skills/                       # 12 prompt-only skill definitions
│       ├── skill_runtime/                # Loader, validator, runner
│       └── runner/run_skill.py           # CLI interface
├── backend/                              # FastAPI REST API
│   ├── app/
│   │   ├── main.py                       # 24 endpoints, upload + pipeline
│   │   ├── models.py                     # SQLAlchemy ORM (8 tables)
│   │   ├── database.py                   # PostgreSQL config
│   │   ├── security.py                   # JWT + bcrypt auth
│   │   └── seed_data.py                  # Sample data loader
│   └── requirements.txt
├── calltone-UI/                          # React 18 + Vite + TypeScript
│   ├── src/
│   │   ├── pages/                        # All page components
│   │   ├── components/                   # Shared UI components
│   │   ├── services/api.ts              # Typed API client
│   │   └── contexts/AuthContext.tsx      # Auth state management
│   └── package.json
├── config.py                             # Path resolution
└── download_models.py                    # Downloads all model weights
```

## The 7 Rating Criteria

| # | Criterion | Weight | What It Measures |
|---|-----------|--------|------------------|
| 1 | Script Compliance | 25% | Did the agent follow greeting, verification, closing scripts? |
| 2 | Factual Accuracy | 25% | Was product/policy information correct? |
| 3 | Politeness & Tone | 15% | Professional and respectful communication? |
| 4 | Empathy | 10% | Acknowledged customer feelings before problem-solving? |
| 5 | Conflict Detection | 15% | Recognized and de-escalated tension? |
| 6 | Issue Resolution | 5% | Was the problem actually solved? |
| 7 | Overall Severity | 5% | Holistic assessment of call quality |

Scores use a 5-point rubric (0/25/50/75/100) with evidence-before-score to reduce hallucination. The weighted sum produces the final 0-100 score.

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- PostgreSQL 17+
- CUDA GPU recommended (works on CPU, just slower)
- ~15 GB disk for model weights

### 1. Set up the database

```bash
# Create the database
psql -U postgres -c "CREATE DATABASE calltone_db;"

# Configure connection
cd backend
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

### 2. Start the backend

```bash
cd backend
pip install -r requirements.txt
python -m app.seed_data          # Populate sample data
uvicorn app.main:app --port 8000
```

### 3. Start the frontend

```bash
cd calltone-UI
npm install
npm run dev
```

### 4. Log in

Open `http://localhost:5173` and use one of the seeded accounts:

| Email | Password | Role |
|-------|----------|------|
| admin@calltone.ai | Admin123! | Super Admin |
| qa@calltone.ai | Qa123456! | QA Analyst |
| agent1@calltone.ai | Agent123! | Agent |

### 5. Run the full AI pipeline (on GPU machine)

```bash
cd models
conda run -n main python run_full_pipeline.py path/to/call.wav --company "CompanyName"
```

Or upload audio directly through the web UI at `/qa/upload`.

## Skills Framework

The system uses 12 prompt-only LLM skills. Skills contain only prompts and config — no logic allowed. This is enforced by a validator that rejects any skill with loops, conditionals, imports, or function calls.

| Skill | Purpose |
|-------|---------|
| identify-call-roles | Label speakers as Agent or Customer |
| rate-script-compliance | Score against call scripts |
| rate-factual-accuracy | Score product/policy accuracy |
| rate-politeness-tone | Score communication tone |
| rate-empathy | Score emotional acknowledgment |
| rate-conflict-detection | Score de-escalation handling |
| rate-issue-resolution | Score problem resolution |
| rate-overall-severity | Holistic severity assessment |
| detect-prompt-injection | Identify manipulation attempts in transcripts |
| format-company-context | Optimize policy text for LLM consumption |
| process-context-change | Semantic equivalence check for policy updates |
| generate-call-report | Generate narrative report explanations |

All skills run with deterministic decoding: temperature=0.0, top_p=1.0, seed=12345.

## Security

Transcripts are untrusted input — a caller could try to manipulate the AI evaluator. The system uses three layers of defense:

1. **Static scanner** — regex patterns catch explicit override commands, jailbreak keywords, injected system markers
2. **LLM sandbox detector** — a separate Llama instance analyzes the transcript for manipulation attempts (the transcript is wrapped in XML data tags so it can't inject instructions)
3. **Structural sandboxing** — during rating, the transcript is wrapped in delimiters that tell the rating LLM it's data, not instructions

Blocked calls never reach the scoring pipeline.

## Models

| Model | Size | Purpose |
|-------|------|---------|
| Meta-Llama-3.1-8B-Instruct | ~8 GB | Role ID, scoring, reports (GGUF Q8) |
| SenseVoiceSmall | ~893 MB | Speech-to-text transcription |
| resemble-enhance | ~681 MB | Audio denoising |
| Audio2Emotion-v3.0 | ~1.2 GB | Per-utterance emotion detection (ONNX) |
| pyannote segmentation-3.0 | ~500 MB | Speaker segmentation |
| pyannote wespeaker-resnet34-LM | ~500 MB | Speaker embedding |

Download all weights:
```bash
python download_models.py
```

## What's Implemented

- [x] Full audio processing pipeline (Layer 1)
- [x] 7-criterion QA scoring with company policy context (Layer 2)
- [x] LaTeX report generation — simple and narrative modes (Layer 3)
- [x] Zettelkasten-style context graph with semantic tag retrieval
- [x] 3-layer prompt injection defense
- [x] Policy change management with semantic equivalence checking
- [x] FastAPI backend with 24 endpoints and PostgreSQL
- [x] JWT authentication with 6 roles
- [x] Admin panel (clients, team management, permissions, activity log)
- [x] QA dashboard with call list, search, filters, 7-dimension detail view
- [x] Agent dashboard with score cards and performance trends
- [x] Audio upload with real-time pipeline progress tracking
- [x] Deterministic scoring (same input = same output)

---

Zewail City of Science and Technology — CSAI 498/499, Spring 2026
