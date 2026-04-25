import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.database import SessionLocal, settings
from app.models import Call, Customer, Employee, User


def _seed_audio_call(audio_path: str) -> str:
    db = SessionLocal()
    try:
        employee = db.query(Employee).first()
        if employee is None:
            employee = Employee(
                id=str(uuid.uuid4()),
                employee_code=f"AUD-{uuid.uuid4().hex[:6]}",
                full_name="Audio Agent",
                role="AGENT",
            )
            db.add(employee)
            db.flush()

        customer = db.query(Customer).first()
        if customer is None:
            customer = Customer(
                id=str(uuid.uuid4()),
                display_name="Audio Customer",
                phone_hash=f"audio-{uuid.uuid4().hex[:8]}",
            )
            db.add(customer)
            db.flush()

        call_id = str(uuid.uuid4())
        db.add(
            Call(
                id=call_id,
                customer_id=customer.id,
                employee_id=employee.id,
                original_filename="audio-fixture.wav",
                storage_path=audio_path,
                duration_seconds=1.0,
                size_bytes=128,
                sha256="audio-test",
                status="COMPLETED",
                current_step="completed",
                call_time=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return call_id
    finally:
        db.close()


def _user_id_for(email: str) -> int:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        return user.id
    finally:
        db.close()


def test_call_detail_returns_short_lived_media_token(client, qa_token, tmp_path):
    audio_file = tmp_path / "fixture.wav"
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    call_id = _seed_audio_call(str(audio_file))

    response = client.get(
        f"/api/qa/calls/{call_id}",
        headers={"Authorization": f"Bearer {qa_token}"},
    )

    assert response.status_code == 200, response.text
    audio_url = response.json()["audioUrl"]
    assert audio_url.startswith(f"/api/qa/calls/{call_id}/audio?media_token=")


def test_audio_stream_accepts_media_token_without_authorization(client, qa_token, tmp_path):
    audio_file = tmp_path / "fixture.wav"
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    call_id = _seed_audio_call(str(audio_file))

    detail = client.get(
        f"/api/qa/calls/{call_id}",
        headers={"Authorization": f"Bearer {qa_token}"},
    )
    media_url = detail.json()["audioUrl"]

    response = client.get(media_url)

    assert response.status_code == 200, response.text
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cross-origin-resource-policy"] == "cross-origin"
    assert response.headers["content-type"].startswith("audio/")
    assert response.content.startswith(b"RIFF")


def test_audio_stream_still_accepts_bearer_authorization(client, qa_token, tmp_path):
    audio_file = tmp_path / "fixture.wav"
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    call_id = _seed_audio_call(str(audio_file))

    response = client.get(
        f"/api/qa/calls/{call_id}/audio",
        headers={"Authorization": f"Bearer {qa_token}"},
    )

    assert response.status_code == 200, response.text
    assert response.content.startswith(b"RIFF")


def test_audio_stream_requires_auth_or_media_token(client, tmp_path):
    audio_file = tmp_path / "fixture.wav"
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    call_id = _seed_audio_call(str(audio_file))

    response = client.get(f"/api/qa/calls/{call_id}/audio")

    assert response.status_code == 401


def test_audio_stream_rejects_malformed_media_token_subject(client, tmp_path):
    audio_file = tmp_path / "fixture.wav"
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    call_id = _seed_audio_call(str(audio_file))
    bad_token = jwt.encode(
        {
            "sub": "not-an-int",
            "call_id": call_id,
            "scope": "call_audio",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = client.get(f"/api/qa/calls/{call_id}/audio?media_token={bad_token}")

    assert response.status_code == 401


def test_audio_media_token_still_enforces_agent_call_visibility(client, tmp_path):
    audio_file = tmp_path / "fixture.wav"
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    call_id = _seed_audio_call(str(audio_file))
    agent_user_id = _user_id_for("agent1@calltone.ai")
    agent_scoped_token = jwt.encode(
        {
            "sub": str(agent_user_id),
            "call_id": call_id,
            "scope": "call_audio",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = client.get(f"/api/qa/calls/{call_id}/audio?media_token={agent_scoped_token}")

    assert response.status_code == 403
