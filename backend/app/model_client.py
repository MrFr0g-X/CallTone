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


def configured() -> bool:
    return bool(os.getenv("MODEL_SERVER_URL"))


def _base_url() -> str:
    url = os.getenv("MODEL_SERVER_URL")
    if not url:
        raise ModelServerError("MODEL_SERVER_URL is not set")
    return url.rstrip("/")


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

    url = f"{_base_url()}/v1/analyze"
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
            extra={"event": "submit_ok", "job_id": job_id},
        )
        return job_id

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


def put_context(company: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Mirror a backend context JSON to the Tier-3 model server."""
    url = f"{_base_url()}/v1/contexts/{quote(company, safe='')}"
    r = httpx.put(
        url,
        headers={**_auth_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=POLL_READ_TIMEOUT_SECONDS,
    )
    if r.status_code >= 400:
        raise ModelServerError(f"put_context failed: HTTP {r.status_code} {r.text[:400]}")
    body = r.json()
    return body if isinstance(body, dict) else {"ok": True}


def poll(job_id: str) -> dict[str, Any]:
    """Return ``{status, progress_pct, error?, …}`` for *job_id*."""
    url = f"{_base_url()}/v1/jobs/{job_id}"
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
    url = f"{_base_url()}/v1/jobs/{job_id}/result"
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
