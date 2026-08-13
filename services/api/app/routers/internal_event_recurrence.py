"""Materialise the rolling horizon for recurring event series."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.events.recurrence import RecurrenceError, materialize_recurrence_instances
from fastapi import APIRouter, Depends, Request
from pydantic import Field

router = APIRouter(prefix="/internal/event-recurrence", tags=["internal-event-recurrence"])
logger = logging.getLogger(__name__)

_INTERNAL_TOKEN_ENV = "INTERNAL_EVENT_RECURRENCE_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-event-recurrence"


class RecurrenceTickRequest(StrictModel):
    limit: int = Field(default=100, ge=1, le=500)


class RecurrenceTickResponse(StrictModel):
    scanned: int
    materialised: int
    failed: int


def _expected_internal_token() -> str:
    try:
        return resolve_internal_token(
            _INTERNAL_TOKEN_ENV,
            dev_default=_DEFAULT_INTERNAL_TOKEN,
        )
    except InternalTokenMisconfigured as exc:
        raise AppError(code="configuration_error", message=str(exc), http_status=503) from exc


async def require_internal_event_recurrence_token(request: Request) -> None:
    if request.headers.get("X-Internal-Token") != _expected_internal_token():
        raise AppError(code="unauthorized", message="Invalid internal recurrence token", http_status=401)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


@router.post(
    "/tick",
    response_model=RecurrenceTickResponse,
    dependencies=[Depends(require_internal_event_recurrence_token)],
)
async def materialize_recurrence_tick(
    supabase: Annotated[Any, Depends(get_supabase_client)],
    body: RecurrenceTickRequest | None = None,
) -> RecurrenceTickResponse:
    request = body or RecurrenceTickRequest()
    client = supabase.client
    events = _rows(
        client.table("events")
        .select("id, recurrence_rule, recurrence_timezone, recurrence_until, recurrence_horizon_days")
        .eq("event_type", "recurring")
        .in_("status", ["draft", "published"])
        .order("updated_at")
        .limit(request.limit)
        .execute()
    )
    materialised = 0
    failed = 0
    for event in events:
        event_id = str(event.get("id") or "")
        try:
            instances = _rows(
                client.table("event_instances")
                .select("starts_at, ends_at, capacity")
                .eq("event_id", event_id)
                .order("starts_at")
                .limit(1)
                .execute()
            )
            if not instances:
                raise RecurrenceError("recurring event has no seed instance")
            seed = instances[0]
            starts_at = datetime.fromisoformat(str(seed["starts_at"]).replace("Z", "+00:00"))
            ends_at = datetime.fromisoformat(str(seed["ends_at"]).replace("Z", "+00:00"))
            until_raw = event.get("recurrence_until")
            until = (
                datetime.fromisoformat(str(until_raw).replace("Z", "+00:00"))
                if until_raw is not None
                else None
            )
            materialised += materialize_recurrence_instances(
                client,
                event_id=event_id,
                seed_starts_at=starts_at.astimezone(UTC),
                seed_ends_at=ends_at.astimezone(UTC),
                capacity=int(seed.get("capacity") or 0),
                rule=str(event.get("recurrence_rule") or ""),
                timezone=str(event.get("recurrence_timezone") or ""),
                horizon_days=int(event.get("recurrence_horizon_days") or 90),
                until=until.astimezone(UTC) if until else None,
            )
        except (KeyError, TypeError, ValueError, RecurrenceError) as exc:
            failed += 1
            logger.warning("recurrence materialisation skipped event_id=%s error=%s", event_id, exc)
    return RecurrenceTickResponse(scanned=len(events), materialised=materialised, failed=failed)
