"""Collection kickoff — create payment row and USSD-push via Lenco."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.errors import AppError
from app.services.payments import gate
from app.services.payments.base import (
    CollectionStatus,
    InitiateCollectionRequest,
    PaymentProviderError,
    PaymentStrategy,
    ProviderOutcome,
    QueryStatusRequest,
)
from app.services.payments.references import make_order_reference
from app.services.payments.registry import LENCO_PROVIDER, get
from app.services.payments.state import (
    PaymentStatus,
    ServiceRoleClient,
    apply_payment_status,
    collection_observation_from_query,
    lenco_collection_status_to_payment_status,
    validate_query_collection_observation,
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
    if request.rail not in {"mtn", "airtel"}:
        raise AppError(
            code="unsupported_rail", message="Use the hosted card session", http_status=422
        )
    payment_id = str(uuid4())
    lenco_reference = make_order_reference(request.checkout_group_id, attempt=payment_id)
    claimed = claim_payment_attempt(
        service_client,
        checkout_group_id=request.checkout_group_id,
        actor_id=actor_id,
        payment_id=payment_id,
        rail=request.rail,
        reference=lenco_reference,
        raw={"payer_phone": request.phone},
    )
    amount_ngwee = int(claimed["amount_ngwee"])

    provider = strategy or get(request.provider)
    try:
        collection = await provider.initiate_collection(
            InitiateCollectionRequest(
                reference=lenco_reference,
                amount_ngwee=amount_ngwee,
                phone=request.phone,
                operator=request.rail,
            )
        )
    except PaymentProviderError:
        # The durable claimed reference is still reconcilable after response loss.
        return InitiatePaymentResult(payment_id, PaymentStatus.INITIATED, lenco_reference, None)

    raw_patch: dict[str, Any] = {
        "payer_phone": request.phone,
        "collection": collection.model_dump(),
    }
    if collection.provider_reference:
        raw_patch["provider_reference"] = collection.provider_reference
    service_client.client.table("payments").update({"raw": raw_patch}).eq(
        "id", payment_id
    ).execute()

    current_status = PaymentStatus.INITIATED
    if collection.status in {CollectionStatus.SUCCESSFUL, CollectionStatus.FAILED}:
        try:
            result = await provider.query_status(QueryStatusRequest(reference=lenco_reference))
            if result.outcome != ProviderOutcome.NOT_FOUND:
                validate_query_collection_observation(
                    service_client, payment_id=payment_id, result=result
                )
                incoming = lenco_collection_status_to_payment_status(result.status)
                if incoming is not None:
                    apply_payment_status(
                        service_client,
                        payment_id=payment_id,
                        incoming_status=incoming,
                        actor_id=actor_id,
                        note="Collection initiation verified by canonical status query",
                        observation=collection_observation_from_query(
                            result, source="initiation_query"
                        ),
                    )
        except PaymentProviderError:
            pass
    else:
        apply_payment_status(
            service_client,
            payment_id=payment_id,
            incoming_status=PaymentStatus.USSD_PUSHED,
            actor_id=actor_id,
            note="Collection initiated",
        )
        incoming = (
            PaymentStatus.PAY_OFFLINE
            if collection.status == CollectionStatus.PAY_OFFLINE
            else PaymentStatus.USSD_PUSHED
        )
        apply_payment_status(
            service_client,
            payment_id=payment_id,
            incoming_status=incoming,
            actor_id=actor_id,
            note="Collection initiated",
        )
    # A callback may have won; return the stored result, never overwrite it.
    row = _single_row(
        service_client.client.table("payments")
        .select("status")
        .eq("id", payment_id)
        .maybe_single()
        .execute()
    )
    if row:
        current_status = PaymentStatus(row["status"])

    return InitiatePaymentResult(
        payment_id=payment_id,
        status=current_status,
        lenco_reference=lenco_reference,
        provider_reference=collection.provider_reference,
    )


def require_payments_enabled(*, rail: str, reference: str) -> None:
    enabled, reason = gate.payments_gate_status()
    if not enabled:
        gate.log_payment_blocked(reason, method=rail, reference=reference)
        raise gate.PaymentsDisabledError()


def claim_payment_attempt(
    service_client: ServiceRoleClient,
    *,
    checkout_group_id: str,
    actor_id: str,
    payment_id: str,
    rail: str,
    reference: str,
    raw: dict[str, Any],
    resume: bool = False,
) -> dict[str, Any]:
    """Gate before work; lifecycle and competition decided with insertion under DB lock.

    A timeout after claiming leaves the original reference in flight. Only a
    validated terminal provider failure permits a new attempt. No SELECT fallback.
    """
    require_payments_enabled(rail=rail, reference=checkout_group_id)
    response = service_client.client.rpc(
        "claim_payable_payment",
        {
            "p_checkout_id": checkout_group_id,
            "p_actor_id": actor_id,
            "p_payment_id": payment_id,
            "p_rail": rail,
            "p_reference": reference,
            "p_raw": raw,
            "p_resume": resume,
        },
    ).execute()
    result = _single_row(response)
    if not result or result.get("result") != "claimed":
        raise AppError(
            code="payment.not_payable",
            message="Payment cannot be started or resumed",
            http_status=409,
            details={"reason": (result or {}).get("result", "claim_failed")},
        )
    return result
