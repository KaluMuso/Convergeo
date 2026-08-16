"""Buyer ticket-cancellation refund matrix (strategy §5.5).

Windows are measured against the purchased instance start in UTC:

* more than 7 days out → full refund minus 5% admin fee
* 1–7 days out (and ≥24 hours) → 50% refund
* less than 24 hours → no refund (transfer still allowed)

Organiser-cancel remains 100% via ``event_refund_jobs`` source ``organiser_cancel``.
This module never calls ``execute_refund``; it only computes policy and amounts,
voids the ticket, and enqueues ``event_refund_jobs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from app.errors import AppError
from app.services.events.refund_jobs import (
    SOURCE_BUYER_CANCEL,
    SOURCE_RESCHEDULE_OPT_OUT,
    enqueue_event_refund_job,
)
from app.services.stock.claim import run_sql_script, sql_uuid

ADMIN_FEE_BPS = 500
FULL_WINDOW = timedelta(days=7)
NO_REFUND_WINDOW = timedelta(hours=24)

BuyerCancelBand = Literal["full_minus_admin", "half", "none"]


@dataclass(frozen=True, slots=True)
class BuyerCancelPolicy:
    band: BuyerCancelBand
    refund_ngwee: int
    admin_fee_ngwee: int
    hours_until_start: float


def buyer_cancel_band(starts_at: datetime, *, now: datetime | None = None) -> BuyerCancelBand:
    instant = now or datetime.now(UTC)
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    lead = starts_at.astimezone(UTC) - instant.astimezone(UTC)
    if lead >= FULL_WINDOW:
        return "full_minus_admin"
    if lead >= NO_REFUND_WINDOW:
        return "half"
    return "none"


def compute_buyer_cancel_refund(
    *,
    paid_ngwee: int,
    starts_at: datetime,
    now: datetime | None = None,
) -> BuyerCancelPolicy:
    if paid_ngwee < 0:
        paid_ngwee = 0
    instant = now or datetime.now(UTC)
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)
    hours = (starts_at.astimezone(UTC) - instant.astimezone(UTC)).total_seconds() / 3600
    band = buyer_cancel_band(starts_at, now=instant)
    if band == "none" or paid_ngwee == 0:
        return BuyerCancelPolicy(
            band=band, refund_ngwee=0, admin_fee_ngwee=0, hours_until_start=hours
        )
    if band == "half":
        refund = paid_ngwee // 2
        return BuyerCancelPolicy(
            band=band,
            refund_ngwee=refund,
            admin_fee_ngwee=paid_ngwee - refund,
            hours_until_start=hours,
        )
    admin_fee = (paid_ngwee * ADMIN_FEE_BPS) // 10_000
    return BuyerCancelPolicy(
        band=band,
        refund_ngwee=max(paid_ngwee - admin_fee, 0),
        admin_fee_ngwee=admin_fee,
        hours_until_start=hours,
    )


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class BuyerCancelResult:
    ticket_id: str
    band: BuyerCancelBand
    refund_ngwee: int
    queued: bool


def _load_holder_ticket_for_cancel(ticket_id: str, holder_user_id: str) -> dict[str, Any]:
    ticket_sql = sql_uuid(ticket_id, "ticket_id")
    holder_sql = sql_uuid(holder_user_id, "holder_user_id")
    result = run_sql_script(
        f"""
SELECT
  t.id::text,
  t.status,
  t.holder_user_id::text,
  t.order_item_id::text,
  ei.starts_at::text,
  e.id::text,
  oi.order_id::text,
  oi.qty::text,
  oi.unit_price_ngwee::text,
  o.customer_id::text,
  coalesce(o.platform_fee_ngwee::text, '0')
FROM public.tickets t
JOIN public.event_instances ei ON ei.id = t.instance_id
JOIN public.events e ON e.id = ei.event_id
LEFT JOIN public.order_items oi ON oi.id = t.order_item_id
LEFT JOIN public.orders o ON o.id = oi.order_id
WHERE t.id = {ticket_sql}
  AND t.holder_user_id = {holder_sql};
"""
    )
    if not result.ok:
        raise RuntimeError(f"buyer cancel lookup failed: {result.error}")
    if not result.rows:
        raise AppError(code="not_found", message="Ticket not found", http_status=404)
    parts = result.rows[0].split("|")
    if len(parts) != 11:
        raise RuntimeError("unexpected buyer cancel lookup shape")
    return {
        "ticket_id": parts[0],
        "status": parts[1],
        "holder_user_id": parts[2],
        "order_item_id": parts[3] or None,
        "starts_at": parts[4],
        "event_id": parts[5],
        "order_id": parts[6] or None,
        "qty": int(parts[7] or "0"),
        "unit_price_ngwee": int(parts[8] or "0"),
        "customer_id": parts[9] or None,
        "platform_fee_ngwee": int(parts[10] or "0"),
    }


def _open_reschedule(event_id: str) -> tuple[str, str] | None:
    event_sql = sql_uuid(event_id, "event_id")
    open_result = run_sql_script(
        f"""
SELECT id::text, opt_out_deadline::text
FROM public.event_reschedules
WHERE event_id = {event_sql}
  AND opt_out_deadline > timezone('utc', now())
ORDER BY announced_at DESC
LIMIT 1;
"""
    )
    if not open_result.ok:
        raise RuntimeError(f"reschedule lookup failed: {open_result.error}")
    if not open_result.rows:
        return None
    parts = open_result.rows[0].split("|")
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


@dataclass(frozen=True, slots=True)
class BuyerCancelPreview:
    ticket_id: str
    status: str
    band: BuyerCancelBand
    refund_ngwee: int
    admin_fee_ngwee: int
    hours_until_start: float
    cancellable: bool
    reschedule_opt_out_open: bool
    reschedule_deadline: str | None


def preview_buyer_cancel(*, ticket_id: str, holder_user_id: str) -> BuyerCancelPreview:
    row = _load_holder_ticket_for_cancel(ticket_id, holder_user_id)
    starts_at = _parse_dt(str(row["starts_at"]))
    paid = _ticket_paid_ngwee(row) if row.get("order_id") else 0
    policy = compute_buyer_cancel_refund(paid_ngwee=paid, starts_at=starts_at)
    open_reschedule = _open_reschedule(str(row["event_id"]))
    cancellable = (
        str(row["status"]) == "issued"
        and bool(row.get("order_id"))
        and policy.refund_ngwee > 0
        and policy.band != "none"
    )
    return BuyerCancelPreview(
        ticket_id=ticket_id,
        status=str(row["status"]),
        band=policy.band,
        refund_ngwee=policy.refund_ngwee,
        admin_fee_ngwee=policy.admin_fee_ngwee,
        hours_until_start=policy.hours_until_start,
        cancellable=cancellable,
        reschedule_opt_out_open=open_reschedule is not None and str(row["status"]) == "issued",
        reschedule_deadline=open_reschedule[1] if open_reschedule else None,
    )


def _void_issued_ticket(ticket_id: str, holder_user_id: str) -> bool:
    ticket_sql = sql_uuid(ticket_id, "ticket_id")
    holder_sql = sql_uuid(holder_user_id, "holder_user_id")
    result = run_sql_script(
        f"""
UPDATE public.tickets
SET status = 'void'
WHERE id = {ticket_sql}
  AND holder_user_id = {holder_sql}
  AND status = 'issued'
RETURNING id::text;
"""
    )
    if not result.ok:
        raise RuntimeError(f"ticket void failed: {result.error}")
    return bool(result.rows)


def _ticket_paid_ngwee(row: dict[str, Any]) -> int:
    unit = int(row["unit_price_ngwee"])
    qty = max(int(row["qty"]), 1)
    fee_share = int(row["platform_fee_ngwee"]) // qty
    return unit + fee_share


def cancel_buyer_ticket(*, ticket_id: str, holder_user_id: str) -> BuyerCancelResult:
    row = _load_holder_ticket_for_cancel(ticket_id, holder_user_id)
    if row["status"] == "void":
        return BuyerCancelResult(ticket_id=ticket_id, band="none", refund_ngwee=0, queued=False)
    if row["status"] != "issued":
        raise AppError(
            code="ticket_not_cancellable",
            message="Only unused tickets can be cancelled",
            http_status=409,
            details={"message_key": "events.wallet.cancel.errors.notCancellable"},
        )
    if not row["order_id"] or not row["customer_id"]:
        raise AppError(
            code="ticket_unpaid_hold",
            message="Unpaid tickets cannot be refunded",
            http_status=409,
            details={"message_key": "events.wallet.cancel.errors.unpaid"},
        )
    starts_at = _parse_dt(str(row["starts_at"]))
    paid = _ticket_paid_ngwee(row)
    policy = compute_buyer_cancel_refund(paid_ngwee=paid, starts_at=starts_at)
    if policy.band == "none" or policy.refund_ngwee <= 0:
        raise AppError(
            code="ticket_cancel_window_closed",
            message="Tickets cannot be refunded within 24 hours of the event",
            http_status=422,
            details={
                "message_key": "events.wallet.cancel.errors.windowClosed",
                "band": policy.band,
            },
        )
    if not _void_issued_ticket(ticket_id, holder_user_id):
        raise AppError(
            code="ticket_not_cancellable",
            message="Only unused tickets can be cancelled",
            http_status=409,
            details={"message_key": "events.wallet.cancel.errors.notCancellable"},
        )
    queued = enqueue_event_refund_job(
        event_id=str(row["event_id"]),
        order_id=str(row["order_id"]),
        customer_id=str(row["customer_id"]),
        amount_ngwee=policy.refund_ngwee,
        source=SOURCE_BUYER_CANCEL,
        source_key=ticket_id,
        extra_policy={
            "band": policy.band,
            "ticket_id": ticket_id,
            "admin_fee_ngwee": policy.admin_fee_ngwee,
        },
    )
    return BuyerCancelResult(
        ticket_id=ticket_id,
        band=policy.band,
        refund_ngwee=policy.refund_ngwee,
        queued=queued,
    )


def opt_out_rescheduled_ticket(*, ticket_id: str, holder_user_id: str) -> BuyerCancelResult:
    row = _load_holder_ticket_for_cancel(ticket_id, holder_user_id)
    if row["status"] == "void":
        return BuyerCancelResult(
            ticket_id=ticket_id, band="full_minus_admin", refund_ngwee=0, queued=False
        )
    if row["status"] != "issued":
        raise AppError(
            code="ticket_not_cancellable",
            message="Only unused tickets can opt out of a reschedule",
            http_status=409,
            details={"message_key": "events.wallet.reschedule.errors.notCancellable"},
        )
    open_reschedule = _open_reschedule(str(row["event_id"]))
    if open_reschedule is None:
        raise AppError(
            code="reschedule_opt_out_closed",
            message="There is no open reschedule opt-out window for this ticket",
            http_status=422,
            details={"message_key": "events.wallet.reschedule.errors.windowClosed"},
        )
    if not row["order_id"] or not row["customer_id"]:
        raise AppError(
            code="ticket_unpaid_hold",
            message="Unpaid tickets cannot be refunded",
            http_status=409,
        )
    paid = _ticket_paid_ngwee(row)
    if not _void_issued_ticket(ticket_id, holder_user_id):
        raise AppError(
            code="ticket_not_cancellable",
            message="Only unused tickets can opt out of a reschedule",
            http_status=409,
        )
    queued = enqueue_event_refund_job(
        event_id=str(row["event_id"]),
        order_id=str(row["order_id"]),
        customer_id=str(row["customer_id"]),
        amount_ngwee=paid,
        source=SOURCE_RESCHEDULE_OPT_OUT,
        source_key=ticket_id,
        extra_policy={"ticket_id": ticket_id, "reschedule_id": open_reschedule[0]},
    )
    return BuyerCancelResult(
        ticket_id=ticket_id,
        band="full_minus_admin",
        refund_ngwee=paid,
        queued=queued,
    )
