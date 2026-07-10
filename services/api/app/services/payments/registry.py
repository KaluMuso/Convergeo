"""Payment provider registry — name → strategy lookup."""

from __future__ import annotations

from app.services.payments.base import PaymentProviderError, PaymentStrategy
from app.services.payments.lenco.client import LencoStrategy

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


register(LENCO_PROVIDER, LencoStrategy())
