"""Free service booking requests — no quote, no order, no payment, no commission.

A customer requests a free service (``services.is_free``); the vendor accepts or
declines. Rows live in ``public.service_free_bookings`` and status moves only via
``public.transition_service_free_booking`` (guarded + audited in SQL).
Idempotent per (customer, service, idempotency_key).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from app.errors import AppError
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.stock.claim import sql_uuid

FreeBookingStatus = Literal["requested", "accepted", "declined", "cancelled"]
MAX_NOTE_LEN = 2000


@dataclass(frozen=True, slots=True)
class FreeBooking:
    id: str
    service_id: str
    vendor_id: str
    customer_id: str
    status: FreeBookingStatus
    note: str | None
    preferred_date: str | None
    created_at: str
    replayed: bool = False


def _row_sql(where: str, *, limit: int = 1) -> str:
    return f"""
SELECT json_build_object(
  'id', id, 'service_id', service_id, 'vendor_id', vendor_id,
  'customer_id', customer_id, 'status', status, 'note', note,
  'preferred_date', preferred_date, 'created_at', created_at)::text
FROM public.service_free_bookings
WHERE {where}
ORDER BY created_at DESC
LIMIT {int(limit)};
"""


def _parse(raw: str, *, replayed: bool = False) -> FreeBooking:
    d: dict[str, Any] = json.loads(raw)
    return FreeBooking(
        id=str(d["id"]),
        service_id=str(d["service_id"]),
        vendor_id=str(d["vendor_id"]),
        customer_id=str(d["customer_id"]),
        status=d["status"],
        note=d.get("note"),
        preferred_date=d.get("preferred_date"),
        created_at=str(d["created_at"]),
        replayed=replayed,
    )


def _not_found() -> AppError:
    return AppError(
        code="not_found",
        message="Service not found",
        http_status=404,
        details={"message_key": "services.errors.not_found"},
    )


def request_free_booking(
    *,
    service_id: str,
    customer_id: str,
    idempotency_key: str,
    note: str | None = None,
    preferred_date: date | None = None,
) -> FreeBooking:
    svc = sql_uuid(service_id, "service_id")
    cust = sql_uuid(customer_id, "customer_id")
    key = sql_literal(idempotency_key)

    existing = run_sql_script(
        _row_sql(f"customer_id = {cust} AND service_id = {svc} AND idempotency_key = {key}")
    )
    if existing.ok and existing.rows:
        return _parse(existing.rows[0], replayed=True)

    svc_row = run_sql_script(
        f"""
SELECT concat_ws('|', s.vendor_id, s.status, s.is_free, coalesce(v.owner_user_id::text, ''))
FROM public.services s JOIN public.vendors v ON v.id = s.vendor_id
WHERE s.id = {svc};
"""
    )
    if not svc_row.ok:
        raise RuntimeError(f"free booking service lookup failed: {svc_row.error}")
    if not svc_row.rows:
        raise _not_found()
    vendor_id, status, is_free, owner = svc_row.rows[0].split("|")
    if status != "active":
        raise _not_found()
    if is_free not in ("t", "true"):
        raise AppError(
            code="conflict",
            message="This service is not free; request a quote or book it",
            http_status=409,
            details={"message_key": "services.freeBooking.errors.notFree"},
        )
    if owner and owner == customer_id:
        raise AppError(
            code="forbidden",
            message="You cannot book your own service",
            http_status=422,
            details={"message_key": "services.booking.errors.ownService"},
        )

    note_clean = (note or "").strip()[:MAX_NOTE_LEN] or None
    note_sql = sql_literal(note_clean) if note_clean else "NULL"
    date_sql = sql_literal(preferred_date.isoformat()) + "::date" if preferred_date else "NULL"
    inserted = run_sql_script(
        f"""
INSERT INTO public.service_free_bookings
  (service_id, vendor_id, customer_id, idempotency_key, note, preferred_date)
VALUES ({svc}, {sql_uuid(vendor_id, "vendor_id")}, {cust}, {key}, {note_sql}, {date_sql})
ON CONFLICT DO NOTHING
RETURNING id::text;
"""
    )
    if not inserted.ok:
        raise RuntimeError(f"free booking insert failed: {inserted.error}")
    if not inserted.rows:
        # Same key raced us (replay) or an open request already exists.
        again = run_sql_script(
            _row_sql(f"customer_id = {cust} AND service_id = {svc} AND idempotency_key = {key}")
        )
        if again.ok and again.rows:
            return _parse(again.rows[0], replayed=True)
        raise AppError(
            code="conflict",
            message="You already have an open request for this service",
            http_status=409,
            details={"message_key": "services.freeBooking.errors.alreadyRequested"},
        )
    row = run_sql_script(_row_sql(f"id = {sql_uuid(inserted.rows[0], 'id')}"))
    if not row.ok or not row.rows:
        raise RuntimeError(f"free booking reload failed: {row.error}")
    return _parse(row.rows[0])


_TRANSITION_ERRORS: dict[str, tuple[int, str, str]] = {
    "P0002": (404, "not_found", "services.freeBooking.errors.notFound"),
    "42501": (403, "forbidden", "services.freeBooking.errors.forbidden"),
    "55000": (409, "conflict", "services.freeBooking.errors.invalidTransition"),
}


def transition_free_booking(
    *, booking_id: str, to: FreeBookingStatus, actor_id: str
) -> FreeBooking:
    """Accept/decline (vendor) or cancel (customer) via the guarded SQL function."""
    bid = sql_uuid(booking_id, "booking_id")
    result = run_sql_script(
        f"SELECT public.transition_service_free_booking({bid}, {sql_literal(to)}, "
        f"{sql_uuid(actor_id, 'actor_id')});"
    )
    if not result.ok:
        err = str(result.error or "")
        for state, (http, code, key) in _TRANSITION_ERRORS.items():
            if state in err or getattr(result, "sqlstate", None) == state:
                raise AppError(
                    code=code, message="Free booking transition refused",
                    http_status=http, details={"message_key": key},
                )
        lowered = err.lower()
        if "not found" in lowered:
            raise AppError(code="not_found", message="Booking not found", http_status=404,
                           details={"message_key": "services.freeBooking.errors.notFound"})
        if "only the" in lowered:
            raise AppError(code="forbidden", message="Not allowed", http_status=403,
                           details={"message_key": "services.freeBooking.errors.forbidden"})
        if "invalid transition" in lowered:
            raise AppError(code="conflict", message="Invalid transition", http_status=409,
                           details={"message_key": "services.freeBooking.errors.invalidTransition"})
        raise RuntimeError(f"free booking transition failed: {err}")
    row = run_sql_script(_row_sql(f"id = {bid}"))
    if not row.ok or not row.rows:
        raise RuntimeError(f"free booking reload failed: {row.error}")
    return _parse(row.rows[0])


def list_vendor_free_bookings(*, vendor_owner_id: str, limit: int = 50) -> list[FreeBooking]:
    owner = sql_uuid(vendor_owner_id, "vendor_owner_id")
    result = run_sql_script(
        _row_sql(
            "vendor_id IN (SELECT id FROM public.vendors WHERE owner_user_id = " + owner + ")",
            limit=limit,
        )
    )
    if not result.ok:
        raise RuntimeError(f"free booking list failed: {result.error}")
    return [_parse(r) for r in result.rows]
