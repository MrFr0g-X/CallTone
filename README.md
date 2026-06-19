# CallTone

AI-powered quality assurance for customer-service calls. Takes a raw call recording and produces a scored, evidence-backed QA report grounded in the company's own written policies. Runs fully offline on open models — no cloud AI APIs.

Built as a graduation project for CSAI 498/499 at Zewail City of Science and Technology, Spring 2026. Deployed live at **[calltone.tech](https://calltone.tech)** (API: `api.calltone.tech`).

## What It Does

A QA manager writes their company's call-handling policies in plain text. CallTone handles the rest:

1. Processes the audio (denoising, speaker diarization, transcription, role identification, emotion detection)
2. Scans the transcript for prompt-injection attempts
3. Rates the call on 7 weighted criteria using the company's policies as ground truth, attaching an evidence quote and a confidence value to every score
4. Flags low-confidence calls for human review and generates a narrative report explaining every score

Manual QA typically covers 2–5% of calls. CallTone scores 100% — reproducibly.

## Architecture

A three-layer inference pipeline, served behind a three-tier deployment. No model is trained; the system composes pre-trained open models.

```
Raw Audio (MP3/WAV/FLAC)
        |
  [ LAYER 1 ]  Audio Intelligence
  resemble-enhance (SNR-gated) -> pyannote 3.1 diarization
  -> faster-whisper (Whisper large-v3, CTranslate2) transcription
  -> Qwen3-8B role identification -> Audio2Emotion v3 emotion
        |
  Structured transcript JSON (speaker roles, emotions, behavioral signals)
        |
  [ Security Gate ]  Prompt-Injection Scan (static regex + LLM detector, fail-closed)
        |
  [ LAYER 2 ]  QA Scoring
  Qwen3-8B (Q4_K_M, llama.cpp), 7 weighted dimensions, evidence + confidence,
  low-confidence (<0.70) -> human-review flag, selective "thinking"
        |
  [ LAYER 3 ]  Report Generation (narrative + LaTeX export, opt-in)
        |
  Structured QA report (JSON + narrative)
```

### Deployment (three tiers)

```
Tier 1  Web UI            React + Vite, static host
   | HTTPS
Tier 2  Backend + DB      FastAPI + PostgreSQL 16 (VM), JWT, RBAC, Caddy TLS, systemd
   | SSH reverse tunnel (autossh) + bearer token + IP allow-list
Tier 3  GPU Model Server  Qwen3 / faster-whisper / pyannote / Audio2Emotion (RTX 4090, 24 GB)
```

The GPU tier is never exposed to the public internet; the backend reaches it only through a private SSH reverse tunnel. Capacity scales by adding GPUs behind a durable, tenant-fair job queue.

## Project Structure

```
CallTone/
├── models/
│   ├── run_full_pipeline.py              # End-to-end: L1 -> L2 -> L3
│   ├── LAYER_1/                          # Audio intelligence pipeline
│   │   ├── pipeline/transcribe_diarize.py
│   │   ├── role_identification.py
│   │   ├── emotion_integration.py
│   │   └── models/                       # Downloaded model weights
│   ├── LAYER_2/                          # QA scoring engine
│   │   ├── pipeline.py                   # Rating pipeline (7 dimensions)
│   │   ├── company_context/              # Company policy storage
│   │   ├── context_graph/                # Zettelkasten-style knowledge graph
│   │   ├── consensus/                    # Deterministic scoring runner
│   │   ├── security/                     # Prompt-injection scanner
│   │   └── change_management/            # AI-gated policy change tickets
│   ├── LAYER_3/                          # Report generation
│   │   ├── pipeline.py
│   │   └── renderers/                    # LaTeX simple + narrative
│   ├── model_server/                     # GPU model server (FastAPI, bearer-token auth)
│   └── skill_implementation/             # LLM skills framework
│       ├── skills/                       # prompt-only skill definitions
│       ├── skill_runtime/                # loader, validator, runner
│       └── runner/run_skill.py           # CLI interface
├── backend/                              # FastAPI REST API (~30 endpoints)
│   ├── app/
│   │   ├── main.py                       # auth, upload, queue, appeals, health
│   │   ├── models.py                     # SQLAlchemy ORM (multi-tenant schema)
│   │   ├── model_client.py               # talks to the GPU model server
│   │   ├── database.py                   # PostgreSQL config
│   │   ├── security.py                   # JWT + bcrypt + capability RBAC
│   │   └── seed_data.py                  # Sample data loader
│   └── requirements.txt
├── calltone-UI/                          # React + Vite + TypeScript
│   ├── src/{pages,components,services,contexts}
│   └── package.json
├── config.py                             # Path resolution
└── download_models.py                    # Downloads all model weights
```

## The 7 Rating Dimensions

| # | Dimension | Weight | What It Measures |
|---|-----------|--------|------------------|
| 1 | Script Compliance | 0.25 | Did the agent follow greeting, verification, closing scripts? |
| 2 | Factual Accuracy | 0.25 | Was product/policy information correct? |
| 3 | Politeness & Tone | 0.15 | Professional and respectful communication? |
| 4 | Conflict Detection | 0.15 | Recognized and de-escalated tension? |
| 5 | Empathy | 0.10 | Acknowledged customer feelings before problem-solving? |
| 6 | Issue Resolution | 0.05 | Was the problem actually solved? |
| 7 | Overall Severity | 0.05 | Holistic assessment of call quality |

Each dimension is scored on a 5-point rubric with **evidence-before-score** to curb hallucination; the weighted aggregate produces the final **0–100** score and a letter grade. Any dimension scored with **confidence < 0.70** flags the whole call for human review.

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- PostgreSQL 16+
- CUDA GPU recommended (runs on CPU, just slower); ~15 GB disk for model weights

### 1. Set up the database

```bash
psql -U postgres -c "CREATE DATABASE calltone_db;"
cd backend
cp .env.example .env          # set DB URL, SECRET_KEY, model-server token/URL
```

### 2. Start the backend

```bash
cd backend
pip install -r requirements.txt
python -m app.seed_data        # populate sample data
uvicorn app.main:app --port 8000
```

### 3. Start the frontend

```bash
cd calltone-UI
npm install
npm run dev
```

### 4. Log in

Open `http://localhost:5173` and use a seeded account:

| Email | Password | Role |
|-------|----------|------|
| admin@calltone.ai | Admin123! | Super Admin |
| qa@calltone.ai | Qa123456! | QA Analyst |
| agent1@calltone.ai | Agent123! | Agent |

### 5. Run the full AI pipeline (on the GPU machine)

```bash
cd models
python run_full_pipeline.py path/to/call.wav --company "CompanyName"
```

Or upload audio directly through the web UI.

## Skills Framework

The system uses **prompt-only** LLM skills: skill files contain only prompts and config — **no control logic** (no loops, conditionals, imports, or function calls), enforced by a validator. All logic lives in a separate runtime. This is the basis of the determinism and injection-resistance guarantees.

Representative skills: `identify-call-roles`, the seven `rate-*` scoring skills, `detect-prompt-injection`, `format-company-context`, `process-context-change`, and `generate-call-report`.

**Determinism contract:** temperature 0, top-p 1.0, greedy decoding, fixed seed. Verified empirically — two independent end-to-end runs of the same call produced byte-identical transcripts, identical emotion labels, and identical scores on all seven dimensions. Scoring uses **selective thinking**: only the highest-weight dimensions (script compliance, factual accuracy, conflict detection) reason before scoring; the rest score directly to save latency.

## Security & Governance

Transcripts and company context are untrusted input that flows into LLM prompts. Defense is layered and enforced server-side:

1. **Prompt-injection scanner** — fast static pattern matcher plus an LLM detector on the model server; transcripts are screened before scoring and context edits before they are applied. If the detector is unreachable, the system **fails closed** (holds the edit / blocks the call) rather than trusting unverified text.
2. **Capability-based RBAC** — 6 roles map to fine-grained capabilities; every endpoint asserts the capability it needs (the frontend only mirrors this cosmetically).
3. **Multi-tenant isolation** — every query is filtered by the caller's company; cross-tenant access returns HTTP 403.
4. **Transport / inter-tier** — JWT (bcrypt), per-IP rate limiting, security headers, Caddy TLS; GPU reached only over SSH + bearer token (constant-time compare) + IP allow-list.

**Human-in-the-loop:** agents can appeal a flagged or poorly-graded call; a QA reviewer upholds or overturns it. An overturn never overwrites the AI score — the human decision is stored alongside it with a "human-reviewed" marker (full audit trail). Company-context edits are submitted as **AI-gated change tickets**: safe edits are auto-applied (with a version bump, mirrored to the model server), injections are auto-declined.

## Models

| Model | Purpose | Format / Notes |
|-------|---------|----------------|
| Qwen3-8B (Q4_K_M) | Role ID + QA scoring + injection detection | GGUF via llama.cpp, ~5 GB VRAM, selective thinking |
| faster-whisper (Whisper large-v3) | Transcription (ASR) | CTranslate2 engine |
| pyannote 3.1 (segmentation + embedding) | Speaker diarization | PyTorch, local snapshots |
| NVIDIA Audio2Emotion v3.0 | Speech emotion (6 classes) | ONNX — license-restricted, treated as replaceable |
| resemble-enhance | Denoise / enhance | applied only when SNR is low |

> The earlier stack used Llama 3.1 8B (Q8) and SenseVoice; the production system migrated to Qwen3-8B and faster-whisper (see the thesis for the rationale).

Download all weights:
```bash
python download_models.py        # pyannote needs an accepted HF license + HF_TOKEN
```

## Results (measured)

- **Transcription WER:** 10.56% plain / **4.09% normalized** (full pipeline vs an independent 445-word human reference); ASR-only 12.36% / 5.82%. Beats the 20% MVP and 8% production targets.
- **Speed:** real-time factor **0.24** (~124 s avg per call), ~2× faster than target.
- **Scaling:** near-linear — 2 GPUs ≈ **2.2×** throughput; 16 concurrent calls, **0 failures**, flat VRAM (per-pipeline peak 23.2 / 24 GB).
- **Tests:** **188** automated tests under CI (142 backend/pipeline + 22 model-server + 24 frontend).
- **Determinism:** identical input → byte-identical output.

## What's Implemented

- [x] Audio intelligence pipeline — Layer 1 (denoise, diarize, transcribe, role-ID, emotion)
- [x] 7-dimension weighted QA scoring with company-policy context — Layer 2
- [x] Narrative + LaTeX report generation (opt-in) — Layer 3
- [x] Zettelkasten-style context graph with semantic tag retrieval
- [x] Prompt-injection defense (static + LLM, fail-closed)
- [x] AI-gated company-context change tickets
- [x] Agent appeals with human-in-the-loop review (AI score preserved)
- [x] FastAPI backend (~30 endpoints), PostgreSQL, durable tenant-fair job queue
- [x] JWT auth + capability-based RBAC (6 roles), multi-tenant isolation, usage quota
- [x] Three-tier production deployment (static UI · FastAPI+Postgres VM · GPU model server over SSH)
- [x] QA / Agent / Admin dashboards, audio upload with live progress
- [x] Deterministic scoring (same input = same output), 188 tests under CI

## Future Work

Formal human–AI scoring-agreement study (target >60% agreement), a larger labeled evaluation set, a permissively licensed emotion model, multilingual support, and managed observability (Prometheus/Grafana) with autoscaling.

---

Zewail City of Science and Technology — CSAI 498/499, Spring 2026
