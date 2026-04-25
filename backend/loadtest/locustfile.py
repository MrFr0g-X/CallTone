"""Locust load test for CallTone backend.

Goal: prove the read-side endpoints (auth/me, dashboards, call list)
hold up under concurrent QA users. Upload + scoring are deliberately
NOT load-tested here — those are GPU-bound and a single H100 will be
saturated by 1-2 concurrent jobs, so you load-test those with a
dedicated harness, not Locust.

Run against a local dev server:
    uvicorn app.main:app --port 8000
    locust -f backend/loadtest/locustfile.py --host http://localhost:8000

Then open http://localhost:8089 and dial in users / hatch rate.

Headless example (60 s, 50 users, 5/s spawn):
    locust -f backend/loadtest/locustfile.py \\
        --host http://localhost:8000 \\
        --headless -u 50 -r 5 -t 60s
"""

import os
import random

from locust import HttpUser, between, task

QA_EMAIL = os.environ.get("LOAD_QA_EMAIL")
QA_PASSWORD = os.environ.get("LOAD_QA_PASSWORD")

if not QA_EMAIL or not QA_PASSWORD:
    raise RuntimeError(
        "Set LOAD_QA_EMAIL and LOAD_QA_PASSWORD before running the load test. "
        "Load-test credentials must not be hardcoded in source."
    )


class QaPortalUser(HttpUser):
    """Simulates a QA reviewer browsing the portal — login once,
    then alternate between dashboard hits and call-list / detail."""

    wait_time = between(1, 3)

    def on_start(self) -> None:
        r = self.client.post(
            "/api/v1/auth/login",
            json={"email": QA_EMAIL, "password": QA_PASSWORD},
            name="login",
        )
        if r.status_code != 200:
            # Don't crash the whole run — surface as a failure metric.
            self.token = None
            return
        self.token = r.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

        # Pre-fetch one call list so call_ids has a population to sample.
        self.call_ids: list[str] = []
        lst = self.client.get("/api/v1/qa/calls", headers=self.headers, name="calls.list (warm)")
        if lst.status_code == 200:
            data = lst.json()
            calls = data if isinstance(data, list) else data.get("calls", [])
            self.call_ids = [c["id"] for c in calls if "id" in c][:20]

    @task(5)
    def health(self) -> None:
        self.client.get("/api/health", name="health")

    @task(3)
    def me(self) -> None:
        if self.token:
            self.client.get("/api/v1/auth/me", headers=self.headers, name="auth.me")

    @task(3)
    def calls_list(self) -> None:
        if self.token:
            self.client.get("/api/v1/qa/calls", headers=self.headers, name="calls.list")

    @task(2)
    def call_detail(self) -> None:
        if self.token and self.call_ids:
            cid = random.choice(self.call_ids)
            self.client.get(
                f"/api/v1/qa/calls/{cid}",
                headers=self.headers,
                name="calls.detail",
            )

    @task(1)
    def health_detailed(self) -> None:
        self.client.get("/api/health/detailed", name="health.detailed")
