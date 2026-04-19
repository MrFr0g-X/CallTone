"""HTTP security-headers middleware.

Injects a conservative set of security response headers on every reply.
Designed for a single-page-app where:
  - the SPA is served first-party
  - the API is same-origin to the SPA in prod (nginx multiplexes by path)
  - Tailwind needs `'unsafe-inline'` styles, but no inline scripts

HSTS is only emitted when DEBUG=false so local http development keeps
working. CORS is configured separately in app.main; this module does
not touch CORS headers.
"""

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
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        for header, value in _BASE_HEADERS.items():
            response.headers.setdefault(header, value)
        if not settings.DEBUG:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
