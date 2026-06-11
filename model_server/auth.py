"""Bearer-token + IP-allowlist middleware for the model server.

The threat model (see ``docs/DEMO_DEPLOYMENT_STUDY.md``) treats the model
server as an *internal* API: only the Tier-2 backend (Hetzner CPX31,
``91.99.208.254``) should ever reach it. Defence-in-depth:

1. IP allowlist (``ALLOWED_IPS``) — network-layer filter.
2. Bearer token (``MODEL_SERVER_TOKEN``) — transport-layer auth.

``/v1/health`` bypasses both so Vast's platform probes can hit it.
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Iterable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("calltone.model_server.auth")

PUBLIC_PATHS = {"/v1/health"}


def _parse_allowlist(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {ip.strip() for ip in raw.split(",") if ip.strip()}


def _client_ip(request: Request) -> str:
    # Trust the socket peer; we are not behind a reverse proxy in the Vast
    # deployment (caddy/nginx lives on the backend tier, not here).
    client = request.client
    return client.host if client else ""


class BearerAndIPMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        token: str | None,
        allowed_ips: Iterable[str],
    ) -> None:
        super().__init__(app)
        self.token = token
        self.allowed_ips = set(allowed_ips)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_PATHS:
            return await call_next(request)

        ip = _client_ip(request)
        if self.allowed_ips and ip not in self.allowed_ips:
            log.warning(
                "model_server.auth.ip_denied",
                extra={"event": "ip_denied", "ip": ip, "path": path},
            )
            return JSONResponse({"detail": "forbidden"}, status_code=403)

        expected = self.token
        if not expected:
            log.error(
                "model_server.auth.no_token_configured",
                extra={"event": "no_token_configured"},
            )
            return JSONResponse(
                {"detail": "server misconfigured"}, status_code=500
            )

        header = request.headers.get("authorization", "")
        provided = header[len("Bearer ") :] if header.startswith("Bearer ") else ""
        if not header.startswith("Bearer ") or not hmac.compare_digest(provided, expected):
            log.warning(
                "model_server.auth.token_denied",
                extra={"event": "token_denied", "ip": ip, "path": path},
            )
            return JSONResponse({"detail": "unauthorized"}, status_code=401)

        return await call_next(request)


def install_auth_middleware(app: FastAPI) -> None:
    token = os.getenv("MODEL_SERVER_TOKEN")
    allowed_ips = _parse_allowlist(os.getenv("ALLOWED_IPS"))
    app.add_middleware(
        BearerAndIPMiddleware,
        token=token,
        allowed_ips=allowed_ips,
    )
