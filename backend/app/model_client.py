"""Client shim the backend uses to talk to the Tier-3 model server.

Two-tier architecture (see ``docs/DEMO_DEPLOYMENT_STUDY.md``): the backend
forwards every audio upload to the model server, which runs the GPU
pipeline and returns a QA report. This module hides the HTTP surface
behind three small functions: ``submit``, ``poll``, ``fetch_result``.

Configured via env vars:
  - ``MODEL_SERVER_URL``    — base URL, e.g. ``http://1.2.3.4:8080``.
                              If unset, ``configured()`` returns False and
                              the backend falls back to local subprocess.
  - ``MODEL_SERVER_TOKEN``  — bearer token shared with the model server.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

log = logging.getLogger("calltone.model_client")

# Timeouts: connect is short (the server is a known IP); read is long
# because the first /analyze call waits for upload upstream to complete.
# Individual polls use a much shorter read timeout.
CONNECT_TIMEOUT_SECONDS = 10.0
UPLOAD_READ_TIMEOUT_SECONDS = 600.0
POLL_READ_TIMEOUT_SECONDS = 15.0
MAX_RETRIES = 3


class ModelServerError(RuntimeError):
    """Raised when the model server is unreachable or returns an error body."""


# Composite job handle: when a GPU pool is configured we prefix the job_id with
# the server that owns it so poll/fetch_result route back to the right GPU.
# Single-server deployments keep the bare job_id (backward compatible).
HANDLE_DELIM = "|@|"
HEALTH_TTL_SECONDS = 15.0
_rr_counter = 0
_health_cache: dict[str, tuple[float, bool]] = {}


def _server_urls() -> list[str]:
    """All configured model-server base URLs.

    ``MODEL_SERVER_URLS`` (comma-separated) defines a GPU pool; ``MODEL_SERVER_URL``
    is the single-server fallback. Either enables the two-tier path.
    """
    raw = os.getenv("MODEL_SERVER_URLS") or os.getenv("MODEL_SERVER_URL") or ""
    return [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]


def configured() -> bool:
    return bool(_server_urls())


def _base_url() -> str:
    """Default target for server-agnostic ops (health, contexts, scan)."""
    urls = _server_urls()
    if not urls:
        raise ModelServerError("MODEL_SERVER_URL / MODEL_SERVER_URLS is not set")
    return urls[0]


def _is_healthy(url: str) -> bool:
    """Cheap cached health probe so a dead GPU is skipped by the balancer."""
    now = time.time()
    cached = _health_cache.get(url)
    if cached and now - cached[0] < HEALTH_TTL_SECONDS:
        return cached[1]
    try:
        ok = httpx.get(f"{url}/v1/health", timeout=2.0).status_code < 400
    except httpx.RequestError:
        ok = False
    _health_cache[url] = (now, ok)
    return ok


def _select_base_url() -> str:
    """Round-robin a job across healthy GPUs (the load balancer)."""
    global _rr_counter
    urls = _server_urls()
    if not urls:
        raise ModelServerError("MODEL_SERVER_URL / MODEL_SERVER_URLS is not set")
    if len(urls) == 1:
        return urls[0]
    healthy = [u for u in urls if _is_healthy(u)] or urls
    _rr_counter += 1
    return healthy[_rr_counter % len(healthy)]


def _make_handle(url: str, job_id: str) -> str:
    return job_id if len(_server_urls()) <= 1 else f"{url}{HANDLE_DELIM}{job_id}"


def _split_handle(handle: str) -> tuple[str, str]:
    if HANDLE_DELIM in handle:
        url, job_id = handle.split(HANDLE_DELIM, 1)
        return url.rstrip("/"), job_id
    return _base_url(), handle


def _auth_headers() -> dict[str, str]:
    token = os.getenv("MODEL_SERVER_TOKEN")
    if not token:
        raise ModelServerError("MODEL_SERVER_TOKEN is not set")
    return {"Authorization": f"Bearer {token}"}


def _retry_sleep(attempt: int) -> None:
    # Exponential backoff: 1s, 2s, 4s.
    time.sleep(2 ** (attempt - 1))


def model_server_health(timeout: float = 2.0) -> dict[str, Any]:
    """Probe the remote /v1/health endpoint. Used by the readiness check;
    short timeout so a paused Vast instance doesn't hang the probe."""
    url = f"{_base_url()}/v1/health"
    resp = httpx.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def submit(
    audio_path: str | Path,
    *,
    company: str,
    speakers: int | None = None,
    filename: str | None = None,
    asr_engine: str = "fasterwhisper",
    report_mode: str = "narrative",
    use_consensus: bool = False,
) -> str:
    """Upload audio to /v1/analyze and return the job_id."""
    path = Path(audio_path)
    if not path.is_file():
        raise ModelServerError(f"audio file not found: {path}")

    server = _select_base_url()
    url = f"{server}/v1/analyze"
    display_name = filename or path.name

    data: dict[str, Any] = {
        "company": company,
        "asr_engine": asr_engine,
        "report_mode": report_mode,
        "use_consensus": "true" if use_consensus else "false",
    }
    if speakers is not None:
        data["speakers"] = str(speakers)

    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with path.open("rb") as fh:
                files = {"audio": (display_name, fh, "audio/wav")}
                r = httpx.post(
                    url,
                    headers=_auth_headers(),
                    data=data,
                    files=files,
                    timeout=httpx.Timeout(
                        connect=CONNECT_TIMEOUT_SECONDS,
                        read=UPLOAD_READ_TIMEOUT_SECONDS,
                        write=UPLOAD_READ_TIMEOUT_SECONDS,
                        pool=UPLOAD_READ_TIMEOUT_SECONDS,
                    ),
                )
        except httpx.RequestError as exc:
            last_err = exc
            log.warning(
                "model_client.submit.connect_fail",
                extra={"event": "submit_connect_fail", "attempt": attempt, "err": str(exc)},
            )
            if attempt < MAX_RETRIES:
                _retry_sleep(attempt)
                continue
            raise ModelServerError(f"model server unreachable: {exc}") from exc

        # 4xx / 5xx indicate real failures — no retry, propagate.
        if r.status_code >= 400:
            raise ModelServerError(
                f"submit failed: HTTP {r.status_code} {r.text[:400]}"
            )
        body = r.json()
        job_id = body.get("job_id")
        if not isinstance(job_id, str):
            raise ModelServerError(f"malformed /analyze response: {body!r}")
        log.info(
            "model_client.submit.ok",
            extra={"event": "submit_ok", "job_id": job_id, "server": server},
        )
        return _make_handle(server, job_id)

    raise ModelServerError(f"submit exhausted retries: {last_err}")


def list_contexts() -> list[dict[str, Any]]:
    """Return company contexts known by the Tier-3 model server."""
    url = f"{_base_url()}/v1/contexts"
    r = httpx.get(url, headers=_auth_headers(), timeout=POLL_READ_TIMEOUT_SECONDS)
    if r.status_code >= 400:
        raise ModelServerError(f"list_contexts failed: HTTP {r.status_code} {r.text[:400]}")
    body = r.json()
    contexts = body.get("contexts", [])
    return contexts if isinstance(contexts, list) else []


def get_context(company: str) -> dict[str, Any] | None:
    """Fetch one model-server context. Returns None when missing."""
    url = f"{_base_url()}/v1/contexts/{quote(company, safe='')}"
    r = httpx.get(url, headers=_auth_headers(), timeout=POLL_READ_TIMEOUT_SECONDS)
    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        raise ModelServerError(f"get_context failed: HTTP {r.status_code} {r.text[:400]}")
    body = r.json()
    return body if isinstance(body, dict) else None


def context_exists(company: str) -> bool:
    return get_context(company) is not None


def scan_injection(text: str) -> dict[str, Any]:
    """Run the full prompt-injection scan (static + LLM) on the model server.

    Used by the context-ticket gate: the LLM detector can only run where the
    model + skill_runtime live. Read timeout is generous because the first call
    may cold-load the model.
    """
    url = f"{_base_url()}/v1/scan-injection"
    r = httpx.post(
        url,
        headers=_auth_headers(),
        json={"text": text},
        timeout=httpx.Timeout(connect=5.0, read=180.0, write=10.0, pool=5.0),
    )
    if r.status_code >= 400:
        raise ModelServerError(f"scan_injection failed: HTTP {r.status_code} {r.text[:400]}")
    body = r.json()
    if not isinstance(body, dict):
        raise ModelServerError("scan_injection returned non-dict")
    return body


def put_context(company: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Mirror a backend context JSON to *every* GPU in the pool.

    In a multi-GPU deployment any server may score a given tenant, so the
    company context must exist on all of them. Succeeds if at least one
    server accepts; raises only when every server fails.
    """
    path = f"/v1/contexts/{quote(company, safe='')}"
    headers = {**_auth_headers(), "Content-Type": "application/json"}
    result: dict[str, Any] = {"ok": True}
    last_err: str | None = None
    ok_any = False
    for base in _server_urls():
        try:
            r = httpx.put(f"{base}{path}", headers=headers, json=payload,
                          timeout=POLL_READ_TIMEOUT_SECONDS)
        except httpx.RequestError as exc:
            last_err = f"{base}: {exc}"
            continue
        if r.status_code >= 400:
            last_err = f"{base}: HTTP {r.status_code} {r.text[:200]}"
            continue
        ok_any = True
        body = r.json()
        if isinstance(body, dict):
            result = body
    if not ok_any:
        raise ModelServerError(f"put_context failed on all servers: {last_err}")
    return result


def poll(job_id: str) -> dict[str, Any]:
    """Return ``{status, progress_pct, error?, …}`` for *job_id*."""
    base, jid = _split_handle(job_id)
    url = f"{base}/v1/jobs/{jid}"
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = httpx.get(
                url,
                headers=_auth_headers(),
                timeout=httpx.Timeout(
                    connect=CONNECT_TIMEOUT_SECONDS,
                    read=POLL_READ_TIMEOUT_SECONDS,
                    write=POLL_READ_TIMEOUT_SECONDS,
                    pool=POLL_READ_TIMEOUT_SECONDS,
                ),
            )
        except httpx.RequestError as exc:
            last_err = exc
            if attempt < MAX_RETRIES:
                _retry_sleep(attempt)
                continue
            raise ModelServerError(f"model server unreachable: {exc}") from exc

        if r.status_code == 404:
            raise ModelServerError(f"unknown job: {job_id}")
        if r.status_code >= 400:
            raise ModelServerError(
                f"poll failed: HTTP {r.status_code} {r.text[:400]}"
            )
        return r.json()

    raise ModelServerError(f"poll exhausted retries: {last_err}")


def fetch_result(job_id: str) -> dict[str, Any]:
    """Fetch the final QA report; raises if the job isn't done."""
    base, jid = _split_handle(job_id)
    url = f"{base}/v1/jobs/{jid}/result"
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = httpx.get(
                url,
                headers=_auth_headers(),
                timeout=httpx.Timeout(
                    connect=CONNECT_TIMEOUT_SECONDS,
                    read=POLL_READ_TIMEOUT_SECONDS,
                    write=POLL_READ_TIMEOUT_SECONDS,
                    pool=POLL_READ_TIMEOUT_SECONDS,
                ),
            )
        except httpx.RequestError as exc:
            last_err = exc
            if attempt < MAX_RETRIES:
                _retry_sleep(attempt)
                continue
            raise ModelServerError(f"model server unreachable: {exc}") from exc

        if r.status_code == 409:
            raise ModelServerError(f"result not ready: {r.json().get('detail')}")
        if r.status_code >= 400:
            raise ModelServerError(
                f"fetch_result failed: HTTP {r.status_code} {r.text[:400]}"
            )
        body = r.json()
        result = body.get("result")
        if not isinstance(result, dict):
            raise ModelServerError(f"malformed /result response: {body!r}")
        return result

    raise ModelServerError(f"fetch_result exhausted retries: {last_err}")
