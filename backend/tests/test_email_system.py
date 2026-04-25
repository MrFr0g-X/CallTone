import secrets

from app.database import SessionLocal
from app.models import EmailEvent


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_invite_records_email_event_even_when_mail_disabled(client, admin_token):
    email = f"mail_invite_{secrets.token_hex(4)}@calltone.ai"

    response = client.post(
        "/api/admin/users/invite",
        headers=_auth(admin_token),
        json={"name": "Mail Invite", "email": email, "role": "qa"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["emailStatus"] == "suppressed"

    db = SessionLocal()
    try:
        event = (
            db.query(EmailEvent)
            .filter(EmailEvent.recipient_email == email)
            .order_by(EmailEvent.created_at.desc())
            .first()
        )
        assert event is not None
        assert event.event_type == "account.invite"
        assert event.status == "suppressed"
        assert event.error == "MAIL_ENABLED=false"
    finally:
        db.close()


def test_mail_status_and_null_provider_test_send(client, admin_token, monkeypatch):
    monkeypatch.setenv("MAIL_ENABLED", "true")
    monkeypatch.setenv("MAIL_PROVIDER", "null")
    monkeypatch.setenv("MAIL_FROM", "CallTone Support <support@calltone.tech>")

    status = client.get("/api/settings/mail", headers=_auth(admin_token))
    assert status.status_code == 200, status.text
    assert status.json()["enabled"] is True
    assert status.json()["provider"] == "null"
    assert status.json()["fromEmail"] == "support@calltone.tech"

    send = client.post("/api/settings/mail/test", headers=_auth(admin_token))
    assert send.status_code == 200, send.text
    assert send.json()["ok"] is True
    assert send.json()["event"]["status"] == "sent"
    assert send.json()["event"]["provider"] == "null"


def test_qa_cannot_send_test_email(client, qa_token):
    response = client.post("/api/settings/mail/test", headers=_auth(qa_token))
    assert response.status_code == 403

