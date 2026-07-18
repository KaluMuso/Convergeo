"""Thin cart funnel emitters — call from cart/checkout hooks.

Each emitter is fire-and-forget (``record_event_best_effort`` swallows every error),
so a funnel write can never break the cart/checkout request that triggered it. These
are server operational events: written regardless of analytics consent, anonymized.
"""

from __future__ import annotations

from typing import Any

from app.services.analytics.funnel import record_event_best_effort


def emit_cart_add(
    *,
    checkout_group_id: str | None,
    customer_id: str | None,
    snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    """Record cart_add funnel stage (pre-checkout when group is absent)."""
    return record_event_best_effort(
        stage="cart_add",
        checkout_group_id=checkout_group_id,
        customer_id=customer_id,
        snapshot=snapshot,
    )


def emit_checkout_start(
    *,
    checkout_group_id: str,
    customer_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    """Record checkout_start when a checkout session is created."""
    return record_event_best_effort(
        stage="checkout_start",
        checkout_group_id=checkout_group_id,
        customer_id=customer_id,
        snapshot=snapshot,
    )


def emit_step_complete(
    *,
    checkout_group_id: str,
    customer_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    """Record step_complete for a checkout step transition."""
    return record_event_best_effort(
        stage="step_complete",
        checkout_group_id=checkout_group_id,
        customer_id=customer_id,
        snapshot=snapshot,
    )
