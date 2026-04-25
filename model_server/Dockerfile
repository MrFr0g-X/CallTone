# Base image carries CUDA 12.1 runtime + cuDNN. Matches torch+cu121 and
# the llama-cpp-python wheels we pin.
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3-pip \
        ffmpeg git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/bin/python

WORKDIR /app

# Server-tier deps (fast). ML-tier deps are layered in by
# setup_vast_instance.sh at boot so the image stays small.
COPY model_server/requirements.txt /tmp/server-reqs.txt
RUN pip install --upgrade pip && pip install -r /tmp/server-reqs.txt

# Copy the package + the pipeline it wraps.
COPY model_server /app/model_server
COPY models /app/models
COPY skill_implementation /app/skill_implementation

EXPOSE 8080

# Single worker on purpose — GPU VRAM is shared state.
CMD ["uvicorn", "model_server.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
