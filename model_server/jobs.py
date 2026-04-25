"""In-memory job store for the model server.

A single GPU runs one pipeline at a time, so the store doubles as an
in-flight guard: ``acquire_slot()`` rejects with ``None`` when a job is
already running. Jobs are garbage-collected ``JOB_TTL_SECONDS`` after they
reach a terminal state (``done`` / ``failed``) so clients always have a
short window to fetch results.

The store is process-local by design. The server is single-process (one
uvicorn worker, ``--workers 1``) because the pipeline holds GPU VRAM and
sharing it across workers would defeat the point.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

JobStatus = Literal[
    "queued",
    "denoising",
    "diarising",
    "transcribing",
    "role_ident",
    "emotion",
    "scoring",
    "rendering",
    "done",
    "failed",
]

_TERMINAL: set[JobStatus] = {"done", "failed"}

JOB_TTL_SECONDS = 300  # 5 minutes after terminal state


@dataclass
class Job:
    id: str
    status: JobStatus = "queued"
    progress_pct: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    terminal_at: float | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    # Caller-supplied metadata (filename, company) for traceability.
    meta: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class JobStore:
    """Thread-safe map of job_id → Job with a single-slot guard."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._active_id: str | None = None

    # ── slot management ────────────────────────────────────────────────
    def acquire_slot(self, *, meta: dict[str, Any] | None = None) -> Job | None:
        """Reserve the single GPU slot; returns a new Job or ``None`` if busy."""
        with self._lock:
            self._sweep_locked()
            if self._active_id is not None:
                return None
            job = Job(id=uuid.uuid4().hex, meta=dict(meta or {}))
            self._jobs[job.id] = job
            self._active_id = job.id
            return job

    def release_slot(self, job_id: str) -> None:
        with self._lock:
            if self._active_id == job_id:
                self._active_id = None

    def is_busy(self) -> bool:
        with self._lock:
            return self._active_id is not None

    def snapshot(self) -> dict[str, Any]:
        """Return safe public scheduler state for capacity/ops endpoints."""
        with self._lock:
            self._sweep_locked()
            active = self._jobs.get(self._active_id) if self._active_id else None
            terminal = [j for j in self._jobs.values() if j.status in _TERMINAL]
            return {
                "busy": self._active_id is not None,
                "activeJobId": self._active_id,
                "activeStatus": active.status if active else None,
                "activeProgressPct": active.progress_pct if active else None,
                "activeMeta": dict(active.meta) if active else None,
                "knownJobs": len(self._jobs),
                "terminalJobs": len(terminal),
            }

    # ── state updates ──────────────────────────────────────────────────
    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        progress_pct: int | None = None,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if status is not None:
                job.status = status
                if status in _TERMINAL:
                    job.terminal_at = time.time()
                    if self._active_id == job_id:
                        self._active_id = None
            if progress_pct is not None:
                job.progress_pct = max(0, min(100, progress_pct))
            if error is not None:
                job.error = error
            if result is not None:
                job.result = result
            job.updated_at = time.time()

    # ── accessors ──────────────────────────────────────────────────────
    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    # ── gc ─────────────────────────────────────────────────────────────
    def _sweep_locked(self) -> None:
        now = time.time()
        stale = [
            jid
            for jid, j in self._jobs.items()
            if j.terminal_at is not None and (now - j.terminal_at) > JOB_TTL_SECONDS
        ]
        for jid in stale:
            del self._jobs[jid]
