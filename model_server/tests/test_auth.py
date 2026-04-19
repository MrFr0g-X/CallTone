"""D-5 auth middleware tests.

Covers the three branches of ``BearerAndIPMiddleware``:
  1. Public path (``/v1/health``) bypasses auth.
  2. IP allowlist rejection → 403.
  3. Missing / wrong bearer token → 401.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


def _build_client() -> TestClient:
    from model_server.main import create_app

    return TestClient(create_app())


def test_health_bypasses_auth():
    """No Authorization header, no IP restriction — still 200."""
    c = _build_client()
    r = c.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_missing_token_returns_401():
    c = _build_client()
    r = c.get("/v1/jobs/anything")
    assert r.status_code == 401
    assert r.json()["detail"] == "unauthorized"


def test_wrong_token_returns_401():
    c = _build_client()
    r = c.get(
        "/v1/jobs/anything",
        headers={"Authorization": "Bearer nope-nope-nope"},
    )
    assert r.status_code == 401


def test_correct_token_reaches_handler():
    c = _build_client()
    headers = {"Authorization": f"Bearer {os.environ['MODEL_SERVER_TOKEN']}"}
    r = c.get("/v1/jobs/missing-id", headers=headers)
    # Authenticated but job doesn't exist → 404 (not 401/403).
    assert r.status_code == 404


def test_non_bearer_scheme_rejected():
    c = _build_client()
    r = c.get(
        "/v1/jobs/anything",
        headers={"Authorization": f"Token {os.environ['MODEL_SERVER_TOKEN']}"},
    )
    assert r.status_code == 401


def test_ip_allowlist_blocks_unknown_client(monkeypatch):
    """TestClient reports IP ``testclient``; if we only allow 91.99.208.254,
    the request must be rejected at the network layer."""
    monkeypatch.setenv("ALLOWED_IPS", "91.99.208.254")
    from model_server.main import create_app

    c = TestClient(create_app())
    r = c.get(
        "/v1/jobs/anything",
        headers={"Authorization": f"Bearer {os.environ['MODEL_SERVER_TOKEN']}"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden"


def test_server_misconfigured_without_token(monkeypatch):
    monkeypatch.setenv("MODEL_SERVER_TOKEN", "")
    from model_server.main import create_app

    c = TestClient(create_app())
    r = c.get("/v1/jobs/anything")
    # Public path still works.
    assert c.get("/v1/health").status_code == 200
    # Protected path returns 500 — a missing shared secret is operator error,
    # and we must refuse rather than silently accept any request.
    assert r.status_code == 500


def test_empty_allowlist_disables_ip_check(monkeypatch):
    """An empty ALLOWED_IPS falls back to token-only — useful for local dev."""
    monkeypatch.setenv("ALLOWED_IPS", "")
    from model_server.main import create_app

    c = TestClient(create_app())
    r = c.get(
        "/v1/jobs/nothing",
        headers={"Authorization": f"Bearer {os.environ['MODEL_SERVER_TOKEN']}"},
    )
    assert r.status_code == 404  # got past auth to the handler
