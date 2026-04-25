import io
import asyncio
import hashlib

import pytest
from fastapi import HTTPException


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_upload_rejects_non_audio_content_type(client, qa_token):
    files = {
        "file": (
            "evil.exe",
            io.BytesIO(b"MZ\x90\x00"),
            "application/x-msdownload",
        )
    }
    r = client.post("/api/calls/upload", files=files, headers=_auth(qa_token))
    assert r.status_code in (400, 415, 422)


def test_pipeline_settings_admin_only(client, admin_token, agent_token):
    r1 = client.get("/api/settings/pipeline", headers=_auth(admin_token))
    assert r1.status_code == 200
    r2 = client.put(
        "/api/settings/pipeline",
        json={
            "audioMode": "denoise",
            "injectionScan": "static",
            "reportMode": "simple",
            "useConsensus": False,
            "companyName": "BankServ Global",
        },
        headers=_auth(agent_token),
    )
    assert r2.status_code in (401, 403)


def test_status_polling_unknown_call_returns_404(client, qa_token):
    r = client.get(
        "/api/calls/00000000-0000-0000-0000-000000000000/status",
        headers=_auth(qa_token),
    )
    assert r.status_code == 404


class _ChunkedUpload:
    def __init__(self, chunks):
        self.filename = "sample.wav"
        self._chunks = list(chunks)
        self.read_sizes = []
        self.closed = False

    async def read(self, size=-1):
        self.read_sizes.append(size)
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    async def close(self):
        self.closed = True


def test_stream_upload_to_disk_writes_chunks_and_hashes(tmp_path):
    from app import main as app_main

    upload = _ChunkedUpload([b"abc", b"def"])
    dest = tmp_path / "streamed.wav"

    total, digest = asyncio.run(app_main._stream_upload_to_disk(upload, dest))

    assert total == 6
    assert digest == hashlib.sha256(b"abcdef").hexdigest()
    assert dest.read_bytes() == b"abcdef"
    assert upload.read_sizes == [app_main.UPLOAD_CHUNK_SIZE] * 3
    assert upload.closed is True


def test_stream_upload_to_disk_deletes_partial_file_when_too_large(monkeypatch, tmp_path):
    from app import main as app_main

    monkeypatch.setattr(app_main, "MAX_FILE_SIZE", 5)
    upload = _ChunkedUpload([b"abc", b"def"])
    dest = tmp_path / "too_large.wav"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(app_main._stream_upload_to_disk(upload, dest))

    assert exc.value.status_code == 400
    assert "File too large" in exc.value.detail
    assert not dest.exists()
    assert upload.closed is True


def test_upload_enqueues_pipeline_instead_of_starting_immediate_process(
    monkeypatch, tmp_path, client, qa_token
):
    from app import main as app_main

    captured = {}

    def fake_enqueue(call_id, audio_path, asr_engine="fasterwhisper", company_name=None):
        captured.update(
            {
                "call_id": call_id,
                "audio_path": audio_path,
                "asr_engine": asr_engine,
                "company_name": company_name,
            }
        )
        return 3

    monkeypatch.setattr(app_main, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(app_main, "_ensure_known_company_context", lambda name: name)
    monkeypatch.setattr(app_main, "_audio_duration_metadata", lambda path: (1.25, 16000, 1))
    monkeypatch.setattr(app_main, "_enqueue_pipeline", fake_enqueue)

    files = {"file": ("sample.wav", io.BytesIO(b"RIFFsmall"), "audio/wav")}
    r = client.post(
        "/api/calls/upload",
        files=files,
        data={"company_name": "BankServ Global", "asr_engine": "fasterwhisper"},
        headers=_auth(qa_token),
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "QUEUED"
    assert body["queuePosition"] == 3
    assert body["etaSeconds"] > 0
    assert captured["call_id"] == body["callId"]
    assert captured["asr_engine"] == "fasterwhisper"
    assert captured["company_name"] == "BankServ Global"
    assert (tmp_path / f"{body['callId']}_sample.wav").read_bytes() == b"RIFFsmall"


def test_enqueue_pipeline_persists_durable_job(monkeypatch):
    from app import main as app_main
    from app.database import SessionLocal
    from app.models import PipelineJob

    monkeypatch.setattr(app_main, "_ensure_pipeline_queue_worker_started", lambda: None)
    monkeypatch.setattr(app_main._PIPELINE_QUEUE_WAKE_EVENT, "set", lambda: None)

    db = SessionLocal()
    try:
        db.query(PipelineJob).filter(PipelineJob.call_id == "durable-call").delete()
        db.commit()

        position = app_main._enqueue_pipeline(
            "durable-call",
            "/tmp/durable.wav",
            "sensevoice",
            "BankServ Global",
        )

        job = db.query(PipelineJob).filter(PipelineJob.call_id == "durable-call").first()
        assert position == 1
        assert job is not None
        assert job.status == "queued"
        assert job.audio_path == "/tmp/durable.wav"
        assert job.asr_engine == "sensevoice"
        assert job.company_name == "BankServ Global"
    finally:
        db.query(PipelineJob).filter(PipelineJob.call_id == "durable-call").delete()
        db.commit()
        db.close()


def test_pipeline_queue_snapshot_reports_active_and_queued_positions(client):
    from app import main as app_main
    from app.database import SessionLocal
    from app.models import PipelineJob

    db = SessionLocal()
    with app_main._PIPELINE_QUEUE_LOCK:
        old_active = app_main._PIPELINE_ACTIVE_CALL_ID
        app_main._PIPELINE_ACTIVE_CALL_ID = "active-call"

    try:
        db.query(PipelineJob).filter(PipelineJob.call_id.in_(["queued-1", "queued-2"])).delete(
            synchronize_session=False
        )
        db.add(PipelineJob(call_id="queued-1", audio_path="/tmp/1.wav", status="queued", priority=1))
        db.add(PipelineJob(call_id="queued-2", audio_path="/tmp/2.wav", status="queued", priority=2))
        db.commit()

        active = app_main._pipeline_queue_snapshot("active-call")
        queued = app_main._pipeline_queue_snapshot("queued-2")
        missing = app_main._pipeline_queue_snapshot("missing")

        assert active["queuePosition"] == 0
        assert queued["queuePosition"] == 2
        assert queued["queuedCount"] == 2
        assert missing["queuePosition"] is None
    finally:
        db.query(PipelineJob).filter(PipelineJob.call_id.in_(["queued-1", "queued-2"])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()
        with app_main._PIPELINE_QUEUE_LOCK:
            app_main._PIPELINE_ACTIVE_CALL_ID = old_active


def test_recover_interrupted_pipeline_jobs_requeues_running_jobs(client):
    from app import main as app_main
    from app.database import SessionLocal
    from app.models import PipelineJob

    db = SessionLocal()
    try:
        db.query(PipelineJob).filter(PipelineJob.call_id == "interrupted-call").delete()
        db.add(PipelineJob(call_id="interrupted-call", audio_path="/tmp/i.wav", status="running"))
        db.commit()

        app_main._recover_interrupted_pipeline_jobs()

        job = db.query(PipelineJob).filter(PipelineJob.call_id == "interrupted-call").first()
        assert job.status == "queued"
        assert job.locked_at is None
    finally:
        db.query(PipelineJob).filter(PipelineJob.call_id == "interrupted-call").delete()
        db.commit()
        db.close()


def test_pipeline_queue_endpoint_is_role_protected(client, qa_token, agent_token):
    from app import main as app_main
    from app.database import SessionLocal
    from app.models import PipelineJob

    db = SessionLocal()
    with app_main._PIPELINE_QUEUE_LOCK:
        old_active = app_main._PIPELINE_ACTIVE_CALL_ID
        app_main._PIPELINE_ACTIVE_CALL_ID = "active-call"

    try:
        db.query(PipelineJob).filter(PipelineJob.call_id.in_(["queued-1", "queued-2"])).delete(
            synchronize_session=False
        )
        db.add(PipelineJob(call_id="queued-1", audio_path="/tmp/1.wav", status="queued", priority=1))
        db.add(PipelineJob(call_id="queued-2", audio_path="/tmp/2.wav", status="queued", priority=2))
        db.commit()

        allowed = client.get("/api/pipeline/queue", headers=_auth(qa_token))
        denied = client.get("/api/pipeline/queue", headers=_auth(agent_token))

        assert allowed.status_code == 200
        body = allowed.json()
        assert body["activeCallId"] == "active-call"
        assert body["queuedCount"] == 2
        assert body["queuedCallIds"] == ["queued-1", "queued-2"]
        assert body["estimatedDrainSeconds"] == 2 * app_main.PIPELINE_QUEUE_ETA_SECONDS
        assert denied.status_code in (401, 403)
    finally:
        db.query(PipelineJob).filter(PipelineJob.call_id.in_(["queued-1", "queued-2"])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()
        with app_main._PIPELINE_QUEUE_LOCK:
            app_main._PIPELINE_ACTIVE_CALL_ID = old_active


def test_pipeline_jobs_list_retry_and_dead_letter(client, admin_token, qa_token, agent_token):
    from app.database import SessionLocal
    from app.models import PipelineJob

    db = SessionLocal()
    try:
        db.query(PipelineJob).filter(PipelineJob.call_id.in_(["failed-job", "queued-job"])).delete(
            synchronize_session=False
        )
        db.add(
            PipelineJob(
                call_id="failed-job",
                audio_path="/tmp/failed.wav",
                status="failed",
                attempts=2,
                max_attempts=2,
                error_message="boom",
            )
        )
        db.add(PipelineJob(call_id="queued-job", audio_path="/tmp/queued.wav", status="queued"))
        db.commit()

        list_allowed = client.get("/api/pipeline/jobs?status_filter=failed", headers=_auth(qa_token))
        list_denied = client.get("/api/pipeline/jobs", headers=_auth(agent_token))
        assert list_allowed.status_code == 200
        assert any(job["callId"] == "failed-job" for job in list_allowed.json()["jobs"])
        assert list_denied.status_code in (401, 403)

        retry_denied = client.post("/api/pipeline/jobs/failed-job/retry", headers=_auth(qa_token))
        retry_allowed = client.post("/api/pipeline/jobs/failed-job/retry", headers=_auth(admin_token))
        assert retry_denied.status_code in (401, 403)
        assert retry_allowed.status_code == 200
        retried = retry_allowed.json()["job"]
        assert retried["status"] == "queued"
        assert retried["attempts"] == 0
        assert retried["errorMessage"] is None

        dead_letter = client.post("/api/pipeline/jobs/queued-job/dead-letter", headers=_auth(admin_token))
        assert dead_letter.status_code == 200
        assert dead_letter.json()["job"]["status"] == "failed"
    finally:
        db.query(PipelineJob).filter(PipelineJob.call_id.in_(["failed-job", "queued-job"])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()
