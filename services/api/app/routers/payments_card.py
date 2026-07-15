"""Card payments via Lenco hosted widget — session create and server-verified return."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import uuid4

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.identity import lookup_user_email
from app.services.payments.base import PaymentStrategy, QueryStatusRequest
from app.services.payments.lenco.config import LencoEnvironment, get_lenco_environment
from app.services.payments.money import ngwee_to_major_str
from app.services.payments.references import make_order_reference
from app.services.payments.registry import LENCO_PROVIDER
from app.services.payments.registry import get as get_payment_strategy
from app.services.payments.state import (
    SYSTEM_ACTOR_ID,
    PaymentEvent,
    PaymentStatus,
    apply_payment_status,
    lenco_collection_status_to_payment_status,
    lenco_webhook_event_to_payment_status,
    process_webhook_event,
    release_checkout_for_retry,
    transition_payment,
)
from fastapi import APIRouter, Depends
from pydantic import Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments/card", tags=["payments-card"])

WIDGET_SCRIPT_PROD = "https://pay.lenco.co/js/v1/inline.js"
WIDGET_SCRIPT_SANDBOX = "https://pay.sandbox.lenco.co/js/v1/inline.js"

ClientReturnStatus = Literal["success", "failed", "closed", "pending"]


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class CreateCardSessionRequest(StrictModel):
    checkout_group_id: str = Field(min_length=1)


class WidgetCustomerOut(StrictModel):
    email: str
    first_name: str
    last_name: str
    phone: str


class CreateCardSessionResponse(StrictModel):
    payment_id: str
    checkout_group_id: str
    reference: str
    amount_major: str
    currency: str = "ZMW"
    amount_ngwee: int
    widget_script_url: str
    customer: WidgetCustomerOut


class VerifyCardReturnRequest(StrictModel):
    client_status: ClientReturnStatus = "pending"


class VerifyCardReturnResponse(StrictModel):
    payment_id: str
    checkout_group_id: str
    status: str
    verified: bool
    order_confirmed: bool
    held: bool = False
    retry_checkout: bool = False


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _widget_script_url() -> str:
    if get_lenco_environment() == LencoEnvironment.SANDBOX:
        return WIDGET_SCRIPT_SANDBOX
    return WIDGET_SCRIPT_PROD


def _load_checkout_group(
    service_client: ServiceRoleClient,
    *,
    checkout_group_id: str,
    customer_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("checkout_groups")
        .select("id, customer_id, total_ngwee, status")
        .eq("id", checkout_group_id)
        .eq("customer_id", customer_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Checkout session not found",
            http_status=404,
        )
    return row


def _load_payment(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("payments")
        .select(
            "id, checkout_group_id, status, lenco_reference, amount_ngwee, rail, provider, raw"
        )
        .eq("id", payment_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Payment not found", http_status=404)
    return row


def _load_customer_profile(
    service_client: ServiceRoleClient,
    *,
    customer_id: str,
) -> dict[str, Any]:
    # profiles has no email column (email lives in auth.users) and the name
    # column is display_name — select only what actually exists.
    response = (
        service_client.client.table("profiles")
        .select("id, phone, display_name")
        .eq("id", customer_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Customer profile not found",
            http_status=404,
        )
    return row


def _split_name(display_name: str | None) -> tuple[str, str]:
    if not display_name or not display_name.strip():
        return "Customer", "Vergeo5"
    parts = display_name.strip().split()
    if len(parts) == 1:
        return parts[0], "Customer"
    return parts[0], " ".join(parts[1:])


def _widget_customer(profile: dict[str, Any], *, email: str | None) -> WidgetCustomerOut:
    # email is resolved from auth.users (not profiles) by the caller.
    phone = profile.get("phone")
    if not isinstance(email, str) or not email.strip():
        raise AppError(
            code="checkout.profile_incomplete",
            message="An email address is required for card payment",
            http_status=422,
            details={"field": "email"},
        )
    if not isinstance(phone, str) or not phone.strip():
        raise AppError(
            code="checkout.profile_incomplete",
            message="A phone number is required for card payment",
            http_status=422,
            details={"field": "phone"},
        )
    first_name, last_name = _split_name(
        profile.get("display_name") if isinstance(profile.get("display_name"), str) else None
    )
    return WidgetCustomerOut(
        email=email.strip(),
        first_name=first_name,
        last_name=last_name,
        phone=phone.strip(),
    )


def _webhook_indicates_success(raw: dict[str, Any]) -> bool:
    event_name = str(raw.get("event", ""))
    mapped = lenco_webhook_event_to_payment_status(event_name)
    if mapped == PaymentStatus.SUCCESS:
        return True
    data = raw.get("data")
    if isinstance(data, dict):
        status = data.get("status")
        if isinstance(status, str):
            return lenco_collection_status_to_payment_status(status) == PaymentStatus.SUCCESS
    return False


def _find_success_webhook(
    service_client: ServiceRoleClient,
    *,
    reference: str,
) -> dict[str, Any] | None:
    response = (
        service_client.client.table("webhook_events")
        .select("id, provider, event_id, raw, processed_at")
        .eq("provider", "lenco")
        .order("created_at", desc=True)
        .execute()
    )
    for row in _rows(response):
        raw = row.get("raw")
        if not isinstance(raw, dict):
            continue
        data = raw.get("data")
        if not isinstance(data, dict):
            continue
        row_reference = data.get("reference")
        if row_reference != reference:
            continue
        if _webhook_indicates_success(raw):
            return row
    return None


def _patch_payment_raw(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    patch: dict[str, Any],
) -> None:
    payment = _load_payment(service_client, payment_id=payment_id)
    existing = payment.get("raw")
    merged: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    merged.update(patch)
    service_client.client.table("payments").update({"raw": merged}).eq("id", payment_id).execute()


def _hold_payment_mismatch(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    lenco_reference: str,
    reason: str,
    lenco_status: str | None,
) -> None:
    logger.error(
        "Card payment verification mismatch — payment held",
        extra={
            "alert": "card_payment_verification_mismatch",
            "payment_id": payment_id,
            "lenco_reference": lenco_reference,
            "reason": reason,
            "lenco_status": lenco_status,
        },
    )
    _patch_payment_raw(
        service_client,
        payment_id=payment_id,
        patch={
            "hold": {
                "reason": reason,
                "at": datetime.now(UTC).isoformat(),
                "lenco_status": lenco_status,
            }
        },
    )


def _mark_fulfilled(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    note: str,
) -> None:
    _patch_payment_raw(
        service_client,
        payment_id=payment_id,
        patch={
            "fulfilled_at": datetime.now(UTC).isoformat(),
            "fulfilment_note": note,
        },
    )


async def _query_lenco_status(
    strategy: PaymentStrategy,
    *,
    reference: str,
) -> PaymentStatus | None:
    result = await strategy.query_status(QueryStatusRequest(reference=reference))
    return lenco_collection_status_to_payment_status(result.status)


def _ensure_card_payment_owned(
    payment: dict[str, Any],
    *,
    customer_id: str,
    service_client: ServiceRoleClient,
) -> None:
    if str(payment.get("rail")) != "card":
        raise AppError(
            code="payment_invalid_rail",
            message="Payment is not a card payment",
            http_status=409,
            details={"rail": payment.get("rail")},
        )
    _load_checkout_group(
        service_client,
        checkout_group_id=str(payment["checkout_group_id"]),
        customer_id=customer_id,
    )


async def verify_card_payment_return(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    customer_id: str,
    client_status: ClientReturnStatus,
    strategy: PaymentStrategy | None = None,
) -> VerifyCardReturnResponse:
    """Server-side verify before fulfilment — Lenco status query + webhook cross-check."""
    payment = _load_payment(service_client, payment_id=payment_id)
    _ensure_card_payment_owned(payment, customer_id=customer_id, service_client=service_client)

    checkout_group_id = str(payment["checkout_group_id"])
    lenco_reference = str(payment["lenco_reference"])
    current_status = PaymentStatus(str(payment["status"]))

    if current_status == PaymentStatus.SUCCESS:
        return VerifyCardReturnResponse(
            payment_id=payment_id,
            checkout_group_id=checkout_group_id,
            status=PaymentStatus.SUCCESS.value,
            verified=True,
            order_confirmed=True,
        )

    provider = strategy or get_payment_strategy(str(payment.get("provider", LENCO_PROVIDER)))
    lenco_status = await _query_lenco_status(provider, reference=lenco_reference)

    webhook_row = _find_success_webhook(service_client, reference=lenco_reference)
    if webhook_row is not None and webhook_row.get("processed_at") is None:
        process_webhook_event(service_client, webhook_event_id=str(webhook_row["id"]))
        payment = _load_payment(service_client, payment_id=payment_id)
        current_status = PaymentStatus(str(payment["status"]))
        if current_status == PaymentStatus.SUCCESS:
            _mark_fulfilled(
                service_client,
                payment_id=payment_id,
                note="Card payment fulfilled after webhook processing",
            )
            return VerifyCardReturnResponse(
                payment_id=payment_id,
                checkout_group_id=checkout_group_id,
                status=PaymentStatus.SUCCESS.value,
                verified=True,
                order_confirmed=True,
            )

    webhook_confirmed = webhook_row is not None

    if client_status == "success" and lenco_status != PaymentStatus.SUCCESS:
        _hold_payment_mismatch(
            service_client,
            payment_id=payment_id,
            lenco_reference=lenco_reference,
            reason="client_claimed_success_lenco_mismatch",
            lenco_status=lenco_status.value if lenco_status is not None else None,
        )
        return VerifyCardReturnResponse(
            payment_id=payment_id,
            checkout_group_id=checkout_group_id,
            status=current_status.value,
            verified=False,
            order_confirmed=False,
            held=True,
        )

    if lenco_status == PaymentStatus.SUCCESS and webhook_confirmed:
        outcome = apply_payment_status(
            service_client,
            payment_id=payment_id,
            incoming_status=PaymentStatus.SUCCESS,
            actor_id=SYSTEM_ACTOR_ID,
            note="Card payment verified via Lenco status query and webhook cross-check",
        )
        if outcome is not None:
            _mark_fulfilled(
                service_client,
                payment_id=payment_id,
                note="Card payment fulfilled after server verification",
            )
        return VerifyCardReturnResponse(
            payment_id=payment_id,
            checkout_group_id=checkout_group_id,
            status=PaymentStatus.SUCCESS.value,
            verified=True,
            order_confirmed=True,
        )

    if lenco_status in {PaymentStatus.FAILED, PaymentStatus.EXPIRED} or client_status in {
        "failed",
        "closed",
    }:
        target = lenco_status or PaymentStatus.FAILED
        if target not in {PaymentStatus.FAILED, PaymentStatus.EXPIRED}:
            target = PaymentStatus.FAILED
        apply_payment_status(
            service_client,
            payment_id=payment_id,
            incoming_status=target,
            actor_id=SYSTEM_ACTOR_ID,
            note="Card widget payment failed or closed by customer",
        )
        release_checkout_for_retry(
            service_client,
            checkout_group_id=checkout_group_id,
            actor_id=SYSTEM_ACTOR_ID,
            note="Card payment failed — checkout released for retry",
        )
        return VerifyCardReturnResponse(
            payment_id=payment_id,
            checkout_group_id=checkout_group_id,
            status=target.value,
            verified=False,
            order_confirmed=False,
            retry_checkout=True,
        )

    return VerifyCardReturnResponse(
        payment_id=payment_id,
        checkout_group_id=checkout_group_id,
        status=current_status.value,
        verified=False,
        order_confirmed=False,
    )


async def create_card_widget_session(
    service_client: ServiceRoleClient,
    *,
    checkout_group_id: str,
    customer_id: str,
    actor_id: str,
) -> CreateCardSessionResponse:
    """Create a card payment row and return Lenco widget session parameters."""
    group = _load_checkout_group(
        service_client,
        checkout_group_id=checkout_group_id,
        customer_id=customer_id,
    )
    group_status = str(group.get("status", ""))
    if group_status == "expired":
        raise AppError(
            code="checkout.reservation_expired",
            message="Your reservation has expired",
            http_status=410,
        )

    total_raw = group.get("total_ngwee")
    if not isinstance(total_raw, int) or total_raw <= 0:
        raise AppError(
            code="validation_error",
            message="Checkout total is invalid",
            http_status=422,
        )

    profile = _load_customer_profile(service_client, customer_id=customer_id)
    email = lookup_user_email(service_client, user_id=customer_id)
    customer = _widget_customer(profile, email=email)

    payment_id = str(uuid4())
    # Salt with this attempt's payment_id so a retried card session on the same
    # checkout group gets a distinct reference (no UNIQUE lenco_reference clash).
    lenco_reference = make_order_reference(checkout_group_id, attempt=payment_id)
    amount_major = ngwee_to_major_str(total_raw)

    insert_row = {
        "id": payment_id,
        "checkout_group_id": checkout_group_id,
        "provider": LENCO_PROVIDER,
        "rail": "card",
        "lenco_reference": lenco_reference,
        "amount_ngwee": total_raw,
        "status": PaymentStatus.INITIATED.value,
        "raw": {
            "widget": {
                "script_url": _widget_script_url(),
                "created_at": datetime.now(UTC).isoformat(),
            }
        },
    }
    service_client.client.table("payments").insert(insert_row).execute()

    transition_payment(
        service_client,
        payment_id=payment_id,
        event=PaymentEvent.USSD_PUSHED,
        actor_id=actor_id,
        note="Lenco card widget session created",
    )

    return CreateCardSessionResponse(
        payment_id=payment_id,
        checkout_group_id=checkout_group_id,
        reference=lenco_reference,
        amount_major=amount_major,
        amount_ngwee=total_raw,
        widget_script_url=_widget_script_url(),
        customer=customer,
    )


@router.post("/session", response_model=CreateCardSessionResponse)
async def create_card_session(
    body: CreateCardSessionRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CreateCardSessionResponse:
    return await create_card_widget_session(
        service_client,
        checkout_group_id=body.checkout_group_id,
        customer_id=current_user.id,
        actor_id=current_user.id,
    )


@router.get("/{payment_id}/session", response_model=CreateCardSessionResponse)
async def get_card_session(
    payment_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CreateCardSessionResponse:
    """Return widget parameters for an existing in-flight card payment."""
    payment = _load_payment(service_client, payment_id=payment_id)
    _ensure_card_payment_owned(
        payment, customer_id=current_user.id, service_client=service_client
    )
    profile = _load_customer_profile(service_client, customer_id=current_user.id)
    email = lookup_user_email(service_client, user_id=current_user.id)
    customer = _widget_customer(profile, email=email)
    amount_ngwee = int(payment["amount_ngwee"])
    return CreateCardSessionResponse(
        payment_id=payment_id,
        checkout_group_id=str(payment["checkout_group_id"]),
        reference=str(payment["lenco_reference"]),
        amount_major=ngwee_to_major_str(amount_ngwee),
        amount_ngwee=amount_ngwee,
        widget_script_url=_widget_script_url(),
        customer=customer,
    )


@router.post("/{payment_id}/verify", response_model=VerifyCardReturnResponse)
async def verify_card_return(
    payment_id: str,
    body: VerifyCardReturnRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VerifyCardReturnResponse:
    return await verify_card_payment_return(
        service_client,
        payment_id=payment_id,
        customer_id=current_user.id,
        client_status=body.client_status,
    )
