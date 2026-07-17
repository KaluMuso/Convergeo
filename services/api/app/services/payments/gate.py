"""Safe-by-default payment kill switch.

Blocks all Lenco payment *initiation* (mobile money + card) unless payments are
explicitly enabled for the current environment. The default — no configuration —
is DISABLED. Cash on delivery (COD) is never gated here: it moves no money
through an external provider at initiation.

Environment contract (names only — values are never read for content or logged):

- ``PAYMENTS_ENABLED``          truthy to attempt enabling (default: unset -> disabled)
- ``PAYMENTS_ALLOW_PRODUCTION`` truthy to permit live-production initiation
- ``LENCO_ENV`` (existing)      ``sandbox`` | ``production`` (default: production)

Enable matrix::

    PAYMENTS_ENABLED falsy/unset        -> (False, "disabled_by_default")
    enabled + sandbox                   -> (True,  "enabled_sandbox")
    enabled + production, no PROD ack    -> (False, "production_not_acknowledged")
    enabled + production + PROD ack      -> (True,  "enabled_production")

Two independent locks guard the live path and the default at every layer is off.
``lenco.config`` is imported lazily inside the functions to avoid an import cycle
(``lenco/__init__`` eagerly imports the client, which imports this module).
"""

from __future__ import annotations

import logging
import os

from app.errors import AppError

PAYMENTS_ENABLED_ENV = "PAYMENTS_ENABLED"
PAYMENTS_ALLOW_PRODUCTION_ENV = "PAYMENTS_ALLOW_PRODUCTION"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

logger = logging.getLogger(__name__)


def _is_truthy(env_name: str) -> bool:
    return os.environ.get(env_name, "").strip().lower() in _TRUTHY


def _lenco_env_value() -> str:
    # Lazy import: see module docstring (import-cycle avoidance).
    from app.services.payments.lenco.config import get_lenco_environment

    return get_lenco_environment().value


def payments_gate_status() -> tuple[bool, str]:
    """Return ``(enabled, reason_code)``.

    ``reason_code`` is a stable, non-PII label for logging/telemetry only. It is
    never returned to the client.
    """
    if not _is_truthy(PAYMENTS_ENABLED_ENV):
        return False, "disabled_by_default"
    if _lenco_env_value() == "sandbox":
        return True, "enabled_sandbox"
    if not _is_truthy(PAYMENTS_ALLOW_PRODUCTION_ENV):
        return False, "production_not_acknowledged"
    return True, "enabled_production"


def payments_enabled() -> bool:
    """True only when payment initiation is explicitly enabled for this env."""
    enabled, _reason = payments_gate_status()
    return enabled


class PaymentsDisabledError(AppError):
    """Raised when a Lenco payment initiation is attempted while payments are off.

    Subclasses :class:`AppError`, so it maps to a clean HTTP 503 via the handler
    registered in ``app.main`` with no additional wiring. The user-facing message
    reveals no configuration and points the shopper at COD.
    """

    def __init__(self) -> None:
        super().__init__(
            code="payments_disabled",
            message=(
                "Online payment is temporarily unavailable. Please use Cash on "
                "Delivery where available, or try again shortly."
            ),
            http_status=503,
        )


def log_payment_blocked(
    reason_code: str,
    *,
    method: str | None,
    reference: str | None,
) -> None:
    """Emit a structured, non-PII record that an initiation was blocked.

    Deliberately excludes payer phone, token, and amount — only the stable
    ``reason_code``, the rail/method label, our own ``reference`` (an encoded
    order/checkout id, not PII), and the Lenco environment name.
    """
    logger.warning(
        "payment_initiation_blocked",
        extra={
            "event": "payment_initiation_blocked",
            "reason_code": reason_code,
            "method": method,
            "reference": reference,
            "lenco_env": _lenco_env_value(),
        },
    )
