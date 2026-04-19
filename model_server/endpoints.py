"""HTTP endpoints for the model server (D-4).

Wired into ``main.create_app``. Routes:

    POST /v1/analyze                  multipart(audio) → {job_id, eta_seconds}
    GET  /v1/jobs/{job_id}            status + progress
    GET  /v1/jobs/{job_id}/result     full QA report (only when done)

Concurrency: the ``JobStore`` single-slot guard enforces one job in flight.
``/v1/analyze`` returns **409** when busy.

Pipeline dispatch: the subprocess runs on a worker thread via
``asyncio.to_thread`` so ``/v1/jobs/{id}`` stays responsive while the
pipeline progresses through its stages.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from .jobs import Job, JobStore
from .pipeline_adapter import (
    classify_line,
    load_result_json,
    run_pipeline_blocking,
)

log = logging.getLogger("calltone.model_server.endpoints")

router = APIRouter(prefix="/v1")

# Accept the audio formats LAYER 1 supports. Kept as a set so we can reject
# early instead of booting the pipeline on a PDF someone uploaded by mistake.
ALLOWED_AUDIO_CTYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/flac",
    "audio/x-flac",
    "audio/ogg",
    "application/octet-stream",  # curl default; inspected by the pipeline
}

# Guard rails — keep the service from being used as a generic file store.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB (≈ 60-min WAV at 16-bit mono 44.1k)
PIPELINE_TIMEOUT_SECONDS = 900  # 15 minutes — well above the 3-min SLA
ETA_SECONDS = 180  # rough estimate surfaced to clients


# ── dispatch ───────────────────────────────────────────────────────────────


def _worker(
    *,
    store: JobStore,
    job_id: str,
    audio_path: Path,
    company: str,
    speakers: int | None,
    output_dir: Path,
) -> None:
    """Run the pipeline and funnel progress into the store."""

    def on_line(line: str) -> None:
        hit = classify_line(line)
        if hit is None:
            return
        status, pct = hit
        store.update(job_id, status=status, progress_pct=pct)  # type: ignore[arg-type]

    # First status bump — tells clients we picked the job up.
    store.update(job_id, status="denoising", progress_pct=1)

    try:
        rc = run_pipeline_blocking(
            audio_path=audio_path,
            company=company,
            output_dir=output_dir,
            speakers=speakers,
            timeout_seconds=PIPELINE_TIMEOUT_SECONDS,
            on_line=on_line,
        )
    except Exception as exc:
        log.exception("model_server.pipeline.crash", extra={"job_id": job_id})
        store.update(job_id, status="failed", error=f"pipeline crashed: {exc}")
        return
    finally:
        # Always release the slot so new jobs can start, even after a crash.
        store.release_slot(job_id)

    if rc != 0:
        store.update(
            job_id,
            status="failed",
            error=f"pipeline exited with code {rc}",
        )
        return

    result = load_result_json(output_dir)
    if result is None:
        store.update(
            job_id,
            status="failed",
            error="pipeline completed but no result JSON was produced",
        )
        return

    store.update(job_id, status="done", progress_pct=100, result=result)


# ── routes ─────────────────────────────────────────────────────────────────


@router.post("/analyze")
async def analyze(
    request: Request,
    audio: UploadFile = File(...),
    company: str = Form(...),
    speakers: int | None = Form(None),
):
    store: JobStore = request.app.state.jobs

    if audio.content_type and audio.content_type not in ALLOWED_AUDIO_CTYPES:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported content-type: {audio.content_type}",
        )

    # Save upload to a dedicated tempdir we fully own — pipeline wants a
    # real filesystem path, and we also need to garbage-collect it later.
    workdir = Path(tempfile.mkdtemp(prefix="calltone_job_"))
    suffix = Path(audio.filename or "upload.wav").suffix or ".wav"
    audio_path = workdir / f"input{suffix}"
    output_dir = workdir / "results"
    output_dir.mkdir(exist_ok=True)

    total = 0
    with audio_path.open("wb") as fh:
        while True:
            chunk = await audio.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                shutil.rmtree(workdir, ignore_errors=True)
                raise HTTPException(status_code=413, detail="audio too large")
            fh.write(chunk)

    if total == 0:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="empty upload")

    meta = {
        "filename": audio.filename or "unknown",
        "bytes": total,
        "company": company,
    }
    job: Job | None = store.acquire_slot(meta=meta)
    if job is None:
        shutil.rmtree(workdir, ignore_errors=True)
        return JSONResponse(
            {"detail": "another job is in flight", "retry_after_seconds": 30},
            status_code=409,
        )

    log.info(
        "model_server.analyze.accepted",
        extra={
            "event": "analyze_accepted",
            "job_id": job.id,
            "upload_filename": meta["filename"],
            "upload_bytes": meta["bytes"],
            "company": meta["company"],
        },
    )

    # Detached worker thread. We use ``threading.Thread`` instead of
    # ``asyncio.create_task`` because TestClient (and production uvicorn at
    # graceful shutdown) will wait for pending asyncio tasks, which defeats
    # the fire-and-forget contract.
    threading.Thread(
        target=_worker,
        kwargs={
            "store": store,
            "job_id": job.id,
            "audio_path": audio_path,
            "company": company,
            "speakers": speakers,
            "output_dir": output_dir,
        },
        daemon=True,
        name=f"calltone-pipeline-{job.id[:8]}",
    ).start()

    return {"job_id": job.id, "eta_seconds": ETA_SECONDS}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, request: Request):
    store: JobStore = request.app.state.jobs
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return job.to_public()


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str, request: Request):
    store: JobStore = request.app.state.jobs
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    if job.status != "done":
        # 409 matches the "not ready yet" semantics; backend client retries
        # by polling /v1/jobs/{id} again.
        raise HTTPException(
            status_code=409,
            detail=f"job not ready (status={job.status})",
        )
    return {"job_id": job.id, "result": job.result}
