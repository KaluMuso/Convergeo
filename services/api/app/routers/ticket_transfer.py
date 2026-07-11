"""Ticket transfer-to-friend — initiate / cancel / claim (M10-P07).

No resale (D2 scope): free transfer only. Sender initiates by phone until T-6h
before the event instance starts; the recipient claims by signing in with the
matching verified phone. Claiming reassigns ``tickets.holder_user_id`` and
reissues a fresh ``qr_secret``/``pin_hash`` (via the M10-FIX helpers in
``app.services.tickets.qr``), which permanently voids the sender's old QR/PIN —
``ticket_verify.py`` always re-reads the current secret from the row, so the
old credentials simply stop matching.

Both the transfer-state flip and the ticket holder/secret reassignment on claim
are server-controlled: ``ticket_transfers`` has no client insert/update/delete
RLS policy (see migration 0026), and ``tickets`` is guarded by
``guard_ticket_client_mutation``. The claim transition runs as a single atomic
SQL script via ``run_sql_script`` (same pattern as ``ticket_verify.py``'s
``_atomic_check_in``), executed as the ``postgres`` role, which the guard
trigger explicitly exempts.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import sql_uuid
from app.services.tickets.qr import generate_pin, generate_qr_secret, seal_pin_storage
from fastapi import APIRouter, Depends, Request
from postgrest.exceptions import APIError
from pydantic import Field, field_validator

router = APIRouter(prefix="/tickets", tags=["ticket-transfer"])

TRANSFER_CUTOFF = timedelta(hours=6)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _normalize_phone(value: str) -> str:
    """Best-effort normalisation to E.164, defaulting bare local numbers to Zambia (+260)."""
    digits = "".join(ch for ch in value.strip() if ch.isdigit() or ch == "+")
    if digits.startswith("+"):
        return digits
    if digits.startswith("260"):
        return f"+{digits}"
    if digits.startswith("0"):
        return f"+260{digits[1:]}"
    return f"+{digits}"


def _is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


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


class InitiateTransferRequest(StrictModel):
    to_phone: str = Field(min_length=6, max_length=20)

    @field_validator("to_phone")
    @classmethod
    def normalize_and_validate_phone(cls, value: str) -> str:
        normalized = _normalize_phone(value)
        if not _E164_RE.match(normalized):
            raise ValueError("to_phone must be a valid phone number")
        return normalized


class TicketTransferOut(StrictModel):
    id: str
    ticket_id: str
    to_phone: str
    status: str
    expires_at: str
    created_at: str


class InitiateTransferResponse(StrictModel):
    transfer: TicketTransferOut


class CurrentTransferResponse(StrictModel):
    transfer: TicketTransferOut | None


class CancelTransferResponse(StrictModel):
    transfer: TicketTransferOut


class ClaimTransferResponse(StrictModel):
    transfer: TicketTransferOut
    ticket_id: str


class InboundTransferOut(StrictModel):
    id: str
    ticket_id: str
    expires_at: str
    event_title: str | None = None
    event_venue: str | None = None
    starts_at: str | None = None


class InboundTransfersResponse(StrictModel):
    transfers: list[InboundTransferOut]


def _serialize_transfer(row: dict[str, Any]) -> TicketTransferOut:
    return TicketTransferOut(
        id=str(row["id"]),
        ticket_id=str(row["ticket_id"]),
        to_phone=str(row["to_phone"]),
        status=str(row["status"]),
        expires_at=str(row["expires_at"]),
        created_at=str(row["created_at"]),
    )


def _rate_limit_transfer(
    request: Request,
    user_id: str,
    service_client: _ServiceRoleClient,
    *,
    scope: str,
) -> None:
    ip = get_client_ip(request)
    allowed_ip, retry_ip = bump_rate_counter(
        scope=f"{scope}_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=30,
        client=service_client.client,
    )
    if not allowed_ip:
        raise_rate_limited(
            retry_after=retry_ip,
            message_key="events.transfer.errors.rateLimited",
            message="Too many ticket transfer requests",
        )

    allowed_user, retry_user = bump_rate_counter(
        scope=f"{scope}_user",
        key=user_id,
        window=timedelta(minutes=1),
        limit=10,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=retry_user,
            message_key="events.transfer.errors.rateLimited",
            message="Too many ticket transfer requests",
        )


def _not_found() -> AppError:
    return AppError(
        code="not_found",
        message="Ticket not found",
        http_status=404,
        details={"message_key": "events.transfer.errors.notFound"},
    )


def _load_ticket(service_client: _ServiceRoleClient, ticket_id: str) -> dict[str, Any]:
    if not _is_uuid(ticket_id):
        raise _not_found()
    response = (
        service_client.client.table("tickets")
        .select("id, status, holder_user_id, order_item_id, instance_id")
        .eq("id", ticket_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise _not_found()
    return row


def _load_instance(service_client: _ServiceRoleClient, instance_id: str) -> dict[str, Any]:
    response = (
        service_client.client.table("event_instances")
        .select("id, starts_at, event_id")
        .eq("id", instance_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise _not_found()
    return row


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _assert_holder(ticket: dict[str, Any], user_id: str) -> None:
    if str(ticket.get("holder_user_id")) != user_id:
        raise AppError(
            code="forbidden",
            message="Only the ticket holder may transfer this ticket",
            http_status=403,
            details={"message_key": "events.transfer.errors.notHolder"},
        )


def _assert_transferable(ticket: dict[str, Any]) -> None:
    status = str(ticket.get("status"))
    if status != "issued" or not ticket.get("order_item_id"):
        raise AppError(
            code="ticket_not_transferable",
            message="Ticket is not eligible for transfer",
            http_status=409,
            details={"status": status, "message_key": "events.transfer.errors.notTransferable"},
        )


def _cutoff_for_instance(instance: dict[str, Any], *, now: datetime) -> datetime:
    starts_at = _parse_dt(str(instance["starts_at"]))
    cutoff = starts_at - TRANSFER_CUTOFF
    if now > cutoff:
        raise AppError(
            code="ticket_transfer_cutoff_passed",
            message="Transfers close 6 hours before the event starts",
            http_status=409,
            details={"message_key": "events.transfer.errors.cutoffPassed"},
        )
    return cutoff


def _load_transfer(service_client: _ServiceRoleClient, transfer_id: str) -> dict[str, Any]:
    if not _is_uuid(transfer_id):
        raise _not_found()
    response = (
        service_client.client.table("ticket_transfers")
        .select("id, ticket_id, from_user_id, to_phone, status, expires_at, created_at")
        .eq("id", transfer_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise _not_found()
    return row


def _load_verified_phone(service_client: _ServiceRoleClient, user_id: str) -> str | None:
    response = (
        service_client.client.table("profiles")
        .select("phone")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None
    phone = row.get("phone")
    if not isinstance(phone, str) or not phone.strip():
        return None
    return _normalize_phone(phone)


def _notify_recipient(client: Any, *, transfer_row: dict[str, Any], ticket_id: str) -> None:
    transfer_id = str(transfer_row["id"])
    to_phone = str(transfer_row["to_phone"])
    enqueue_outbox_row(
        client,
        event_type="ticket_transfer_invite",
        entity_id=transfer_id,
        channel="whatsapp",
        template="ticket_transfer_invite",
        payload={
            "to": to_phone,
            "phone": to_phone,
            "ticket_id": ticket_id,
            "transfer_id": transfer_id,
        },
    )


def _claim_transfer_atomic(
    *,
    transfer_id: str,
    claiming_user_id: str,
    qr_secret: str,
    pin_hash: str,
    now: datetime,
) -> tuple[str, str] | None:
    """Atomically flip pending -> claimed and reassign the ticket holder/secrets.

    Returns (transfer_id, ticket_id) on success, or None when the transfer/ticket
    were not in an eligible state (already resolved, expired, or ticket no longer
    'issued') — nothing is mutated in that case.
    """
    transfer_sql = sql_uuid(transfer_id, "transfer_id")
    holder_sql = sql_uuid(claiming_user_id, "claiming_user_id")
    now_sql = sql_literal(now.isoformat())
    script = f"""
BEGIN;
WITH target_transfer AS (
  SELECT id, ticket_id
  FROM public.ticket_transfers
  WHERE id = {transfer_sql}
    AND status = 'pending'
    AND expires_at > {now_sql}::timestamptz
  FOR UPDATE
),
target_ticket AS (
  SELECT t.id
  FROM public.tickets t
  WHERE t.id = (SELECT ticket_id FROM target_transfer)
    AND t.status = 'issued'
    AND t.order_item_id IS NOT NULL
  FOR UPDATE
),
ticket_upd AS (
  UPDATE public.tickets t
  SET holder_user_id = {holder_sql},
      qr_secret = {sql_literal(qr_secret)},
      pin_hash = {sql_literal(pin_hash)}
  WHERE t.id IN (SELECT id FROM target_ticket)
  RETURNING t.id::text AS ticket_id
),
transfer_upd AS (
  UPDATE public.ticket_transfers tt
  SET status = 'claimed',
      claimed_by_user_id = {holder_sql},
      claimed_at = timezone('utc', now())
  WHERE tt.id IN (SELECT id FROM target_transfer)
    AND EXISTS (SELECT 1 FROM ticket_upd)
  RETURNING tt.id::text AS transfer_id, tt.ticket_id::text AS ticket_id
)
SELECT transfer_id, ticket_id FROM transfer_upd;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"ticket transfer claim failed: {result.error}")
    if not result.rows:
        return None
    parts = result.rows[0].split("|")
    if len(parts) != 2:
        raise RuntimeError("unexpected ticket transfer claim return shape")
    return parts[0], parts[1]


@router.post("/{ticket_id}/transfer", response_model=InitiateTransferResponse)
async def initiate_transfer(
    ticket_id: str,
    body: InitiateTransferRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> InitiateTransferResponse:
    _rate_limit_transfer(request, current_user.id, service_client, scope="ticket_transfer_initiate")
    ticket = _load_ticket(service_client, ticket_id)
    _assert_holder(ticket, current_user.id)
    _assert_transferable(ticket)
    instance = _load_instance(service_client, str(ticket["instance_id"]))
    cutoff = _cutoff_for_instance(instance, now=datetime.now(UTC))

    insert_row = {
        "ticket_id": ticket_id,
        "from_user_id": current_user.id,
        "to_phone": body.to_phone,
        "status": "pending",
        "expires_at": cutoff.isoformat(),
    }
    try:
        response = service_client.client.table("ticket_transfers").insert(insert_row).execute()
    except APIError as exc:
        if exc.code == "23505":
            raise AppError(
                code="ticket_transfer_pending_exists",
                message="A pending transfer already exists for this ticket",
                http_status=409,
                details={"message_key": "events.transfer.errors.pendingExists"},
            ) from exc
        raise

    row = _single_row(response)
    if row is None:
        raise AppError(code="internal_error", message="Failed to create transfer", http_status=500)

    _notify_recipient(service_client.client, transfer_row=row, ticket_id=ticket_id)

    return InitiateTransferResponse(transfer=_serialize_transfer(row))


@router.get("/{ticket_id}/transfer", response_model=CurrentTransferResponse)
async def get_current_transfer(
    ticket_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CurrentTransferResponse:
    ticket = _load_ticket(service_client, ticket_id)
    _assert_holder(ticket, current_user.id)

    response = (
        service_client.client.table("ticket_transfers")
        .select("id, ticket_id, from_user_id, to_phone, status, expires_at, created_at")
        .eq("ticket_id", ticket_id)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    transfer = _serialize_transfer(rows[0]) if rows else None
    return CurrentTransferResponse(transfer=transfer)


@router.post("/transfers/{transfer_id}/cancel", response_model=CancelTransferResponse)
async def cancel_transfer(
    transfer_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CancelTransferResponse:
    _rate_limit_transfer(request, current_user.id, service_client, scope="ticket_transfer_cancel")
    row = _load_transfer(service_client, transfer_id)
    if str(row["from_user_id"]) != current_user.id:
        raise AppError(
            code="forbidden",
            message="Only the sender may cancel this transfer",
            http_status=403,
            details={"message_key": "events.transfer.errors.notHolder"},
        )
    if str(row["status"]) != "pending":
        raise AppError(
            code="ticket_transfer_not_pending",
            message="This transfer is no longer pending",
            http_status=409,
            details={"message_key": "events.transfer.errors.notPending"},
        )

    now_iso = datetime.now(UTC).isoformat()
    update_response = (
        service_client.client.table("ticket_transfers")
        .update({"status": "cancelled", "cancelled_at": now_iso})
        .eq("id", transfer_id)
        .eq("status", "pending")
        .execute()
    )
    updated = _single_row(update_response)
    if updated is None:
        raise AppError(
            code="ticket_transfer_not_pending",
            message="Transfer status changed before it could be cancelled",
            http_status=409,
            details={"message_key": "events.transfer.errors.notPending"},
        )
    return CancelTransferResponse(transfer=_serialize_transfer(updated))


@router.post("/transfers/{transfer_id}/claim", response_model=ClaimTransferResponse)
async def claim_transfer(
    transfer_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> ClaimTransferResponse:
    _rate_limit_transfer(request, current_user.id, service_client, scope="ticket_transfer_claim")
    row = _load_transfer(service_client, transfer_id)

    recipient_phone = _load_verified_phone(service_client, current_user.id)
    if recipient_phone is None or recipient_phone != str(row["to_phone"]):
        raise AppError(
            code="forbidden",
            message="Sign in with the phone number this ticket was sent to",
            http_status=403,
            details={"message_key": "events.transfer.errors.phoneMismatch"},
        )

    if str(row["status"]) != "pending":
        raise AppError(
            code="ticket_transfer_not_pending",
            message="This transfer is no longer pending",
            http_status=409,
            details={"message_key": "events.transfer.errors.notPending"},
        )

    now = datetime.now(UTC)
    if now > _parse_dt(str(row["expires_at"])):
        service_client.client.table("ticket_transfers").update({"status": "expired"}).eq(
            "id", transfer_id
        ).eq("status", "pending").execute()
        raise AppError(
            code="ticket_transfer_expired",
            message="This transfer offer has expired",
            http_status=409,
            details={"message_key": "events.transfer.errors.expired"},
        )

    ticket_id = str(row["ticket_id"])
    new_qr_secret = generate_qr_secret()
    new_pin_hash = seal_pin_storage(pin=generate_pin(), ticket_id=ticket_id)

    claimed = _claim_transfer_atomic(
        transfer_id=transfer_id,
        claiming_user_id=current_user.id,
        qr_secret=new_qr_secret,
        pin_hash=new_pin_hash,
        now=now,
    )
    if claimed is None:
        refreshed = _load_transfer(service_client, transfer_id)
        if str(refreshed["status"]) != "pending":
            raise AppError(
                code="ticket_transfer_not_pending",
                message="This transfer is no longer pending",
                http_status=409,
                details={"message_key": "events.transfer.errors.notPending"},
            )
        raise AppError(
            code="ticket_not_transferable",
            message="Ticket is no longer eligible for transfer",
            http_status=409,
            details={"message_key": "events.transfer.errors.notTransferable"},
        )

    claimed_transfer_id, claimed_ticket_id = claimed
    updated_row = _load_transfer(service_client, claimed_transfer_id)
    return ClaimTransferResponse(
        transfer=_serialize_transfer(updated_row),
        ticket_id=claimed_ticket_id,
    )


@router.get("/transfers/inbound", response_model=InboundTransfersResponse)
async def list_inbound_transfers(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> InboundTransfersResponse:
    phone = _load_verified_phone(service_client, current_user.id)
    if phone is None:
        return InboundTransfersResponse(transfers=[])

    now_iso = datetime.now(UTC).isoformat()
    response = (
        service_client.client.table("ticket_transfers")
        .select("id, ticket_id, expires_at")
        .eq("to_phone", phone)
        .eq("status", "pending")
        .gt("expires_at", now_iso)
        .order("created_at", desc=True)
        .execute()
    )

    items: list[InboundTransferOut] = []
    for transfer_row in _rows(response):
        ticket_id = str(transfer_row["ticket_id"])
        event_title: str | None = None
        event_venue: str | None = None
        starts_at: str | None = None
        try:
            ticket = _load_ticket(service_client, ticket_id)
            instance = _load_instance(service_client, str(ticket["instance_id"]))
            starts_at = str(instance["starts_at"])
            event_response = (
                service_client.client.table("events")
                .select("title, venue")
                .eq("id", str(instance["event_id"]))
                .maybe_single()
                .execute()
            )
            event_row = _single_row(event_response)
            if event_row is not None:
                event_title = event_row.get("title")
                event_venue = event_row.get("venue")
        except AppError:
            pass

        items.append(
            InboundTransferOut(
                id=str(transfer_row["id"]),
                ticket_id=ticket_id,
                expires_at=str(transfer_row["expires_at"]),
                event_title=event_title,
                event_venue=event_venue,
                starts_at=starts_at,
            )
        )
    return InboundTransfersResponse(transfers=items)
