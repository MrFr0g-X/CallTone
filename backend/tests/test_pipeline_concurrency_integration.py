"""End-to-end integration test of the concurrent pipeline queue.

Unlike test_pipeline_concurrency.py (which exercises the claim function in
isolation), this starts the REAL worker pool with REAL threads and a stubbed
pipeline body, enqueues many jobs across many tenants, and proves at runtime:

  * actual parallelism (more than one job runs at once),
  * the concurrency cap is never exceeded,
  * every job is processed exactly once (no double-processing),
  * scheduling is tenant-fair (early slots span multiple tenants).

Run in isolation so the global worker pool is clean:
    python -m pytest tests/test_pipeline_concurrency_integration.py -v -s
"""

import threading
import time
from datetime import datetime, timezone

from app import main as app_main
from app.models import Call, PipelineJob

import pytest

pytestmark = pytest.mark.integration

CONCURRENCY = 4
TENANTS = ["alpha", "beta", "gamma", "delta"]
JOBS_PER_TENANT = 6
WORK_SECONDS = 0.15


def _session():
    return app_main.SessionLocal()


def test_worker_pool_runs_parallel_fair_and_exactly_once(monkeypatch):
    state = {"active": 0, "max_active": 0, "order": [], "processed": []}
    lock = threading.Lock()

    def fake_run_pipeline(call_id, audio_path, asr_engine, company):
        with lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            state["order"].append(company)
        time.sleep(WORK_SECONDS)
        db = _session()
        try:
            c = db.query(Call).filter(Call.id == call_id).first()
            if c:
                c.status = "COMPLETED"
                db.commit()
        finally:
            db.close()
        with lock:
            state["active"] -= 1
            state["processed"].append(call_id)

    monkeypatch.setattr(app_main, "PIPELINE_WORKER_CONCURRENCY", CONCURRENCY)
    monkeypatch.setattr(app_main, "_run_pipeline", fake_run_pipeline)

    # Seed Call + queued PipelineJob rows for every tenant.
    call_ids = []
    db = _session()
    try:
        db.query(PipelineJob).delete()
        now = datetime.now(timezone.utc)
        seq = 0
        for t in TENANTS:
            for _ in range(JOBS_PER_TENANT):
                seq += 1
                cid = f"itest-{t}-{seq}"
                call_ids.append(cid)
                db.add(Call(id=cid, employee_id="emp-x", original_filename=f"{cid}.wav",
                            status="PENDING", created_at=now, updated_at=now))
                db.add(PipelineJob(call_id=cid, company_name=t, audio_path=f"/tmp/{cid}.wav",
                                   asr_engine="fasterwhisper", status="queued", priority=100,
                                   attempts=0, created_at=now, updated_at=now))
        db.commit()
    finally:
        db.close()

    total = len(call_ids)
    app_main._ensure_pipeline_queue_worker_started()  # start the real pool

    # Wait for the queue to drain (all jobs terminal) or time out.
    deadline = time.time() + 60
    while time.time() < deadline:
        db = _session()
        try:
            remaining = (
                db.query(PipelineJob)
                .filter(PipelineJob.call_id.in_(call_ids),
                        PipelineJob.status.in_(["queued", "running"]))
                .count()
            )
        finally:
            db.close()
        if remaining == 0:
            break
        time.sleep(0.1)

    # --- assertions ---
    db = _session()
    try:
        completed = (
            db.query(PipelineJob)
            .filter(PipelineJob.call_id.in_(call_ids), PipelineJob.status == "completed")
            .count()
        )
    finally:
        db.close()

    print(f"\n[integration] total={total} completed={completed} "
          f"max_parallel={state['max_active']} processed={len(state['processed'])}")

    assert completed == total, f"only {completed}/{total} completed"
    # exactly once: no call processed twice
    assert len(state["processed"]) == total
    assert len(set(state["processed"])) == total, "a job was processed more than once"
    # real parallelism happened, but never above the cap
    assert state["max_active"] >= 2, "no real concurrency observed"
    assert state["max_active"] <= CONCURRENCY, "concurrency cap exceeded"
    # tenant fairness: the first CONCURRENCY*2 slots span at least 3 tenants
    early = state["order"][: CONCURRENCY * 2]
    assert len(set(early)) >= 3, f"early scheduling not fair across tenants: {early}"

    # cleanup
    db = _session()
    try:
        db.query(PipelineJob).filter(PipelineJob.call_id.in_(call_ids)).delete(synchronize_session=False)
        db.query(Call).filter(Call.id.in_(call_ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
