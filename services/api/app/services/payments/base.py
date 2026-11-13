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
from pydantic import model_validator


class CollectionStatus(StrEnum):
    PENDING = "pending"
    PAY_OFFLINE = "pay-offline"
    SUCCESSFUL = "successful"
    FAILED = "failed"


class TransferStatus(StrEnum):
    PENDING = "pending"
    SUCCESSFUL = "successful"
    FAILED = "failed"


class ProviderOutcome(StrEnum):
    """Authoritative provider observation, separate from observation errors."""

    SUCCESSFUL = "successful"
    PENDING = "pending"
    FAILED = "failed"
    NOT_FOUND = "not_found"


class ProviderErrorKind(StrEnum):
    """Why no authoritative provider observation was available."""

    TRANSPORT = "transport"
    AUTHENTICATION = "authentication"
    INVALID_OBSERVATION = "invalid_observation"
    PROVIDER = "provider"


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


class ProviderResult(StrictModel):
    requested_reference: str | None = None
    outcome: ProviderOutcome | None = None
    reference: str | None = None
    status: str | None = None
    amount_major: str | None = None
    currency: str | None = "ZMW"
    provider_reference: str | None = None
    debit_account_id: str | None = None
    destination: dict[str, Any] | None = None
    failure_reason: str | None = None
    raw: dict[str, Any] | None = None

    @model_validator(mode="after")
    def derive_compatibility_fields(self) -> ProviderResult:
        """Keep existing result constructors valid while making provenance explicit."""
        if self.requested_reference is None:
            self.requested_reference = self.reference
        if self.outcome is None and self.status is not None:
            normalized = self.status.strip().lower()
            if normalized == "successful":
                self.outcome = ProviderOutcome.SUCCESSFUL
            elif normalized == "failed":
                self.outcome = ProviderOutcome.FAILED
            else:
                self.outcome = ProviderOutcome.PENDING
        return self


class InitiatePayoutRequest(StrictModel):
    reference: PaymentReference | RefundReference
    amount_ngwee: NgweeInt
    currency: str = "ZMW"
    account_id: str
    narration: str | None = None


class InitiatePayoutResult(StrictModel):
    reference: str | None = None
    provider_reference: str | None = None
    status: TransferStatus
    amount_major: str
    currency: str = "ZMW"
    debit_account_id: str | None = None
    destination: dict[str, Any] | None = None
    failure_reason: str | None = None
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


QueryStatusResult = ProviderResult


class PaymentProviderError(Exception):
    """Typed error from the payment provider layer."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        kind: ProviderErrorKind = ProviderErrorKind.PROVIDER,
        reference: str | None = None,
        observation_uncertain: bool = False,
        dispatch_may_have_succeeded: bool = False,
    ) -> None:
        self.code = code
        self.message = message
        self.kind = kind
        self.reference = reference
        self.observation_uncertain = observation_uncertain
        self.dispatch_may_have_succeeded = dispatch_may_have_succeeded
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
