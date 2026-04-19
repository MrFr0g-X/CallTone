"""D-4 endpoint tests — pipeline is mocked so no GPU / ML wheels needed."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


def _fake_pipeline_factory(
    *, exit_code: int = 0, lines: list[str] | None = None, result_payload: dict | None = None
):
    """Return a ``run_pipeline_blocking`` stand-in that writes a fake result."""

    default_lines = [
        "LAYER 1 — STEP 1: DENOISING",
        "LAYER 1 — STEP 2: TRANSCRIPTION & DIARIZATION",
        "LAYER 1 — STEP 3: ROLE IDENTIFICATION",
        "LAYER 1 — STEP 4: EMOTION DETECTION",
        "LAYER 2 — CALL QUALITY RATING",
        "LAYER 3 — REPORT GENERATION",
    ]
    stream = list(lines if lines is not None else default_lines)
    payload = result_payload if result_payload is not None else {"overall_score": 4.2}

    def fake(
        *,
        audio_path: Path,
        company: str,
        output_dir: Path,
        speakers=None,
        report_mode="both",
        timeout_seconds=600,
        on_line=None,
    ) -> int:
        if on_line is not None:
            for ln in stream:
                on_line(ln)
        output_dir.mkdir(parents=True, exist_ok=True)
        if exit_code == 0:
            (output_dir / "call_rating.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
        return exit_code

    return fake


def _wait_until(predicate, *, timeout=5.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_analyze_rejects_unsupported_content_type(client, auth_headers):
    r = client.post(
        "/v1/analyze",
        headers=auth_headers,
        files={"audio": ("note.pdf", b"%PDF-1.4", "application/pdf")},
        data={"company": "Acme"},
    )
    assert r.status_code == 415


def test_analyze_rejects_empty_upload(client, auth_headers):
    r = client.post(
        "/v1/analyze",
        headers=auth_headers,
        files={"audio": ("a.wav", b"", "audio/wav")},
        data={"company": "Acme"},
    )
    assert r.status_code == 400


def test_analyze_happy_path(client, auth_headers, monkeypatch):
    from model_server import endpoints

    monkeypatch.setattr(
        endpoints, "run_pipeline_blocking", _fake_pipeline_factory()
    )

    r = client.post(
        "/v1/analyze",
        headers=auth_headers,
        files={"audio": ("sample.wav", b"RIFFDATAXXXX", "audio/wav")},
        data={"company": "Acme", "speakers": "2"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    job_id = body["job_id"]
    assert isinstance(job_id, str) and len(job_id) == 32
    assert body["eta_seconds"] == 180

    # Worker runs on the thread pool; poll the status until it finishes.
    def _done() -> bool:
        s = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()
        return s["status"] in ("done", "failed")

    assert _wait_until(_done), "job never reached terminal state"

    status = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()
    assert status["status"] == "done"
    assert status["progress_pct"] == 100

    result = client.get(f"/v1/jobs/{job_id}/result", headers=auth_headers).json()
    assert result["job_id"] == job_id
    # load_result_json bundles whatever the pipeline wrote; the stub writes
    # ``call_rating.json`` so it ends up under that key.
    assert result["result"]["call_rating"]["overall_score"] == 4.2


def test_analyze_second_call_while_busy_returns_409(client, auth_headers, monkeypatch):
    from model_server import endpoints

    # Worker sleeps so the slot stays held while we submit the second call.
    def slow_pipeline(**kwargs):
        on_line = kwargs.get("on_line")
        if on_line is not None:
            on_line("LAYER 1 — STEP 1: DENOISING")
        time.sleep(0.5)
        output_dir: Path = kwargs["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "call_rating.json").write_text(json.dumps({"ok": True}))
        return 0

    monkeypatch.setattr(endpoints, "run_pipeline_blocking", slow_pipeline)

    r1 = client.post(
        "/v1/analyze",
        headers=auth_headers,
        files={"audio": ("a.wav", b"RIFFDATA", "audio/wav")},
        data={"company": "Acme"},
    )
    assert r1.status_code == 200

    # Busy-wait briefly so the worker really has the slot.
    time.sleep(0.1)

    r2 = client.post(
        "/v1/analyze",
        headers=auth_headers,
        files={"audio": ("b.wav", b"RIFFDATA", "audio/wav")},
        data={"company": "Acme"},
    )
    assert r2.status_code == 409
    assert "in flight" in r2.json()["detail"]


def test_result_before_done_returns_409(client, auth_headers, monkeypatch):
    from model_server import endpoints

    def slow_pipeline(**kwargs):
        time.sleep(0.5)
        output_dir: Path = kwargs["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "call_rating.json").write_text(json.dumps({"ok": True}))
        return 0

    monkeypatch.setattr(endpoints, "run_pipeline_blocking", slow_pipeline)

    r = client.post(
        "/v1/analyze",
        headers=auth_headers,
        files={"audio": ("a.wav", b"RIFFDATA", "audio/wav")},
        data={"company": "Acme"},
    )
    job_id = r.json()["job_id"]

    # Hit /result immediately — should be 409 because status != done.
    early = client.get(f"/v1/jobs/{job_id}/result", headers=auth_headers)
    assert early.status_code == 409


def test_unknown_job_returns_404(client, auth_headers):
    r = client.get("/v1/jobs/doesnotexist", headers=auth_headers)
    assert r.status_code == 404


def test_pipeline_failure_marks_job_failed(client, auth_headers, monkeypatch):
    from model_server import endpoints

    monkeypatch.setattr(
        endpoints,
        "run_pipeline_blocking",
        _fake_pipeline_factory(exit_code=1),
    )

    r = client.post(
        "/v1/analyze",
        headers=auth_headers,
        files={"audio": ("a.wav", b"RIFFDATA", "audio/wav")},
        data={"company": "Acme"},
    )
    job_id = r.json()["job_id"]

    def _terminal() -> bool:
        s = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()
        return s["status"] in ("done", "failed")

    assert _wait_until(_terminal)

    status = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()
    assert status["status"] == "failed"
    assert "pipeline exited" in (status["error"] or "")


def test_classify_line_recognises_stage_markers():
    from model_server.pipeline_adapter import classify_line

    assert classify_line("LAYER 1 — STEP 1: DENOISING") == ("denoising", 10)
    assert classify_line("... LAYER 2 — CALL QUALITY RATING ...") == ("scoring", 80)
    assert classify_line("random chatter") is None
