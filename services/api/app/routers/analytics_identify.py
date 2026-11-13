"""analytics_v2 sign-in linking endpoint (Convergeo Intelligence 1A-08, plan §R-B, OD-2).

``POST /analytics/identify {session_id}`` links the caller's anonymous v2 session to their
account. The user id is resolved from the verified JWT only (never client-asserted) and the
body carries nothing but the anonymous session id. Inert unless feature flag
``analytics_v2_collect`` is ON, and refused when the visitor has opted out (consent
``denied`` or Global Privacy Control), so an opt-out never produces a journey link.
"""

from __future__ import annotations

import logging
from typing import Annotated

from anyio import to_thread
from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import ANALYTICS_IDENTIFY
from app.errors import AppError
from app.services.analytics.flags import collect_v2_enabled_async
from app.services.analytics.session_links import link_session
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
#: Sent by the client (and browsers) when the visitor has opted out of analytics.
CONSENT_HEADER = "X-Analytics-Consent"


class IdentifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    session_id: str = Field(pattern=UUID_PATTERN)


class IdentifyResponse(BaseModel):
    linked: bool
    skipped: str | None = None


def _opted_out(request: Request) -> bool:
    if request.headers.get(CONSENT_HEADER, "").strip().lower() == "denied":
        return True
    return request.headers.get("Sec-GPC", "").strip() == "1"


def _enforce_rate_limit(user_id: str) -> None:
    """Per-user cap. Fail-open: a limiter outage must not break sign-in."""
    try:
        allowed, retry_after = bump_rate_counter(
            scope=ANALYTICS_IDENTIFY.scope,
            key=user_id,
            window=ANALYTICS_IDENTIFY.window,
            limit=ANALYTICS_IDENTIFY.limit,
        )
    except Exception:  # noqa: BLE001 — analytics is non-critical; allow on failure.
        logger.debug("analytics identify rate-limit check failed (allowing)", exc_info=True)
        return
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="analytics.rate_limited",
            message="Too many analytics identify calls",
        )


@router.post("/identify", response_model=IdentifyResponse)
async def identify(
    request: Request,
    body: IdentifyRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> IdentifyResponse:
    if not await collect_v2_enabled_async():
        return IdentifyResponse(linked=False, skipped="flag_off")
    if _opted_out(request):
        raise AppError(
            code="analytics.opted_out",
            message="Analytics linking is disabled for this visitor",
            http_status=403,
        )
    _enforce_rate_limit(current_user.id)
    try:
        linked = await to_thread.run_sync(
            lambda: link_session(user_id=current_user.id, session_id=body.session_id.lower())
        )
    except RuntimeError as exc:
        logger.warning("analytics identify write failed", exc_info=True)
        raise AppError(
            code="analytics.identify_unavailable",
            message="Analytics linking is temporarily unavailable",
            http_status=503,
        ) from exc
    return IdentifyResponse(linked=linked)
