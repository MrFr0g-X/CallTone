"""Tests for the multi-GPU model-server pool (the Tier-3 load balancer).

Single-server behavior must stay byte-identical (bare job_id); multi-server
adds round-robin distribution, health-aware skipping, sticky job routing, and
context broadcast. httpx is faked so no network is touched.
"""

import pytest

from app import model_client as mc


class FakeResp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("MODEL_SERVER_TOKEN", "tok")
    mc._health_cache.clear()
    mc._rr_counter = 0
    yield
    mc._health_cache.clear()
    mc._rr_counter = 0


def _audio(tmp_path):
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....WAVE")
    return str(p)


def test_single_server_returns_bare_job_id(monkeypatch, tmp_path):
    monkeypatch.delenv("MODEL_SERVER_URLS", raising=False)
    monkeypatch.setenv("MODEL_SERVER_URL", "http://gpu1:8080")
    monkeypatch.setattr(mc.httpx, "post", lambda *a, **k: FakeResp(200, {"job_id": "j1"}))

    handle = mc.submit(_audio(tmp_path), company="acme")
    assert handle == "j1"  # no routing prefix when single server


def test_round_robin_distributes_across_servers(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_SERVER_URLS", "http://gpu1:8080,http://gpu2:8080")
    posts = []

    def fake_post(url, *a, **k):
        posts.append(url)
        return FakeResp(200, {"job_id": "j"})

    monkeypatch.setattr(mc.httpx, "post", fake_post)
    monkeypatch.setattr(mc.httpx, "get", lambda *a, **k: FakeResp(200, {"ok": True}))  # healthy

    h1 = mc.submit(_audio(tmp_path), company="acme")
    h2 = mc.submit(_audio(tmp_path), company="acme")

    servers = {p.split("/v1/")[0] for p in posts}
    assert servers == {"http://gpu1:8080", "http://gpu2:8080"}  # both used
    assert mc.HANDLE_DELIM in h1 and mc.HANDLE_DELIM in h2
    assert h1.split(mc.HANDLE_DELIM)[0] != h2.split(mc.HANDLE_DELIM)[0]


def test_handle_routes_poll_and_fetch(monkeypatch):
    monkeypatch.setenv("MODEL_SERVER_URLS", "http://gpu1:8080,http://gpu2:8080")
    seen = []

    def fake_get(url, *a, **k):
        seen.append(url)
        if url.endswith("/result"):
            return FakeResp(200, {"result": {"score": 1}})
        return FakeResp(200, {"status": "completed"})

    monkeypatch.setattr(mc.httpx, "get", fake_get)
    handle = f"http://gpu2:8080{mc.HANDLE_DELIM}job-x"

    mc.poll(handle)
    mc.fetch_result(handle)

    assert seen[0] == "http://gpu2:8080/v1/jobs/job-x"
    assert seen[1] == "http://gpu2:8080/v1/jobs/job-x/result"


def test_unhealthy_server_is_skipped(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_SERVER_URLS", "http://gpu1:8080,http://gpu2:8080")

    def fake_health(url, *a, **k):
        # gpu1 is down, gpu2 is healthy
        return FakeResp(200 if "gpu2" in url else 503)

    monkeypatch.setattr(mc.httpx, "get", fake_health)
    monkeypatch.setattr(mc.httpx, "post", lambda url, *a, **k: FakeResp(200, {"job_id": "j"}))

    handles = [mc.submit(_audio(tmp_path), company="acme") for _ in range(4)]
    assert all(h.split(mc.HANDLE_DELIM)[0] == "http://gpu2:8080" for h in handles)


def test_put_context_broadcasts_to_all_servers(monkeypatch):
    monkeypatch.setenv("MODEL_SERVER_URLS", "http://gpu1:8080,http://gpu2:8080")
    puts = []

    def fake_put(url, *a, **k):
        puts.append(url)
        return FakeResp(200, {"ok": True})

    monkeypatch.setattr(mc.httpx, "put", fake_put)
    mc.put_context("acme", {"x": 1})

    targets = {u.split("/v1/")[0] for u in puts}
    assert targets == {"http://gpu1:8080", "http://gpu2:8080"}
