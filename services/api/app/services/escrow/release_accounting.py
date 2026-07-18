"""Release-side payment accounting contract helpers.

Purchase-time ``orders.commission_snapshot`` is the sole source of commission at
escrow release. Present-day ``commission_rates`` must never be consulted here.

Lifecycle (prepaid product / service / event):

  CHARGE_RECEIVED (−escrow gross)
  → COMMISSION_CAPTURE (+escrow commission / −commission_revenue)
  → RELEASE_TO_VENDOR (+escrow net / −vendor_payable)

Invariant: ``commission_ngwee + net_ngwee == gross_ngwee`` (integer ngwee;
commission uses floor ``(gross * bps) // 10_000``). After the three posts,
escrow for the order nets to zero.

COD collects via ``cod_collected`` then the same capture→release pair with
``cod-commission-*`` / ``cod-release-*`` keys (unchanged by this module).

Fail-closed: invalid snapshots, active refunds, and ledger posting errors must
never silently mark escrow released. Retries are idempotent via ledger keys.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.commissions.engine import compute_order_commission, parse_snapshot_lines
from app.services.orders.audit import run_sql_script, sql_literal

ACTIVE_REFUND_STATUSES = frozenset({"pending", "processing", "completed"})

REFUND_LEDGER_KINDS = frozenset({"refund_lane1", "refund_lane2"})


class ReleaseAccountingError(ValueError):
    """Release blocked by an accounting invariant (fail-closed)."""


@dataclass(frozen=True, slots=True)
class ReleaseAccountingAmounts:
    """Gross / commission / net for one order at release time."""

    order_id: str
    gross_ngwee: int
    commission_ngwee: int
    net_ngwee: int

    def __post_init__(self) -> None:
        if self.gross_ngwee < 0 or self.commission_ngwee < 0 or self.net_ngwee < 0:
            msg = "release accounting amounts must be non-negative ngwee"
            raise ReleaseAccountingError(msg)
        if self.commission_ngwee + self.net_ngwee != self.gross_ngwee:
            msg = (
                "commission + net must equal gross "
                f"({self.commission_ngwee} + {self.net_ngwee} != {self.gross_ngwee})"
            )
            raise ReleaseAccountingError(msg)


@dataclass(frozen=True, slots=True)
class OrderReleaseLedgerSummary:
    """Ledger-observed release accounting for one order (reconciliation)."""

    order_id: str
    charge_received_ngwee: int
    commission_captured_ngwee: int
    vendor_released_ngwee: int
    refund_drained_ngwee: int

    @property
    def expected_net_after_commission(self) -> int:
        return self.charge_received_ngwee - self.commission_captured_ngwee

    @property
    def balanced(self) -> bool:
        """True when charge − commission − release − refunds nets to zero escrow drain."""
        return (
            self.charge_received_ngwee
            - self.commission_captured_ngwee
            - self.vendor_released_ngwee
            - self.refund_drained_ngwee
            == 0
        )


def commission_snapshot_is_usable(
    snapshot: Mapping[str, Any] | None,
    *,
    gross_ngwee: int,
) -> bool:
    """Return True when the purchase-time snapshot is complete enough for release.

    Zero-gross orders may carry an empty snapshot. Positive-gross orders require
    at least one parseable line with integer ``rate_bps`` and ``line_total_ngwee``.
    Explicit ``rate_bps: 0`` lines (free / 0%) are valid.
    """
    if gross_ngwee < 0:
        return False
    if gross_ngwee == 0:
        return True
    if not isinstance(snapshot, Mapping):
        return False
    lines = parse_snapshot_lines(snapshot)
    if not lines:
        return False
    for line in lines:
        rate = line.get("rate_bps")
        if not isinstance(rate, int) or rate < 0:
            return False
        if "line_total_ngwee" not in line:
            return False
        try:
            line_total = int(line["line_total_ngwee"])
        except (TypeError, ValueError):
            return False
        if line_total < 0:
            return False
    return True


def require_usable_commission_snapshot(
    snapshot: Mapping[str, Any] | None,
    *,
    gross_ngwee: int,
) -> None:
    """Raise ``ReleaseAccountingError`` when the snapshot cannot drive release math."""
    if not commission_snapshot_is_usable(snapshot, gross_ngwee=gross_ngwee):
        raise ReleaseAccountingError("invalid_commission_snapshot")


def compute_release_amounts(
    *,
    order_id: str,
    gross_ngwee: int,
    commission_snapshot: Mapping[str, Any],
) -> ReleaseAccountingAmounts:
    """Derive net vendor payout from purchase-time snapshot only (integer ngwee)."""
    require_usable_commission_snapshot(commission_snapshot, gross_ngwee=gross_ngwee)
    commission = compute_order_commission(commission_snapshot)
    net = gross_ngwee - commission.commission_ngwee
    if net < 0:
        raise ReleaseAccountingError("net vendor amount must not be negative")
    return ReleaseAccountingAmounts(
        order_id=order_id,
        gross_ngwee=gross_ngwee,
        commission_ngwee=commission.commission_ngwee,
        net_ngwee=net,
    )


def _sql_uuid(value: str) -> str:
    return f"'{value}'::uuid"


def order_has_active_refund(order_id: str) -> bool:
    """True when a pending/processing/completed refund row exists for the order."""
    order_sql = _sql_uuid(order_id)
    statuses_sql = ", ".join(sql_literal(status) for status in sorted(ACTIVE_REFUND_STATUSES))
    script = f"""
SELECT count(*)::text
FROM public.refunds
WHERE order_id = {order_sql}
  AND status IN ({statuses_sql});
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return False
    return int(result.rows[0]) > 0


def order_has_refund_ledger(order_id: str) -> bool:
    """True when a pre-release refund ledger drain was posted for the order."""
    order_sql = _sql_uuid(order_id)
    kinds_sql = ", ".join(sql_literal(kind) for kind in sorted(REFUND_LEDGER_KINDS))
    script = f"""
SELECT count(*)::text
FROM public.ledger_transactions
WHERE order_id = {order_sql}
  AND kind IN ({kinds_sql});
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return False
    return int(result.rows[0]) > 0


def order_is_refund_blocked(order_id: str) -> bool:
    """True when an active refund row or refund ledger drain blocks vendor release."""
    return order_has_active_refund(order_id) or order_has_refund_ledger(order_id)


def release_blocked_reason(*, status: str, order_id: str) -> str | None:
    """Return a blocking reason code, or None when release accounting may proceed."""
    if status == "cancelled":
        return "order_cancelled"
    if order_is_refund_blocked(order_id):
        return "order_refunded"
    return None


def summarize_order_release_ledger(order_id: str) -> OrderReleaseLedgerSummary:
    """Aggregate charge / commission / release / refund legs for reconciliation."""
    order_sql = _sql_uuid(order_id)
    script = f"""
SELECT
  coalesce(sum(CASE WHEN lt.kind IN (
      'charge_received', 'escrow_hold', 'cod_receivable_opened'
    ) THEN abs(lp.amount_ngwee) ELSE 0 END), 0)::text,
  coalesce(sum(CASE WHEN lt.kind = 'commission_capture'
    THEN abs(lp.amount_ngwee) ELSE 0 END), 0)::text,
  coalesce(sum(CASE WHEN lt.kind = 'release_to_vendor'
    THEN abs(lp.amount_ngwee) ELSE 0 END), 0)::text,
  coalesce(sum(CASE WHEN lt.kind IN ('refund_lane1', 'refund_lane2')
    THEN abs(lp.amount_ngwee) ELSE 0 END), 0)::text
FROM public.ledger_transactions lt
INNER JOIN public.ledger_postings lp ON lp.transaction_id = lt.id
INNER JOIN public.ledger_accounts la ON la.id = lp.account_id
WHERE lt.order_id = {order_sql}
  AND la.kind = 'escrow';
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return OrderReleaseLedgerSummary(
            order_id=order_id,
            charge_received_ngwee=0,
            commission_captured_ngwee=0,
            vendor_released_ngwee=0,
            refund_drained_ngwee=0,
        )
    # Each CASE sums |escrow legs|; charge/cod credit escrow once per txn so abs
    # equals the economic amount. Commission/release debit escrow — abs likewise.
    parts = result.rows[0].split("|")
    if len(parts) != 4:
        return OrderReleaseLedgerSummary(
            order_id=order_id,
            charge_received_ngwee=0,
            commission_captured_ngwee=0,
            vendor_released_ngwee=0,
            refund_drained_ngwee=0,
        )
    return OrderReleaseLedgerSummary(
        order_id=order_id,
        charge_received_ngwee=int(parts[0]),
        commission_captured_ngwee=int(parts[1]),
        vendor_released_ngwee=int(parts[2]),
        refund_drained_ngwee=int(parts[3]),
    )


def build_release_accounting_day_totals(*, report_date: str) -> dict[str, int]:
    """Day-scoped escrow release totals for the daily reconciliation summary.

    ``report_date`` is an ISO date (UTC day). Totals are absolute escrow-leg
    amounts so gross, commission, and net are directly comparable.
    """
    day_sql = sql_literal(report_date)
    script = f"""
SELECT
  coalesce(sum(CASE WHEN lt.kind IN (
      'charge_received', 'escrow_hold', 'cod_receivable_opened'
    ) THEN abs(lp.amount_ngwee) ELSE 0 END), 0)::text,
  coalesce(sum(CASE WHEN lt.kind = 'commission_capture'
    THEN abs(lp.amount_ngwee) ELSE 0 END), 0)::text,
  coalesce(sum(CASE WHEN lt.kind = 'release_to_vendor'
    THEN abs(lp.amount_ngwee) ELSE 0 END), 0)::text
FROM public.ledger_transactions lt
INNER JOIN public.ledger_postings lp ON lp.transaction_id = lt.id
INNER JOIN public.ledger_accounts la ON la.id = lp.account_id
WHERE la.kind = 'escrow'
  AND lt.created_at >= ({day_sql}::date)::timestamptz
  AND lt.created_at < (({day_sql}::date) + 1)::timestamptz;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return {
            "gross_collected_ngwee": 0,
            "commission_captured_ngwee": 0,
            "vendor_released_ngwee": 0,
        }
    parts = result.rows[0].split("|")
    if len(parts) != 3:
        return {
            "gross_collected_ngwee": 0,
            "commission_captured_ngwee": 0,
            "vendor_released_ngwee": 0,
        }
    return {
        "gross_collected_ngwee": int(parts[0]),
        "commission_captured_ngwee": int(parts[1]),
        "vendor_released_ngwee": int(parts[2]),
    }
