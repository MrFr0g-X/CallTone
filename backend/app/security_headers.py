"""HTTP security middleware.

Restricts production API documentation to trusted devices and injects a
conservative set of security response headers on every reply.
Designed for a single-page-app where:
  - the SPA is served first-party
  - the API is same-origin to the SPA in prod (nginx multiplexes by path)
  - Tailwind needs `'unsafe-inline'` styles, but no inline scripts

HSTS is only emitted when DEBUG=false so local http development keeps
working. CORS is configured separately in app.main; this module does
not touch CORS headers.
"""

import ipaddress

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.database import settings


_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
}


_DEFAULT_CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


_DOCS_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


def _content_security_policy(path: str) -> str:
    if path == "/redoc" or path == "/redoc/" or path == "/docs" or path.startswith("/docs/"):
        return _DOCS_CSP
    return _DEFAULT_CSP


def _is_docs_path(path: str) -> bool:
    return (
        path == "/openapi.json"
        or path == "/docs"
        or path.startswith("/docs/")
        or path == "/redoc"
        or path == "/redoc/"
    )


def _allowed_docs_networks() -> list[ipaddress._BaseNetwork]:
    raw = getattr(settings, "DOCS_ALLOWED_IPS", "") or ""
    values = [item.strip() for item in raw.split(",") if item.strip()]
    # Loopback stays allowed so local health/debug commands on the VPS work.
    values.extend(["127.0.0.1", "::1"])
    networks: list[ipaddress._BaseNetwork] = []
    for value in values:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            # Invalid allowlist entries must fail closed rather than breaking
            # the whole API process during a live demo.
            continue
    return networks


def _client_ip(request: Request) -> str:
    # Uvicorn's proxy-header parsing can be influenced by X-Forwarded-For if the
    # edge proxy passes it through. Use Caddy's X-Real-IP instead; Caddy sets
    # this header at the reverse-proxy boundary, while direct local/dev traffic
    # falls back to request.client.
    real_ip = request.headers.get("x-real-ip", "").split(",")[0].strip()
    if real_ip:
        return real_ip
    return request.client.host if request.client else ""


def _docs_allowed(request: Request) -> bool:
    if settings.DEBUG:
        return True
    try:
        ip = ipaddress.ip_address(_client_ip(request))
    except ValueError:
        return False
    return any(ip in network for network in _allowed_docs_networks())


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _is_docs_path(request.url.path) and not _docs_allowed(request):
            # Return 404 instead of 403 so unauthorised clients do not get a
            # useful signal that API docs exist.
            response = Response("Not Found", status_code=404, media_type="text/plain")
        else:
            response = await call_next(request)
        for header, value in _BASE_HEADERS.items():
            response.headers.setdefault(header, value)
        response.headers.setdefault(
            "Content-Security-Policy",
            _content_security_policy(request.url.path),
        )
        if not settings.DEBUG:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
