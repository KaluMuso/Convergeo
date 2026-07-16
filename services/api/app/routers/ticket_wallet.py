from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.tickets.qr import (
    DEFAULT_HORIZON_WINDOWS,
    MAX_HORIZON_WINDOWS,
    build_qr_payload,
    current_window,
    extract_pin_for_holder,
    horizon_entry_to_dict,
    issue_horizon,
    seconds_remaining_in_window,
    window_code,
)
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/account/tickets", tags=["ticket-wallet"])

TicketStatus = Literal["issued", "checked_in", "transferred", "void"]


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class WalletEventOut(StrictModel):
    id: str
    title: str
    venue: str | None = None
    slug: str


class WalletInstanceOut(StrictModel):
    id: str
    starts_at: str


class WalletTicketTypeOut(StrictModel):
    id: str
    name: str
    kind: str


class WalletTicketSummary(StrictModel):
    id: str
    status: TicketStatus
    holder_name: str | None = None
    event: WalletEventOut
    instance: WalletInstanceOut
    ticket_type: WalletTicketTypeOut


class WalletListResponse(StrictModel):
    tickets: list[WalletTicketSummary]


class WalletQrOut(StrictModel):
    window: int
    code: str
    qr_payload: str
    seconds_remaining: int


class WalletTicketDetailResponse(StrictModel):
    id: str
    status: TicketStatus
    holder_name: str | None = None
    pin: str | None = None
    pin_available: bool
    qr: WalletQrOut | None = None
    event: WalletEventOut
    instance: WalletInstanceOut
    ticket_type: WalletTicketTypeOut


class HorizonEntryOut(StrictModel):
    window: int
    code: str
    qr_payload: str


class WalletHorizonResponse(StrictModel):
    ticket_id: str
    from_window: int
    horizon_size: int
    last_window: int
    pin: str | None = None
    pin_available: bool
    entries: list[HorizonEntryOut]


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _holder_name(row: dict[str, Any]) -> str | None:
    value = row.get("holder_name")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _load_holder_ticket_row(
    service_client: _ServiceRoleClient,
    *,
    ticket_id: str,
    holder_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("tickets")
        .select(
            "id, status, holder_name, qr_secret, pin_hash, instance_id, "
            "ticket_type_id, holder_user_id"
        )
        .eq("id", ticket_id)
        .eq("holder_user_id", holder_user_id)
        .not_.is_("order_item_id", "null")
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Ticket not found",
            http_status=404,
        )
    return row


def _load_event_context(
    service_client: _ServiceRoleClient,
    *,
    instance_id: str,
    ticket_type_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    instance_response = (
        service_client.client.table("event_instances")
        .select("id, starts_at, event_id")
        .eq("id", instance_id)
        .maybe_single()
        .execute()
    )
    instance_row = _single_row(instance_response)
    if instance_row is None:
        raise AppError(
            code="not_found",
            message="Ticket not found",
            http_status=404,
        )

    event_id = str(instance_row["event_id"])
    event_response = (
        service_client.client.table("events")
        .select("id, title, venue, slug")
        .eq("id", event_id)
        .maybe_single()
        .execute()
    )
    event_row = _single_row(event_response)
    if event_row is None:
        raise AppError(
            code="not_found",
            message="Ticket not found",
            http_status=404,
        )

    type_response = (
        service_client.client.table("ticket_types")
        .select("id, name, kind")
        .eq("id", ticket_type_id)
        .maybe_single()
        .execute()
    )
    type_row = _single_row(type_response)
    if type_row is None:
        raise AppError(
            code="not_found",
            message="Ticket not found",
            http_status=404,
        )

    return event_row, instance_row, type_row


def _build_event_out(event_row: dict[str, Any]) -> WalletEventOut:
    return WalletEventOut(
        id=str(event_row["id"]),
        title=str(event_row["title"]),
        venue=event_row.get("venue"),
        slug=str(event_row["slug"]),
    )


def _build_instance_out(instance_row: dict[str, Any]) -> WalletInstanceOut:
    return WalletInstanceOut(
        id=str(instance_row["id"]),
        starts_at=str(instance_row["starts_at"]),
    )


def _build_type_out(type_row: dict[str, Any]) -> WalletTicketTypeOut:
    return WalletTicketTypeOut(
        id=str(type_row["id"]),
        name=str(type_row["name"]),
        kind=str(type_row["kind"]),
    )


def _pin_fields(
    pin_hash: str | None,
    *,
    ticket_id: str,
) -> tuple[str | None, bool]:
    pin = extract_pin_for_holder(pin_hash, ticket_id=ticket_id)
    return pin, pin is not None


def _build_live_qr(
    *,
    ticket_id: str,
    ticket_secret: str | None,
    status: str,
    now: datetime | None = None,
) -> WalletQrOut | None:
    if status != "issued" or not ticket_secret:
        return None
    window = current_window(now)
    return WalletQrOut(
        window=window,
        code=window_code(ticket_secret, window),
        qr_payload=build_qr_payload(
            ticket_id=ticket_id,
            window=window,
            ticket_secret=ticket_secret,
        ),
        seconds_remaining=seconds_remaining_in_window(now),
    )


@router.get("", response_model=WalletListResponse)
async def list_wallet_tickets(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> WalletListResponse:
    response = (
        service_client.client.table("tickets")
        .select("id, status, holder_name, instance_id, ticket_type_id, created_at")
        .eq("holder_user_id", current_user.id)
        .not_.is_("order_item_id", "null")
        .order("created_at", desc=True)
        .execute()
    )
    tickets: list[WalletTicketSummary] = []
    for row in _rows(response):
        event_row, instance_row, type_row = _load_event_context(
            service_client,
            instance_id=str(row["instance_id"]),
            ticket_type_id=str(row["ticket_type_id"]),
        )
        tickets.append(
            WalletTicketSummary(
                id=str(row["id"]),
                status=str(row["status"]),  # type: ignore[arg-type]
                holder_name=_holder_name(row),
                event=_build_event_out(event_row),
                instance=_build_instance_out(instance_row),
                ticket_type=_build_type_out(type_row),
            )
        )
    return WalletListResponse(tickets=tickets)


@router.get("/{ticket_id}", response_model=WalletTicketDetailResponse)
async def get_wallet_ticket(
    ticket_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> WalletTicketDetailResponse:
    row = _load_holder_ticket_row(
        service_client,
        ticket_id=ticket_id,
        holder_user_id=current_user.id,
    )
    event_row, instance_row, type_row = _load_event_context(
        service_client,
        instance_id=str(row["instance_id"]),
        ticket_type_id=str(row["ticket_type_id"]),
    )
    pin_hash = row.get("pin_hash")
    pin_hash_str = str(pin_hash) if isinstance(pin_hash, str) else None
    pin, pin_available = _pin_fields(pin_hash_str, ticket_id=ticket_id)
    qr_secret = row.get("qr_secret")
    qr_secret_str = str(qr_secret) if isinstance(qr_secret, str) and qr_secret.strip() else None

    return WalletTicketDetailResponse(
        id=str(row["id"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        holder_name=_holder_name(row),
        pin=pin,
        pin_available=pin_available,
        qr=_build_live_qr(
            ticket_id=ticket_id,
            ticket_secret=qr_secret_str,
            status=str(row["status"]),
        ),
        event=_build_event_out(event_row),
        instance=_build_instance_out(instance_row),
        ticket_type=_build_type_out(type_row),
    )


@router.get("/{ticket_id}/horizon", response_model=WalletHorizonResponse)
async def get_wallet_horizon(
    ticket_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    n: int = Query(default=DEFAULT_HORIZON_WINDOWS, ge=1, le=MAX_HORIZON_WINDOWS),
) -> WalletHorizonResponse:
    row = _load_holder_ticket_row(
        service_client,
        ticket_id=ticket_id,
        holder_user_id=current_user.id,
    )
    status = str(row["status"])
    if status != "issued":
        raise AppError(
            code="ticket_unusable",
            message="Ticket is not eligible for offline horizon sync",
            http_status=409,
            details={"status": status},
        )

    qr_secret = row.get("qr_secret")
    if not isinstance(qr_secret, str) or not qr_secret.strip():
        raise AppError(
            code="ticket_unusable",
            message="Ticket secrets are unavailable",
            http_status=409,
        )

    from_window = current_window()
    entries = issue_horizon(
        qr_secret,
        ticket_id=ticket_id,
        from_window=from_window,
        n=n,
    )
    pin_hash = row.get("pin_hash")
    pin_hash_str = str(pin_hash) if isinstance(pin_hash, str) else None
    pin, pin_available = _pin_fields(pin_hash_str, ticket_id=ticket_id)

    return WalletHorizonResponse(
        ticket_id=ticket_id,
        from_window=from_window,
        horizon_size=n,
        last_window=from_window + n - 1,
        pin=pin,
        pin_available=pin_available,
        entries=[HorizonEntryOut(**horizon_entry_to_dict(entry)) for entry in entries],
    )
