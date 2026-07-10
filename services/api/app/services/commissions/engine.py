"""Commission engine — bps from purchase-time snapshot, supplies +3% stack, integer floor."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate, commission_ngwee_from_bps

SUPPLIES_STACK_BPS = 300
FREE_EVENTS_CATEGORY = "free_events"


@dataclass(frozen=True, slots=True)
class CommissionLineResult:
    listing_id: str | None
    category_key: str
    line_total_ngwee: int
    base_rate_bps: int
    effective_rate_bps: int
    commission_ngwee: int
    wholesale: bool


@dataclass(frozen=True, slots=True)
class OrderCommissionResult:
    lines: tuple[CommissionLineResult, ...]
    gross_ngwee: int
    commission_ngwee: int


@dataclass(frozen=True, slots=True)
class CommissionCaptureResult:
    order_id: str
    commission: OrderCommissionResult
    posted_transaction_ids: tuple[str, ...]


def commission_ngwee_for_line(*, line_total_ngwee: int, rate_bps: int) -> int:
    """Integer-exact bps → ngwee using floor division (matches ledger template)."""
    if rate_bps <= 0 or line_total_ngwee <= 0:
        return 0
    return commission_ngwee_from_bps(gross_ngwee=line_total_ngwee, commission_bps=rate_bps)


def effective_rate_bps(*, base_rate_bps: int, category_key: str, wholesale: bool) -> int:
    """Resolve purchase-time rate; wholesale/supplies lines stack +300 bps on category rate."""
    if category_key == FREE_EVENTS_CATEGORY or base_rate_bps <= 0:
        return 0
    if wholesale:
        return base_rate_bps + SUPPLIES_STACK_BPS
    return base_rate_bps


def parse_snapshot_lines(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalize ``orders.commission_snapshot`` into per-line dicts."""
    raw_lines = snapshot.get("lines")
    if isinstance(raw_lines, list) and raw_lines:
        return [line for line in raw_lines if isinstance(line, dict)]
    fallback_rate = snapshot.get("rate_bps")
    if isinstance(fallback_rate, int):
        return [
            {
                "listing_id": None,
                "category_key": str(snapshot.get("category_key", "default")),
                "rate_bps": fallback_rate,
                "line_total_ngwee": int(snapshot.get("line_total_ngwee", 0)),
                "wholesale": bool(snapshot.get("wholesale", False)),
            }
        ]
    return []


def compute_order_commission(snapshot: Mapping[str, Any]) -> OrderCommissionResult:
    """Compute total commission from the immutable purchase-time snapshot."""
    line_results: list[CommissionLineResult] = []
    gross = 0
    total_commission = 0

    for line in parse_snapshot_lines(snapshot):
        line_total = int(line.get("line_total_ngwee", 0))
        category_key = str(line.get("category_key", "default"))
        base_rate = int(line.get("rate_bps", 0))
        wholesale = bool(line.get("wholesale", False))
        rate = effective_rate_bps(
            base_rate_bps=base_rate,
            category_key=category_key,
            wholesale=wholesale,
        )
        commission = commission_ngwee_for_line(line_total_ngwee=line_total, rate_bps=rate)
        gross += line_total
        total_commission += commission
        line_results.append(
            CommissionLineResult(
                listing_id=(
                    str(line["listing_id"]) if line.get("listing_id") is not None else None
                ),
                category_key=category_key,
                line_total_ngwee=line_total,
                base_rate_bps=base_rate,
                effective_rate_bps=rate,
                commission_ngwee=commission,
                wholesale=wholesale,
            )
        )

    return OrderCommissionResult(
        lines=tuple(line_results),
        gross_ngwee=gross,
        commission_ngwee=total_commission,
    )


def capture_order_commission(
    *,
    order_id: str,
    commission_snapshot: Mapping[str, Any],
    idempotency_key_prefix: str,
    payment_id: str | None = None,
) -> CommissionCaptureResult:
    """Compute snapshot commission and post per-line ``commission_capture`` ledger entries."""
    commission = compute_order_commission(commission_snapshot)
    posted_ids: list[str] = []

    for index, line in enumerate(commission.lines):
        if line.commission_ngwee <= 0:
            continue
        suffix = line.listing_id or str(index)
        posted = post_transaction(
            idempotency_key=f"{idempotency_key_prefix}-commission-{suffix}",
            template=LedgerTemplate.COMMISSION_CAPTURE,
            order_id=order_id,
            payment_id=payment_id,
            gross_ngwee=line.line_total_ngwee,
            commission_bps=line.effective_rate_bps,
        )
        posted_ids.append(posted.id)

    return CommissionCaptureResult(
        order_id=order_id,
        commission=commission,
        posted_transaction_ids=tuple(posted_ids),
    )
