"""FastAPI entrypoint for the CallTone model server.

The real endpoint implementations live in separate modules:
  - ``jobs.py``              — in-memory job store
  - ``pipeline_adapter.py``  — subprocess wrapper around ``models/run_full_pipeline.py``
  - ``auth.py``              — bearer-token + IP allowlist middleware

D-3 (this file) only wires the app together and exposes ``/v1/health``.
D-4 will add ``/v1/analyze``, ``/v1/jobs/{id}``, ``/v1/jobs/{id}/result``.
"""

from __future__ import annotations

import logging
import os
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .auth import install_auth_middleware
from .endpoints import router as v1_router
from .jobs import JobStore

log = logging.getLogger("calltone.model_server")


def _gpu_available() -> bool:
    """Cheap probe — no torch import, just ``nvidia-smi``.

    Keeps the healthcheck dependency-light so Vast's probe can hit /v1/health
    before the heavyweight CUDA wheels finish initialising.
    """
    return shutil.which("nvidia-smi") is not None


def _prewarm_models() -> None:
    """Warm the OS page cache for model weights at startup.

    Each /v1/analyze spawns a fresh Python subprocess for VRAM/crash isolation
    (see pipeline_adapter.py), so we cannot share loaded model state across
    jobs. What we *can* share is the OS file page cache: reading the model
    files at boot fills the cache, so the subprocess's cold-load drops from
    multi-minutes (disk I/O bound) to seconds (RAM-resident files).

    Set CALLTONE_PREWARM=0 to skip (CI/tests).
    """
    if os.getenv("CALLTONE_PREWARM", "1") == "0":
        log.info("model_server.prewarm.skipped", extra={"event": "prewarm_skipped"})
        return
    # Real cache locations on Vast: faster-whisper + Audio2Emotion + pyannote
    # are HF Hub downloads; LLaMA + resemble-enhance live under /opt/calltone.
    hf_home = os.getenv("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    hf_hub = os.path.join(hf_home, "hub")
    targets = [
        os.path.join(hf_hub, "models--Systran--faster-whisper-large-v3"),
        os.path.join(hf_hub, "models--pyannote--segmentation-3.0"),
        os.path.join(hf_hub, "models--pyannote--wespeaker-voxceleb-resnet34-LM"),
        os.path.join(hf_hub, "models--nvidia--Audio2Emotion-v3.0"),
        os.getenv("CALLTONE_SKILL_MODELS_DIR", "/app/models/skill_implementation/models"),
        os.getenv("CALLTONE_LAYER1_MODELS_DIR", "/app/models/LAYER_1/models/resemble-enhance"),
        "/opt/calltone/models/skill_implementation/models",
        "/opt/calltone/models/LAYER_1/models/resemble-enhance",
    ]
    total_bytes = 0
    for root in targets:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                fpath = os.path.join(dirpath, name)
                try:
                    with open(fpath, "rb", buffering=1024 * 1024) as f:
                        while f.read(1024 * 1024):
                            pass
                    total_bytes += os.path.getsize(fpath)
                except OSError as exc:
                    log.debug(
                        "model_server.prewarm.read_failed",
                        extra={"event": "prewarm_read_failed", "path": fpath, "err": str(exc)},
                    )
    log.info(
        "model_server.prewarm.ok",
        extra={"event": "prewarm_ok", "bytes": total_bytes},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("model_server.startup", extra={"event": "startup"})
    _prewarm_models()
    yield
    log.info("model_server.shutdown", extra={"event": "shutdown"})


def create_app() -> FastAPI:
    app = FastAPI(
        title="CallTone Model Server",
        version="0.1.0",
        docs_url="/docs" if os.getenv("MODEL_SERVER_DEBUG") == "1" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    # Set up state *before* lifespan fires so TestClient (which skips lifespan
    # by default) still has access to the job store.
    app.state.jobs = JobStore()
    install_auth_middleware(app)
    app.include_router(v1_router)

    @app.get("/v1/health")
    def health():
        return JSONResponse(
            {
                "ok": True,
                "gpu_available": _gpu_available(),
                "model_cache_warm": os.path.isdir("/root/.cache/calltone/models"),
                "version": "0.1.0",
            }
        )

    return app


app = create_app()
