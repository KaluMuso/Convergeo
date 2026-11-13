"""Internal cron: enforce overdue organiser advance debts (suspend, blacklist, legal flag)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.events.advance_policy import enforce_overdue_advance_debts
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/event-advance-debts", tags=["internal-event-advance-debts"])

_INTERNAL_TOKEN_ENV = "INTERNAL_EVENT_ADVANCE_DEBTS_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-event-advance-debts"


class EventAdvanceDebtsTickResponse(StrictModel):
    debts_flagged: int
    vendors_suspended: int


def _expected_internal_token() -> str:
    try:
        return resolve_internal_token(_INTERNAL_TOKEN_ENV, dev_default=_DEFAULT_INTERNAL_TOKEN)
    except InternalTokenMisconfigured as exc:
        raise AppError(code="configuration_error", message=str(exc), http_status=503) from exc


async def require_internal_event_advance_debts_token(request: Request) -> None:
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal event advance debts token",
            http_status=401,
        )


@router.post(
    "/tick",
    response_model=EventAdvanceDebtsTickResponse,
    dependencies=[Depends(require_internal_event_advance_debts_token)],
)
async def event_advance_debts_tick() -> EventAdvanceDebtsTickResponse:
    result = enforce_overdue_advance_debts(now=datetime.now(UTC))
    return EventAdvanceDebtsTickResponse(
        debts_flagged=result.debts_flagged, vendors_suspended=result.vendors_suspended
    )
