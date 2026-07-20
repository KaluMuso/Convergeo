"""Protected Sentry test-event path (observability verification).

Disabled in production unless ENABLE_SENTRY_TEST_ENDPOINT=true AND
INTERNAL_SENTRY_TEST_TOKEN is configured. Never commits a DSN; only emits when
Sentry is already initialised from SENTRY_DSN.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.settings import get_settings
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/sentry-test", tags=["internal-sentry-test"])

_INTERNAL_TOKEN_ENV = "INTERNAL_SENTRY_TEST_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-sentry-test"


def _sentry_test_enabled() -> bool:
    settings = get_settings()
    if settings.env == "production":
        return os.environ.get("ENABLE_SENTRY_TEST_ENDPOINT", "").strip().lower() == "true"
    return True


def _expected_internal_token() -> str:
    try:
        return resolve_internal_token(
            _INTERNAL_TOKEN_ENV,
            dev_default=_DEFAULT_INTERNAL_TOKEN,
        )
    except InternalTokenMisconfigured as exc:
        raise AppError(
            code="configuration_error",
            message=str(exc),
            http_status=503,
        ) from exc


async def require_sentry_test_token(request: Request) -> None:
    if not _sentry_test_enabled():
        raise AppError(
            code="not_found",
            message="Sentry test endpoint is disabled",
            http_status=404,
        )
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal sentry-test token",
            http_status=401,
        )


@router.post("", dependencies=[Depends(require_sentry_test_token)])
async def sentry_test_event(request: Request) -> dict[str, Any]:
    """Emit a single controlled test exception capture (scrubbed + tagged)."""
    settings = get_settings()
    if not settings.sentry_dsn:
        raise AppError(
            code="configuration_error",
            message="SENTRY_DSN is not configured",
            http_status=503,
        )

    import sentry_sdk

    request_id = getattr(request.state, "request_id", None) or "unknown"
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("application", "api")
        scope.set_tag("request_id", request_id)
        scope.set_tag("route", "/internal/sentry-test")
        scope.set_tag("test_event", "true")
        release = settings.sentry_release or settings.git_sha
        if release:
            scope.set_tag("release_sha", release)
        event_id = sentry_sdk.capture_message(
            "Vergeo5 observability test event (api)",
            level="error",
        )

    return {
        "ok": True,
        "application": "api",
        "event_id": event_id,
        "environment": settings.sentry_environment or settings.env,
        "release": settings.sentry_release or settings.git_sha or None,
        "request_id": request_id,
    }
