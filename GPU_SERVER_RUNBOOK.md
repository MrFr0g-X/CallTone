# CallTone — GPU Server Deployment Runbook

Target server: B200 GPU (179 GB VRAM), AMD EPYC 9575F 64-Core, 256 GB RAM, NVMe disk.

## Prerequisites

- Docker + Docker Compose installed
- NVIDIA Container Toolkit installed (`nvidia-ctk`)
- `nvidia-smi` works and shows the B200

## Step 1: Clone the repo

```bash
git clone https://github.com/MrFr0g-X/CallTone.git
cd CallTone
```

## Step 2: Download model weights

Models are NOT in the Docker image — they're mounted via volume.

```bash
# Create the mount directory
mkdir -p model-weights

# Option A: Use the download script (recommended)
pip install huggingface_hub   # if not already installed
python download_models.py --hf-token YOUR_HF_TOKEN

# Then copy/symlink the downloaded weights to model-weights/
cp -r models/LAYER_1/models model-weights/LAYER_1/models
cp -r models/skill_implementation/models model-weights/skill_implementation/models
cp -r models/LAYER_1/resemble-enhance/enhancer_stage2 model-weights/LAYER_1/resemble-enhance/enhancer_stage2
```

**What you need in `model-weights/`:**

```
model-weights/
├── LAYER_1/
│   ├── models/
│   │   ├── whisper/openai/whisper-large-v3/     (~4.5 GB)
│   │   ├── sensevoice/iic/SenseVoiceSmall/      (~893 MB)
│   │   ├── pyannote/
│   │   │   ├── speaker-diarization-3.1/
│   │   │   ├── segmentation-3.0/
│   │   │   └── wespeaker-resnet34-LM/
│   │   └── Audio2Emotion-v3.0/network.onnx      (~1.2 GB)
│   └── resemble-enhance/
│       └── enhancer_stage2/                      (~681 MB)
└── skill_implementation/
    └── models/
        └── Meta-Llama-3.1-8B-Instruct-Q8_0.gguf (~8.5 GB)
```

**Total: ~16 GB of model weights.**

## Step 3: Set environment variables

```bash
# Required: HuggingFace token (for pyannote model access at runtime)
export HF_TOKEN=hf_your_token_here

# Optional: change the default secret key
export SECRET_KEY=$(openssl rand -hex 32)
```

## Step 4: Build and run

```bash
# Build (takes ~15-20 min first time — compiles llama-cpp-python with CUDA)
docker compose build

# Start
docker compose up -d

# Watch logs
docker compose logs -f calltone
```

## Step 5: Verify

```bash
# Health check
curl http://localhost:8000/

# Should return: {"message": "CallTone API is running"}

# Check GPU is visible inside container
docker exec calltone python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0)}')"

# Check llama.cpp has CUDA
docker exec calltone python -c "from llama_cpp import Llama; print('llama-cpp OK')"
```

## Step 6: Use the app

Open `http://<server-ip>:8000` in a browser.

**Demo accounts** (seeded automatically):

| Role | Email | Password |
|------|-------|----------|
| Super Admin | admin@calltone.ai | Admin123! |
| QA | qa@calltone.ai | Qa123456! |
| Agent | agent1@calltone.ai | Agent123! |

**Demo flow for video recording:**
1. Login as QA (`qa@calltone.ai`)
2. View existing analyzed calls on the QA Dashboard
3. Click a call to see the full detail: transcript, scores, evidence, report
4. Go to Upload → drag an audio file → watch pipeline progress in real time
5. Login as Agent (`agent1@calltone.ai`) → see personal dashboard
6. Login as Admin (`admin@calltone.ai`) → see platform-wide dashboard, clients, team management

## Ports

| Port | Service |
|------|---------|
| 8000 | FastAPI API + React frontend |

## Troubleshooting

### "CUDA out of memory" during pipeline
Not expected on B200 (179 GB), but if it happens:
```bash
# Check VRAM usage
docker exec calltone nvidia-smi
```

### Pipeline fails to import
Check model weights are mounted correctly:
```bash
docker exec calltone ls /app/models/LAYER_1/models/whisper/openai/whisper-large-v3/
docker exec calltone ls /app/models/skill_implementation/models/
```

### Database issues
The SQLite DB is created on first run. To reset:
```bash
docker compose down -v   # removes volumes (DB + uploads)
docker compose up -d     # recreates everything fresh
```

### Rebuild after code changes
```bash
git pull
docker compose build --no-cache
docker compose up -d
```

## Architecture in Docker

```
Container (port 8000)
├── FastAPI (uvicorn, 1 worker)
│   ├── /api/*  → REST endpoints (auth, admin, QA, agent, upload, pipeline settings)
│   ├── /assets/* → Vite build output (JS/CSS bundles)
│   └── /*      → React SPA (index.html fallback)
├── Pipeline (multiprocessing.spawn per upload)
│   ├── Layer 1: denoise → transcribe → diarize → role ID → emotion
│   ├── Layer 2: 7-criterion QA scoring via LLM
│   └── Layer 3: report generation
└── Volumes
    ├── /app/models/LAYER_1/models/         → model weights (read-only)
    ├── /app/models/skill_implementation/models/ → GGUF LLM (read-only)
    ├── /app/backend/uploads/               → uploaded audio files
    └── /app/backend/calltone.db            → SQLite database
```
