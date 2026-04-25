import secrets
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Call, Client, ClientPolicy, EmailEvent, Employee, PipelineSettings, QaReport, Role, User
from app.security import hash_password


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_user(email: str, role_name: str, password: str = "OwnerTest123!") -> int:
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        assert role is not None, f"Missing role {role_name}"
        user = User(
            full_name=f"{role.display_name} Test User",
            email=email,
            password_hash=hash_password(password),
            role_id=role.id,
            client_id=None,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def _login(client, email: str, password: str = "OwnerTest123!") -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _create_email_event(user_id: int, email: str) -> str:
    db = SessionLocal()
    try:
        event = EmailEvent(
            event_type="account.invite",
            recipient_email=email,
            recipient_user_id=user_id,
            subject="Invitation",
            status="sent",
            provider="null",
            provider_message_id="test-message",
            metadata_json={"test": True},
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event.id
    finally:
        db.close()


def _create_other_agent_report(score: float = 91.0) -> None:
    db = SessionLocal()
    try:
        client = Client(
            name=f"Leak Test Client {secrets.token_hex(4)}",
            industry="QA",
            status="active",
            plan="trial",
        )
        db.add(client)
        agent = Employee(
            employee_code=f"AG-{secrets.token_hex(4)}",
            full_name="Linked Agent With Reports",
            role="AGENT",
        )
        qa = Employee(
            employee_code=f"QA-{secrets.token_hex(4)}",
            full_name="QA Reviewer",
            role="QA",
        )
        db.add_all([agent, qa])
        db.flush()
        call = Call(
            employee_id=agent.id,
            original_filename="leak-test.wav",
            status="COMPLETED",
            call_time=datetime.now(timezone.utc),
        )
        db.add(call)
        db.flush()
        db.add(
            QaReport(
                call_id=call.id,
                qa_id=qa.id,
                overall_score=score,
                grade="A",
                severity="Minor",
                dimension_scores={"politeness_tone": score, "empathy": score, "issue_resolution": score},
                report_json={"summary": "security regression fixture"},
            )
        )
        db.commit()
    finally:
        db.close()


def test_owner_can_invite_super_admin(client):
    owner_email = f"owner_invite_{secrets.token_hex(4)}@calltone.ai"
    _create_user(owner_email, "owner")
    owner_token = _login(client, owner_email)

    invite_email = f"new_super_{secrets.token_hex(4)}@calltone.ai"
    response = client.post(
        "/api/admin/users/invite",
        headers=_auth(owner_token),
        json={"name": "Promoted Super Admin", "email": invite_email, "role": "super_admin"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == "super_admin"


def test_super_admin_cannot_invite_super_admin(client, admin_token):
    invite_email = f"blocked_super_{secrets.token_hex(4)}@calltone.ai"
    response = client.post(
        "/api/admin/users/invite",
        headers=_auth(admin_token),
        json={"name": "Blocked Super Admin", "email": invite_email, "role": "super_admin"},
    )

    assert response.status_code == 400, response.text
    assert "Allowed roles" in response.json()["detail"]


def test_platform_admin_can_create_client_with_policy_and_settings(client, admin_token):
    client_name = f"New Company {secrets.token_hex(4)}"
    response = client.post(
        "/api/admin/clients",
        headers=_auth(admin_token),
        json={"name": client_name, "industry": "Telecom", "status": "trial", "plan": "starter"},
    )

    assert response.status_code == 200, response.text
    body = response.json()["client"]
    assert body["name"] == client_name

    db = SessionLocal()
    try:
        created = db.query(Client).filter(Client.name == client_name).first()
        assert created is not None
        assert db.query(ClientPolicy).filter(ClientPolicy.client_id == created.id).first() is not None
        settings = db.query(PipelineSettings).filter(PipelineSettings.client_id == created.id).first()
        assert settings is not None
        assert settings.company_name == client_name
    finally:
        db.close()


def test_super_admin_cannot_mutate_owner(client, admin_token):
    owner_email = f"protected_owner_{secrets.token_hex(4)}@calltone.ai"
    owner_id = _create_user(owner_email, "owner")

    role_response = client.patch(
        f"/api/admin/users/{owner_id}/role",
        headers=_auth(admin_token),
        json={"role": "admin"},
    )
    assert role_response.status_code == 403, role_response.text

    status_response = client.patch(
        f"/api/admin/users/{owner_id}/status",
        headers=_auth(admin_token),
        json={"status": "disabled"},
    )
    assert status_response.status_code == 403, status_response.text

    delete_response = client.delete(
        f"/api/admin/users/{owner_id}",
        headers=_auth(admin_token),
    )
    assert delete_response.status_code == 403, delete_response.text


def test_owner_can_demote_and_delete_super_admin(client):
    owner_email = f"owner_mutate_{secrets.token_hex(4)}@calltone.ai"
    _create_user(owner_email, "owner")
    owner_token = _login(client, owner_email)

    target_email = f"temp_super_{secrets.token_hex(4)}@calltone.ai"
    target_id = _create_user(target_email, "super_admin")

    role_response = client.patch(
        f"/api/admin/users/{target_id}/role",
        headers=_auth(owner_token),
        json={"role": "admin"},
    )
    assert role_response.status_code == 200, role_response.text
    assert role_response.json()["user"]["role"] == "admin"

    delete_response = client.delete(
        f"/api/admin/users/{target_id}",
        headers=_auth(owner_token),
    )
    assert delete_response.status_code == 200, delete_response.text


def test_owner_can_delete_user_with_email_audit_events(client):
    owner_email = f"owner_delete_email_{secrets.token_hex(4)}@calltone.ai"
    _create_user(owner_email, "owner")
    owner_token = _login(client, owner_email)

    target_email = f"delete_email_event_{secrets.token_hex(4)}@calltone.ai"
    target_id = _create_user(target_email, "viewer")
    event_id = _create_email_event(target_id, target_email)

    delete_response = client.delete(
        f"/api/admin/users/{target_id}",
        headers=_auth(owner_token),
    )

    assert delete_response.status_code == 200, delete_response.text

    db = SessionLocal()
    try:
        detached_event = db.query(EmailEvent).filter(EmailEvent.id == event_id).first()
        assert detached_event is not None
        assert detached_event.recipient_user_id is None
        assert detached_event.recipient_email == target_email
    finally:
        db.close()


def test_unlinked_agent_dashboard_does_not_leak_global_scores(client):
    _create_other_agent_report(score=97.0)
    agent_email = f"unlinked_agent_{secrets.token_hex(4)}@calltone.ai"
    _create_user(agent_email, "agent")
    agent_token = _login(client, agent_email)

    response = client.get("/api/agent/dashboard", headers=_auth(agent_token))

    assert response.status_code == 403, response.text
