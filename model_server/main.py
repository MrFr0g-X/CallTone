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


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("model_server.startup", extra={"event": "startup"})
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
