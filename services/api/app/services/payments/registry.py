"""Payment provider registry — name → strategy lookup."""

from __future__ import annotations

from app.services.payments.base import (
    InitiateCollectionRequest,
    InitiateCollectionResult,
    InitiatePayoutRequest,
    InitiatePayoutResult,
    PaymentProviderError,
    PaymentStrategy,
    QueryStatusRequest,
    QueryStatusResult,
    ResolveAccountRequest,
    ResolveAccountResult,
    VerifyWebhookRequest,
    VerifyWebhookResult,
)

LENCO_PROVIDER = "lenco"

_REGISTRY: dict[str, PaymentStrategy] = {}


class UnknownProviderError(PaymentProviderError):
    """Raised when no strategy is registered for the requested provider."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__("unknown_provider", f"unknown provider: {provider}")


def register(provider: str, strategy: PaymentStrategy) -> None:
    """Register a payment strategy under a provider name."""
    _REGISTRY[provider] = strategy


def get(provider: str) -> PaymentStrategy:
    """Return the registered strategy or raise UnknownProviderError."""
    try:
        return _REGISTRY[provider]
    except KeyError as exc:
        raise UnknownProviderError(provider) from exc


class _LencoPlaceholderStrategy:
    """Registered by name only — real HTTP client lands in M08-P02."""

    async def initiate_collection(
        self,
        request: InitiateCollectionRequest,
    ) -> InitiateCollectionResult:
        raise NotImplementedError("Lenco client not implemented (M08-P02)")

    async def query_status(self, request: QueryStatusRequest) -> QueryStatusResult:
        raise NotImplementedError("Lenco client not implemented (M08-P02)")

    async def initiate_payout(self, request: InitiatePayoutRequest) -> InitiatePayoutResult:
        raise NotImplementedError("Lenco client not implemented (M08-P02)")

    async def resolve_account(self, request: ResolveAccountRequest) -> ResolveAccountResult:
        raise NotImplementedError("Lenco client not implemented (M08-P02)")

    async def verify_webhook(self, request: VerifyWebhookRequest) -> VerifyWebhookResult:
        raise NotImplementedError("Lenco client not implemented (M08-P02)")


register(LENCO_PROVIDER, _LencoPlaceholderStrategy())
