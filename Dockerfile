# ── CallTone Production Dockerfile ──────────────────────────────────────────
# Single container: FastAPI (backend + GPU pipeline) + built React frontend.
# Models are mounted via volume — NOT baked into the image.
#
# Build:   docker build -t calltone .
# Run:     docker compose up   (see docker-compose.yml)
# ────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build frontend ─────────────────────────────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /build
COPY calltone-UI/package.json calltone-UI/package-lock.json ./
RUN npm ci --ignore-scripts

COPY calltone-UI/ ./
# API calls go to the same origin in production (FastAPI serves both)
ENV VITE_API_BASE_URL=/api
RUN npm run build


# ── Stage 2: Python + CUDA (devel for compiling llama-cpp-python) ───────────
FROM nvidia/cuda:13.2.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DS_BUILD_OPS=0 \
    TOKENIZERS_PARALLELISM=false \
    HF_HUB_OFFLINE=1

# System deps (ffmpeg for torchaudio, libsndfile for soundfile, git for pyannote)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    ffmpeg libsndfile1 git curl build-essential cmake \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

# ── Python dependencies (install in stages for better caching) ──────────────

# PyTorch + torchaudio (CUDA 12.4)
RUN pip install --no-cache-dir \
    torch==2.5.1+cu124 torchaudio==2.5.1+cu124 \
    --index-url https://download.pytorch.org/whl/cu124

# Backend deps
COPY backend/requirements.txt /tmp/backend-req.txt
RUN pip install --no-cache-dir -r /tmp/backend-req.txt

# Pipeline deps (Layer 1)
RUN pip install --no-cache-dir \
    transformers accelerate pyannote.audio lightning-fabric \
    huggingface_hub sentencepiece \
    soundfile librosa scipy numpy resampy \
    omegaconf rich tabulate tqdm \
    onnxruntime-gpu \
    jinja2 pyyaml

# llama-cpp-python with CUDA offload (compiles from source)
# CMAKE_ARGS enables cuBLAS for GPU-accelerated LLM inference
ENV CMAKE_ARGS="-DGGML_CUDA=on" \
    FORCE_CMAKE=1
RUN pip install --no-cache-dir "llama-cpp-python>=0.3.0" --verbose

# ── Copy application code ──────────────────────────────────────────────────

# Backend
COPY backend/ /app/backend/

# Models code (not weights — those are mounted via volume)
COPY models/ /app/models/

# Built frontend → backend/static/ (served by FastAPI SPA handler)
COPY --from=frontend-build /build/dist/ /app/backend/static/

# ── Runtime configuration ──────────────────────────────────────────────────

# Default env vars (override via docker-compose or -e flags)
ENV SECRET_KEY=change-me-in-production \
    CORS_ORIGINS=* \
    DEBUG=false

EXPOSE 8000

# Health check — hit the root endpoint
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Seed DB on first run, then start uvicorn
CMD ["sh", "-c", "\
    cd /app/backend && \
    python -m app.seed_data 2>/dev/null; \
    exec python -m uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 1 \
        --timeout-keep-alive 300 \
    "]
