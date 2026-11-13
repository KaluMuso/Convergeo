"""Founder analytics dashboards: users, growth, revenue, vendors, services and events.

Every figure is an aggregate over the authoritative tables (never client events, never
``funnel_events`` snapshots), bucketed by **Africa/Lusaka** reporting day (OD-9). Stored
timestamps stay UTC; a row at 23:30 UTC belongs to the next Lusaka day.

Definitions (also the export column meanings):

* **registered customer** — an account holding the ``customer`` role whose profile is not
  deleted. **New customer** — that role granted on the day.
* **registered vendor** — a row in ``vendors`` (any status). **Active vendor** —
  ``vendors.status = 'active'``. **Selling vendor** — a vendor with a paid order in range.
* **paid order** — an order, not cancelled, whose checkout group has a payment with
  ``status = 'success'`` (the same rule as ``analytics_commercial_daily``).
* **paid order value** — items + delivery fee of paid orders. It is *not* revenue.
* **platform revenue** — what the ledger credited to the platform's own accounts in the
  range: ``commission_revenue`` + ``delivery_revenue`` (credits are negative postings, so
  revenue is the negated net; refund debits reduce it). Payment processing fees
  (``fees``) are a cost and reported separately.
* **refunds** — refund rows requested in range; completed ones carry their amount.
* **tickets sold** — tickets issued in range that are not void; **check-ins** — tickets
  checked in during the range.

Money is integer ngwee; rates are integer basis points. Activity (DAU/WAU/MAU) comes from
the analytics_v2 event log and is reported only while ``analytics_v2_rollups`` is ON.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Final, Literal

from app.services.analytics.metrics import CommercialSummary, commercial_summary, previous_period
from app.services.analytics.reporting_day import REPORTING_TZ_NAME, reporting_today
from app.services.orders.audit import run_sql_script, sql_literal

STATEMENT_TIMEOUT: Final = "8s"
MAX_RANGE_DAYS: Final = 366
COHORT_MONTHS: Final = 6
TOP_VENDORS: Final = 10
SMALL_COHORT: Final = 20

Period = Literal["today", "7d", "30d", "custom"]
PERIODS: Final[tuple[str, ...]] = ("today", "7d", "30d", "custom")

TZ: Final = sql_literal(REPORTING_TZ_NAME)

# A paid order (shared by every report). Mirrors analytics_commercial_daily.
PAID_ORDERS_SQL: Final = (
    "SELECT o.id, o.customer_id, o.vendor_id, o.checkout_group_id, o.created_at, "
    "o.delivery_fee_ngwee FROM public.orders o "
    "WHERE o.status <> 'cancelled' AND EXISTS (SELECT 1 FROM public.payments p "
    "WHERE p.checkout_group_id = o.checkout_group_id AND p.status = 'success')"
)


class RangeError(ValueError):
    """The requested reporting window is invalid."""


@dataclass(frozen=True, slots=True)
class Window:
    period: str
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def as_dict(self) -> dict[str, str]:
        return {"period": self.period, "from": self.start.isoformat(), "to": self.end.isoformat()}


def resolve_window(
    period: str | None,
    start: date | None = None,
    end: date | None = None,
    *,
    today: date | None = None,
) -> Window:
    """``today`` / ``7d`` / ``30d`` end on today's Lusaka day (partial); ``custom`` is inclusive."""
    today = today or reporting_today()
    chosen = period or ("custom" if start or end else "7d")
    if chosen not in PERIODS:
        raise RangeError(f"period must be one of {', '.join(PERIODS)}")
    if chosen == "today":
        return Window(chosen, today, today)
    if chosen in ("7d", "30d"):
        length = 7 if chosen == "7d" else 30
        return Window(chosen, today - timedelta(days=length - 1), today)
    if start is None or end is None:
        raise RangeError("custom period needs from and to")
    if end > today:
        raise RangeError("to must not be in the future")
    if start > end:
        raise RangeError("from must not be after to")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise RangeError(f"range exceeds {MAX_RANGE_DAYS} days")
    return Window(chosen, start, end)


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


def _d(value: date) -> str:
    return f"{sql_literal(value.isoformat())}::date"


def lower_bound(day: date) -> str:
    """First instant of a Lusaka day as timestamptz SQL."""
    return f"({_d(day)}::timestamp AT TIME ZONE {TZ})"


def upper_bound(day: date) -> str:
    """First instant after a Lusaka day (exclusive) as timestamptz SQL."""
    return f"(({_d(day)} + 1)::timestamp AT TIME ZONE {TZ})"


def in_window(column: str, start: date, end: date) -> str:
    return f"{column} >= {lower_bound(start)} AND {column} < {upper_bound(end)}"


def lusaka_day(column: str) -> str:
    return f"({column} AT TIME ZONE {TZ})::date"


def _rows(sql: str) -> list[list[str]]:
    script = f"BEGIN;\nSET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}';\n{sql}\nCOMMIT;\n"
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"analytics dashboard read failed: {result.error}")
    return [row.split("|") for row in result.rows if row.strip()]


def _ints(sql: str, width: int) -> list[int]:
    rows = _rows(sql)
    if not rows or len(rows[0]) != width:
        raise RuntimeError("analytics dashboard read returned an unexpected shape")
    return [int(value) if value != "" else 0 for value in rows[0]]


def _daily(sql: str, start: date, end: date, names: tuple[str, ...]) -> list[dict[str, Any]]:
    """Zero-filled per-day series; ``sql`` yields ``day|v1|v2…`` rows."""
    found: dict[str, list[int]] = {}
    for row in _rows(sql):
        if len(row) == len(names) + 1:
            found[row[0]] = [int(v) if v != "" else 0 for v in row[1:]]
    out: list[dict[str, Any]] = []
    day = start
    while day <= end:
        values = found.get(day.isoformat(), [0] * len(names))
        out.append({"day": day.isoformat(), **dict(zip(names, values, strict=True))})
        day += timedelta(days=1)
    return out


def _sum(series: list[dict[str, Any]], key: str) -> int:
    return sum(int(item[key]) for item in series)


def rate_bps(numerator: int, denominator: int) -> int | None:
    """Integer basis points, half-up; ``None`` without a denominator."""
    if denominator <= 0:
        return None
    return (20_000 * numerator + denominator) // (2 * denominator)


def _count_by_day(table: str, column: str, start: date, end: date, where: str = "TRUE") -> str:
    return (
        f"SELECT {lusaka_day(column)}::text AS day, count(*) AS count FROM {table} "
        f"WHERE {in_window(column, start, end)} AND {where} GROUP BY 1"
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

_CUSTOMER_ROLES: Final = (
    "SELECT ur.user_id, ur.created_at FROM public.user_roles ur "
    "WHERE ur.role = 'customer' AND NOT EXISTS (SELECT 1 FROM public.profiles p "
    "WHERE p.id = ur.user_id AND p.deleted_at IS NOT NULL)"
)


def registration_daily(start: date, end: date) -> list[dict[str, Any]]:
    sql = (
        f"WITH c AS ({_count_by_day(f'({_CUSTOMER_ROLES}) cr', 'cr.created_at', start, end)}), "
        f"v AS ({_count_by_day('public.vendors v', 'v.created_at', start, end)}), "
        "d AS (SELECT day FROM c UNION SELECT day FROM v) "
        "SELECT d.day, coalesce(c.count, 0), coalesce(v.count, 0) FROM d "
        "LEFT JOIN c USING (day) LEFT JOIN v USING (day);"
    )
    return _daily(sql, start, end, ("customers", "vendors"))


def registration_totals() -> dict[str, int]:
    customers, vendors, active_vendors = _ints(
        f"SELECT (SELECT count(DISTINCT user_id) FROM ({_CUSTOMER_ROLES}) cr), "
        "(SELECT count(*) FROM public.vendors), "
        "(SELECT count(*) FROM public.vendors WHERE status = 'active');",
        3,
    )
    return {"customers": customers, "vendors": vendors, "active_vendors": active_vendors}


def activity(end: date, start: date) -> dict[str, Any]:
    """DAU/WAU/MAU windows ending on ``end`` from the v2 event log (flag checked by caller).

    ``visitors`` are distinct anonymous visitor ids; ``signed_in`` distinct linked accounts.
    The raw log keeps 30 days, so MAU is exact only for a window ending within that span.
    """
    windows = {"dau": end, "wau": end - timedelta(days=6), "mau": end - timedelta(days=29)}
    parts = []
    for first in windows.values():
        cond = in_window("received_at", first, end)
        parts.append(
            f"(SELECT count(DISTINCT anon_id) FROM public.analytics_event_log WHERE {cond})"
        )
        parts.append(
            f"(SELECT count(DISTINCT user_id) FROM public.analytics_event_log WHERE {cond})"
        )
    values = _ints("SELECT " + ", ".join(parts) + ";", 6)
    daily = _daily(
        "SELECT day::text, value FROM public.analytics_daily_rollup "
        f"WHERE day BETWEEN {_d(start)} AND {_d(end)} AND metric = 'visitors' AND dim_key = '';",
        start,
        end,
        ("visitors",),
    )
    return {
        "enabled": True,
        "as_of": end.isoformat(),
        "dau": values[0],
        "dau_signed_in": values[1],
        "wau": values[2],
        "wau_signed_in": values[3],
        "mau": values[4],
        "mau_signed_in": values[5],
        "daily_visitors": daily,
    }


def _month_offset(first: date, later: date) -> int:
    return (later.year - first.year) * 12 + later.month - first.month


def _add_months(day: date, months: int) -> date:
    total = day.year * 12 + day.month - 1 + months
    return date(total // 12, total % 12 + 1, 1)


def retention_cohorts(end: date, months: int = COHORT_MONTHS) -> list[dict[str, Any]]:
    """Monthly purchase cohorts: customers by the Lusaka month of their first paid order.

    ``retained[n]`` = cohort customers with a paid order ``n`` months later (``n = 0`` is the
    cohort size); ``None`` for months that have not happened yet relative to ``end``.
    """
    last = end.replace(day=1)
    first = _add_months(last, -(months - 1))
    month = f"date_trunc('month', po.created_at AT TIME ZONE {TZ})::date"
    sql = (
        f"WITH po AS ({PAID_ORDERS_SQL} AND o.created_at < {upper_bound(end)}), "
        f"f AS (SELECT po.customer_id, min({month}) AS cohort FROM po GROUP BY 1), "
        f"a AS (SELECT DISTINCT po.customer_id, {month} AS m FROM po) "
        "SELECT f.cohort::text, a.m::text, count(DISTINCT a.customer_id) "
        "FROM f JOIN a USING (customer_id) "
        f"WHERE f.cohort BETWEEN {_d(first)} AND {_d(last)} GROUP BY 1, 2;"
    )
    counts: dict[tuple[str, int], int] = {}
    for row in _rows(sql):
        if len(row) == 3:
            cohort = date.fromisoformat(row[0])
            counts[(row[0], _month_offset(cohort, date.fromisoformat(row[1])))] = int(row[2])
    out: list[dict[str, Any]] = []
    for index in range(months):
        cohort = _add_months(first, index)
        key = cohort.isoformat()
        size = counts.get((key, 0), 0)
        horizon = _month_offset(cohort, last)
        retained: list[int | None] = [
            counts.get((key, n), 0) if n <= horizon else None for n in range(months)
        ]
        out.append(
            {
                "cohort": key[:7],
                "size": size,
                "retained": retained,
                "retained_bps": [
                    rate_bps(v, size) if v is not None and size else None for v in retained
                ],
                "small_sample": size < SMALL_COHORT,
            }
        )
    return out


def build_users(window: Window, *, activity_enabled: bool) -> dict[str, Any]:
    prev_start, prev_end = previous_period(window.start, window.end)
    daily = registration_daily(window.start, window.end)
    previous = registration_daily(prev_start, prev_end)
    return {
        "range": window.as_dict(),
        "previous_range": {"from": prev_start.isoformat(), "to": prev_end.isoformat()},
        "totals": registration_totals(),
        "new": {"customers": _sum(daily, "customers"), "vendors": _sum(daily, "vendors")},
        "previous_new": {
            "customers": _sum(previous, "customers"),
            "vendors": _sum(previous, "vendors"),
        },
        "daily": daily,
        "activity": (
            activity(window.end, window.start) if activity_enabled else {"enabled": False}
        ),
        "cohorts": retention_cohorts(window.end),
    }


# ---------------------------------------------------------------------------
# Growth (counts only — no money)
# ---------------------------------------------------------------------------


def _growth_series(start: date, end: date) -> list[dict[str, Any]]:
    regs = registration_daily(start, end)
    listings = _daily(
        _count_by_day("public.vendor_listings vl", "vl.created_at", start, end),
        start,
        end,
        ("listings",),
    )
    commerce = commercial_summary(start, end)
    by_day = {d.day.isoformat(): d for d in commerce.days}
    out = []
    for reg, listing in zip(regs, listings, strict=True):
        day = by_day.get(reg["day"])
        out.append(
            {
                "day": reg["day"],
                "customers": reg["customers"],
                "vendors": reg["vendors"],
                "listings": listing["listings"],
                "checkouts_started": day.checkouts_started if day else 0,
                "orders_placed": day.orders_placed if day else 0,
                "orders_paid": day.orders_paid if day else 0,
            }
        )
    return out


GROWTH_KEYS: Final = (
    "customers",
    "vendors",
    "listings",
    "checkouts_started",
    "orders_placed",
    "orders_paid",
)


def build_growth(window: Window) -> dict[str, Any]:
    prev_start, prev_end = previous_period(window.start, window.end)
    daily = _growth_series(window.start, window.end)
    previous = _growth_series(prev_start, prev_end)
    totals = {key: _sum(daily, key) for key in GROWTH_KEYS}
    return {
        "range": window.as_dict(),
        "previous_range": {"from": prev_start.isoformat(), "to": prev_end.isoformat()},
        "totals": totals,
        "previous_totals": {key: _sum(previous, key) for key in GROWTH_KEYS},
        "checkout_to_paid_bps": rate_bps(totals["orders_paid"], totals["checkouts_started"]),
        "daily": daily,
    }


# ---------------------------------------------------------------------------
# Revenue and commissions (finance.read)
# ---------------------------------------------------------------------------


def ledger_revenue_daily(start: date, end: date) -> list[dict[str, Any]]:
    sql = (
        f"SELECT {lusaka_day('lp.created_at')}::text, "
        "coalesce(-sum(lp.amount_ngwee) FILTER (WHERE la.kind = 'commission_revenue'), 0), "
        "coalesce(-sum(lp.amount_ngwee) FILTER (WHERE la.kind = 'delivery_revenue'), 0), "
        "coalesce(sum(lp.amount_ngwee) FILTER (WHERE la.kind = 'fees'), 0) "
        "FROM public.ledger_postings lp JOIN public.ledger_accounts la ON la.id = lp.account_id "
        "WHERE la.vendor_id IS NULL "
        "AND la.kind IN ('commission_revenue', 'delivery_revenue', 'fees') "
        f"AND {in_window('lp.created_at', start, end)} GROUP BY 1;"
    )
    return _daily(sql, start, end, ("commission_ngwee", "delivery_ngwee", "processing_fees_ngwee"))


def refund_summary(start: date, end: date) -> dict[str, int]:
    requested, completed, completed_ngwee, open_, failed = _ints(
        "SELECT count(*), count(*) FILTER (WHERE status = 'completed'), "
        "coalesce(sum(amount_ngwee) FILTER (WHERE status = 'completed'), 0), "
        "count(*) FILTER (WHERE status NOT IN ('completed', 'failed')), "
        "count(*) FILTER (WHERE status = 'failed') "
        f"FROM public.refunds WHERE {in_window('created_at', start, end)};",
        5,
    )
    return {
        "requested": requested,
        "completed": completed,
        "completed_ngwee": completed_ngwee,
        "open": open_,
        "failed": failed,
    }


def paid_then_cancelled(start: date, end: date) -> int:
    (count,) = _ints(
        "SELECT count(*) FROM public.orders o WHERE o.status = 'cancelled' "
        f"AND {in_window('o.created_at', start, end)} AND EXISTS (SELECT 1 FROM public.payments p "
        "WHERE p.checkout_group_id = o.checkout_group_id AND p.status = 'success');",
        1,
    )
    return count


def _orders_block(summary: CommercialSummary) -> dict[str, Any]:
    return {
        "placed": summary.orders_placed,
        "paid": summary.orders_paid,
        "cancelled": summary.orders_cancelled,
        "paid_order_value_ngwee": summary.gmv_paid_ngwee,
        "average_paid_order_ngwee": summary.aov_ngwee,
        "payments_reconciled": summary.reconciled,
        "payment_mismatch_days": [d.isoformat() for d in summary.mismatch_days],
    }


def _revenue_block(series: list[dict[str, Any]]) -> dict[str, int]:
    commission = _sum(series, "commission_ngwee")
    delivery = _sum(series, "delivery_ngwee")
    return {
        "commission_ngwee": commission,
        "delivery_ngwee": delivery,
        "total_ngwee": commission + delivery,
        "processing_fees_ngwee": _sum(series, "processing_fees_ngwee"),
    }


def build_revenue(window: Window) -> dict[str, Any]:
    prev_start, prev_end = previous_period(window.start, window.end)
    current = commercial_summary(window.start, window.end)
    previous = commercial_summary(prev_start, prev_end)
    ledger = ledger_revenue_daily(window.start, window.end)
    previous_ledger = ledger_revenue_daily(prev_start, prev_end)
    by_day = {d.day.isoformat(): d for d in current.days}
    daily = []
    for item in ledger:
        day = by_day.get(item["day"])
        daily.append(
            {
                "day": item["day"],
                "orders_paid": day.orders_paid if day else 0,
                "paid_order_value_ngwee": day.gmv_paid_ngwee if day else 0,
                "commission_ngwee": item["commission_ngwee"],
                "delivery_ngwee": item["delivery_ngwee"],
            }
        )
    orders = _orders_block(current)
    orders["paid_then_cancelled"] = paid_then_cancelled(window.start, window.end)
    revenue = _revenue_block(ledger)
    return {
        "range": window.as_dict(),
        "previous_range": {"from": prev_start.isoformat(), "to": prev_end.isoformat()},
        "orders": orders,
        "previous_orders": _orders_block(previous),
        "platform_revenue": revenue,
        "previous_platform_revenue": _revenue_block(previous_ledger),
        "take_rate_bps": rate_bps(revenue["total_ngwee"], current.gmv_paid_ngwee),
        "refunds": refund_summary(window.start, window.end),
        "daily": daily,
    }


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------

KYC_STATUSES: Final = ("submitted", "under_review", "approved", "rejected", "suspended", "revoked")
VENDOR_STATUSES: Final = ("draft", "pending_kyc", "active", "suspended", "suspended_compliance")


def _status_counts(sql: str, statuses: tuple[str, ...]) -> dict[str, int]:
    found = {row[0]: int(row[1]) for row in _rows(sql) if len(row) == 2}
    return {status: found.get(status, 0) for status in statuses}


def build_vendors(window: Window, *, include_money: bool) -> dict[str, Any]:
    start, end = window.start, window.end
    kyc_current = _status_counts(
        "SELECT status, count(*) FROM (SELECT DISTINCT ON (vendor_id) status "
        "FROM public.kyc_records ORDER BY vendor_id, created_at DESC, id DESC) k GROUP BY 1;",
        KYC_STATUSES,
    )
    submitted, approved, rejected, decision_seconds_avg = _ints(
        "SELECT "
        f"(SELECT count(*) FROM public.kyc_records WHERE {in_window('created_at', start, end)}), "
        "count(*) FILTER (WHERE status = 'approved'), "
        "count(*) FILTER (WHERE status = 'rejected'), "
        "coalesce(round(avg(extract(epoch FROM reviewed_at - created_at)))::bigint, 0) "
        "FROM public.kyc_records WHERE status IN ('approved', 'rejected') "
        f"AND reviewed_at IS NOT NULL AND {in_window('reviewed_at', start, end)};",
        4,
    )
    vendor_status = _status_counts(
        "SELECT status, count(*) FROM public.vendors GROUP BY 1;", VENDOR_STATUSES
    )
    new_vendors, selling, reviews, rating_x100 = _ints(
        "SELECT "
        f"(SELECT count(*) FROM public.vendors WHERE {in_window('created_at', start, end)}), "
        f"(SELECT count(DISTINCT po.vendor_id) FROM ({PAID_ORDERS_SQL}) po "
        f"WHERE {in_window('po.created_at', start, end)}), "
        "count(*), coalesce(round(avg(r.rating) * 100)::bigint, 0) "
        "FROM public.reviews r WHERE r.status = 'published' "
        f"AND {in_window('r.created_at', start, end)};",
        4,
    )
    top_rows = _rows(
        f"WITH po AS ({PAID_ORDERS_SQL} AND {in_window('o.created_at', start, end)}), "
        "sales AS (SELECT po.vendor_id, count(*) AS paid_orders, "
        "coalesce(sum(oi.qty::bigint * oi.unit_price_ngwee), 0) AS items_ngwee "
        "FROM po LEFT JOIN public.order_items oi ON oi.order_id = po.id GROUP BY 1), "
        "orders_n AS (SELECT po.vendor_id, count(*) AS n FROM po GROUP BY 1), "
        "rating AS (SELECT o.vendor_id, count(*) AS n, round(avg(r.rating) * 100)::bigint AS x100 "
        "FROM public.reviews r JOIN public.order_items oi ON oi.id = r.order_item_id "
        "JOIN public.orders o ON o.id = oi.order_id WHERE r.status = 'published' GROUP BY 1) "
        "SELECT v.id, replace(replace(v.display_name, '|', '/'), E'\\n', ' '), n.n, "
        "s.items_ngwee, coalesce(rt.n, 0), coalesce(rt.x100, 0) "
        "FROM orders_n n JOIN sales s USING (vendor_id) "
        "JOIN public.vendors v ON v.id = n.vendor_id "
        "LEFT JOIN rating rt ON rt.vendor_id = n.vendor_id "
        f"ORDER BY n.n DESC, s.items_ngwee DESC, v.id LIMIT {TOP_VENDORS};"
    )
    top = [
        {
            "vendor_id": row[0],
            "name": row[1],
            "paid_orders": int(row[2]),
            "item_sales_ngwee": int(row[3]) if include_money else None,
            "rating_count": int(row[4]),
            "rating_avg_x100": int(row[5]) if int(row[4]) else None,
        }
        for row in top_rows
        if len(row) == 6
    ]
    return {
        "range": window.as_dict(),
        "finance_visible": include_money,
        "kyc": {
            "current": kyc_current,
            "submitted": submitted,
            "approved": approved,
            "rejected": rejected,
            "avg_decision_hours": (decision_seconds_avg // 3600) if approved + rejected else None,
        },
        "vendors": {
            "by_status": vendor_status,
            "total": sum(vendor_status.values()),
            "active": vendor_status["active"],
            "new": new_vendors,
            "selling": selling,
        },
        "ratings": {
            "reviews": reviews,
            "avg_x100": rating_x100 if reviews else None,
        },
        "top": top,
    }


# ---------------------------------------------------------------------------
# Services and events
# ---------------------------------------------------------------------------


def build_services_events(window: Window) -> dict[str, Any]:
    start, end = window.start, window.end
    (
        services_active,
        jobs_posted,
        quotes_submitted,
        quotes_accepted,
        rfq_opened,
        rfq_quoted,
        rfq_accepted,
        bookings,
        bookings_paid,
    ) = _ints(
        "SELECT "
        "(SELECT count(*) FROM public.services WHERE status = 'active'), "
        f"(SELECT count(*) FROM public.jobs WHERE {in_window('created_at', start, end)}), "
        f"(SELECT count(*) FROM public.job_quotes WHERE {in_window('created_at', start, end)}), "
        "(SELECT count(*) FROM public.job_quotes WHERE status = 'accepted' "
        f"AND {in_window('created_at', start, end)}), "
        f"(SELECT count(*) FROM public.rfq_threads WHERE {in_window('created_at', start, end)}), "
        "(SELECT count(*) FROM public.rfq_threads WHERE quoted_at IS NOT NULL "
        f"AND {in_window('quoted_at', start, end)}), "
        "(SELECT count(*) FROM public.rfq_threads WHERE status = 'accepted' "
        f"AND {in_window('created_at', start, end)}), "
        "(SELECT count(DISTINCT o.id) FROM public.orders o JOIN public.order_items oi "
        "ON oi.order_id = o.id WHERE oi.item_kind = 'service_deposit' AND o.status <> 'cancelled' "
        f"AND {in_window('o.created_at', start, end)}), "
        f"(SELECT count(DISTINCT po.id) FROM ({PAID_ORDERS_SQL}) po JOIN public.order_items oi "
        "ON oi.order_id = po.id WHERE oi.item_kind = 'service_deposit' "
        f"AND {in_window('po.created_at', start, end)});",
        9,
    )
    events_published, instances, tickets_sold, check_ins, held, held_checked_in = _ints(
        "SELECT "
        "(SELECT count(*) FROM public.events WHERE status = 'published'), "
        "(SELECT count(*) FROM public.event_instances WHERE status <> 'cancelled' "
        f"AND {in_window('starts_at', start, end)}), "
        "(SELECT count(*) FROM public.tickets WHERE status <> 'void' "
        f"AND {in_window('created_at', start, end)}), "
        "(SELECT count(*) FROM public.tickets WHERE checked_in_at IS NOT NULL "
        f"AND {in_window('checked_in_at', start, end)}), "
        "(SELECT count(*) FROM public.tickets t JOIN public.event_instances ei "
        "ON ei.id = t.instance_id WHERE t.status <> 'void' AND ei.starts_at <= now() "
        f"AND {in_window('ei.starts_at', start, end)}), "
        "(SELECT count(*) FROM public.tickets t JOIN public.event_instances ei "
        "ON ei.id = t.instance_id WHERE t.status <> 'void' AND t.checked_in_at IS NOT NULL "
        f"AND ei.starts_at <= now() AND {in_window('ei.starts_at', start, end)});",
        6,
    )
    tickets_daily = _daily(
        "WITH s AS ("
        + _count_by_day("public.tickets", "created_at", start, end, "status <> 'void'")
        + "), c AS ("
        + _count_by_day("public.tickets", "checked_in_at", start, end, "checked_in_at IS NOT NULL")
        + "), d AS (SELECT day FROM s UNION SELECT day FROM c) "
        "SELECT d.day, coalesce(s.count, 0), coalesce(c.count, 0) FROM d "
        "LEFT JOIN s USING (day) LEFT JOIN c USING (day);",
        start,
        end,
        ("tickets_sold", "check_ins"),
    )
    requests_daily = _daily(
        "WITH j AS ("
        + _count_by_day("public.jobs", "created_at", start, end)
        + "), r AS ("
        + _count_by_day("public.rfq_threads", "created_at", start, end)
        + "), d AS (SELECT day FROM j UNION SELECT day FROM r) "
        "SELECT d.day, coalesce(j.count, 0), coalesce(r.count, 0) FROM d "
        "LEFT JOIN j USING (day) LEFT JOIN r USING (day);",
        start,
        end,
        ("jobs_posted", "rfq_opened"),
    )
    daily = [{**req, **tick} for req, tick in zip(requests_daily, tickets_daily, strict=True)]
    return {
        "range": window.as_dict(),
        "services": {
            "active_listings": services_active,
            "jobs_posted": jobs_posted,
            "quotes_submitted": quotes_submitted,
            "quotes_accepted": quotes_accepted,
            "rfq_opened": rfq_opened,
            "rfq_quoted": rfq_quoted,
            "rfq_accepted": rfq_accepted,
            "bookings": bookings,
            "bookings_paid": bookings_paid,
        },
        "events": {
            "published": events_published,
            "instances": instances,
            "tickets_sold": tickets_sold,
            "check_ins": check_ins,
            "check_in_rate_bps": rate_bps(held_checked_in, held),
        },
        "daily": daily,
    }
