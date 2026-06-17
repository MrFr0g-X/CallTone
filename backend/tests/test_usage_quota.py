"""Per-tenant usage-quota enforcement tests.

Covers: unlimited-by-default (backward compatible), real-time monthly metering,
the /usage transparency endpoint, hard-quota upload block (429), and soft-quota
metered overage (not blocked). Mirrors the tenant harness in
test_tenant_isolation.py.
"""
import io
import secrets
from datetime import datetime, timezone

from app import main as app_main
from app.database import SessionLocal
from app.models import Call, Client, ClientPolicy, Employee, Role, User
from app.security import hash_password


def _auth(token): return {"Authorization": f"Bearer {token}"}


def _login(client, email, password="TenantPass123!"):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _client_id(name="MetroBoost Telecom"):
    db = SessionLocal()
    try:
        return db.query(Client).filter(Client.name == name).first().id
    finally:
        db.close()


def _make_qa(client_id):
    email = f"quota_qa_{secrets.token_hex(4)}@calltone.ai"
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "qa").first()
        u = User(full_name="Quota QA", email=email, password_hash=hash_password("TenantPass123!"),
                 role_id=role.id, client_id=client_id, is_active=True)
        db.add(u); db.commit()
        return email
    finally:
        db.close()


def _set_quota(client_id, quota, enforcement="hard"):
    db = SessionLocal()
    try:
        p = db.query(ClientPolicy).filter(ClientPolicy.client_id == client_id).first()
        if not p:
            p = ClientPolicy(client_id=client_id)
            db.add(p)
        p.monthly_call_quota = quota
        p.quota_enforcement = enforcement
        p.qa_can_upload_calls = True
        db.commit()
    finally:
        db.close()


def _seed_calls(client_id, n):
    db = SessionLocal()
    try:
        emp = Employee(client_id=client_id, employee_code=f"AG-Q-{secrets.token_hex(3)}",
                       full_name="Quota Agent", role="AGENT")
        db.add(emp); db.flush()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(n):
            db.add(Call(client_id=client_id, employee_id=emp.id,
                        original_filename=f"q-{secrets.token_hex(3)}.wav",
                        status="COMPLETED", created_at=now, updated_at=now))
        db.commit()
    finally:
        db.close()


def _count_calls(client_id):
    db = SessionLocal()
    try:
        return db.query(Call).filter(Call.client_id == client_id).count()
    finally:
        db.close()


# ── unit: metering + status ─────────────────────────────────────────────────

def test_quota_unlimited_by_default():
    cid = _client_id()
    db = SessionLocal()
    try:
        # a policy with no quota set → unlimited (pre-quota behavior)
        st = app_main._quota_status(db, ClientPolicy(client_id=cid), cid)
    finally:
        db.close()
    assert st["monthlyCallQuota"] is None
    assert st["remaining"] is None
    assert st["exceeded"] is False


def test_metering_counts_calls_this_month():
    cid = _client_id()
    before = _count_calls(cid)
    _seed_calls(cid, 3)
    db = SessionLocal()
    try:
        used = app_main._tenant_calls_this_month(db, cid)
    finally:
        db.close()
    assert used >= before + 3


# ── endpoint: transparency ──────────────────────────────────────────────────

def test_usage_endpoint_reports_quota(client):
    cid = _client_id()
    _set_quota(cid, quota=100000, enforcement="hard")  # high so not exceeded
    email = _make_qa(cid)
    token = _login(client, email)
    r = client.get("/api/usage", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["monthlyCallQuota"] == 100000
    assert body["enforcement"] == "hard"
    assert body["remaining"] == 100000 - body["used"]
    assert body["exceeded"] is False


# ── enforcement: hard blocks, soft allows ───────────────────────────────────

def _upload(client, token):
    return client.post(
        "/api/calls/upload",
        headers=_auth(token),
        files={"file": ("x.wav", io.BytesIO(b"RIFFxxxxWAVE"), "audio/wav")},
        data={"agent_id": "", "asr_engine": "fasterwhisper"},
    )


def test_hard_quota_blocks_upload_with_429(client):
    cid = _client_id()
    used = _count_calls(cid)
    _set_quota(cid, quota=used, enforcement="hard")  # already at/over quota
    token = _login(client, _make_qa(cid))
    r = _upload(client, token)
    assert r.status_code == 429, r.text
    assert "quota" in r.json()["detail"].lower()


def test_soft_quota_does_not_block_upload(client):
    cid = _client_id()
    used = _count_calls(cid)
    _set_quota(cid, quota=used, enforcement="soft")  # over quota but soft
    token = _login(client, _make_qa(cid))
    r = _upload(client, token)
    # Soft quota must NOT 429; it may fail later (no agent) but never on quota.
    assert r.status_code != 429, r.text
