"""D-3 smoke tests — skeleton only.

These verify the package *imports cleanly* and ``/v1/health`` works without
auth. Real endpoint + auth behaviour is tested in D-9 (test_auth.py,
test_analyze.py).
"""

from __future__ import annotations


def test_package_imports():
    import model_server  # noqa: F401
    from model_server import main, auth, jobs, pipeline_adapter  # noqa: F401


def test_health_is_public(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "gpu_available" in body
    assert "model_cache_warm" in body
    assert body["version"] == "0.1.0"


def test_job_store_single_slot():
    from model_server.jobs import JobStore

    store = JobStore()
    first = store.acquire_slot(meta={"filename": "a.wav"})
    assert first is not None
    assert store.is_busy() is True

    # Second acquire while first is in-flight must be rejected.
    second = store.acquire_slot()
    assert second is None

    store.update(first.id, status="done", result={"ok": True})
    assert store.is_busy() is False

    third = store.acquire_slot()
    assert third is not None
    assert third.id != first.id


def test_pipeline_adapter_builds_command(tmp_path):
    from model_server.pipeline_adapter import build_command

    audio = tmp_path / "x.wav"
    audio.write_bytes(b"RIFF")
    out = tmp_path / "out"

    cmd = build_command(
        audio_path=audio,
        company="Acme",
        output_dir=out,
        speakers=2,
    )
    assert str(audio) in cmd
    assert "Acme" in cmd
    assert "--speakers" in cmd and "2" in cmd
    assert "--output-dir" in cmd
    assert cmd[0].endswith("python") or cmd[0].endswith("python.exe") or "python" in cmd[0]
