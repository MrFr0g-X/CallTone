"""Health endpoint tests.

The basic /health is intentionally cheap (load-balancer probe).
The /health/detailed endpoint checks DB, model dir, and disk so ops
can diagnose a degraded service without reading logs.
"""


def test_health_basic_is_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_detailed_returns_full_payload(client):
    r = client.get("/api/health/detailed")
    assert r.status_code == 200
    body = r.json()

    assert body["status"] in {"ok", "degraded"}
    assert "version" in body
    assert isinstance(body["uptime_seconds"], int)
    assert body["uptime_seconds"] >= 0

    checks = body["checks"]
    assert "database" in checks
    assert "models_dir" in checks
    assert "disk" in checks
    # Database must be reachable in tests (we have a temp SQLite file)
    assert checks["database"]["ok"] is True


def test_health_endpoints_require_no_auth(client):
    """Both endpoints must work without a bearer token — they're probes."""
    r1 = client.get("/api/health")
    r2 = client.get("/api/health/detailed")
    assert r1.status_code == 200
    assert r2.status_code == 200
