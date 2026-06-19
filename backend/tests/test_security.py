"""Security-control tests — covers C-1, C-2, C-4, C-5, C-6 from
docs/SECURITY_PLAN.md.

C-3 (SECRET_KEY startup guard) is verified manually because the guard
fires at import time and exercising it inside an already-imported pytest
process would require re-importing the entire module graph.
"""

import logging
from types import SimpleNamespace

import pytest

from app.main import _sanitize_filename
from app.security_headers import _client_ip, _docs_allowed, _is_docs_path
from app.rate_limit import login_limiter, invite_accept_limiter
from app.database import SessionLocal
from app.models import Client


# ── C-2: HTTP security headers ──────────────────────────────────────────────


def _bankserv_client_id() -> int:
    db = SessionLocal()
    try:
        return db.query(Client).filter(Client.name == "BankServ Global").first().id
    finally:
        db.close()


@pytest.mark.parametrize(
    "header",
    [
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Cross-Origin-Opener-Policy",
        "Cross-Origin-Resource-Policy",
        "Content-Security-Policy",
    ],
)
def test_security_headers_present_on_root(client, header):
    r = client.get("/")
    assert r.status_code == 200
    assert header in r.headers, f"missing security header: {header}"


def test_x_frame_options_denies_framing(client):
    r = client.get("/")
    assert r.headers["X-Frame-Options"] == "DENY"


def test_csp_disallows_inline_script(client):
    r = client.get("/")
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src", 1)[1].split(";", 1)[0]


def test_hsts_absent_in_debug(client):
    # conftest does not set DEBUG=false, so HSTS must not appear locally.
    r = client.get("/")
    assert "Strict-Transport-Security" not in r.headers


def test_docs_paths_are_classified_for_production_lockdown():
    assert _is_docs_path("/docs")
    assert _is_docs_path("/docs/oauth2-redirect")
    assert _is_docs_path("/redoc")
    assert _is_docs_path("/openapi.json")
    assert not _is_docs_path("/api/health")


def test_docs_lock_uses_edge_real_ip_not_spoofed_forwarded_client(monkeypatch):
    monkeypatch.setattr("app.security_headers.settings.DEBUG", False)
    monkeypatch.setattr("app.security_headers.settings.DOCS_ALLOWED_IPS", "102.191.217.207")
    request = SimpleNamespace(
        headers={"x-real-ip": "117.18.102.40"},
        # Simulates a spoofed/forwarded client value. The docs gate must ignore it.
        client=SimpleNamespace(host="102.191.217.207"),
    )
    assert _client_ip(request) == "117.18.102.40"
    assert _docs_allowed(request) is False


# ── C-4: Filename sanitization ──────────────────────────────────────────────


def test_filename_sanitization_strips_traversal():
    assert "/" not in _sanitize_filename("../../etc/passwd")
    assert "\\" not in _sanitize_filename("..\\..\\etc\\passwd")
    # Result must not start with a dot (would be a hidden file)
    assert not _sanitize_filename("../../etc/passwd").startswith(".")


def test_filename_sanitization_caps_length():
    long_name = "a" * 200 + ".wav"
    out = _sanitize_filename(long_name)
    assert len(out) <= 80
    # Extension is preserved when present
    assert out.endswith(".wav")


def test_filename_sanitization_handles_empty_and_none():
    assert _sanitize_filename("") == "upload.bin"
    assert _sanitize_filename(None) == "upload.bin"


def test_filename_sanitization_replaces_control_chars():
    # NUL bytes must not survive
    out = _sanitize_filename("audio\x00.wav")
    assert "\x00" not in out


def test_filename_sanitization_keeps_normal_names():
    assert _sanitize_filename("normal.wav") == "normal.wav"
    assert _sanitize_filename("call_2026-04-19.mp3") == "call_2026-04-19.mp3"


# ── C-5: Password length window ─────────────────────────────────────────────


def _create_invite(client, admin_token):
    r = client.post(
        "/api/admin/users/invite",
        json={"name": "Test User", "email": "lengthtest@calltone.ai", "role": "qa", "clientId": _bankserv_client_id()},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["inviteUrl"].rsplit("=", 1)[1]


def test_password_too_long_rejected(client, admin_token):
    invite_accept_limiter.reset()
    token = _create_invite(client, admin_token)
    long_pw = "A" * 100  # 100 ASCII bytes > 72-byte bcrypt cap
    r = client.post(
        "/api/auth/invite/accept",
        json={"token": token, "password": long_pw, "confirmPassword": long_pw},
    )
    assert r.status_code == 400
    assert "72 bytes" in r.json()["detail"]


def test_password_too_short_still_rejected(client, admin_token):
    """Regression: existing 8-char minimum must still apply."""
    invite_accept_limiter.reset()
    # Use a brand new email so the invite endpoint is happy
    inv = client.post(
        "/api/admin/users/invite",
        json={"name": "Short PW", "email": "shortpw@calltone.ai", "role": "qa", "clientId": _bankserv_client_id()},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert inv.status_code == 200, inv.text
    token = inv.json()["inviteUrl"].rsplit("=", 1)[1]

    r = client.post(
        "/api/auth/invite/accept",
        json={"token": token, "password": "short", "confirmPassword": "short"},
    )
    assert r.status_code == 400
    assert "at least 8" in r.json()["detail"]


# ── C-1: Login rate limit ───────────────────────────────────────────────────


def test_login_rate_limit_eventually_trips(client, monkeypatch):
    """Lower the limit via the limiter's max_calls and confirm 429."""
    login_limiter.reset()
    original = login_limiter.max_calls
    monkeypatch.setattr(login_limiter, "max_calls", 3)
    try:
        # Three legitimate-shaped failures are admitted (return 401).
        for _ in range(3):
            r = client.post(
                "/api/auth/login",
                json={"email": "noone@calltone.ai", "password": "wrong"},
            )
            assert r.status_code == 401
        # The fourth attempt within the window must be 429.
        r = client.post(
            "/api/auth/login",
            json={"email": "noone@calltone.ai", "password": "wrong"},
        )
        assert r.status_code == 429
        assert "Retry-After" in r.headers
    finally:
        monkeypatch.setattr(login_limiter, "max_calls", original)
        login_limiter.reset()


# ── C-6: Structured security log lines ──────────────────────────────────────


def test_failed_login_emits_security_event(client, caplog):
    login_limiter.reset()
    with caplog.at_level(logging.WARNING, logger="calltone.api"):
        r = client.post(
            "/api/auth/login",
            json={"email": "ghost@calltone.ai", "password": "nope"},
        )
    assert r.status_code == 401
    matching = [
        rec
        for rec in caplog.records
        if getattr(rec, "event", None) == "login_failed"
    ]
    assert matching, "expected a login_failed event in the log records"
    assert getattr(matching[-1], "email", None) == "ghost@calltone.ai"


def test_role_change_emits_security_event(client, admin_token, caplog):
    # Pick an agent seed user — NOT the QA user, whose role is consumed by
    # other test fixtures (qa_token). Mutating QA here would 403 every
    # later test that uploads a call.
    users_r = client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert users_r.status_code == 200, users_r.text
    target = next(
        u for u in users_r.json()["users"]
        if u["role"] == "agent"
    )
    original_role = target["role"]

    with caplog.at_level(logging.WARNING, logger="calltone.api"):
        r = client.patch(
            f"/api/admin/users/{target['id']}/role",
            json={"role": "viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    try:
        assert r.status_code == 200, r.text
        matching = [
            rec
            for rec in caplog.records
            if getattr(rec, "event", None) == "role_changed"
        ]
        assert matching, "expected a role_changed event in the log records"
        rec = matching[-1]
        assert rec.target_user_id == target["id"]
        assert rec.new_role == "viewer"
    finally:
        # Restore so no downstream test inherits a mutated seed user.
        client.patch(
            f"/api/admin/users/{target['id']}/role",
            json={"role": original_role},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
