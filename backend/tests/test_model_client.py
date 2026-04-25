"""Tests for ``backend/app/model_client.py`` (D-6).

We monkeypatch ``httpx.post`` / ``httpx.get`` with stubs — no network, no
MockTransport plumbing. The assertions cover:

  * happy-path submit → job_id
  * retry-then-succeed on connection error
  * no retry on 4xx (real failure surfaced)
  * poll / fetch_result success + 404 / 409 branches
  * ``configured()`` env-driven flag
"""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest

from app import model_client


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_SERVER_URL", "http://model.test:8080")
    monkeypatch.setenv("MODEL_SERVER_TOKEN", "unit-test-token")
    # Disable backoff sleep so retry tests aren't slow.
    monkeypatch.setattr(model_client, "_retry_sleep", lambda *_: None)


@pytest.fixture
def tiny_audio(tmp_path) -> Path:
    p = tmp_path / "clip.wav"
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    return p


def _make_response(
    *, status: int, json_body: dict | None = None, text: str = ""
) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json=json_body if json_body is not None else {},
        text=text if not json_body else None,
    )


# ── configured() ───────────────────────────────────────────────────────────


def test_configured_true_when_url_set():
    assert model_client.configured() is True


def test_configured_false_when_url_unset(monkeypatch):
    monkeypatch.delenv("MODEL_SERVER_URL", raising=False)
    assert model_client.configured() is False


# ── submit() ───────────────────────────────────────────────────────────────


def test_submit_happy_path(monkeypatch, tiny_audio):
    captured = {}

    def fake_post(url, *, headers, data, files, timeout):
        captured["url"] = url
        captured["token"] = headers["Authorization"]
        captured["company"] = data["company"]
        # Exhaust the file stream to mimic a real upload.
        files["audio"][1].read()
        return _make_response(status=200, json_body={"job_id": "abc123", "eta_seconds": 180})

    monkeypatch.setattr(httpx, "post", fake_post)

    job_id = model_client.submit(tiny_audio, company="Acme", speakers=2)

    assert job_id == "abc123"
    assert captured["url"] == "http://model.test:8080/v1/analyze"
    assert captured["token"] == "Bearer unit-test-token"
    assert captured["company"] == "Acme"


def test_submit_retries_on_connect_error(monkeypatch, tiny_audio):
    calls = {"n": 0}

    def flaky_post(url, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("boom")
        kw["files"]["audio"][1].read()
        return _make_response(status=200, json_body={"job_id": "retry-ok"})

    monkeypatch.setattr(httpx, "post", flaky_post)

    assert model_client.submit(tiny_audio, company="Acme") == "retry-ok"
    assert calls["n"] == 2


def test_submit_does_not_retry_on_4xx(monkeypatch, tiny_audio):
    calls = {"n": 0}

    def fake_post(url, **kw):
        calls["n"] += 1
        kw["files"]["audio"][1].read()
        return _make_response(status=415, text="unsupported")

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(model_client.ModelServerError) as exc_info:
        model_client.submit(tiny_audio, company="Acme")
    assert "HTTP 415" in str(exc_info.value)
    assert calls["n"] == 1  # no retry


def test_submit_exhausts_retries_then_raises(monkeypatch, tiny_audio):
    def always_fail(url, **kw):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(httpx, "post", always_fail)

    with pytest.raises(model_client.ModelServerError, match="unreachable"):
        model_client.submit(tiny_audio, company="Acme")


def test_submit_requires_existing_file(tmp_path):
    missing = tmp_path / "nope.wav"
    with pytest.raises(model_client.ModelServerError, match="not found"):
        model_client.submit(missing, company="Acme")


def test_submit_requires_token(monkeypatch, tiny_audio):
    monkeypatch.delenv("MODEL_SERVER_TOKEN", raising=False)
    with pytest.raises(model_client.ModelServerError, match="MODEL_SERVER_TOKEN"):
        model_client.submit(tiny_audio, company="Acme")


# ── poll() ─────────────────────────────────────────────────────────────────


def test_poll_happy_path(monkeypatch):
    def fake_get(url, **kw):
        assert url == "http://model.test:8080/v1/jobs/j1"
        return _make_response(
            status=200,
            json_body={"job_id": "j1", "status": "transcribing", "progress_pct": 30},
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    body = model_client.poll("j1")
    assert body["status"] == "transcribing"
    assert body["progress_pct"] == 30


def test_poll_unknown_job_raises_with_job_id(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda url, **kw: _make_response(status=404, json_body={"detail": "unknown job"})
    )
    with pytest.raises(model_client.ModelServerError, match="unknown job: jx"):
        model_client.poll("jx")


# ── fetch_result() ─────────────────────────────────────────────────────────


def test_fetch_result_happy_path(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: _make_response(
            status=200,
            json_body={"job_id": "j1", "result": {"overall_score": 3.9}},
        ),
    )
    out = model_client.fetch_result("j1")
    assert out == {"overall_score": 3.9}


def test_fetch_result_not_ready_raises(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: _make_response(
            status=409, json_body={"detail": "job not ready (status=scoring)"}
        ),
    )
    with pytest.raises(model_client.ModelServerError, match="not ready"):
        model_client.fetch_result("j1")


def test_fetch_result_malformed_body_raises(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: _make_response(status=200, json_body={"job_id": "j1"}),
    )
    with pytest.raises(model_client.ModelServerError, match="malformed"):
        model_client.fetch_result("j1")
