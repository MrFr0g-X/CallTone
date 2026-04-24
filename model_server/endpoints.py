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
import os
import json
import shutil
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from .jobs import Job, JobStore
from .pipeline_adapter import (
    classify_line,
    load_result_json,
    run_pipeline_blocking,
)

log = logging.getLogger("calltone.model_server.endpoints")

router = APIRouter(prefix="/v1")

_MODEL_SERVER_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _MODEL_SERVER_DIR.parent
CONTEXTS_DIR = _REPO_ROOT / "models" / "LAYER_2" / "company_context" / "contexts"

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


def _env_timeout_seconds(name: str) -> int | None:
    """
    Parse an optional timeout env var.

    Unset, empty, zero, or negative means "no hard timeout". This lets long
    calls finish instead of being killed by an arbitrary server-side cap.
    """
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        log.warning("invalid timeout env %s=%r; disabling hard timeout", name, raw)
        return None
    return value if value > 0 else None


PIPELINE_TIMEOUT_SECONDS = _env_timeout_seconds("MODEL_SERVER_PIPELINE_TIMEOUT_SECONDS")
ETA_SECONDS = int(os.getenv("MODEL_SERVER_ETA_SECONDS", "180"))  # rough estimate surfaced to clients


def _context_slug(company: str) -> str:
    return str(company or "").strip().lower().replace(" ", "_")


def _context_path(company: str) -> Path:
    return CONTEXTS_DIR / f"{_context_slug(company)}.json"


def _load_context(company: str) -> dict | None:
    path = _context_path(company)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _list_contexts() -> list[dict]:
    contexts: list[dict] = []
    if not CONTEXTS_DIR.is_dir():
        return contexts
    for path in sorted(CONTEXTS_DIR.glob("*.json")):
        if path.stem.endswith("_graph") or path.stem.endswith("_backup"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        field_count = sum(
            1
            for value in data.values()
            if isinstance(value, str) and value.strip()
        )
        for section in ("script_compliance", "factual_accuracy", "behavioral"):
            if isinstance(data.get(section), dict):
                field_count += sum(1 for v in data[section].values() if isinstance(v, str) and v.strip())
        contexts.append(
            {
                "name": data.get("company_name") or path.stem,
                "slug": path.stem,
                "version": data.get("context_version") or data.get("version") or "1.0.0",
                "updated": data.get("last_updated", ""),
                "file": path.name,
                "fieldCount": field_count,
            }
        )
    return contexts


def _assert_context_exists(company: str) -> dict:
    context = _load_context(company)
    if context is None:
        available = ", ".join(c["name"] for c in _list_contexts()) or "none"
        raise HTTPException(
            status_code=400,
            detail=f"unknown company context: {company}. Available contexts: {available}",
        )
    return context


# ── dispatch ───────────────────────────────────────────────────────────────


def _worker(
    *,
    store: JobStore,
    job_id: str,
    audio_path: Path,
    company: str,
    speakers: int | None,
    output_dir: Path,
    report_mode: str = "narrative",
    asr_engine: str = "fasterwhisper",
    use_consensus: bool = False,
) -> None:
    """Run the pipeline and funnel progress into the store.

    Layer 3 defaults to narrative so completed calls always carry report
    artifacts. The backend still synthesizes UI JSON if rendering fails.
    """

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
            report_mode=report_mode,
            asr_engine=asr_engine,
            use_consensus=use_consensus,
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
    asr_engine: str = Form("fasterwhisper"),
    report_mode: str = Form("narrative"),
    use_consensus: bool = Form(False),
):
    store: JobStore = request.app.state.jobs

    asr_engine = str(asr_engine or "fasterwhisper").strip().lower()
    if asr_engine not in {"fasterwhisper", "sensevoice"}:
        raise HTTPException(status_code=400, detail="asr_engine must be fasterwhisper|sensevoice")
    report_mode = str(report_mode or "narrative").strip().lower()
    if report_mode not in {"none", "simple", "narrative", "both"}:
        raise HTTPException(status_code=400, detail="report_mode must be none|simple|narrative|both")

    if audio.content_type and audio.content_type not in ALLOWED_AUDIO_CTYPES:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported content-type: {audio.content_type}",
        )
    company = str(company or "").strip()
    if not company:
        raise HTTPException(status_code=400, detail="company is required")

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

    _assert_context_exists(company)

    meta = {
        "filename": audio.filename or "unknown",
        "bytes": total,
        "company": company,
        "asr_engine": asr_engine,
        "report_mode": report_mode,
        "use_consensus": bool(use_consensus),
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
            "asr_engine": meta["asr_engine"],
            "report_mode": meta["report_mode"],
            "use_consensus": meta["use_consensus"],
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
            "asr_engine": asr_engine,
            "report_mode": report_mode,
            "use_consensus": bool(use_consensus),
        },
        daemon=True,
        name=f"calltone-pipeline-{job.id[:8]}",
    ).start()

    return {"job_id": job.id, "eta_seconds": ETA_SECONDS}


@router.get("/contexts")
def list_contexts():
    return {"contexts": _list_contexts()}


@router.get("/contexts/{company}")
def get_context(company: str):
    context = _load_context(company)
    if context is None:
        raise HTTPException(status_code=404, detail="company context not found")
    return context


@router.put("/contexts/{company}")
def put_context(company: str, payload: dict = Body(...)):
    company = str(company or "").strip()
    if not company:
        raise HTTPException(status_code=400, detail="company is required")
    payload_company = str(payload.get("company_name") or company).strip()
    if _context_slug(payload_company) != _context_slug(company):
        raise HTTPException(
            status_code=400,
            detail="payload company_name does not match URL company",
        )
    CONTEXTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _context_path(company)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    # Invalidate graph cache for this context. It will be rebuilt with the new
    # version/content on the next score request.
    graph_path = path.with_name(f"{path.stem}_graph.json")
    graph_path.unlink(missing_ok=True)
    return {"ok": True, "company": payload_company, "file": path.name}


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
