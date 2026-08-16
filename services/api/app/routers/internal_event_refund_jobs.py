"""Internal batch job for event cancellation refund orchestration (Prompt G).

Mirrors internal_event_release.py's guard pattern with its own rotatable token.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.events.refund_jobs import sweep_event_refund_jobs
from fastapi import APIRouter, Depends, Request
from pydantic import Field

router = APIRouter(prefix="/internal/event-refund-jobs", tags=["internal-event-refund-jobs"])

_INTERNAL_TOKEN_ENV = "INTERNAL_EVENT_REFUND_JOBS_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-event-refund-jobs"

DEFAULT_BATCH_LIMIT = 50
MAX_BATCH_LIMIT = 200


class EventRefundJobsTickRequest(StrictModel):
    limit: int = Field(default=DEFAULT_BATCH_LIMIT, ge=1, le=MAX_BATCH_LIMIT)


class EventRefundJobsTickResponse(StrictModel):
    scanned: int
    executed: int
    awaiting_payout: int
    needs_destination: int
    manual_review: int
    completed: int
    retried: int
    dead: int
    skipped: int


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


async def require_internal_event_refund_jobs_token(request: Request) -> None:
    """Guard cron ticks — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal event refund jobs token",
            http_status=401,
        )


@router.post(
    "/tick",
    response_model=EventRefundJobsTickResponse,
    dependencies=[Depends(require_internal_event_refund_jobs_token)],
)
async def event_refund_jobs_tick(
    body: EventRefundJobsTickRequest | None = None,
) -> EventRefundJobsTickResponse:
    from app.deps import get_supabase_client

    service = next(get_supabase_client())
    request = body or EventRefundJobsTickRequest()
    now = datetime.now(UTC)
    result = sweep_event_refund_jobs(service, limit=request.limit, now=now)
    return EventRefundJobsTickResponse(
        scanned=result.scanned,
        executed=result.executed,
        awaiting_payout=result.awaiting_payout,
        needs_destination=result.needs_destination,
        manual_review=result.manual_review,
        completed=result.completed,
        retried=result.retried,
        dead=result.dead,
        skipped=result.skipped,
    )
