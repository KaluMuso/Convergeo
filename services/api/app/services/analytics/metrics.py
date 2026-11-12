"""Convergeo Intelligence 1B-03: authoritative commercial metrics (plan §R-I).

Paid orders, payments and GMV come ONLY from ``orders``, ``order_items``,
``checkout_groups`` and ``payments`` through the SQL function
``public.analytics_commercial_daily(from, to)`` — the same definition the daily rollup
stores. Nothing here reads ``analytics_event_log`` or ``funnel_events`` snapshots.

Definitions (UTC days):

* **orders placed** — orders created that day (any status).
* **orders paid** — orders whose checkout group has a payment with ``status='success'``.
* **paid GMV** — ``sum(qty * unit_price_ngwee) + delivery_fee_ngwee`` over paid orders that
  are not cancelled. Integer ngwee throughout; no float ever touches money.
* **AOV** — paid GMV / paid checkouts, rounded half-up to a whole ngwee (integer math).
* **payment reconciliation** — per day, successful payments must equal paid checkouts
  (one success per group) and their amounts must equal the groups' ``total_ngwee``. A
  mismatch is reported as a data-quality flag; nothing is corrected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Final

from app.services.orders.audit import run_sql_script, sql_literal

STATEMENT_TIMEOUT: Final = "10s"
MAX_RANGE_DAYS: Final = 366

_COLUMNS: Final = (
    "day",
    "checkouts_started",
    "orders_placed",
    "orders_cancelled",
    "orders_paid",
    "paid_checkouts",
    "payments_succeeded",
    "payments_succeeded_ngwee",
    "paid_checkout_total_ngwee",
    "gmv_paid_ngwee",
)


@dataclass(frozen=True, slots=True)
class CommercialDay:
    day: date
    checkouts_started: int
    orders_placed: int
    orders_cancelled: int
    orders_paid: int
    paid_checkouts: int
    payments_succeeded: int
    payments_succeeded_ngwee: int
    paid_checkout_total_ngwee: int
    gmv_paid_ngwee: int

    @property
    def payment_mismatch(self) -> bool:
        return (
            self.payments_succeeded != self.paid_checkouts
            or self.payments_succeeded_ngwee != self.paid_checkout_total_ngwee
        )


@dataclass(frozen=True, slots=True)
class CommercialSummary:
    start: date
    end: date
    checkouts_started: int
    orders_placed: int
    orders_cancelled: int
    orders_paid: int
    paid_checkouts: int
    payments_succeeded: int
    payments_succeeded_ngwee: int
    gmv_paid_ngwee: int
    aov_ngwee: int | None
    reconciled: bool
    mismatch_days: list[date] = field(default_factory=list)
    days: list[CommercialDay] = field(default_factory=list)


def _validate_range(start: date, end: date) -> None:
    if end < start:
        raise ValueError("end must not be before start")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"range exceeds {MAX_RANGE_DAYS} days")


def commercial_daily(start: date, end: date) -> list[CommercialDay]:
    """One row per UTC day in ``[start, end]`` (zero-filled)."""
    _validate_range(start, end)
    script = (
        "BEGIN;\n"
        f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}';\n"
        "SELECT concat_ws('|', " + ", ".join(_COLUMNS) + ") "
        "FROM public.analytics_commercial_daily("
        f"{sql_literal(start.isoformat())}::date, {sql_literal(end.isoformat())}::date);\n"
        "COMMIT;\n"
    )
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"commercial metrics query failed: {result.error}")
    days: list[CommercialDay] = []
    for row in result.rows:
        parts = row.strip().split("|")
        if len(parts) != len(_COLUMNS):
            continue
        days.append(
            CommercialDay(
                day=date.fromisoformat(parts[0]),
                checkouts_started=int(parts[1]),
                orders_placed=int(parts[2]),
                orders_cancelled=int(parts[3]),
                orders_paid=int(parts[4]),
                paid_checkouts=int(parts[5]),
                payments_succeeded=int(parts[6]),
                payments_succeeded_ngwee=int(parts[7]),
                paid_checkout_total_ngwee=int(parts[8]),
                gmv_paid_ngwee=int(parts[9]),
            )
        )
    return days


def average_ngwee(total_ngwee: int, count: int) -> int | None:
    """Integer mean rounded half-up; ``None`` when there is nothing to average."""
    if count <= 0:
        return None
    return (2 * total_ngwee + count) // (2 * count)


def summarize(start: date, end: date, days: list[CommercialDay]) -> CommercialSummary:
    gmv = sum(d.gmv_paid_ngwee for d in days)
    paid_checkouts = sum(d.paid_checkouts for d in days)
    mismatch_days = [d.day for d in days if d.payment_mismatch]
    return CommercialSummary(
        start=start,
        end=end,
        checkouts_started=sum(d.checkouts_started for d in days),
        orders_placed=sum(d.orders_placed for d in days),
        orders_cancelled=sum(d.orders_cancelled for d in days),
        orders_paid=sum(d.orders_paid for d in days),
        paid_checkouts=paid_checkouts,
        payments_succeeded=sum(d.payments_succeeded for d in days),
        payments_succeeded_ngwee=sum(d.payments_succeeded_ngwee for d in days),
        gmv_paid_ngwee=gmv,
        aov_ngwee=average_ngwee(gmv, paid_checkouts),
        reconciled=not mismatch_days,
        mismatch_days=mismatch_days,
        days=days,
    )


def commercial_summary(start: date, end: date) -> CommercialSummary:
    return summarize(start, end, commercial_daily(start, end))


def previous_period(start: date, end: date) -> tuple[date, date]:
    """The equally long window immediately before ``[start, end]`` (for deltas)."""
    length = (end - start).days + 1
    return start - timedelta(days=length), start - timedelta(days=1)
