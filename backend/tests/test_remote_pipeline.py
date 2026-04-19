"""D-7 — wire backend upload → model server.

We don't have a real model server during unit tests, so we stub the
``model_client`` module and call ``_run_remote_pipeline`` directly. The
test verifies that:

  * the Call record transitions through the status machine,
  * a Transcript row is written,
  * a QaReport row is written with the right severity + dim_scores,
  * status ends as COMPLETED.

This is the contract the backend relies on — if D-7 drifts from the local
pipeline's DB shape, this test catches it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _seed_call(db, *, audio_path: str = "/tmp/fake.wav") -> str:
    from app.models import Call, Customer, Employee

    # Find or create minimal dependencies. seed_database() already supplied
    # admin, qa, agent; we just need one employee + one customer.
    emp = db.query(Employee).first()
    if emp is None:
        emp = Employee(
            id=str(uuid.uuid4()),
            first_name="E",
            last_name="One",
            display_name="E One",
            role="AGENT",
        )
        db.add(emp)
        db.flush()

    cust = db.query(Customer).first()
    if cust is None:
        cust = Customer(
            id=str(uuid.uuid4()),
            display_name="Test Customer",
            phone_hash="test-remote",
        )
        db.add(cust)
        db.flush()

    call_id = str(uuid.uuid4())
    call = Call(
        id=call_id,
        customer_id=cust.id,
        employee_id=emp.id,
        original_filename="fake.wav",
        size_bytes=100,
        sha256="deadbeef",
        status="PENDING",
        current_step="uploaded",
        call_time=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()
    return call_id


_SAMPLE_LAYER1 = {
    "call_metadata": {"duration_seconds": 42.5},
    "transcript": [
        {"speaker": "Customer Service Agent", "text": "Hello, this is support."},
        {"speaker": "Customer", "text": "Hi, I have a question."},
    ],
}

_SAMPLE_LAYER2 = {
    "overall_weighted_score": 72.4,
    "criteria_ratings": {
        "politeness": {
            "score": 85,
            "summary": "Agent was courteous.",
            "confidence": 0.9,
            "evidence": [
                {"quote": "Hello, this is support.", "speaker": "Agent", "reason": "polite greeting"}
            ],
        },
        "empathy": {
            "score": 60,
            "summary": "Agent could acknowledge feelings more.",
            "confidence": 0.75,
            "evidence": [],
        },
    },
}


def test_remote_pipeline_happy_path(monkeypatch, client):
    # The client fixture imports app.main and runs seed_database; now we can
    # call the worker directly without multiprocessing.
    from app import main as app_main
    from app.database import SessionLocal
    from app.models import Call, QaReport, Transcript

    # Stub the model_client module the backend uses.
    import app.model_client as mc

    monkeypatch.setattr(mc, "submit", lambda *a, **kw: "remote-job-1")

    poll_states = iter(
        [
            {"status": "transcribing", "progress_pct": 30},
            {"status": "scoring", "progress_pct": 80},
            {"status": "done", "progress_pct": 100},
        ]
    )
    monkeypatch.setattr(mc, "poll", lambda jid: next(poll_states))
    monkeypatch.setattr(
        mc,
        "fetch_result",
        lambda jid: {"layer1": _SAMPLE_LAYER1, "layer2": _SAMPLE_LAYER2},
    )
    # Skip the real sleep to keep the test fast.
    import time

    monkeypatch.setattr(time, "sleep", lambda *_: None)

    db = SessionLocal()
    call_id = _seed_call(db)
    db.close()

    app_main._run_remote_pipeline(call_id, "/tmp/fake.wav", company="Acme")

    db = SessionLocal()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        assert call.status == "COMPLETED"
        assert call.current_step == "completed"
        assert call.duration_seconds == 42.5

        t = db.query(Transcript).filter(Transcript.call_id == call_id).first()
        assert t is not None
        assert "support" in t.full_text
        assert len(t.speaker_turns) == 2

        r = db.query(QaReport).filter(QaReport.call_id == call_id).first()
        assert r is not None
        assert r.overall_score == 72.4
        assert r.severity == "Moderate"  # 65 <= 72.4 < 85
        assert r.dimension_scores["politeness"] == 85
        assert r.confidence_scores["empathy"] == 0.75
    finally:
        db.close()


def test_remote_pipeline_failure_marks_call_failed(monkeypatch, client):
    from app import main as app_main
    from app.database import SessionLocal
    from app.models import Call

    import app.model_client as mc

    monkeypatch.setattr(mc, "submit", lambda *a, **kw: "remote-job-2")
    monkeypatch.setattr(
        mc,
        "poll",
        lambda jid: {"status": "failed", "error": "model crashed"},
    )
    import time

    monkeypatch.setattr(time, "sleep", lambda *_: None)

    db = SessionLocal()
    call_id = _seed_call(db)
    db.close()

    app_main._run_remote_pipeline(call_id, "/tmp/fake.wav")

    db = SessionLocal()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        assert call.status == "FAILED"
        assert "model crashed" in (call.error_message or "")
        assert call.current_step == "error"
    finally:
        db.close()


def test_run_pipeline_chooses_local_when_unset(monkeypatch, client):
    """When MODEL_SERVER_URL is unset, the dispatcher must call the local
    pipeline (not the remote one). We patch ``_run_real_pipeline`` so the
    test doesn't need the ML stack."""
    from app import main as app_main
    import app.model_client as mc

    monkeypatch.delenv("MODEL_SERVER_URL", raising=False)
    assert mc.configured() is False

    calls = {"local": 0, "remote": 0}
    monkeypatch.setattr(
        app_main, "_run_real_pipeline", lambda *a, **kw: calls.__setitem__("local", calls["local"] + 1)
    )
    monkeypatch.setattr(
        app_main, "_run_remote_pipeline", lambda *a, **kw: calls.__setitem__("remote", calls["remote"] + 1)
    )

    app_main._run_pipeline("fake-id", "/tmp/fake.wav")
    assert calls == {"local": 1, "remote": 0}


def test_run_pipeline_chooses_remote_when_configured(monkeypatch, client):
    from app import main as app_main

    monkeypatch.setenv("MODEL_SERVER_URL", "http://model.test:8080")
    monkeypatch.setenv("MODEL_SERVER_TOKEN", "test-token")

    calls = {"local": 0, "remote": 0}
    monkeypatch.setattr(
        app_main, "_run_real_pipeline", lambda *a, **kw: calls.__setitem__("local", calls["local"] + 1)
    )
    monkeypatch.setattr(
        app_main, "_run_remote_pipeline", lambda *a, **kw: calls.__setitem__("remote", calls["remote"] + 1)
    )

    app_main._run_pipeline("fake-id", "/tmp/fake.wav")
    assert calls == {"local": 0, "remote": 1}
