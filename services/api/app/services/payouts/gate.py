"""Safe-by-default payout kill switch.

Blocks all vendor payout execution (batch cron, manual execute, retry sweeper
send path) unless payouts are explicitly enabled for the current environment.
The default — no configuration — is DISABLED.

Environment contract (names only — values are never read for content or logged):

    ``PAYOUTS_ENABLED`` truthy to permit payout execution (default: unset -> disabled)
"""

from __future__ import annotations

import logging
import os

from app.errors import AppError

PAYOUTS_ENABLED_ENV = "PAYOUTS_ENABLED"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

logger = logging.getLogger(__name__)

# Secondary safety: minimum time funds must remain in escrow after collection
# before a payout may execute (D5 settlement promise / sandbox drill guard).
MIN_ESCROW_HOLD_HOURS = 48


def _is_truthy(env_name: str) -> bool:
    return os.environ.get(env_name, "").strip().lower() in _TRUTHY


def payouts_enabled() -> bool:
    """True only when payout execution is explicitly enabled for this env."""
    return _is_truthy(PAYOUTS_ENABLED_ENV)


class PayoutsDisabledError(AppError):
    """Raised when a payout is attempted while ``PAYOUTS_ENABLED`` is off."""

    def __init__(self) -> None:
        super().__init__(
            code="payouts_disabled",
            message=(
                "Vendor payouts are temporarily unavailable. "
                "Please try again later."
            ),
            http_status=503,
        )


def assert_payouts_enabled() -> None:
    """Raise :class:`PayoutsDisabledError` when the payout kill switch is off."""
    if not payouts_enabled():
        logger.warning(
            "payout_execution_blocked",
            extra={
                "event": "payout_execution_blocked",
                "reason_code": "disabled_by_default",
            },
        )
        raise PayoutsDisabledError()


def assert_payouts_execution_allowed() -> None:
    """Enforce both payout kill switches before any provider-facing work."""
    from app.core.env_guards import payouts_suppressed

    assert_payouts_enabled()
    if payouts_suppressed():
        raise AppError(
            code="payouts_suppressed_on_staging",
            message=(
                "Payouts are suppressed on staging. "
                "Set STAGING_ALLOW_PAYOUTS=true only for sandbox drills."
            ),
            http_status=503,
        )
