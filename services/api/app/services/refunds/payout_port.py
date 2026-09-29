"""Customer-refund payout port.

Records the refund payout row; the actual Lenco send + status re-query is done by the
shared payout sweeper (`app.services.payouts.retry.retry_payout_row`), which is now
customer-refund-aware via the ``kind: customer_refund`` tag on ``resolve_snapshot``
(sends to the customer momo, and skips the vendor ``payout_executed`` ledger post since
the refund legs were already posted by ``execute_refund``). The row is created
``pending`` (never sent inline — the refund callers are sync); the existing dispatch
job ``POST /internal/payouts/retry`` → ``retry_pending_payouts`` scans
``pending``/``processing`` payouts and drives the sweeper. Live delivery is F9b-gated
(needs Lenco creds for the payout adapters)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from threading import Lock
from typing import Any, Literal, Protocol

from app.errors import AppError
from app.services.payments.references import make_refund_reference
from app.services.payouts.obligation import make_obligation
from postgrest.exceptions import APIError

CustomerRail = Literal["mtn", "airtel", "zamtel"]
_REFUND_PAYOUT_CREATE_LOCK = Lock()


class ServiceRoleClient(Protocol):
    client: Any


@dataclass(frozen=True, slots=True)
class CustomerRefundPayoutResult:
    payout_id: str
    lenco_reference: str
    amount_ngwee: int


def _result_from_existing(
    existing_data: dict[str, Any],
    *,
    lenco_reference: str,
    amount_ngwee: int,
    rail: CustomerRail,
    customer_momo: str,
) -> CustomerRefundPayoutResult:
    existing_snapshot = existing_data.get("resolve_snapshot")
    existing_customer = (
        existing_snapshot.get("customer_momo")
        if isinstance(existing_snapshot, dict)
        else None
    )
    if (
        existing_data.get("amount_ngwee") != amount_ngwee
        or existing_data.get("rail") != rail
        or existing_customer != customer_momo
    ):
        raise AppError(
            code="refund_payout_obligation_mismatch",
            message="Existing refund payout has a different immutable obligation",
            http_status=409,
            details={"lenco_reference": lenco_reference},
        )
    return CustomerRefundPayoutResult(
        payout_id=str(existing_data["id"]),
        lenco_reference=str(existing_data.get("lenco_reference") or lenco_reference),
        amount_ngwee=int(existing_data.get("amount_ngwee") or amount_ngwee),
    )


def _find_existing_payout(
    service_client: ServiceRoleClient,
    lenco_reference: str,
) -> dict[str, Any] | None:
    response = (
        service_client.client.table("payouts")
        .select("id, amount_ngwee, rail, lenco_reference, resolve_snapshot")
        .eq("lenco_reference", lenco_reference)
        .maybe_single()
        .execute()
    )
    data = getattr(response, "data", None)
    return data if isinstance(data, dict) and data.get("id") else None


def _initiate_customer_refund_payout_unlocked(
    *,
    service_client: ServiceRoleClient,
    refund_id: str,
    reference_key: str,
    vendor_id: str,
    amount_ngwee: int,
    rail: CustomerRail,
    customer_momo: str,
) -> CustomerRefundPayoutResult:
    """Create a customer-refund payout row and return its idempotent rfd-* reference.

    Persists a ``payouts`` row tagged ``kind: customer_refund`` with status ``pending``
    (never sent inline). The shared sweeper sends it to ``customer_momo`` on the given
    rail; live delivery is F9b-gated.

    The Lenco ``rfd-*`` reference is derived from ``reference_key`` (the caller's stable
    idempotency key), NOT from the per-call ``refund_id``. A retry therefore resumes
    the same durable obligation and stable provider reference.
    """
    if amount_ngwee <= 0:
        msg = "refund payout amount must be positive"
        raise ValueError(msg)

    lenco_reference = make_refund_reference(reference_key)

    # Resume-safe: same reference_key → same rfd-* reference. Prefer the existing
    # row so a mid-flight crash cannot mint a second pending customer payout.
    existing_data = _find_existing_payout(service_client, lenco_reference)
    if existing_data is not None:
        return _result_from_existing(
            existing_data,
            lenco_reference=lenco_reference,
            amount_ngwee=amount_ngwee,
            rail=rail,
            customer_momo=customer_momo,
        )

    payout_id = str(uuid.uuid4())
    destination = {
        "type": "mobile-money",
        "phone": customer_momo,
        "operator": rail,
    }
    row = {
        "id": payout_id,
        "vendor_id": vendor_id,
        "amount_ngwee": amount_ngwee,
        "rail": rail,
        "lenco_reference": lenco_reference,
        "status": "pending",
        "payout_kind": "customer_refund",
        "resolve_snapshot": {
            "kind": "customer_refund",
            "refund_id": refund_id,
            "customer_momo": customer_momo,
            "rail": rail,
            "retry_attempts": 0,
            "obligation": make_obligation(
                merchant_reference=lenco_reference,
                amount_ngwee=amount_ngwee,
                debit_account_id=None,
                destination=destination,
            ),
            "dispatch": {"state": "never_sent"},
        },
    }
    try:
        response = service_client.client.table("payouts").insert(row).execute()
    except APIError as exc:
        if str(getattr(exc, "code", "")) != "23505":
            raise
        winner = _find_existing_payout(service_client, lenco_reference)
        if winner is None:
            raise
        return _result_from_existing(
            winner,
            lenco_reference=lenco_reference,
            amount_ngwee=amount_ngwee,
            rail=rail,
            customer_momo=customer_momo,
        )
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


def initiate_customer_refund_payout(
    *,
    service_client: ServiceRoleClient,
    refund_id: str,
    reference_key: str,
    vendor_id: str,
    amount_ngwee: int,
    rail: CustomerRail,
    customer_momo: str,
) -> CustomerRefundPayoutResult:
    """Serialize local creators; the unique provider reference covers other workers."""
    with _REFUND_PAYOUT_CREATE_LOCK:
        return _initiate_customer_refund_payout_unlocked(
            service_client=service_client,
            refund_id=refund_id,
            reference_key=reference_key,
            vendor_id=vendor_id,
            amount_ngwee=amount_ngwee,
            rail=rail,
            customer_momo=customer_momo,
        )
