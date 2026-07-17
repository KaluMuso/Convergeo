"""Collection kickoff — create payment row and USSD-push via Lenco."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.errors import AppError
from app.services.payments.base import (
    CollectionStatus,
    InitiateCollectionRequest,
    PaymentStrategy,
)
from app.services.payments.gate import (
    PaymentsDisabledError,
    log_payment_blocked,
    payments_gate_status,
)
from app.services.payments.references import make_order_reference
from app.services.payments.registry import LENCO_PROVIDER, get
from app.services.payments.state import (
    PaymentEvent,
    PaymentStatus,
    ServiceRoleClient,
    transition_payment,
)


@dataclass(frozen=True, slots=True)
class InitiatePaymentRequest:
    checkout_group_id: str
    amount_ngwee: int
    rail: str
    phone: str
    provider: str = LENCO_PROVIDER
    order_id: str | None = None


@dataclass(frozen=True, slots=True)
class InitiatePaymentResult:
    payment_id: str
    status: PaymentStatus
    lenco_reference: str
    provider_reference: str | None


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first
    return None


def _load_checkout_group(
    service_client: ServiceRoleClient,
    checkout_group_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("checkout_groups")
        .select("id, total_ngwee, status")
        .eq("id", checkout_group_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Checkout group not found", http_status=404)
    return row


async def initiate_checkout_payment(
    service_client: ServiceRoleClient,
    request: InitiatePaymentRequest,
    *,
    strategy: PaymentStrategy | None = None,
    actor_id: str,
) -> InitiatePaymentResult:
    """Start MoMo collection for a checkout group: initiated → ussd_pushed (+ pay_offline)."""
    # Safe-by-default payment gate: block prepaid initiation (mobile money + card)
    # unless payments are explicitly enabled for this environment. Runs before any
    # DB write or provider call, so a disabled gate creates no payment row.
    enabled, reason_code = payments_gate_status()
    if not enabled:
        log_payment_blocked(
            reason_code,
            method=request.rail,
            reference=request.checkout_group_id,
        )
        raise PaymentsDisabledError()

    group = _load_checkout_group(service_client, request.checkout_group_id)
    if str(group.get("status")) == "completed":
        raise AppError(
            code="checkout_completed",
            message="Checkout group is already completed",
            http_status=409,
        )

    amount_ngwee = request.amount_ngwee
    group_total = group.get("total_ngwee")
    if isinstance(group_total, int) and group_total > 0:
        amount_ngwee = group_total

    payment_id = str(uuid4())
    reference_source = request.order_id or request.checkout_group_id
    # Salt the reference with this attempt's payment_id so a retry after a
    # failed/expired attempt gets a distinct, still-decodable reference and does
    # not collide on the UNIQUE payments.lenco_reference constraint.
    lenco_reference = make_order_reference(reference_source, attempt=payment_id)

    insert_row = {
        "id": payment_id,
        "checkout_group_id": request.checkout_group_id,
        "provider": request.provider,
        "rail": request.rail,
        "lenco_reference": lenco_reference,
        "amount_ngwee": amount_ngwee,
        "status": PaymentStatus.INITIATED.value,
        "raw": {},
    }
    insert_response = service_client.client.table("payments").insert(insert_row).execute()
    if _single_row(insert_response) is None and not getattr(insert_response, "data", None):
        raise AppError(
            code="payment_write_failed",
            message="Failed to create payment row",
            http_status=500,
        )

    provider = strategy or get(request.provider)
    collection = await provider.initiate_collection(
        InitiateCollectionRequest(
            reference=lenco_reference,
            amount_ngwee=amount_ngwee,
            phone=request.phone,
            operator=request.rail,
        )
    )

    transition_payment(
        service_client,
        payment_id=payment_id,
        event=PaymentEvent.USSD_PUSHED,
        actor_id=actor_id,
        note="USSD push initiated via Lenco collection",
    )

    current_status = PaymentStatus.USSD_PUSHED
    if collection.status == CollectionStatus.PAY_OFFLINE:
        transition_payment(
            service_client,
            payment_id=payment_id,
            event=PaymentEvent.PAY_OFFLINE,
            actor_id=actor_id,
            note="Lenco collection entered pay-offline",
        )
        current_status = PaymentStatus.PAY_OFFLINE

    raw_patch: dict[str, Any] = {"collection": collection.model_dump()}
    if collection.provider_reference:
        raw_patch["provider_reference"] = collection.provider_reference
    service_client.client.table("payments").update({"raw": raw_patch}).eq(
        "id", payment_id
    ).execute()

    return InitiatePaymentResult(
        payment_id=payment_id,
        status=current_status,
        lenco_reference=lenco_reference,
        provider_reference=collection.provider_reference,
    )
