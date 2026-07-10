"""Organiser-scoped ticket QR/PIN verify and atomic check-in (M10-P06)."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.orders.audit import run_sql_script
from app.services.orders.state import sql_uuid
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
    if not pin_hash:
        return False
    try:
        expected = hash_ticket_pin(pin=pin, ticket_id=ticket_id, secret=secret)
    except ValueError:
        return False
    return hmac.compare_digest(expected, pin_hash)


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
    qr_secret: str | None
    pin_hash: str | None
    checked_in_at: str | None
    organiser_vendor_id: str


@dataclass(frozen=True, slots=True)
class CheckInResult:
    ticket_id: str
    from_status: str
    to_status: str
    checked_in_at: datetime


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _load_vendor_for_owner(
    service_client: _ServiceRoleClient,
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


def _fetch_ticket_row(ticket_id: str) -> TicketRow:
    ticket_sql = sql_uuid(ticket_id, "ticket_id")
    script = f"""
SELECT
  t.id::text,
  t.status,
  t.qr_secret,
  t.pin_hash,
  coalesce(t.checked_in_at::text, ''),
  e.organiser_vendor_id::text
FROM public.tickets t
JOIN public.event_instances ei ON ei.id = t.instance_id
JOIN public.events e ON e.id = ei.event_id
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

    parts = result.rows[0].split("|")
    if len(parts) != 6:
        raise RuntimeError("unexpected ticket verify lookup shape")

    return TicketRow(
        ticket_id=parts[0],
        status=parts[1],
        qr_secret=parts[2] or None,
        pin_hash=parts[3] or None,
        checked_in_at=parts[4] or None,
        organiser_vendor_id=parts[5],
    )


def _assert_organiser_scope(*, ticket: TicketRow, vendor_id: str) -> None:
    if ticket.organiser_vendor_id != vendor_id:
        raise AppError(
            code="forbidden",
            message="Organiser may only verify tickets for their own events",
            http_status=403,
            details={"ticket_id": ticket.ticket_id},
        )


def _assert_checkinable_status(ticket: TicketRow) -> None:
    if ticket.status == "checked_in":
        raise AppError(
            code="ticket_already_checked_in",
            message="Ticket has already been checked in",
            http_status=409,
            details={"ticket_id": ticket.ticket_id},
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


def _atomic_check_in(*, ticket_id: str, vendor_id: str) -> CheckInResult | None:
    """Single-use claim: exactly one concurrent caller may transition issued → checked_in."""
    ticket_sql = sql_uuid(ticket_id, "ticket_id")
    vendor_sql = sql_uuid(vendor_id, "vendor_id")
    script = f"""
BEGIN;
WITH locked AS (
  SELECT t.id
  FROM public.tickets t
  JOIN public.event_instances ei ON ei.id = t.instance_id
  JOIN public.events e ON e.id = ei.event_id
  WHERE t.id = {ticket_sql}
    AND e.organiser_vendor_id = {vendor_sql}
    AND t.status = 'issued'
  FOR UPDATE
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
) -> CheckInResult:
    ticket = _fetch_ticket_row(ticket_id)
    _assert_organiser_scope(ticket=ticket, vendor_id=vendor_id)
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

    claimed = _atomic_check_in(ticket_id=ticket_id, vendor_id=vendor_id)
    if claimed is None:
        refreshed = _fetch_ticket_row(ticket_id)
        if refreshed.status == "checked_in":
            raise AppError(
                code="ticket_already_checked_in",
                message="Ticket has already been checked in",
                http_status=409,
                details={"ticket_id": ticket_id},
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
    scans: list[BatchScanItem] = Field(min_length=1, max_length=500)


BatchOutcome = Literal["checked_in", "duplicate", "rejected", "already_checked_in"]


class BatchScanResult(StrictModel):
    ticket_id: str
    scanned_at: datetime
    outcome: BatchOutcome
    from_status: str | None = None
    checked_in_at: datetime | None = None
    error_code: str | None = None


class BatchVerifyResponse(StrictModel):
    results: list[BatchScanResult]


def _process_batch_scan(
    *,
    item: BatchScanItem,
    vendor_id: str,
    is_primary: bool,
    now: datetime | None = None,
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
        )

    try:
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

    claimed = _atomic_check_in(ticket_id=item.ticket_id, vendor_id=vendor_id)
    if claimed is None:
        refreshed = _fetch_ticket_row(item.ticket_id)
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
    )


def verify_batch_scans(
    *,
    scans: list[BatchScanItem],
    vendor_id: str,
    now: datetime | None = None,
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
        )
    return [result for result in results if result is not None]


@router.post("/verify", response_model=VerifyTicketResponse)
def verify_ticket(
    body: VerifyTicketRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> VerifyTicketResponse:
    _rate_limit_verify(request, current_user.id, service_client)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])

    result = verify_and_check_in_ticket(
        ticket_id=body.ticket_id.strip(),
        vendor_id=vendor_id,
        code=body.code.strip() if body.code else None,
        pin=body.pin.strip() if body.pin else None,
    )
    return VerifyTicketResponse(
        ticket_id=result.ticket_id,
        from_status=result.from_status,
        to_status=result.to_status,
        checked_in_at=result.checked_in_at,
    )


@router.post("/verify/batch", response_model=BatchVerifyResponse)
def verify_ticket_batch(
    body: BatchVerifyRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> BatchVerifyResponse:
    _rate_limit_verify(request, current_user.id, service_client)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])

    results = verify_batch_scans(scans=body.scans, vendor_id=vendor_id)
    return BatchVerifyResponse(results=results)
