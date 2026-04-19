"""Demo readiness probe — run before opening the browser.

Checks every tier of the demo stack and prints a GO/NO-GO summary.

  Tier 3 (model server) → http://127.0.0.1:8090/v1/health    (via SSH tunnel)
  Tier 2 (backend)      → http://127.0.0.1:8000/api/health/detailed
  Tier 1 (frontend)     → http://127.0.0.1:8080/

Usage:
    python scripts/demo_ready.py

Env vars honoured:
    MODEL_SERVER_URL     default http://127.0.0.1:8090
    MODEL_SERVER_TOKEN   required for the authenticated /v1/jobs/ping probe
    BACKEND_URL          default http://127.0.0.1:8000
    FRONTEND_URL         default http://127.0.0.1:8080
"""

from __future__ import annotations

import os
import sys

import httpx

OK = "[ OK ]"
WARN = "[WARN]"
FAIL = "[FAIL]"


def _probe(label: str, url: str, *, timeout: float = 3.0, **kwargs):
    try:
        r = httpx.get(url, timeout=timeout, **kwargs)
    except httpx.RequestError as exc:
        return FAIL, f"{label}: unreachable ({exc.__class__.__name__})"
    if r.status_code >= 400:
        return FAIL, f"{label}: HTTP {r.status_code}"
    return OK, f"{label}: HTTP {r.status_code}"


def main() -> int:
    model_url = os.getenv("MODEL_SERVER_URL", "http://127.0.0.1:8090").rstrip("/")
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:8080").rstrip("/")
    token = os.getenv("MODEL_SERVER_TOKEN", "")

    results: list[tuple[str, str]] = []

    # ── Tier 3 ───────────────────────────────────────────────────────────
    results.append(_probe("Tier 3 /v1/health", f"{model_url}/v1/health"))
    if token:
        # 404 on a non-existent job means auth + IP passed — that's what we
        # want. 401/403 means the token or allowlist is wrong.
        status, msg = _probe(
            "Tier 3 auth",
            f"{model_url}/v1/jobs/readiness-probe-nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )
        if "404" in msg:
            status = OK
            msg = "Tier 3 auth: token accepted (404 on probe job = expected)"
        results.append((status, msg))
    else:
        results.append((WARN, "Tier 3 auth: MODEL_SERVER_TOKEN not set — skipped"))

    # ── Tier 2 ───────────────────────────────────────────────────────────
    results.append(_probe("Tier 2 /api/health/detailed", f"{backend_url}/api/health/detailed"))

    # Confirm the backend sees MODEL_SERVER_URL the same way we do.
    try:
        r = httpx.get(f"{backend_url}/api/health/detailed", timeout=3.0)
        if r.status_code == 200:
            body = r.json()
            # The endpoint may not surface env — but dispatcher check is implicit:
            # if the backend's MODEL_SERVER_URL is unset, it'll run locally (fine
            # for dev, surprising for remote demo). Warn only.
            if os.getenv("MODEL_SERVER_URL"):
                results.append((OK, "Tier 2 dispatch: MODEL_SERVER_URL exported in this shell"))
            else:
                results.append((WARN, "Tier 2 dispatch: MODEL_SERVER_URL is NOT set — backend will run the pipeline locally"))
            _ = body  # shape varies; not asserting
    except httpx.RequestError:
        pass  # already reported by the earlier probe

    # ── Tier 1 ───────────────────────────────────────────────────────────
    results.append(_probe("Tier 1 frontend", frontend_url))

    # ── print ────────────────────────────────────────────────────────────
    print()
    print(f"Demo readiness probe — {os.getcwd()}")
    print("─" * 70)
    for tag, msg in results:
        print(f"  {tag}  {msg}")
    print("─" * 70)

    failed = [m for tag, m in results if tag == FAIL]
    warned = [m for tag, m in results if tag == WARN]

    if failed:
        print()
        print("NO-GO — fix the FAIL rows above, then re-run this script.")
        print()
        print("Common fixes:")
        print("  * Tier 3 unreachable  → SSH tunnel isn't open.")
        print("      ssh -L 8090:localhost:8080 -p <vast-port> root@<vast-ip>")
        print("  * Tier 3 auth         → MODEL_SERVER_TOKEN doesn't match Vast's value.")
        print("      on Vast: grep MODEL_SERVER_TOKEN model_server/.env")
        print("  * Tier 2 unreachable  → backend isn't running.")
        print("      run_local.bat --backend-only")
        print("  * Tier 1 unreachable  → frontend isn't running.")
        print("      run_local.bat --frontend-only")
        return 1

    print()
    if warned:
        print("GO (with warnings). Open:")
    else:
        print("GO. Open:")
    print(f"    {frontend_url}")
    print()
    print("Log in, click 'Upload call', pick a WAV/MP3.")
    print("Status should transition: queued → transcribing → scoring → completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
