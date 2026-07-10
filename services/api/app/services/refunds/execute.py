"""Refund execution — idempotent, template-only ledger writes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol, cast

from app.errors import AppError
from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.refunds.clawback import clawback_outstanding_from_payable_balance
from app.services.refunds.config import load_restocking_fee_bps
from app.services.refunds.math import (
    Lane1RefundAmount,
    Lane2RefundBreakdown,
    compute_lane1_refund,
    compute_lane2_refund,
)
from app.services.refunds.payout_port import CustomerRail, initiate_customer_refund_payout
from app.services.refunds.release import order_funds_released

Lane = Literal[1, 2]
ACTIVE_REFUND_STATUSES = frozenset({"pending", "processing", "completed"})


class RefundPhase(StrEnum):
    PRE_RELEASE = "pre_release"
    POST_RELEASE = "post_release"


class ServiceRoleClient(Protocol):
    client: Any


@dataclass(frozen=True, slots=True)
class RefundExecutionResult:
    refund_id: str
    order_id: str
    lane: Lane
    phase: RefundPhase
    amount_ngwee: int
    payout_id: str
    lenco_reference: str
    ledger_transaction_ids: tuple[str, ...]
    breakdown: dict[str, Any]
    created: bool


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return cast(dict[str, Any], first)
    return None


def _order_item_total_ngwee(service_client: ServiceRoleClient, order_id: str) -> int:
    response = (
        service_client.client.table("order_items")
        .select("qty, unit_price_ngwee")
        .eq("order_id", order_id)
        .execute()
    )
    total = 0
    for row in _rows(response):
        qty = row.get("qty", 0)
        unit = row.get("unit_price_ngwee", 0)
        if isinstance(qty, int) and isinstance(unit, int):
            total += qty * unit
    return total


def _fetch_order(service_client: ServiceRoleClient, order_id: str) -> dict[str, Any]:
    response = (
        service_client.client.table("orders")
        .select("id, vendor_id, delivery_fee_ngwee, status")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError("order_not_found", "Order not found", 404)
    return row


def _find_existing_refund(
    service_client: ServiceRoleClient,
    order_id: str,
) -> dict[str, Any] | None:
    response = (
        service_client.client.table("refunds")
        .select("*")
        .eq("order_id", order_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return None
    row = rows[0]
    if row.get("status") in ACTIVE_REFUND_STATUSES:
        return row
    return None


def _result_from_existing(row: dict[str, Any]) -> RefundExecutionResult:
    payout_ref = row.get("payout_ref")
    raw_breakdown = row.get("breakdown")
    breakdown: dict[str, Any] = raw_breakdown if isinstance(raw_breakdown, dict) else {}
    phase_raw = breakdown.get("phase", RefundPhase.PRE_RELEASE.value)
    try:
        phase = RefundPhase(str(phase_raw))
    except ValueError:
        phase = RefundPhase.PRE_RELEASE
    ledger_ids = breakdown.get("ledger_transaction_ids", [])
    if not isinstance(ledger_ids, list):
        ledger_ids = []
    return RefundExecutionResult(
        refund_id=str(row["id"]),
        order_id=str(row["order_id"]),
        lane=cast(Lane, row["lane"]),
        phase=phase,
        amount_ngwee=int(row["amount_ngwee"]),
        payout_id=str(payout_ref) if payout_ref else "",
        lenco_reference=str(breakdown.get("lenco_reference", "")),
        ledger_transaction_ids=tuple(str(x) for x in ledger_ids),
        breakdown=breakdown,
        created=False,
    )


def _lane1_breakdown(amount: Lane1RefundAmount, phase: RefundPhase) -> dict[str, Any]:
    return {
        "lane": 1,
        "phase": phase.value,
        "item_ngwee": amount.item_ngwee,
        "delivery_fee_ngwee": amount.delivery_fee_ngwee,
        "refund_ngwee": amount.refund_ngwee,
    }


def _lane2_breakdown(amount: Lane2RefundBreakdown, phase: RefundPhase) -> dict[str, Any]:
    return {
        "lane": 2,
        "phase": phase.value,
        "item_ngwee": amount.item_ngwee,
        "outbound_delivery_ngwee": amount.outbound_delivery_ngwee,
        "return_transport_ngwee": amount.return_transport_ngwee,
        "restocking_fee_bps": amount.restocking_fee_bps,
        "restocking_fee_ngwee": amount.restocking_fee_ngwee,
        "vendor_retained_ngwee": amount.vendor_retained_ngwee,
        "refund_ngwee": amount.refund_ngwee,
        "escrow_release_ngwee": amount.escrow_release_ngwee,
    }


def _post_pre_release_ledger(
    *,
    lane: Lane,
    refund_id: str,
    order_id: str,
    vendor_id: str,
    lane1: Lane1RefundAmount | None,
    lane2: Lane2RefundBreakdown | None,
) -> tuple[str, ...]:
    txn_ids: list[str] = []
    if lane == 1:
        assert lane1 is not None
        posted = post_transaction(
            idempotency_key=f"refund-{refund_id}-ledger",
            template=LedgerTemplate.REFUND_LANE1,
            order_id=order_id,
            refund_id=refund_id,
            refund_ngwee=lane1.refund_ngwee,
        )
        txn_ids.append(posted.id)
    else:
        assert lane2 is not None
        posted = post_transaction(
            idempotency_key=f"refund-{refund_id}-ledger",
            template=LedgerTemplate.REFUND_LANE2,
            order_id=order_id,
            refund_id=refund_id,
            escrow_release_ngwee=lane2.escrow_release_ngwee,
            refund_to_customer_ngwee=lane2.refund_ngwee,
            vendor_retained_ngwee=lane2.vendor_retained_ngwee,
            restocking_fee_ngwee=lane2.restocking_fee_ngwee,
            vendor_id=vendor_id,
        )
        txn_ids.append(posted.id)
    return tuple(txn_ids)


def _post_post_release_clawback(
    *,
    refund_id: str,
    order_id: str,
    vendor_id: str,
    clawback_ngwee: int,
) -> str:
    posted = post_transaction(
        idempotency_key=f"refund-{refund_id}-clawback",
        template=LedgerTemplate.CLAWBACK,
        order_id=order_id,
        refund_id=refund_id,
        clawback_ngwee=clawback_ngwee,
        vendor_id=vendor_id,
    )
    return posted.id


def execute_refund(
    *,
    service_client: ServiceRoleClient,
    order_id: str,
    lane: Lane,
    return_transport_ngwee: int = 0,
    customer_rail: CustomerRail = "mtn",
    customer_momo: str,
    dispute_id: str | None = None,
    idempotency_key: str | None = None,
) -> RefundExecutionResult:
    """Execute or return an existing refund for an order (double-execution guarded)."""
    existing = _find_existing_refund(service_client, order_id)
    if existing is not None:
        return _result_from_existing(existing)

    order = _fetch_order(service_client, order_id)
    vendor_id = str(order["vendor_id"])
    delivery_fee = int(order.get("delivery_fee_ngwee", 0))
    item_total = _order_item_total_ngwee(service_client, order_id)

    lane1: Lane1RefundAmount | None = None
    lane2: Lane2RefundBreakdown | None = None
    if lane == 1:
        lane1 = compute_lane1_refund(item_ngwee=item_total, delivery_fee_ngwee=delivery_fee)
        refund_amount = lane1.refund_ngwee
    else:
        restocking_bps = load_restocking_fee_bps(service_client)
        lane2 = compute_lane2_refund(
            item_ngwee=item_total,
            outbound_delivery_ngwee=delivery_fee,
            return_transport_ngwee=return_transport_ngwee,
            restocking_fee_bps=restocking_bps,
        )
        refund_amount = lane2.refund_ngwee

    if refund_amount <= 0:
        raise AppError(
            "refund_amount_zero",
            "Computed refund amount is zero",
            422,
            {"order_id": order_id, "lane": lane},
        )

    released = order_funds_released(service_client, order_id)
    phase = RefundPhase.POST_RELEASE if released else RefundPhase.PRE_RELEASE

    refund_id = str(uuid.uuid4())
    breakdown: dict[str, Any]
    if lane == 1:
        assert lane1 is not None
        breakdown = _lane1_breakdown(lane1, phase)
    else:
        assert lane2 is not None
        breakdown = _lane2_breakdown(lane2, phase)
    if dispute_id:
        breakdown["dispute_id"] = dispute_id
    if idempotency_key:
        breakdown["idempotency_key"] = idempotency_key

    insert_row = {
        "id": refund_id,
        "order_id": order_id,
        "lane": lane,
        "breakdown": breakdown,
        "amount_ngwee": refund_amount,
        "status": "processing",
    }
    insert_response = service_client.client.table("refunds").insert(insert_row).execute()
    inserted = _single_row(insert_response)
    if inserted is not None:
        refund_id = str(inserted.get("id", refund_id))

    ledger_ids: list[str] = []
    if phase == RefundPhase.PRE_RELEASE:
        ledger_ids.extend(
            _post_pre_release_ledger(
                lane=lane,
                refund_id=refund_id,
                order_id=order_id,
                vendor_id=vendor_id,
                lane1=lane1,
                lane2=lane2,
            )
        )
    else:
        ledger_ids.append(
            _post_post_release_clawback(
                refund_id=refund_id,
                order_id=order_id,
                vendor_id=vendor_id,
                clawback_ngwee=refund_amount,
            )
        )

    payout = initiate_customer_refund_payout(
        service_client=service_client,
        refund_id=refund_id,
        vendor_id=vendor_id,
        amount_ngwee=refund_amount,
        rail=customer_rail,
        customer_momo=customer_momo,
    )

    breakdown["ledger_transaction_ids"] = ledger_ids
    breakdown["lenco_reference"] = payout.lenco_reference
    breakdown["phase"] = phase.value

    service_client.client.table("refunds").update(
        {
            "status": "completed",
            "payout_ref": payout.payout_id,
            "breakdown": breakdown,
        }
    ).eq("id", refund_id).execute()

    return RefundExecutionResult(
        refund_id=refund_id,
        order_id=order_id,
        lane=lane,
        phase=phase,
        amount_ngwee=refund_amount,
        payout_id=payout.payout_id,
        lenco_reference=payout.lenco_reference,
        ledger_transaction_ids=tuple(ledger_ids),
        breakdown=breakdown,
        created=True,
    )


def vendor_payable_clawback_outstanding(vendor_payable_balance_ngwee: int) -> int:
    """Expose clawback balance helper for payout netting (M08-P09)."""
    return clawback_outstanding_from_payable_balance(vendor_payable_balance_ngwee)
