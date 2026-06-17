"""Tests for the concurrent, fair, multi-tenant pipeline queue.

These exercise ``_claim_next_pipeline_job`` directly (without starting the
worker pool, so no real pipeline runs) to prove four properties:

1. The concurrency cap is honored (never more than N running at once).
2. A queued job is claimed exactly once (no double-processing).
3. Scheduling is fair across tenants (a busy company can't starve others).
4. Orphaned 'running' jobs (dead worker) are reaped and requeued.
"""

from datetime import datetime, timezone, timedelta

import pytest

from app import main as app_main
from app.models import PipelineJob


def _session():
    return app_main.SessionLocal()


@pytest.fixture(autouse=True)
def _clean_jobs():
    db = _session()
    try:
        db.query(PipelineJob).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = _session()
    try:
        db.query(PipelineJob).delete()
        db.commit()
    finally:
        db.close()


def _add_job(call_id, company, *, status="queued", priority=100,
             created_offset=0, locked_at=None):
    db = _session()
    try:
        now = datetime.now(timezone.utc)
        db.add(PipelineJob(
            call_id=call_id,
            company_name=company,
            audio_path=f"/tmp/{call_id}.wav",
            asr_engine="fasterwhisper",
            status=status,
            priority=priority,
            attempts=0,
            created_at=now + timedelta(seconds=created_offset),
            updated_at=now,
            locked_at=locked_at,
            started_at=now if status == "running" else None,
        ))
        db.commit()
    finally:
        db.close()


def _running_count():
    db = _session()
    try:
        return db.query(PipelineJob).filter(PipelineJob.status == "running").count()
    finally:
        db.close()


def test_claim_respects_concurrency_cap(monkeypatch):
    monkeypatch.setattr(app_main, "PIPELINE_WORKER_CONCURRENCY", 2)
    _add_job("c-a", "alpha", created_offset=0)
    _add_job("c-b", "beta", created_offset=1)
    _add_job("c-c", "gamma", created_offset=2)

    assert app_main._claim_next_pipeline_job() is not None   # 1 running
    assert app_main._claim_next_pipeline_job() is not None   # 2 running
    assert app_main._claim_next_pipeline_job() is None        # cap hit
    assert _running_count() == 2


def test_queued_job_claimed_exactly_once(monkeypatch):
    monkeypatch.setattr(app_main, "PIPELINE_WORKER_CONCURRENCY", 5)
    _add_job("only", "alpha")

    first = app_main._claim_next_pipeline_job()
    second = app_main._claim_next_pipeline_job()

    assert first is not None and first["call_id"] == "only"
    assert second is None
    assert _running_count() == 1
    db = _session()
    try:
        job = db.query(PipelineJob).filter(PipelineJob.call_id == "only").first()
        assert job.attempts == 1
    finally:
        db.close()


def test_fair_scheduling_prefers_idle_tenant(monkeypatch):
    monkeypatch.setattr(app_main, "PIPELINE_WORKER_CONCURRENCY", 10)
    # Tenant 'busy' already has a running job; its queued job is the OLDEST.
    _add_job("busy-run", "busy", status="running",
             locked_at=datetime.now(timezone.utc))
    _add_job("busy-q", "busy", created_offset=0)     # oldest queued
    _add_job("idle-q", "idle", created_offset=5)     # newer, but idle tenant

    claimed = app_main._claim_next_pipeline_job()
    # Fairness must beat strict FIFO: the idle tenant is served first.
    assert claimed is not None and claimed["call_id"] == "idle-q"


def test_lease_reaper_requeues_orphaned_job(monkeypatch):
    monkeypatch.setattr(app_main, "PIPELINE_WORKER_CONCURRENCY", 1)
    monkeypatch.setattr(app_main, "PIPELINE_JOB_LEASE_SECONDS", 1)
    # A 'running' job whose worker died 1 hour ago (stale lock), nothing queued.
    _add_job("orphan", "alpha", status="running",
             locked_at=datetime.now(timezone.utc) - timedelta(hours=1))

    claimed = app_main._claim_next_pipeline_job()
    # Reaper requeues it, then the free slot re-claims it.
    assert claimed is not None and claimed["call_id"] == "orphan"
    assert _running_count() == 1
