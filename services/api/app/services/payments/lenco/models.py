"""Typed Lenco API request/response contracts and error taxonomy."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, NoReturn

from app.schemas.base import NgweeInt, PaymentReference, RefundReference, StrictModel
from app.services.payments.base import PaymentProviderError

CollectionOperator = Literal["mtn", "airtel", "zamtel"]
PayoutOperator = Literal["mtn", "airtel", "zamtel"]
CollectionStatusValue = Literal[
    "pending",
    "pay-offline",
    "successful",
    "failed",
    "3ds-auth-required",
]
TransferStatusValue = Literal["pending", "successful", "failed"]


class LencoErrorCategory(StrEnum):
    """Mapped failure categories for callers (not bare provider strings)."""

    DECLINED = "declined"
    TIMEOUT = "timeout"
    INSUFFICIENT = "insufficient"
    INVALID_NUMBER = "invalid_number"
    PROVIDER_ERROR = "provider_error"


class LencoClientError(PaymentProviderError):
    """Typed Lenco client failure with a stable category code."""

    def __init__(self, category: LencoErrorCategory, message: str) -> None:
        self.category = category
        super().__init__(category.value, message)


# --- Collections ---


class LencoCollectionRequest(StrictModel):
    amount_major: str
    reference: str
    phone: str
    operator: CollectionOperator
    country: str = "zm"
    bearer: str = "merchant"


class LencoMobileMoneyDetails(StrictModel):
    country: str
    phone: str
    operator: str
    account_name: str | None = None
    operator_transaction_id: str | None = None


class LencoCollectionData(StrictModel):
    id: str
    initiated_at: str
    completed_at: str | None = None
    amount: str
    fee: str | None = None
    bearer: str
    currency: str
    reference: str
    lenco_reference: str
    type: str
    status: CollectionStatusValue
    source: str
    reason_for_failure: str | None = None
    settlement_status: str | None = None
    settlement: dict[str, Any] | None = None
    mobile_money_details: LencoMobileMoneyDetails | None = None
    bank_account_details: dict[str, Any] | None = None
    card_details: dict[str, Any] | None = None


class LencoCollectionResponse(StrictModel):
    status: bool
    message: str
    data: LencoCollectionData | None = None
    error_code: str | None = None


# --- Status query ---


class LencoCollectionStatusResponse(StrictModel):
    status: bool
    message: str
    data: LencoCollectionData | None = None
    error_code: str | None = None


# --- Resolve ---


class LencoResolveMobileMoneyRequest(StrictModel):
    phone: str
    operator: PayoutOperator
    country: str = "zm"


class LencoResolveMobileMoneyData(StrictModel):
    account_name: str


class LencoResolveMobileMoneyResponse(StrictModel):
    status: bool
    message: str
    data: LencoResolveMobileMoneyData | None = None
    error_code: str | None = None


class LencoResolveBankAccountRequest(StrictModel):
    account_number: str
    bank_id: str
    country: str = "zm"


class LencoResolveBankAccountData(StrictModel):
    account_name: str


class LencoResolveBankAccountResponse(StrictModel):
    status: bool
    message: str
    data: LencoResolveBankAccountData | None = None
    error_code: str | None = None


# --- Payouts ---


class LencoMomoPayoutRequest(StrictModel):
    reference: PaymentReference | RefundReference
    amount_ngwee: NgweeInt
    currency: str = "ZMW"
    account_id: str
    phone: str
    operator: PayoutOperator
    country: str = "zm"
    narration: str | None = None
    transfer_recipient_id: str | None = None


class LencoBankPayoutRequest(StrictModel):
    reference: PaymentReference | RefundReference
    amount_ngwee: NgweeInt
    currency: str = "ZMW"
    account_id: str
    account_number: str
    bank_id: str
    country: str = "zm"
    narration: str | None = None
    transfer_recipient_id: str | None = None


class LencoTransferData(StrictModel):
    id: str
    amount: str
    fee: str | None = None
    currency: str
    reference: str
    lenco_reference: str
    status: TransferStatusValue
    reason_for_failure: str | None = None
    narration: str | None = None
    credit_account: dict[str, Any] | None = None


class LencoTransferResponse(StrictModel):
    status: bool
    message: str
    data: LencoTransferData | None = None
    error_code: str | None = None


class LencoTransferStatusResponse(StrictModel):
    status: bool
    message: str
    data: LencoTransferData | None = None
    error_code: str | None = None


# --- Error envelope ---


class LencoErrorEnvelope(StrictModel):
    status: bool
    message: str
    data: dict[str, Any] | None = None
    error_code: str | None = None


_LENCO_ERROR_CODE_MAP: dict[str, LencoErrorCategory] = {
    "01": LencoErrorCategory.PROVIDER_ERROR,
    "02": LencoErrorCategory.INSUFFICIENT,
    "03": LencoErrorCategory.DECLINED,
    "04": LencoErrorCategory.PROVIDER_ERROR,
    "05": LencoErrorCategory.PROVIDER_ERROR,
    "06": LencoErrorCategory.DECLINED,
    "07": LencoErrorCategory.PROVIDER_ERROR,
    "08": LencoErrorCategory.PROVIDER_ERROR,
    "09": LencoErrorCategory.DECLINED,
    "10": LencoErrorCategory.PROVIDER_ERROR,
    "11": LencoErrorCategory.PROVIDER_ERROR,
    "12": LencoErrorCategory.INVALID_NUMBER,
    "13": LencoErrorCategory.DECLINED,
}

_TIMEOUT_MARKERS = frozenset(
    {
        "timeout",
        "timed out",
        "time out",
        "request timeout",
        "gateway timeout",
    }
)
_INSUFFICIENT_MARKERS = frozenset(
    {
        "insufficient",
        "insufficient funds",
        "not enough",
        "low balance",
    }
)
_INVALID_NUMBER_MARKERS = frozenset(
    {
        "invalid mobile",
        "invalid number",
        "invalid phone",
        "invalid msisdn",
    }
)
_DECLINED_MARKERS = frozenset(
    {
        "declined",
        "failed",
        "unauthorized",
        "wrong pin",
        "payment invalid",
        "limit exceeded",
        "denied",
        "rejected",
    }
)


def map_lenco_failure(
    *,
    error_code: str | None = None,
    message: str | None = None,
    reason_for_failure: str | None = None,
    http_status: int | None = None,
    timed_out: bool = False,
) -> LencoErrorCategory:
    """Map a Lenco failure to the stable error taxonomy."""
    if timed_out or http_status == 504:
        return LencoErrorCategory.TIMEOUT

    if error_code:
        mapped = _LENCO_ERROR_CODE_MAP.get(error_code.strip())
        if mapped is not None:
            return mapped

    haystack = " ".join(
        part.lower()
        for part in (message, reason_for_failure)
        if isinstance(part, str) and part.strip()
    )
    if any(marker in haystack for marker in _TIMEOUT_MARKERS):
        return LencoErrorCategory.TIMEOUT
    if any(marker in haystack for marker in _INSUFFICIENT_MARKERS):
        return LencoErrorCategory.INSUFFICIENT
    if any(marker in haystack for marker in _INVALID_NUMBER_MARKERS):
        return LencoErrorCategory.INVALID_NUMBER
    if any(marker in haystack for marker in _DECLINED_MARKERS):
        return LencoErrorCategory.DECLINED
    return LencoErrorCategory.PROVIDER_ERROR


def raise_lenco_failure(
    *,
    error_code: str | None = None,
    message: str | None = None,
    reason_for_failure: str | None = None,
    http_status: int | None = None,
    timed_out: bool = False,
) -> NoReturn:
    raise lenco_failure(
        error_code=error_code,
        message=message,
        reason_for_failure=reason_for_failure,
        http_status=http_status,
        timed_out=timed_out,
    )


def lenco_failure(
    *,
    error_code: str | None = None,
    message: str | None = None,
    reason_for_failure: str | None = None,
    http_status: int | None = None,
    timed_out: bool = False,
) -> LencoClientError:
    category = map_lenco_failure(
        error_code=error_code,
        message=message,
        reason_for_failure=reason_for_failure,
        http_status=http_status,
        timed_out=timed_out,
    )
    detail = message or reason_for_failure or "Lenco request failed"
    return LencoClientError(category, detail)
