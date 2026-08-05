from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.settings import Settings, get_settings

HSTS_VALUE = "max-age=63072000; includeSubDomains; preload"
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
PERMISSIONS_POLICY = (
    "camera=(), microphone=(), geolocation=(), browsing-topics=(), payment=(), usb=()"
)

# Browser-facing CORS preflight allowlist (webhooks / n8n use server-to-server headers).
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "X-Request-ID",
    "Idempotency-Key",
]


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security headers for JSON API responses (mirrors infra/Caddyfile api_security)."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        settings = get_settings()
        response = await call_next(request)
        _apply_secure_headers(response, settings)
        return response


def _apply_secure_headers(response: Response, settings: Settings) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = API_CSP
    response.headers["Permissions-Policy"] = PERMISSIONS_POLICY
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if settings.env != "development":
        response.headers["Strict-Transport-Security"] = HSTS_VALUE
