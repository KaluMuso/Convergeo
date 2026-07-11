"""Organiser-scoped offline scan-sync payload (M10-P05).

Pre-event sync for the organiser scanner PWA: returns, per issued ticket, a
horizon of rotating-window signatures derived from the ticket's `qr_secret`.
The raw secret never leaves the server -- only the derived HMAC signatures do,
so the device can validate an offline scan `{ticket_id, window, sig}` against
the cached signatures (with the same +/-1 window tolerance the online verify
endpoint uses) without ever holding a credential that could forge a new code.

Reuses `current_window` / `window_sig` from `app.routers.ticket_verify` so the
signature derivation is byte-for-byte identical to the online verify path.
Does NOT edit or reimplement `ticket_verify.py` -- the offline queue is
reconciled by POSTing to the existing `/tickets/verify/batch` endpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.ticket_verify import current_window, window_sig
from app.schemas.base import StrictModel
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends
from pydantic import Field

router = APIRouter(prefix="/events", tags=["ticket-scan-sync"])

# Rotating window is 60s (matches ticket_verify.current_window). The sync
# horizon is a bounded window around the instance's start time: doors-open
# lead time plus a generous in-event check-in period. Kept intentionally
# small/bounded per spec (data-cost frugality) -- widen via env/query later
# if organisers report events running longer than the after-horizon.
_WINDOW_SECONDS = 60
_HORIZON_BEFORE = timedelta(hours=2)
_HORIZON_AFTER = timedelta(hours=8)
_ISSUED_STATUSES = frozenset({"issued", "transferred"})


class ScanSyncTicket(StrictModel):
    ticket_id: str
    # Positional: window_sigs[i] corresponds to window (horizon_start_window + i).
    # Keeps the payload compact -- no need to repeat the window number per sig.
    window_sigs: list[str]
    pin_hash_present: bool


class ScanSyncResponse(StrictModel):
    event_id: str
    instance_id: str
    starts_at: datetime
    window_seconds: int = Field(default=_WINDOW_SECONDS)
    horizon_start_window: int
    horizon_end_window: int
    tickets: list[ScanSyncTicket] = Field(default_factory=list)


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _parse_starts_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    raise ValueError(f"Unsupported datetime value: {value!r}")


def _load_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def _load_event_for_vendor(
    client: Any,
    *,
    event_id: str,
    vendor_id: str,
) -> dict[str, Any]:
    response = (
        client.table("events")
        .select("id, organiser_vendor_id")
        .eq("id", event_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Event not found",
            http_status=404,
            details={"message_key": "vendor.events.errors.not_found"},
        )
    if str(row.get("organiser_vendor_id")) != vendor_id:
        raise AppError(
            code="forbidden",
            message="Organiser may only sync scan data for their own events",
            http_status=403,
            details={"message_key": "vendor.scan.errors.forbidden", "event_id": event_id},
        )
    return row


def _load_instance_for_event(
    client: Any,
    *,
    instance_id: str,
    event_id: str,
) -> dict[str, Any]:
    response = (
        client.table("event_instances")
        .select("id, event_id, starts_at, capacity")
        .eq("id", instance_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None or str(row.get("event_id")) != event_id:
        raise AppError(
            code="not_found",
            message="Event instance not found",
            http_status=404,
            details={"message_key": "vendor.scan.errors.instance_not_found"},
        )
    return row


def _load_issued_tickets(client: Any, instance_id: str) -> list[dict[str, Any]]:
    response = (
        client.table("tickets")
        .select("id, status, order_item_id, qr_secret, pin_hash")
        .eq("instance_id", instance_id)
        .in_("status", list(_ISSUED_STATUSES))
        .execute()
    )
    return [row for row in _rows(response) if row.get("order_item_id")]


def compute_horizon_windows(starts_at: datetime) -> tuple[int, int]:
    """Bounded window range [start, end] (inclusive) around an instance's start time."""
    start_window = current_window(starts_at - _HORIZON_BEFORE)
    end_window = current_window(starts_at + _HORIZON_AFTER)
    return start_window, end_window


def build_scan_sync_response(
    *,
    event_id: str,
    instance: dict[str, Any],
    tickets: list[dict[str, Any]],
) -> ScanSyncResponse:
    starts_at = _parse_starts_at(instance["starts_at"])
    horizon_start, horizon_end = compute_horizon_windows(starts_at)

    ticket_payloads: list[ScanSyncTicket] = []
    for row in tickets:
        secret = row.get("qr_secret")
        if not isinstance(secret, str) or not secret:
            # Secret not (yet) provisioned -- device falls back to online verify
            # for this ticket rather than caching an unusable entry.
            continue
        sigs = [window_sig(secret, w) for w in range(horizon_start, horizon_end + 1)]
        ticket_payloads.append(
            ScanSyncTicket(
                ticket_id=str(row["id"]),
                window_sigs=sigs,
                pin_hash_present=bool(row.get("pin_hash")),
            )
        )

    return ScanSyncResponse(
        event_id=event_id,
        instance_id=str(instance["id"]),
        starts_at=starts_at,
        window_seconds=_WINDOW_SECONDS,
        horizon_start_window=horizon_start,
        horizon_end_window=horizon_end,
        tickets=ticket_payloads,
    )


@router.get(
    "/{event_id}/instances/{instance_id}/scan-sync",
    response_model=ScanSyncResponse,
)
async def get_scan_sync(
    event_id: str,
    instance_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ScanSyncResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    client = service_client.client

    _load_event_for_vendor(client, event_id=event_id, vendor_id=vendor_id)
    instance = _load_instance_for_event(client, instance_id=instance_id, event_id=event_id)
    tickets = _load_issued_tickets(client, instance_id)

    return build_scan_sync_response(event_id=event_id, instance=instance, tickets=tickets)
