"""Lifecycle → notification registry.

Single source of truth mapping every documented domain lifecycle event to the
notification (template + audience + channel) it emits — or to ``None`` when the
event is intentionally silent (no template built yet / no customer-facing
message). Keeping silent events as explicit keys makes coverage auditable: the
coverage test asserts that no documented event is missing from this registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.services.notifications.dedupe import enqueue_outbox_row


class Audience(StrEnum):
    CUSTOMER = "customer"
    VENDOR = "vendor"


@dataclass(frozen=True, slots=True)
class NotificationMapping:
    template: str
    audience: Audience
    channel: str = "whatsapp"


# Domain lifecycle event → mapping. ``None`` = intentionally silent (still an
# auditable coverage entry). Only templates that EXIST in the WhatsApp template
# registry are mapped; everything else stays ``None`` until its template ships.
EVENT_REGISTRY: dict[str, NotificationMapping | None] = {
    # --- Orders ---------------------------------------------------------
    "order_placed": NotificationMapping("vendor_new_order", Audience.VENDOR),
    "order_confirmed": NotificationMapping("order_confirmed", Audience.CUSTOMER),
    "order_processing": None,  # no "processing" template built yet
    "order_ready_pickup": NotificationMapping("order_ready_pickup", Audience.CUSTOMER),
    "order_shipped": NotificationMapping("order_shipped", Audience.CUSTOMER),
    "order_delivered": NotificationMapping("order_delivered", Audience.CUSTOMER),
    "order_completed": None,  # terminal-success is silent (already delivered)
    "order_cancelled": None,  # cancellation template not built yet
    # --- Payments -------------------------------------------------------
    "payment_received": NotificationMapping("payment_received", Audience.CUSTOMER),
    "payment_failed": None,  # payment-failed template not built yet
    "payout_sent": None,  # vendor payout template not built yet
    "payout_failed": None,  # vendor payout template not built yet
    # --- KYC ------------------------------------------------------------
    "kyc_approved": None,  # email-only path handled elsewhere; no WA template
    "kyc_rejected": None,  # email-only path handled elsewhere; no WA template
    # --- Disputes -------------------------------------------------------
    "dispute_opened": None,  # dispute templates not built yet
    "dispute_resolved": None,  # dispute templates not built yet
    # --- Events / ticketing --------------------------------------------
    "ticket_issued": None,  # ticket templates not built yet
    "ticket_transferred": None,  # ticket templates not built yet
    # --- Services / RFQ -------------------------------------------------
    "quote_received": None,  # quote templates not built yet
    "quote_accepted": None,  # quote templates not built yet
}


def documented_events() -> frozenset[str]:
    """All lifecycle event names the registry is aware of (mapped or silent)."""
    return frozenset(EVENT_REGISTRY)


def emit_event(
    client: Any,
    *,
    event: str,
    entity_id: str,
    recipient_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Enqueue the notification for a domain lifecycle event.

    Raises ``ValueError`` if the event is not a documented key (the coverage
    test relies on this). Returns ``None`` for silent (``None``-mapped) events
    and for dedupe collisions; otherwise returns the inserted outbox row.
    """
    if event not in EVENT_REGISTRY:
        msg = f"unmapped domain event: {event}"
        raise ValueError(msg)

    mapping = EVENT_REGISTRY[event]
    if mapping is None:
        return None

    return enqueue_outbox_row(
        client,
        event_type=event,
        entity_id=entity_id,
        channel=mapping.channel,
        template=mapping.template,
        payload={**payload, "recipient_id": recipient_id},
    )
