"""Customer-scoped payment status polling and retry for checkout pending UX."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Protocol
from uuid import uuid4

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import NgweeInt, StrictModel
from app.services.payments.base import (
    CollectionStatus,
    InitiateCollectionRequest,
    PaymentStrategy,
)
from app.services.payments.initiate import InitiatePaymentRequest
from app.services.payments.references import make_order_reference
from app.services.payments.registry import get as get_payment_strategy
from app.services.payments.state import PaymentEvent, PaymentStatus, transition_payment
from fastapi import APIRouter, Depends, Query
from pydantic import Field

router = APIRouter(prefix="/payments", tags=["payments"])

WAITING_STATUSES = frozenset(
    {
        PaymentStatus.INITIATED.value,
        PaymentStatus.USSD_PUSHED.value,
        PaymentStatus.PAY_OFFLINE.value,
    }
)
RETRYABLE_STATUSES = frozenset(
    {
        PaymentStatus.FAILED.value,
        PaymentStatus.EXPIRED.value,
        PaymentStatus.CANCELLED.value,
    }
)
PaymentStatusLiteral = Literal[
    "initiated",
    "ussd_pushed",
    "pay_offline",
    "success",
    "failed",
    "expired",
    "cancelled",
    "cod",
]


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class PaymentStatusResponse(StrictModel):
    checkout_group_id: str
    payment_id: str | None
    status: PaymentStatusLiteral
    amount_ngwee: NgweeInt
    rail: str | None = None
    cod: bool
    order_id: str
    payer_phone: str | None = None


class PaymentRetryRequest(StrictModel):
    checkout_group_id: str
    payer_number: str | None = Field(default=None, max_length=20)


class PaymentRetryResponse(StrictModel):
    checkout_group_id: str
    payment_id: str
    status: PaymentStatusLiteral
    order_count: int


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _load_checkout_group(
    service: ServiceRoleClient,
    checkout_group_id: str,
) -> dict[str, Any] | None:
    response = (
        service.client.table("checkout_groups")
        .select("id, customer_id, total_ngwee, status")
        .eq("id", checkout_group_id)
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def _assert_group_owner(group: dict[str, Any] | None, customer_id: str) -> dict[str, Any]:
    if group is None:
        raise AppError(
            code="not_found",
            message="Checkout group not found",
            http_status=404,
            details={"checkout_group_id": "unknown"},
        )
    if str(group.get("customer_id")) != customer_id:
        raise AppError(
            code="forbidden",
            message="You do not have access to this checkout group",
            http_status=403,
        )
    return group


def _load_orders_for_group(
    service: ServiceRoleClient,
    checkout_group_id: str,
) -> list[dict[str, Any]]:
    response = (
        service.client.table("orders")
        .select("id, cod, customer_id")
        .eq("checkout_group_id", checkout_group_id)
        .order("created_at", desc=False)
        .execute()
    )
    return _rows(response)


def _load_latest_payment(
    service: ServiceRoleClient,
    checkout_group_id: str,
) -> dict[str, Any] | None:
    response = (
        service.client.table("payments")
        .select(
            "id, checkout_group_id, status, amount_ngwee, rail, raw, created_at, updated_at"
        )
        .eq("checkout_group_id", checkout_group_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    return rows[0] if rows else None


def _load_payment_by_id(
    service: ServiceRoleClient,
    payment_id: str,
) -> dict[str, Any] | None:
    response = (
        service.client.table("payments")
        .select(
            "id, checkout_group_id, status, amount_ngwee, rail, raw, created_at, updated_at"
        )
        .eq("id", payment_id)
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def _extract_payer_phone(payment: dict[str, Any] | None) -> str | None:
    if payment is None:
        return None
    raw = payment.get("raw")
    if not isinstance(raw, dict):
        return None
    for key in ("payer_phone", "phone", "payer_number"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    collection = raw.get("collection")
    if isinstance(collection, dict):
        phone = collection.get("phone")
        if isinstance(phone, str) and phone.strip():
            return phone.strip()
    return None


def _build_status_response(
    *,
    group: dict[str, Any],
    orders: list[dict[str, Any]],
    payment: dict[str, Any] | None,
) -> PaymentStatusResponse:
    checkout_group_id = str(group["id"])
    if not orders:
        raise AppError(
            code="orders.not_found",
            message="No orders found for this checkout group",
            http_status=404,
            details={"checkout_group_id": checkout_group_id},
        )

    cod = any(bool(order.get("cod")) for order in orders)
    order_id = str(orders[0]["id"])
    total_raw = group.get("total_ngwee", 0)
    amount_ngwee = int(total_raw) if isinstance(total_raw, int) else 0

    if cod:
        return PaymentStatusResponse(
            checkout_group_id=checkout_group_id,
            payment_id=None,
            status="cod",
            amount_ngwee=amount_ngwee,
            rail=None,
            cod=True,
            order_id=order_id,
            payer_phone=None,
        )

    if payment is None:
        raise AppError(
            code="payment.not_found",
            message="No payment found for this checkout group",
            http_status=404,
            details={"checkout_group_id": checkout_group_id},
        )

    payment_amount = payment.get("amount_ngwee")
    if isinstance(payment_amount, int) and payment_amount > 0:
        amount_ngwee = payment_amount

    status_raw = payment.get("status")
    status = str(status_raw) if isinstance(status_raw, str) else PaymentStatus.INITIATED.value

    return PaymentStatusResponse(
        checkout_group_id=checkout_group_id,
        payment_id=str(payment["id"]),
        status=status,  # type: ignore[arg-type]
        amount_ngwee=amount_ngwee,
        rail=str(payment["rail"]) if payment.get("rail") is not None else None,
        cod=False,
        order_id=order_id,
        payer_phone=_extract_payer_phone(payment),
    )


async def _create_retry_payment_attempt(
    service: ServiceRoleClient,
    *,
    request: InitiatePaymentRequest,
    actor_id: str,
    strategy: PaymentStrategy | None = None,
) -> tuple[str, PaymentStatus]:
    """Start a new payment row for an existing checkout group (retry path)."""
    group = _load_checkout_group(service, request.checkout_group_id)
    if group is None:
        raise AppError(code="not_found", message="Checkout group not found", http_status=404)

    amount_ngwee = request.amount_ngwee
    group_total = group.get("total_ngwee")
    if isinstance(group_total, int) and group_total > 0:
        amount_ngwee = group_total

    payment_id = str(uuid4())
    reference_source = request.order_id or request.checkout_group_id
    lenco_reference = make_order_reference(reference_source)

    insert_row = {
        "id": payment_id,
        "checkout_group_id": request.checkout_group_id,
        "provider": request.provider,
        "rail": request.rail,
        "lenco_reference": lenco_reference,
        "amount_ngwee": amount_ngwee,
        "status": PaymentStatus.INITIATED.value,
        "raw": {"payer_phone": request.phone},
    }
    insert_response = service.client.table("payments").insert(insert_row).execute()
    if _single_row(insert_response) is None and not getattr(insert_response, "data", None):
        raise AppError(
            code="payment_write_failed",
            message="Failed to create payment row",
            http_status=500,
        )

    provider = strategy or get_payment_strategy(request.provider)
    collection = await provider.initiate_collection(
        InitiateCollectionRequest(
            reference=lenco_reference,
            amount_ngwee=amount_ngwee,
            phone=request.phone,
            operator=request.rail,
        )
    )

    transition_payment(
        service,
        payment_id=payment_id,
        event=PaymentEvent.USSD_PUSHED,
        actor_id=actor_id,
        note="USSD push initiated (payment retry)",
    )

    current_status = PaymentStatus.USSD_PUSHED
    if collection.status == CollectionStatus.PAY_OFFLINE:
        transition_payment(
            service,
            payment_id=payment_id,
            event=PaymentEvent.PAY_OFFLINE,
            actor_id=actor_id,
            note="Lenco collection entered pay-offline (payment retry)",
        )
        current_status = PaymentStatus.PAY_OFFLINE

    raw_patch: dict[str, Any] = {
        "payer_phone": request.phone,
        "collection": collection.model_dump(),
    }
    if collection.provider_reference:
        raw_patch["provider_reference"] = collection.provider_reference
    service.client.table("payments").update({"raw": raw_patch}).eq("id", payment_id).execute()

    return payment_id, current_status


@router.get("/status", response_model=PaymentStatusResponse)
async def get_payment_status(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    group: str | None = Query(default=None, min_length=1),
    payment: str | None = Query(default=None, min_length=1),
) -> PaymentStatusResponse:
    if not group and not payment:
        raise AppError(
            code="validation_error",
            message="Provide group or payment query parameter",
            http_status=422,
            details={"fields": ["group", "payment"]},
        )

    checkout_group_id: str
    latest_payment: dict[str, Any] | None

    if payment:
        payment_row = _load_payment_by_id(service, payment)
        if payment_row is None:
            raise AppError(
                code="not_found",
                message="Payment not found",
                http_status=404,
                details={"payment_id": payment},
            )
        checkout_group_id = str(payment_row["checkout_group_id"])
        group_row = _assert_group_owner(
            _load_checkout_group(service, checkout_group_id),
            current_user.id,
        )
        latest_payment = payment_row
    else:
        assert group is not None
        checkout_group_id = group
        group_row = _assert_group_owner(
            _load_checkout_group(service, checkout_group_id),
            current_user.id,
        )
        latest_payment = _load_latest_payment(service, checkout_group_id)

    orders = _load_orders_for_group(service, checkout_group_id)
    for order in orders:
        if str(order.get("customer_id")) != current_user.id:
            raise AppError(
                code="forbidden",
                message="You do not have access to this checkout group",
                http_status=403,
            )

    return _build_status_response(group=group_row, orders=orders, payment=latest_payment)


@router.post("/retry", response_model=PaymentRetryResponse)
async def retry_payment(
    body: PaymentRetryRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PaymentRetryResponse:
    group = _assert_group_owner(
        _load_checkout_group(service, body.checkout_group_id),
        current_user.id,
    )
    orders = _load_orders_for_group(service, body.checkout_group_id)
    if not orders:
        raise AppError(
            code="orders.not_found",
            message="No orders found for this checkout group",
            http_status=404,
        )
    if any(bool(order.get("cod")) for order in orders):
        raise AppError(
            code="payment.cod_no_retry",
            message="Cash on delivery orders do not require payment retry",
            http_status=409,
        )

    order_count = len(orders)
    latest = _load_latest_payment(service, body.checkout_group_id)
    if latest is not None:
        status = str(latest.get("status") or "")
        if status in WAITING_STATUSES:
            raise AppError(
                code="payment.in_progress",
                message="A payment attempt is already in progress",
                http_status=409,
                details={"payment_id": str(latest["id"]), "status": status},
            )
        if status not in RETRYABLE_STATUSES and status != PaymentStatus.SUCCESS.value:
            raise AppError(
                code="payment.not_retryable",
                message="Payment cannot be retried in its current state",
                http_status=409,
                details={"status": status},
            )
        if status == PaymentStatus.SUCCESS.value:
            raise AppError(
                code="payment.already_successful",
                message="Payment already succeeded",
                http_status=409,
            )

    payer_phone = body.payer_number or _extract_payer_phone(latest)
    if not payer_phone:
        raise AppError(
            code="checkout.payer_number_required",
            message="Payer mobile number is required to retry payment",
            http_status=422,
            details={"field": "payer_number"},
        )

    rail = str(latest["rail"]) if latest and latest.get("rail") else "mtn"
    total_raw = group.get("total_ngwee", 0)
    amount_ngwee = int(total_raw) if isinstance(total_raw, int) else 0
    first_order_id = str(orders[0]["id"])

    payment_id, new_status = await _create_retry_payment_attempt(
        service,
        request=InitiatePaymentRequest(
            checkout_group_id=body.checkout_group_id,
            amount_ngwee=amount_ngwee,
            rail=rail,
            phone=payer_phone,
            order_id=first_order_id,
        ),
        actor_id=current_user.id,
    )

    orders_after = _load_orders_for_group(service, body.checkout_group_id)
    if len(orders_after) != order_count:
        raise AppError(
            code="orders.duplicate_detected",
            message="Retry must not create duplicate orders",
            http_status=500,
            details={"before": order_count, "after": len(orders_after)},
        )

    return PaymentRetryResponse(
        checkout_group_id=body.checkout_group_id,
        payment_id=payment_id,
        status=new_status.value,
        order_count=order_count,
    )
