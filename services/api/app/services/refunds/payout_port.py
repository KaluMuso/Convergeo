"""Thin customer-refund payout port — stub until M08-P09 merges."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.services.payments.references import make_refund_reference

CustomerRail = Literal["mtn", "airtel", "zamtel"]


class ServiceRoleClient(Protocol):
    client: Any


@dataclass(frozen=True, slots=True)
class CustomerRefundPayoutResult:
    payout_id: str
    lenco_reference: str
    amount_ngwee: int


# TODO(M08-P09): replace stub with payouts service execution + Lenco transfer


def initiate_customer_refund_payout(
    *,
    service_client: ServiceRoleClient,
    refund_id: str,
    vendor_id: str,
    amount_ngwee: int,
    rail: CustomerRail,
    customer_momo: str,
) -> CustomerRefundPayoutResult:
    """Create a refund payout row and return idempotent rfd-* reference.

    Stub: persists ``payouts`` row with status ``processing``; live Lenco send is M08-P09.
    """
    if amount_ngwee <= 0:
        msg = "refund payout amount must be positive"
        raise ValueError(msg)

    payout_id = str(uuid.uuid4())
    lenco_reference = make_refund_reference(refund_id)
    row = {
        "id": payout_id,
        "vendor_id": vendor_id,
        "amount_ngwee": amount_ngwee,
        "rail": rail,
        "lenco_reference": lenco_reference,
        "status": "processing",
        "resolve_snapshot": {
            "kind": "customer_refund",
            "refund_id": refund_id,
            "customer_momo": customer_momo,
            "stub": True,
        },
    }
    response = service_client.client.table("payouts").insert(row).execute()
    data = getattr(response, "data", None)
    if isinstance(data, list) and data:
        payout_id = str(data[0].get("id", payout_id))
    elif isinstance(data, dict):
        payout_id = str(data.get("id", payout_id))

    return CustomerRefundPayoutResult(
        payout_id=payout_id,
        lenco_reference=lenco_reference,
        amount_ngwee=amount_ngwee,
    )
