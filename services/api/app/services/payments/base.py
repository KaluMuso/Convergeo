"""Payment provider strategy interface and shared DTOs."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from app.schemas.base import (
    NgweeInt,
    OrderReference,
    PaymentReference,
    RefundReference,
    StrictModel,
)


class CollectionStatus(StrEnum):
    PENDING = "pending"
    PAY_OFFLINE = "pay-offline"
    SUCCESSFUL = "successful"
    FAILED = "failed"


class TransferStatus(StrEnum):
    PENDING = "pending"
    SUCCESSFUL = "successful"
    FAILED = "failed"


class InitiateCollectionRequest(StrictModel):
    reference: OrderReference
    amount_ngwee: NgweeInt
    currency: str = "ZMW"
    phone: str
    operator: str
    country: str = "zm"
    bearer: str = "merchant"


class InitiateCollectionResult(StrictModel):
    provider_reference: str | None = None
    status: CollectionStatus
    amount_major: str
    currency: str = "ZMW"
    raw: dict[str, Any] | None = None


class QueryStatusRequest(StrictModel):
    reference: str


class QueryStatusResult(StrictModel):
    reference: str
    status: str
    amount_major: str
    currency: str = "ZMW"
    provider_reference: str | None = None
    raw: dict[str, Any] | None = None


class InitiatePayoutRequest(StrictModel):
    reference: PaymentReference | RefundReference
    amount_ngwee: NgweeInt
    currency: str = "ZMW"
    account_id: str
    narration: str | None = None


class InitiatePayoutResult(StrictModel):
    provider_reference: str | None = None
    status: TransferStatus
    amount_major: str
    currency: str = "ZMW"
    raw: dict[str, Any] | None = None


class ResolveAccountRequest(StrictModel):
    phone: str
    operator: str
    country: str = "zm"


class ResolveAccountResult(StrictModel):
    account_name: str
    raw: dict[str, Any] | None = None


class VerifyWebhookRequest(StrictModel):
    raw_body: bytes
    signature: str


class VerifyWebhookResult(StrictModel):
    valid: bool
    event_id: str | None = None


class PaymentProviderError(Exception):
    """Typed error from the payment provider layer."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@runtime_checkable
class PaymentStrategy(Protocol):
    """Provider-agnostic payment seam (Lenco first; others via registry)."""

    async def initiate_collection(
        self,
        request: InitiateCollectionRequest,
    ) -> InitiateCollectionResult:
        """Start a collection (USSD push, card widget session, etc.)."""

    async def query_status(self, request: QueryStatusRequest) -> QueryStatusResult:
        """Poll provider status by our client reference."""

    async def initiate_payout(self, request: InitiatePayoutRequest) -> InitiatePayoutResult:
        """Execute a payout transfer."""

    async def resolve_account(self, request: ResolveAccountRequest) -> ResolveAccountResult:
        """Resolve a mobile-money account name before payout."""

    async def verify_webhook(self, request: VerifyWebhookRequest) -> VerifyWebhookResult:
        """Verify an inbound webhook signature on the raw body."""
