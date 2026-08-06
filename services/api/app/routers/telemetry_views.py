"""Public listing view telemetry — impressions (search cards) and PDP views.

Fire-and-forget: the handler returns immediately and persists via BackgroundTasks
so analytics writes never block the request thread.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Literal

from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.analytics.listing_views import record_listing_views
from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import Field, model_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

MAX_IMPRESSION_BATCH = 50
VIEWS_RATE_LIMIT_PER_MINUTE = 240

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class ViewsRequest(StrictModel):
    session_id: str | None = Field(default=None, max_length=36)
    listing_id: str | None = Field(default=None, max_length=36)
    listing_ids: list[str] | None = None

    @model_validator(mode="after")
    def exactly_one_shape(self) -> ViewsRequest:
        has_single = self.listing_id is not None
        has_batch = bool(self.listing_ids)
        if has_single == has_batch:
            raise ValueError("Provide listing_id (PDP view) or listing_ids (impressions), not both")
        if has_batch and len(self.listing_ids or []) > MAX_IMPRESSION_BATCH:
            raise ValueError(f"listing_ids batch exceeds {MAX_IMPRESSION_BATCH}")
        return self


class ViewsResponse(StrictModel):
    accepted: int
    queued: bool = True


def _enforce_rate_limit(request: Request) -> None:
    try:
        allowed, retry_after = bump_rate_counter(
            scope="telemetry_views_ip",
            key=get_client_ip(request),
            window=timedelta(minutes=1),
            limit=VIEWS_RATE_LIMIT_PER_MINUTE,
        )
    except Exception:  # noqa: BLE001 — telemetry is non-critical; allow on failure.
        logger.debug("telemetry views rate-limit check failed (allowing)", exc_info=True)
        return
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="telemetry.rate_limited",
            message="Too many view beacons",
        )


def _valid_session_id(value: str | None) -> str | None:
    if value is None or not _UUID_RE.match(value):
        return None
    return value


def _persist_views(
    *,
    session_id: str | None,
    listing_ids: list[str],
    view_kind: Literal["impression", "pdp_view"],
) -> None:
    try:
        record_listing_views(session_id=session_id, listing_ids=listing_ids, view_kind=view_kind)
    except Exception:  # noqa: BLE001 — analytics must never crash the worker.
        logger.debug("telemetry views background persist failed", exc_info=True)


@router.post("/views", response_model=ViewsResponse)
async def ingest_views(
    request: Request,
    body: ViewsRequest,
    background_tasks: BackgroundTasks,
) -> ViewsResponse:
    _enforce_rate_limit(request)

    session_id = _valid_session_id(body.session_id)
    if session_id is None:
        raise AppError(
            code="invalid_session",
            message="session_id must be a valid UUID",
            http_status=422,
            details={"message_key": "telemetry.views.errors.invalidSession"},
        )

    if body.listing_id is not None:
        if not _UUID_RE.match(body.listing_id):
            raise AppError(
                code="invalid_listing",
                message="listing_id must be a valid UUID",
                http_status=422,
            )
        listing_ids = [body.listing_id]
        view_kind: Literal["impression", "pdp_view"] = "pdp_view"
    else:
        listing_ids = [lid for lid in (body.listing_ids or []) if _UUID_RE.match(lid)]
        if not listing_ids:
            raise AppError(
                code="invalid_listings",
                message="listing_ids must contain at least one valid UUID",
                http_status=422,
            )
        view_kind = "impression"

    background_tasks.add_task(
        _persist_views,
        session_id=session_id,
        listing_ids=listing_ids,
        view_kind=view_kind,
    )

    return ViewsResponse(accepted=len(listing_ids))
