import io
import secrets
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Call, Client, ClientPolicy, Employee, Role, User
from app.security import hash_password


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email: str, password: str = "TenantPass123!") -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _client_id(name: str) -> int:
    db = SessionLocal()
    try:
        return db.query(Client).filter(Client.name == name).first().id
    finally:
        db.close()


def _create_user(email: str, role_name: str, client_id: int | None, password: str = "TenantPass123!") -> int:
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        user = User(
            full_name=f"{role_name.title()} {secrets.token_hex(3)}",
            email=email,
            password_hash=hash_password(password),
            role_id=role.id,
            client_id=client_id,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def _create_agent_call(client_id: int, filename: str = "tenant-call.wav") -> str:
    db = SessionLocal()
    try:
        agent = Employee(
            client_id=client_id,
            employee_code=f"AG-TEN-{secrets.token_hex(3)}",
            full_name="Tenant Isolation Agent",
            role="AGENT",
        )
        db.add(agent)
        db.flush()
        call = Call(
            client_id=client_id,
            employee_id=agent.id,
            original_filename=filename,
            status="COMPLETED",
            call_time=datetime.now(timezone.utc),
        )
        db.add(call)
        db.commit()
        db.refresh(call)
        return call.id
    finally:
        db.close()


def test_tenant_admin_sees_only_own_company_users(client):
    bank_id = _client_id("BankServ Global")
    metro_id = _client_id("MetroBoost Telecom")
    admin_email = f"tenant_admin_{secrets.token_hex(4)}@calltone.ai"
    other_email = f"other_tenant_{secrets.token_hex(4)}@calltone.ai"
    _create_user(admin_email, "admin", bank_id)
    _create_user(other_email, "qa", metro_id)

    token = _login(client, admin_email)
    response = client.get("/api/admin/users", headers=_auth(token))

    assert response.status_code == 200, response.text
    emails = {user["email"] for user in response.json()["users"]}
    assert admin_email in emails
    assert other_email not in emails
    assert "admin@calltone.ai" not in emails


def test_tenant_admin_cannot_create_platform_clients(client):
    bank_id = _client_id("BankServ Global")
    admin_email = f"tenant_client_create_{secrets.token_hex(4)}@calltone.ai"
    _create_user(admin_email, "admin", bank_id)
    token = _login(client, admin_email)

    response = client.post(
        "/api/admin/clients",
        headers=_auth(token),
        json={"name": f"Forbidden Client {secrets.token_hex(3)}", "status": "trial", "plan": "starter"},
    )

    assert response.status_code == 403


def test_tenant_admin_invite_is_forced_to_own_company(client):
    bank_id = _client_id("BankServ Global")
    admin_email = f"tenant_inviter_{secrets.token_hex(4)}@calltone.ai"
    _create_user(admin_email, "admin", bank_id)
    token = _login(client, admin_email)

    invite_email = f"tenant_agent_{secrets.token_hex(4)}@calltone.ai"
    response = client.post(
        "/api/admin/users/invite",
        headers=_auth(token),
        json={"name": "Tenant Agent", "email": invite_email, "role": "agent", "clientId": _client_id("MetroBoost Telecom")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["clientId"] == bank_id

    blocked = client.post(
        "/api/admin/users/invite",
        headers=_auth(token),
        json={"name": "Bad Admin", "email": f"bad_{secrets.token_hex(4)}@calltone.ai", "role": "super_admin"},
    )
    assert blocked.status_code in (400, 403)


def test_tenant_qa_cannot_list_or_open_other_company_calls(client, qa_token):
    bank_call = _create_agent_call(_client_id("BankServ Global"), "bank.wav")
    metro_call = _create_agent_call(_client_id("MetroBoost Telecom"), "metro.wav")

    listing = client.get("/api/qa/calls", headers=_auth(qa_token))
    assert listing.status_code == 200, listing.text
    ids = {row["callId"] for row in listing.json()["calls"]}
    assert bank_call in ids
    assert metro_call not in ids

    detail = client.get(f"/api/qa/calls/{metro_call}", headers=_auth(qa_token))
    assert detail.status_code == 403


def test_tenant_qa_upload_rejects_cross_company_agent(client, qa_token, monkeypatch, tmp_path):
    from app import main as app_main

    metro_id = _client_id("MetroBoost Telecom")
    db = SessionLocal()
    try:
        agent = Employee(
            client_id=metro_id,
            employee_code=f"AG-CROSS-{secrets.token_hex(3)}",
            full_name="Cross Tenant Agent",
            role="AGENT",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        agent_id = agent.id
    finally:
        db.close()

    monkeypatch.setattr(app_main, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(app_main, "_ensure_known_company_context", lambda name: name)

    response = client.post(
        "/api/calls/upload",
        headers=_auth(qa_token),
        data={"agent_id": agent_id, "company_name": "BankServ Global"},
        files={"file": ("sample.wav", io.BytesIO(b"RIFFsmall"), "audio/wav")},
    )

    assert response.status_code == 400
    assert "agent" in response.json()["detail"].lower()


def test_client_policy_platform_and_tenant_updates_are_scoped(client, admin_token):
    bank_id = _client_id("BankServ Global")
    metro_id = _client_id("MetroBoost Telecom")

    platform_update = client.put(
        "/api/admin/client-policy",
        headers=_auth(admin_token),
        json={"clientId": bank_id, "agentCanPlayAudio": True, "agentCanViewEvidence": True},
    )
    assert platform_update.status_code == 200, platform_update.text
    assert platform_update.json()["policy"]["agentCanPlayAudio"] is True
    assert platform_update.json()["policy"]["agentCanViewEvidence"] is True

    tenant_admin_email = f"policy_admin_{secrets.token_hex(4)}@calltone.ai"
    _create_user(tenant_admin_email, "admin", bank_id)
    tenant_token = _login(client, tenant_admin_email)

    tenant_update = client.put(
        "/api/admin/client-policy",
        headers=_auth(tenant_token),
        json={"clientId": metro_id, "agentCanPlayAudio": False, "qaScope": "company"},
    )
    assert tenant_update.status_code == 200, tenant_update.text
    assert tenant_update.json()["policy"]["clientId"] == bank_id
    assert tenant_update.json()["policy"]["agentCanPlayAudio"] is False

    db = SessionLocal()
    try:
        metro_policy = db.query(ClientPolicy).filter(ClientPolicy.client_id == metro_id).first()
        assert metro_policy is not None
        assert metro_policy.agent_can_play_audio is False
    finally:
        db.close()


def test_qa_cannot_mutate_client_policy(client, qa_token):
    response = client.put(
        "/api/admin/client-policy",
        headers=_auth(qa_token),
        json={"agentCanPlayAudio": True},
    )
    assert response.status_code == 403
