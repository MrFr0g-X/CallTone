"""In-process token-bucket rate limiter.

Defangs credential-stuffing scripts on /auth/login and replay attacks on
/auth/invite/accept without adding a Redis dependency. A single uvicorn
process with ten concurrent reviewers is the documented deployment
target (see docs/SECURITY_STUDY.md §3.2), so module-level state is
sufficient.

If the deployment ever fans out across processes, swap _BUCKETS for a
Redis-backed equivalent — the public surface (`limiter.check(key)`)
stays identical.
"""

import os
import threading
import time
from collections import deque
from typing import Deque, Dict

from fastapi import HTTPException, Request


def _env_int(name: str, default: int) -> int:
    """Read a positive int from env, falling back to ``default`` on bad input."""
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


class RateLimiter:
    """Sliding-window counter keyed on an arbitrary string.

    ``check(key)`` raises ``HTTPException(429)`` when the caller has
    already made ``max_calls`` requests inside the trailing
    ``window_seconds``. A fresh key is admitted immediately.
    """

    def __init__(self, max_calls: int, window_seconds: int, name: str = "rate_limit"):
        if max_calls <= 0 or window_seconds <= 0:
            raise ValueError("max_calls and window_seconds must be positive")
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.name = name
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_calls:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many {self.name} attempts; retry in {retry_after}s",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)

    def reset(self) -> None:
        """Clear all buckets. Test-only helper — not called from app code."""
        with self._lock:
            self._buckets.clear()


def client_key(request: Request) -> str:
    """Best-effort caller identity for limiter keys.

    Prefers ``request.client.host`` (uvicorn-resolved peer address).
    Falls back to a constant so the limiter is still active when the
    socket peer is unknown — failing open would defeat the limiter.
    """
    if request.client and request.client.host:
        return request.client.host
    return "unknown-client"


# ── Pre-configured shared instances ──────────────────────────────────────────
# Limits are deliberately generous for legitimate users and brutal for
# scripts. Override via env (e.g. RATE_LIMIT_LOGIN_PER_MINUTE=3) for tests.

login_limiter = RateLimiter(
    max_calls=_env_int("RATE_LIMIT_LOGIN_PER_MINUTE", 10),
    window_seconds=60,
    name="login",
)

invite_accept_limiter = RateLimiter(
    max_calls=_env_int("RATE_LIMIT_INVITE_ACCEPT_PER_MINUTE", 5),
    window_seconds=60,
    name="invite-accept",
)
