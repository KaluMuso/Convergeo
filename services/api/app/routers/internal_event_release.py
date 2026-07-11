"""Internal batch job for event-date escrow release (M10-P08).

Mirrors internal_order_jobs.py's guard pattern exactly, with its own token env
var so it stays independently rotatable from the order-jobs token.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.escrow.event_release import sweep_event_releases
from fastapi import APIRouter, Depends, Request
from pydantic import Field

router = APIRouter(prefix="/internal/event-release", tags=["internal-event-release"])

_INTERNAL_TOKEN_ENV = "INTERNAL_EVENT_RELEASE_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-event-release"

DEFAULT_BATCH_LIMIT = 50
MAX_BATCH_LIMIT = 200


class EventReleaseTickRequest(StrictModel):
    limit: int = Field(default=DEFAULT_BATCH_LIMIT, ge=1, le=MAX_BATCH_LIMIT)
    cursor: str | None = None


class EventReleaseTickResponse(StrictModel):
    scanned: int
    released: int
    held: int
    already_released: int
    not_eligible: int
    blocked_cancelled: int
    next_cursor: str | None = None


def _expected_internal_token() -> str:
    return os.environ.get(_INTERNAL_TOKEN_ENV, _DEFAULT_INTERNAL_TOKEN)


async def require_internal_event_release_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal event release token",
            http_status=401,
        )


@router.post(
    "/tick",
    response_model=EventReleaseTickResponse,
    dependencies=[Depends(require_internal_event_release_token)],
)
async def event_release_tick(
    body: EventReleaseTickRequest | None = None,
) -> EventReleaseTickResponse:
    from app.deps import get_supabase_client

    service = next(get_supabase_client())
    request = body or EventReleaseTickRequest()
    now = datetime.now(UTC)
    result, next_cursor = sweep_event_releases(
        service,
        limit=request.limit,
        cursor=request.cursor,
        now=now,
    )
    return EventReleaseTickResponse(
        scanned=result.scanned,
        released=result.released,
        held=result.held,
        already_released=result.already_released,
        not_eligible=result.not_eligible,
        blocked_cancelled=result.blocked_cancelled,
        next_cursor=next_cursor,
    )
