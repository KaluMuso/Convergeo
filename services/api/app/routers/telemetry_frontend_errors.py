"""Public browser error beacon for Next.js route/global error boundaries.

Unauthenticated by design (same posture as analytics collect): IP rate-limited,
payload size-bounded, and logged server-side only — never echoed back to the
client with stack traces or internal details.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Literal

from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.core.sentry import scrub
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

FRONTEND_ERROR_RATE_LIMIT_PER_MINUTE = 60
MAX_MESSAGE_CHARS = 500
MAX_STACK_CHARS = 8_000


class FrontendErrorReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    digest: str | None = Field(default=None, max_length=128)
    stack: str | None = Field(default=None, max_length=MAX_STACK_CHARS)
    boundary: Literal["route", "global"] = "route"
    application: Literal["customer", "vendor", "admin"] = "customer"
    locale: str | None = Field(default=None, max_length=8)
    url: str | None = Field(default=None, max_length=2_000)
    user_agent: str | None = Field(default=None, max_length=500)


class FrontendErrorAck(BaseModel):
    accepted: bool = True


def _enforce_rate_limit(request: Request) -> None:
    try:
        allowed, retry_after = bump_rate_counter(
            scope="telemetry_frontend_errors_ip",
            key=get_client_ip(request),
            window=timedelta(minutes=1),
            limit=FRONTEND_ERROR_RATE_LIMIT_PER_MINUTE,
        )
    except Exception:  # noqa: BLE001 — telemetry is non-critical; allow on failure.
        logger.debug("frontend-error rate-limit check failed (allowing)", exc_info=True)
        return
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="telemetry.rate_limited",
            message="Too many frontend error reports",
        )


@router.post("/frontend-errors", response_model=FrontendErrorAck)
async def ingest_frontend_error(request: Request, body: FrontendErrorReport) -> FrontendErrorAck:
    _enforce_rate_limit(request)

    message = str(scrub(body.message))[:MAX_MESSAGE_CHARS]
    stack = str(scrub(body.stack))[:MAX_STACK_CHARS] if body.stack else None

    logger.error(
        "frontend_error boundary=%s application=%s locale=%s digest=%s url=%s message=%s",
        body.boundary,
        body.application,
        body.locale,
        body.digest,
        body.url,
        message,
        extra={
            "boundary": body.boundary,
            "application": body.application,
            "locale": body.locale,
            "digest": body.digest,
            "url": body.url,
            "user_agent": body.user_agent,
            "stack": stack,
            "path": request.url.path,
        },
    )

    return FrontendErrorAck()
