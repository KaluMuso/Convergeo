"""Organiser-scoped ticket QR/PIN verify and atomic check-in (M10-P06)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.events.high_value import ID_CHECK_THRESHOLD_NGWEE
from app.services.events.teams import OVERRIDE_ROLES, SCAN_ROLES, require_event_role
from app.services.orders.audit import run_sql_script
from app.services.orders.state import sql_uuid
from app.services.tickets.qr import verify_pin as qr_verify_pin
from fastapi import APIRouter, Depends, Request
from pydantic import Field, field_validator, model_validator

router = APIRouter(prefix="/tickets", tags=["ticket-verify"])

_PIN_RE = re.compile(r"^\d{6}$")
_SIG_TRUNCATE_LEN = 16
_WINDOW_TOLERANCE = 1


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def current_window(now: datetime | None = None) -> int:
    instant = now or datetime.now(UTC)
    return int(instant.timestamp() // 60)


def window_sig(ticket_secret: str, window: int) -> str:
    digest = hmac.new(
        ticket_secret.encode("utf-8"),
        str(window).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:_SIG_TRUNCATE_LEN]


def build_qr_code(*, ticket_id: str, ticket_secret: str, window: int) -> str:
    return f"{ticket_id}:{window}:{window_sig(ticket_secret, window)}"


def _resolve_signing_secret() -> str:
    secret = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not secret:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for ticket PIN verification")
    return secret


def hash_ticket_pin(*, pin: str, ticket_id: str, secret: str | None = None) -> str:
    if not _PIN_RE.match(pin):
        raise ValueError("PIN must be exactly 6 digits")
    pepper = secret or _resolve_signing_secret()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        f"ticket-pin:{pepper}:{ticket_id}".encode(),
        120_000,
    )
    return digest.hex()


def verify_ticket_pin(
    *,
    pin: str,
    ticket_id: str,
    pin_hash: str,
    secret: str | None = None,
) -> bool:
    return qr_verify_pin(pin=pin, ticket_id=ticket_id, pin_hash=pin_hash, secret=secret)


def parse_qr_code(*, ticket_id: str, code: str) -> tuple[int, str]:
    cleaned = code.strip()
    parts = cleaned.split(":")
    if len(parts) == 3:
        code_ticket_id, window_raw, sig = parts
        if code_ticket_id != ticket_id:
            raise AppError(
                code="ticket_invalid_code",
                message="QR code does not match the ticket",
                http_status=422,
            )
        try:
            window = int(window_raw)
        except ValueError as exc:
            raise AppError(
                code="ticket_invalid_code",
                message="Invalid QR code window",
                http_status=422,
            ) from exc
        return window, sig
    if len(parts) == 2:
        window_raw, sig = parts
        try:
            window = int(window_raw)
        except ValueError as exc:
            raise AppError(
                code="ticket_invalid_code",
                message="Invalid QR code window",
                http_status=422,
            ) from exc
        return window, sig
    raise AppError(
        code="ticket_invalid_code",
        message="Invalid QR code format",
        http_status=422,
    )


def assert_window_within_tolerance(code_window: int, *, now: datetime | None = None) -> None:
    delta = abs(code_window - current_window(now))
    if delta > _WINDOW_TOLERANCE:
        raise AppError(
            code="ticket_qr_stale",
            message="QR code is outside the accepted time window",
            http_status=422,
            details={"window": code_window, "tolerance": _WINDOW_TOLERANCE},
        )


def assert_window_sig(*, qr_secret: str, window: int, sig: str) -> None:
    expected = window_sig(qr_secret, window)
    if not hmac.compare_digest(expected, sig):
        raise AppError(
            code="ticket_invalid_code",
            message="QR code signature is invalid",
            http_status=422,
        )


@dataclass(frozen=True, slots=True)
class TicketRow:
    ticket_id: str
    status: str
    order_item_id: str | None
    qr_secret: str | None
    pin_hash: str | None
    checked_in_at: str | None
    organiser_vendor_id: str
    event_id: str
    instance_id: str
    event_status: str
    holder_name: str | None
    ticket_type_name: str
    event_title: str = ""
    ticket_price_ngwee: int = 0
    id_check_enabled: bool = False


@dataclass(frozen=True, slots=True)
class CheckInResult:
    ticket_id: str
    from_status: str
    to_status: str
    checked_in_at: datetime
    event_id: str
    instance_id: str
    holder_name: str | None
    ticket_type_name: str
    event_title: str = ""
    id_check_required: bool = False


def _id_check_required(ticket: TicketRow) -> bool:
    return bool(ticket.id_check_enabled) and ticket.ticket_price_ngwee >= ID_CHECK_THRESHOLD_NGWEE


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _load_event_organiser(service_client: _ServiceRoleClient, event_id: str) -> dict[str, Any]:
    response = (
        service_client.client.table("events")
        .select("id, organiser_vendor_id, title")
        .eq("id", event_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Event not found", http_status=404)
    vendor = (
        service_client.client.table("vendors")
        .select("id, owner_user_id")
        .eq("id", str(row["organiser_vendor_id"]))
        .maybe_single()
        .execute()
    )
    vendor_row = _single_row(vendor)
    if vendor_row is None:
        raise AppError(code="not_found", message="Event organiser not found", http_status=404)
    return {
        "event_id": str(row["id"]),
        "vendor_id": str(vendor_row["id"]),
        "owner_user_id": str(vendor_row["owner_user_id"]),
        "title": str(row.get("title") or ""),
    }


def _require_scanner_access(
    service_client: _ServiceRoleClient,
    *,
    user_id: str,
    event_id: str,
    allowed: frozenset[str],
) -> str:
    """Return organiser vendor_id if the user may scan/override this event."""
    context = _load_event_organiser(service_client, event_id)
    require_event_role(
        service_client.client,
        event_id=event_id,
        user_id=user_id,
        organiser_owner_user_id=context["owner_user_id"],
        allowed=allowed,
    )
    return str(context["vendor_id"])


def _fetch_ticket_row(ticket_id: str) -> TicketRow:
    ticket_sql = sql_uuid(ticket_id, "ticket_id")
    script = f"""
SELECT json_build_object(
  'ticket_id', t.id,
  'status', t.status,
  'order_item_id', t.order_item_id,
  'qr_secret', t.qr_secret,
  'pin_hash', t.pin_hash,
  'checked_in_at', t.checked_in_at,
  'organiser_vendor_id', e.organiser_vendor_id,
  'event_id', e.id,
  'instance_id', ei.id,
  'event_status', e.status,
  'holder_name', t.holder_name,
  'ticket_type_name', tt.name,
  'event_title', e.title,
  'ticket_price_ngwee', tt.price_ngwee,
  'id_check_enabled', coalesce(e.id_check_enabled, false)
)::text
FROM public.tickets t
JOIN public.event_instances ei ON ei.id = t.instance_id
JOIN public.events e ON e.id = ei.event_id
JOIN public.ticket_types tt ON tt.id = t.ticket_type_id
WHERE t.id = {ticket_sql};
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"ticket verify lookup failed: {result.error}")
    if not result.rows:
        raise AppError(
            code="not_found",
            message="Ticket not found",
            http_status=404,
            details={"ticket_id": ticket_id},
        )

    try:
        row = json.loads(result.rows[0])
    except json.JSONDecodeError as exc:
        raise RuntimeError("unexpected ticket verify lookup shape") from exc
    if not isinstance(row, dict):
        raise RuntimeError("unexpected ticket verify lookup shape")

    order_item_raw = row.get("order_item_id")
    holder_name_raw = row.get("holder_name")
    return TicketRow(
        ticket_id=str(row["ticket_id"]),
        status=str(row["status"]),
        order_item_id=str(order_item_raw) if order_item_raw is not None else None,
        qr_secret=str(row["qr_secret"]) if row.get("qr_secret") is not None else None,
        pin_hash=str(row["pin_hash"]) if row.get("pin_hash") is not None else None,
        checked_in_at=(
            str(row["checked_in_at"]) if row.get("checked_in_at") is not None else None
        ),
        organiser_vendor_id=str(row["organiser_vendor_id"]),
        event_id=str(row["event_id"]),
        instance_id=str(row["instance_id"]),
        event_status=str(row["event_status"]),
        holder_name=str(holder_name_raw) if holder_name_raw is not None else None,
        ticket_type_name=str(row.get("ticket_type_name") or ""),
        event_title=str(row.get("event_title") or ""),
        ticket_price_ngwee=int(row.get("ticket_price_ngwee") or 0),
        id_check_enabled=bool(row.get("id_check_enabled")),
    )


def _safe_ticket_details(ticket: TicketRow) -> dict[str, str | None]:
    return {
        "ticket_id": ticket.ticket_id,
        "event_id": ticket.event_id,
        "instance_id": ticket.instance_id,
        "holder_name": ticket.holder_name,
        "ticket_type_name": ticket.ticket_type_name,
        "event_title": ticket.event_title,
        "checked_in_at": ticket.checked_in_at,
    }


def _assert_organiser_scope(*, ticket: TicketRow, vendor_id: str) -> None:
    if ticket.organiser_vendor_id != vendor_id:
        raise AppError(
            code="forbidden",
            message="Organiser may only verify tickets for their own events",
            http_status=403,
            details={"ticket_id": ticket.ticket_id},
        )


def _assert_event_published(ticket: TicketRow) -> None:
    if ticket.event_status != "published":
        raise AppError(
            code="tickets.event_not_published",
            message="Tickets can only be checked in for published events",
            http_status=409,
            details={"event_id": ticket.event_id},
        )


def _assert_expected_scope(
    ticket: TicketRow,
    *,
    expected_event_id: str | None,
    expected_instance_id: str | None,
) -> None:
    if expected_event_id is not None and ticket.event_id != expected_event_id:
        raise AppError(
            code="ticket_wrong_event",
            message="Ticket belongs to a different event",
            http_status=409,
            details={"ticket_id": ticket.ticket_id, "expected_event_id": expected_event_id},
        )
    if expected_instance_id is not None and ticket.instance_id != expected_instance_id:
        raise AppError(
            code="ticket_wrong_instance",
            message="Ticket belongs to a different event instance",
            http_status=409,
            details={
                "ticket_id": ticket.ticket_id,
                "expected_event_id": expected_event_id,
                "expected_instance_id": expected_instance_id,
            },
        )


def _assert_paid_ticket(ticket: TicketRow) -> None:
    if not ticket.order_item_id:
        raise AppError(
            code="ticket_unpaid_hold",
            message="Ticket is not paid and cannot be checked in",
            http_status=409,
            details={"ticket_id": ticket.ticket_id},
        )


def _assert_checkinable_status(ticket: TicketRow) -> None:
    if ticket.status == "checked_in":
        raise AppError(
            code="ticket_already_checked_in",
            message="Ticket has already been checked in",
            http_status=409,
            details=_safe_ticket_details(ticket),
        )
    if ticket.status == "void":
        raise AppError(
            code="ticket_void",
            message="Ticket is void and cannot be checked in",
            http_status=409,
            details={"ticket_id": ticket.ticket_id},
        )
    if ticket.status == "transferred":
        raise AppError(
            code="ticket_transferred",
            message="Ticket has been transferred and cannot be checked in",
            http_status=409,
            details={"ticket_id": ticket.ticket_id},
        )
    if ticket.status != "issued":
        raise AppError(
            code="ticket_invalid_status",
            message="Ticket cannot be checked in from its current status",
            http_status=409,
            details={"ticket_id": ticket.ticket_id, "status": ticket.status},
        )


def _atomic_check_in(
    *,
    ticket: TicketRow,
    vendor_id: str,
    expected_event_id: str | None,
    expected_instance_id: str | None,
) -> CheckInResult | None:
    """Single-use claim: exactly one concurrent caller may transition issued → checked_in."""
    ticket_sql = sql_uuid(ticket.ticket_id, "ticket_id")
    vendor_sql = sql_uuid(vendor_id, "vendor_id")
    event_clause = ""
    if expected_event_id is not None:
        event_clause = f"AND e.id = {sql_uuid(expected_event_id, 'expected_event_id')}"
    instance_clause = ""
    if expected_instance_id is not None:
        instance_clause = (
            f"AND ei.id = {sql_uuid(expected_instance_id, 'expected_instance_id')}"
        )
    script = f"""
BEGIN;
WITH event_lock AS MATERIALIZED (
  SELECT e.id
  FROM public.tickets t
  JOIN public.event_instances ei ON ei.id = t.instance_id
  JOIN public.events e ON e.id = ei.event_id
  WHERE t.id = {ticket_sql}
    AND e.organiser_vendor_id = {vendor_sql}
    AND e.status = 'published'
    {event_clause}
    {instance_clause}
  FOR SHARE OF e
),
locked AS (
  SELECT t.id
  FROM public.tickets t
  JOIN public.event_instances ei ON ei.id = t.instance_id
  JOIN event_lock e ON e.id = ei.event_id
  WHERE t.id = {ticket_sql}
    AND t.status = 'issued'
  FOR UPDATE OF t
)
UPDATE public.tickets t
SET
  status = 'checked_in',
  checked_in_at = timezone('utc', now())
FROM locked l
WHERE t.id = l.id
RETURNING t.id::text, 'issued', t.status, t.checked_in_at::text;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"ticket check-in failed: {result.error}")
    if not result.rows:
        return None

    parts = result.rows[0].split("|")
    if len(parts) != 4:
        raise RuntimeError("unexpected ticket check-in return shape")

    checked_in_at = datetime.fromisoformat(parts[3].replace("Z", "+00:00"))
    return CheckInResult(
        ticket_id=parts[0],
        from_status=parts[1],
        to_status=parts[2],
        checked_in_at=checked_in_at,
        event_id=ticket.event_id,
        instance_id=ticket.instance_id,
        holder_name=ticket.holder_name,
        ticket_type_name=ticket.ticket_type_name,
        event_title=ticket.event_title,
        id_check_required=_id_check_required(ticket),
    )


def _validate_qr_credentials(
    *,
    ticket: TicketRow,
    code: str,
    now: datetime | None = None,
) -> None:
    if not ticket.qr_secret:
        raise AppError(
            code="ticket_qr_unavailable",
            message="Ticket QR credentials are not available",
            http_status=409,
        )
    code_window, sig = parse_qr_code(ticket_id=ticket.ticket_id, code=code)
    assert_window_within_tolerance(code_window, now=now)
    assert_window_sig(qr_secret=ticket.qr_secret, window=code_window, sig=sig)


def _validate_pin_credentials(*, ticket: TicketRow, pin: str) -> None:
    pin_hash = ticket.pin_hash
    if not isinstance(pin_hash, str) or not verify_ticket_pin(
        pin=pin,
        ticket_id=ticket.ticket_id,
        pin_hash=pin_hash,
    ):
        raise AppError(
            code="ticket_invalid_pin",
            message="Invalid ticket PIN",
            http_status=422,
        )


def verify_and_check_in_ticket(
    *,
    ticket_id: str,
    vendor_id: str,
    code: str | None = None,
    pin: str | None = None,
    now: datetime | None = None,
    expected_event_id: str | None = None,
    expected_instance_id: str | None = None,
) -> CheckInResult:
    ticket = _fetch_ticket_row(ticket_id)
    _assert_organiser_scope(ticket=ticket, vendor_id=vendor_id)
    _assert_event_published(ticket)
    _assert_expected_scope(
        ticket,
        expected_event_id=expected_event_id,
        expected_instance_id=expected_instance_id,
    )
    _assert_paid_ticket(ticket)
    _assert_checkinable_status(ticket)

    if code is not None:
        _validate_qr_credentials(ticket=ticket, code=code, now=now)
    elif pin is not None:
        _validate_pin_credentials(ticket=ticket, pin=pin)
    else:
        raise AppError(
            code="validation_error",
            message="Provide exactly one of code or pin",
            http_status=422,
        )

    claimed = _atomic_check_in(
        ticket=ticket,
        vendor_id=vendor_id,
        expected_event_id=expected_event_id,
        expected_instance_id=expected_instance_id,
    )
    if claimed is None:
        refreshed = _fetch_ticket_row(ticket_id)
        _assert_organiser_scope(ticket=refreshed, vendor_id=vendor_id)
        _assert_event_published(refreshed)
        _assert_expected_scope(
            refreshed,
            expected_event_id=expected_event_id,
            expected_instance_id=expected_instance_id,
        )
        if refreshed.status == "checked_in":
            raise AppError(
                code="ticket_already_checked_in",
                message="Ticket has already been checked in",
                http_status=409,
                details=_safe_ticket_details(refreshed),
            )
        _assert_checkinable_status(refreshed)
        raise AppError(
            code="ticket_check_in_failed",
            message="Ticket could not be checked in",
            http_status=409,
            details={"ticket_id": ticket_id},
        )

    return claimed


def _rate_limit_verify(
    request: Request,
    user_id: str,
    service_client: _ServiceRoleClient,
) -> None:
    ip = get_client_ip(request)
    allowed, retry_after = bump_rate_counter(
        scope="ticket_verify_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=120,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="events.verify.errors.rateLimited",
            message="Too many ticket verify requests",
        )

    allowed_user, user_retry = bump_rate_counter(
        scope="ticket_verify_user",
        key=user_id,
        window=timedelta(minutes=1),
        limit=60,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=user_retry,
            message_key="events.verify.errors.rateLimited",
            message="Too many ticket verify requests",
        )


class VerifyTicketRequest(StrictModel):
    ticket_id: str
    event_id: str
    instance_id: str | None = None
    code: str | None = Field(default=None, min_length=1)
    pin: str | None = Field(default=None, min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_method(self) -> VerifyTicketRequest:
        has_code = bool(self.code and self.code.strip())
        has_pin = bool(self.pin and self.pin.strip())
        if has_code == has_pin:
            raise ValueError("Provide exactly one of code or pin")
        return self


class VerifyTicketResponse(StrictModel):
    ticket_id: str
    from_status: str
    to_status: str
    checked_in_at: datetime
    event_id: str
    instance_id: str
    holder_name: str | None
    ticket_type_name: str
    event_title: str = ""
    id_check_required: bool = False


class BatchScanItem(StrictModel):
    ticket_id: str
    code: str | None = Field(default=None, min_length=1)
    pin: str | None = Field(default=None, min_length=6, max_length=6)
    scanned_at: datetime

    @model_validator(mode="after")
    def validate_method(self) -> BatchScanItem:
        has_code = bool(self.code and self.code.strip())
        has_pin = bool(self.pin and self.pin.strip())
        if has_code == has_pin:
            raise ValueError("Provide exactly one of code or pin")
        return self

    @field_validator("scanned_at")
    @classmethod
    def normalize_scanned_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class BatchVerifyRequest(StrictModel):
    event_id: str
    instance_id: str
    scans: list[BatchScanItem] = Field(min_length=1, max_length=500)


BatchOutcome = Literal["checked_in", "duplicate", "rejected", "already_checked_in"]


class BatchScanResult(StrictModel):
    ticket_id: str
    scanned_at: datetime
    outcome: BatchOutcome
    from_status: str | None = None
    checked_in_at: datetime | None = None
    error_code: str | None = None
    event_id: str | None = None
    instance_id: str | None = None
    holder_name: str | None = None
    ticket_type_name: str | None = None
    event_title: str | None = None
    id_check_required: bool = False


class BatchVerifyResponse(StrictModel):
    results: list[BatchScanResult]


def _process_batch_scan(
    *,
    item: BatchScanItem,
    vendor_id: str,
    is_primary: bool,
    now: datetime | None = None,
    expected_event_id: str | None = None,
    expected_instance_id: str | None = None,
) -> BatchScanResult:
    if not is_primary:
        return BatchScanResult(
            ticket_id=item.ticket_id,
            scanned_at=item.scanned_at,
            outcome="duplicate",
            error_code="ticket_duplicate_scan",
        )

    ticket = _fetch_ticket_row(item.ticket_id)
    _assert_organiser_scope(ticket=ticket, vendor_id=vendor_id)

    try:
        _assert_event_published(ticket)
        _assert_expected_scope(
            ticket,
            expected_event_id=expected_event_id,
            expected_instance_id=expected_instance_id,
        )
    except AppError as exc:
        return BatchScanResult(
            ticket_id=item.ticket_id,
            scanned_at=item.scanned_at,
            outcome="rejected",
            from_status=ticket.status,
            error_code=exc.code,
        )

    if ticket.status == "checked_in":
        checked_in_at = None
        if ticket.checked_in_at:
            checked_in_at = datetime.fromisoformat(ticket.checked_in_at.replace("Z", "+00:00"))
        return BatchScanResult(
            ticket_id=item.ticket_id,
            scanned_at=item.scanned_at,
            outcome="already_checked_in",
            from_status="checked_in",
            checked_in_at=checked_in_at,
            event_id=ticket.event_id,
            instance_id=ticket.instance_id,
            holder_name=ticket.holder_name,
            ticket_type_name=ticket.ticket_type_name,
            event_title=ticket.event_title,
            id_check_required=_id_check_required(ticket),
        )

    try:
        _assert_paid_ticket(ticket)
        _assert_checkinable_status(ticket)
        if item.code is not None:
            _validate_qr_credentials(ticket=ticket, code=item.code, now=now)
        else:
            assert item.pin is not None
            _validate_pin_credentials(ticket=ticket, pin=item.pin)
    except AppError as exc:
        return BatchScanResult(
            ticket_id=item.ticket_id,
            scanned_at=item.scanned_at,
            outcome="rejected",
            from_status=ticket.status,
            error_code=exc.code,
        )

    claimed = _atomic_check_in(
        ticket=ticket,
        vendor_id=vendor_id,
        expected_event_id=expected_event_id,
        expected_instance_id=expected_instance_id,
    )
    if claimed is None:
        refreshed = _fetch_ticket_row(item.ticket_id)
        _assert_organiser_scope(ticket=refreshed, vendor_id=vendor_id)
        try:
            _assert_event_published(refreshed)
            _assert_expected_scope(
                refreshed,
                expected_event_id=expected_event_id,
                expected_instance_id=expected_instance_id,
            )
        except AppError as exc:
            return BatchScanResult(
                ticket_id=item.ticket_id,
                scanned_at=item.scanned_at,
                outcome="rejected",
                from_status=refreshed.status,
                error_code=exc.code,
            )
        if refreshed.status == "checked_in":
            checked_in_at = None
            if refreshed.checked_in_at:
                checked_in_at = datetime.fromisoformat(
                    refreshed.checked_in_at.replace("Z", "+00:00")
                )
            return BatchScanResult(
                ticket_id=item.ticket_id,
                scanned_at=item.scanned_at,
                outcome="already_checked_in",
                from_status="checked_in",
                checked_in_at=checked_in_at,
                event_id=refreshed.event_id,
                instance_id=refreshed.instance_id,
                holder_name=refreshed.holder_name,
                ticket_type_name=refreshed.ticket_type_name,
                event_title=refreshed.event_title,
                id_check_required=_id_check_required(refreshed),
            )
        return BatchScanResult(
            ticket_id=item.ticket_id,
            scanned_at=item.scanned_at,
            outcome="rejected",
            from_status=refreshed.status,
            error_code="ticket_check_in_failed",
        )

    return BatchScanResult(
        ticket_id=item.ticket_id,
        scanned_at=item.scanned_at,
        outcome="checked_in",
        from_status=claimed.from_status,
        checked_in_at=claimed.checked_in_at,
        event_id=claimed.event_id,
        instance_id=claimed.instance_id,
        holder_name=claimed.holder_name,
        ticket_type_name=claimed.ticket_type_name,
        event_title=claimed.event_title,
        id_check_required=claimed.id_check_required,
    )


def verify_batch_scans(
    *,
    scans: list[BatchScanItem],
    vendor_id: str,
    now: datetime | None = None,
    expected_event_id: str | None = None,
    expected_instance_id: str | None = None,
) -> list[BatchScanResult]:
    grouped: dict[str, list[tuple[int, BatchScanItem]]] = defaultdict(list)
    for index, item in enumerate(scans):
        grouped[item.ticket_id].append((index, item))

    primary_indexes: set[int] = set()
    for entries in grouped.values():
        entries.sort(key=lambda pair: (pair[1].scanned_at, pair[0]))
        primary_indexes.add(entries[0][0])

    results: list[BatchScanResult | None] = [None] * len(scans)
    for index, item in enumerate(scans):
        results[index] = _process_batch_scan(
            item=item,
            vendor_id=vendor_id,
            is_primary=index in primary_indexes,
            now=now,
            expected_event_id=expected_event_id,
            expected_instance_id=expected_instance_id,
        )
    return [result for result in results if result is not None]


@router.post("/verify", response_model=VerifyTicketResponse)
def verify_ticket(
    body: VerifyTicketRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> VerifyTicketResponse:
    _rate_limit_verify(request, current_user.id, service_client)
    vendor_id = _require_scanner_access(
        service_client,
        user_id=current_user.id,
        event_id=body.event_id.strip(),
        allowed=SCAN_ROLES,
    )

    result = verify_and_check_in_ticket(
        ticket_id=body.ticket_id.strip(),
        vendor_id=vendor_id,
        code=body.code.strip() if body.code else None,
        pin=body.pin.strip() if body.pin else None,
        expected_event_id=body.event_id.strip(),
        expected_instance_id=body.instance_id.strip() if body.instance_id else None,
    )
    return VerifyTicketResponse(
        ticket_id=result.ticket_id,
        from_status=result.from_status,
        to_status=result.to_status,
        checked_in_at=result.checked_in_at,
        event_id=result.event_id,
        instance_id=result.instance_id,
        holder_name=result.holder_name,
        ticket_type_name=result.ticket_type_name,
        event_title=result.event_title,
        id_check_required=result.id_check_required,
    )


@router.post("/verify/batch", response_model=BatchVerifyResponse)
def verify_ticket_batch(
    body: BatchVerifyRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> BatchVerifyResponse:
    _rate_limit_verify(request, current_user.id, service_client)
    vendor_id = _require_scanner_access(
        service_client,
        user_id=current_user.id,
        event_id=body.event_id.strip(),
        allowed=SCAN_ROLES,
    )

    results = verify_batch_scans(
        scans=body.scans,
        vendor_id=vendor_id,
        expected_event_id=body.event_id.strip(),
        expected_instance_id=body.instance_id.strip(),
    )
    return BatchVerifyResponse(results=results)


class OverrideCheckInRequest(StrictModel):
    ticket_id: str
    event_id: str
    instance_id: str | None = None
    reason: str = Field(min_length=3, max_length=500)


def override_and_check_in_ticket(
    *,
    ticket_id: str,
    vendor_id: str,
    actor_user_id: str,
    reason: str,
    expected_event_id: str,
    expected_instance_id: str | None,
) -> CheckInResult:
    ticket = _fetch_ticket_row(ticket_id)
    _assert_organiser_scope(ticket=ticket, vendor_id=vendor_id)
    _assert_event_published(ticket)
    _assert_expected_scope(
        ticket,
        expected_event_id=expected_event_id,
        expected_instance_id=expected_instance_id,
    )
    _assert_paid_ticket(ticket)
    _assert_checkinable_status(ticket)
    claimed = _atomic_check_in(
        ticket=ticket,
        vendor_id=vendor_id,
        expected_event_id=expected_event_id,
        expected_instance_id=expected_instance_id,
    )
    if claimed is None:
        raise AppError(
            code="ticket_check_in_failed",
            message="Ticket could not be checked in",
            http_status=409,
            details={"ticket_id": ticket_id},
        )
    event_sql = sql_uuid(ticket.event_id, "event_id")
    ticket_sql = sql_uuid(ticket.ticket_id, "ticket_id")
    instance_sql = sql_uuid(ticket.instance_id, "instance_id")
    actor_sql = sql_uuid(actor_user_id, "actor_user_id")
    reason_sql = "'" + reason.replace("'", "''") + "'"
    script = f"""
INSERT INTO public.event_checkin_overrides (
  event_id, ticket_id, instance_id, actor_user_id, reason
) VALUES (
  {event_sql}, {ticket_sql}, {instance_sql}, {actor_sql}, {reason_sql}
);
INSERT INTO public.audit_log (actor, action, entity_type, entity_id, before, after)
VALUES (
  {actor_sql}, 'event_checkin_override', 'ticket', {ticket_sql}, NULL,
  jsonb_build_object('reason', {reason_sql}, 'event_id', {event_sql}::text)
);
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"check-in override audit failed: {result.error}")
    return claimed


@router.post("/verify/override", response_model=VerifyTicketResponse)
def override_ticket_check_in(
    body: OverrideCheckInRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> VerifyTicketResponse:
    _rate_limit_verify(request, current_user.id, service_client)
    vendor_id = _require_scanner_access(
        service_client,
        user_id=current_user.id,
        event_id=body.event_id.strip(),
        allowed=OVERRIDE_ROLES,
    )
    result = override_and_check_in_ticket(
        ticket_id=body.ticket_id.strip(),
        vendor_id=vendor_id,
        actor_user_id=current_user.id,
        reason=body.reason.strip(),
        expected_event_id=body.event_id.strip(),
        expected_instance_id=body.instance_id.strip() if body.instance_id else None,
    )
    return VerifyTicketResponse(
        ticket_id=result.ticket_id,
        from_status=result.from_status,
        to_status=result.to_status,
        checked_in_at=result.checked_in_at,
        event_id=result.event_id,
        instance_id=result.instance_id,
        holder_name=result.holder_name,
        ticket_type_name=result.ticket_type_name,
        event_title=result.event_title,
        id_check_required=result.id_check_required,
    )
