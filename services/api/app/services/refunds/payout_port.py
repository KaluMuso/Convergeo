"""Customer-refund payout port.

Records the refund payout row; the actual Lenco send + status re-query is done by the
shared payout sweeper (`app.services.payouts.retry.retry_payout_row`), which is now
customer-refund-aware via the ``kind: customer_refund`` tag on ``resolve_snapshot``
(sends to the customer momo, and skips the vendor ``payout_executed`` ledger post since
the refund legs were already posted by ``execute_refund``). The row is created
``pending`` (never sent inline — the refund callers are sync). Remaining piece: the
scheduled dispatch job that scans ``pending``/``processing`` payouts and drives the
sweeper (F9b-gated — needs Lenco creds)."""

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


def initiate_customer_refund_payout(
    *,
    service_client: ServiceRoleClient,
    refund_id: str,
    vendor_id: str,
    amount_ngwee: int,
    rail: CustomerRail,
    customer_momo: str,
) -> CustomerRefundPayoutResult:
    """Create a customer-refund payout row and return its idempotent rfd-* reference.

    Persists a ``payouts`` row tagged ``kind: customer_refund`` with status ``pending``
    (never sent inline). The shared sweeper sends it to ``customer_momo`` on the given
    rail; live delivery is F9b-gated.
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
        "status": "pending",
        "resolve_snapshot": {
            "kind": "customer_refund",
            "refund_id": refund_id,
            "customer_momo": customer_momo,
            "rail": rail,
            "retry_attempts": 0,
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
