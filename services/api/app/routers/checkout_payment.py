from __future__ import annotations

import re
from typing import Annotated, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.checkout import _ensure_session_active, _extract_data, _fetch_checkout_group
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from supabase import Client

router = APIRouter(prefix="/checkout", tags=["checkout"])

ALLOWED_MOMO_RAILS = frozenset({"mtn", "airtel"})
DEFAULT_COD_CAP_NGEWEE = 50_000
PAYER_NUMBER_PATTERN = re.compile(r"^\+260[79]\d{8}$")

PaymentMethod = Literal["momo", "card", "cod"]
MomoRail = Literal["mtn", "airtel"]


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Client: ...


class PaymentOptionsResponse(BaseModel):
    session_id: str
    subtotal_ngwee: int
    delivery_fee_ngwee: int
    total_ngwee: int
    cod_cap_ngwee: int
    cod_eligible: bool


class PaymentMethodRequest(BaseModel):
    session_id: str
    method: PaymentMethod
    rail: str | None = None
    payer_number: str | None = Field(default=None, max_length=20)


class PaymentMethodResponse(BaseModel):
    session_id: str
    method: PaymentMethod
    rail: MomoRail | None = None
    payer_number: str | None = None
    subtotal_ngwee: int
    delivery_fee_ngwee: int
    total_ngwee: int
    cod_cap_ngwee: int
    cod_eligible: bool


def _load_cod_cap_ngwee(service: ServiceRoleClient) -> int:
    response = (
        service.client.table("platform_config")
        .select("value")
        .eq("key", "cod_cap_ngwee")
        .maybe_single()
        .execute()
    )
    data = _extract_data(response)
    if isinstance(data, dict) and data.get("value") is not None:
        raw = data["value"]
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
    return DEFAULT_COD_CAP_NGEWEE


def _normalize_payer_number(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if value.strip().startswith("+"):
        return f"+{digits}"
    if digits.startswith("260"):
        return f"+{digits}"
    if len(digits) == 9:
        return f"+260{digits}"
    return value.strip()


def _is_valid_payer_number(value: str) -> bool:
    normalized = _normalize_payer_number(value)
    return PAYER_NUMBER_PATTERN.match(normalized) is not None


def _session_totals(group: dict[str, object]) -> tuple[int, int, int]:
    subtotal_raw = group.get("subtotal_ngwee", 0)
    delivery_raw = group.get("delivery_fee_ngwee", 0)
    total_raw = group.get("total_ngwee", 0)
    subtotal = int(subtotal_raw) if isinstance(subtotal_raw, int) else 0
    delivery_fee = int(delivery_raw) if isinstance(delivery_raw, int) else 0
    total = int(total_raw) if isinstance(total_raw, int) else 0
    return subtotal, delivery_fee, total


def _validate_payment_method(
    *,
    method: PaymentMethod,
    rail: str | None,
    payer_number: str | None,
    total_ngwee: int,
    cod_cap_ngwee: int,
) -> tuple[MomoRail | None, str | None]:
    if method == "cod":
        if total_ngwee > cod_cap_ngwee:
            raise AppError(
                code="checkout.cod_ineligible",
                message="Cash on delivery is not available for orders above the limit",
                http_status=422,
                details={
                    "total_ngwee": total_ngwee,
                    "cod_cap_ngwee": cod_cap_ngwee,
                    "reason": "total_exceeds_cap",
                },
            )
        return None, None

    if method == "card":
        return None, None

    if method == "momo":
        if rail is None:
            raise AppError(
                code="checkout.rail_required",
                message="Mobile money rail is required",
                http_status=422,
                details={"field": "rail"},
            )
        if rail == "zamtel":
            raise AppError(
                code="checkout.rail_not_allowed",
                message="Zamtel mobile money is not available yet",
                http_status=422,
                details={"rail": rail, "allowed_rails": sorted(ALLOWED_MOMO_RAILS)},
            )
        if rail not in ALLOWED_MOMO_RAILS:
            raise AppError(
                code="checkout.rail_not_allowed",
                message="Mobile money rail is not supported",
                http_status=422,
                details={"rail": rail, "allowed_rails": sorted(ALLOWED_MOMO_RAILS)},
            )
        if not payer_number:
            raise AppError(
                code="checkout.payer_number_required",
                message="Payer mobile number is required for mobile money",
                http_status=422,
                details={"field": "payer_number"},
            )
        normalized = _normalize_payer_number(payer_number)
        if not _is_valid_payer_number(normalized):
            raise AppError(
                code="checkout.invalid_payer_number",
                message="Enter a valid Zambian mobile number starting with +260",
                http_status=422,
                details={"field": "payer_number"},
            )
        validated_rail: MomoRail = "mtn" if rail == "mtn" else "airtel"
        return validated_rail, normalized

    raise AppError(
        code="checkout.invalid_payment_method",
        message="Payment method is not supported",
        http_status=422,
        details={"method": method},
    )


@router.get("/steps/payment-options", response_model=PaymentOptionsResponse)
async def get_payment_options(
    session_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PaymentOptionsResponse:
    _ensure_session_active(service, session_id, current_user.id)
    group = _fetch_checkout_group(service, session_id, current_user.id)
    subtotal, delivery_fee, total = _session_totals(group)
    cod_cap = _load_cod_cap_ngwee(service)

    return PaymentOptionsResponse(
        session_id=session_id,
        subtotal_ngwee=subtotal,
        delivery_fee_ngwee=delivery_fee,
        total_ngwee=total,
        cod_cap_ngwee=cod_cap,
        cod_eligible=total <= cod_cap,
    )


@router.post("/steps/payment", response_model=PaymentMethodResponse)
async def validate_payment_method(
    body: PaymentMethodRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PaymentMethodResponse:
    _ensure_session_active(service, body.session_id, current_user.id)
    group = _fetch_checkout_group(service, body.session_id, current_user.id)
    subtotal, delivery_fee, total = _session_totals(group)
    cod_cap = _load_cod_cap_ngwee(service)

    rail_value = body.rail
    validated_rail, validated_payer = _validate_payment_method(
        method=body.method,
        rail=rail_value,
        payer_number=body.payer_number,
        total_ngwee=total,
        cod_cap_ngwee=cod_cap,
    )

    return PaymentMethodResponse(
        session_id=body.session_id,
        method=body.method,
        rail=validated_rail,
        payer_number=validated_payer,
        subtotal_ngwee=subtotal,
        delivery_fee_ngwee=delivery_fee,
        total_ngwee=total,
        cod_cap_ngwee=cod_cap,
        cod_eligible=total <= cod_cap,
    )
