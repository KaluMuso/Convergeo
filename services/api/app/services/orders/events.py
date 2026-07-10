"""Thin order-lifecycle emitter: resolve recipient by audience, then emit."""

from __future__ import annotations

from typing import Any

from app.services.analytics.funnel import record_event
from app.services.notifications.events import (
    EVENT_REGISTRY,
    Audience,
    emit_event,
)

# Money fields (integer ngwee) copied into the notification payload when present.
_MONEY_KEYS: tuple[str, ...] = (
    "total_ngwee",
    "amount_ngwee",
    "delivery_fee_ngwee",
)


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _resolve_vendor_owner(client: Any, vendor_id: str) -> str | None:
    response = (
        client.table("vendors")
        .select("owner_user_id")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None
    owner = row.get("owner_user_id")
    return str(owner) if owner else None


def _resolve_recipient(
    client: Any,
    *,
    audience: Audience,
    order_row: dict[str, Any],
) -> str | None:
    if audience is Audience.VENDOR:
        vendor_id = order_row.get("vendor_id")
        if not vendor_id:
            return None
        return _resolve_vendor_owner(client, str(vendor_id))
    customer_id = order_row.get("customer_id")
    return str(customer_id) if customer_id else None


def emit_order_lifecycle(
    client: Any,
    *,
    event: str,
    order_row: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Emit the notification for an order lifecycle event, or ``None`` if silent."""
    mapping = EVENT_REGISTRY.get(event)
    if mapping is None:
        # Silent (documented) event returns None; an unknown event raises
        # ValueError inside emit_event (recipient/payload unused when silent).
        return emit_event(
            client,
            event=event,
            entity_id=str(order_row.get("id", "")),
            recipient_id="",
            payload={},
        )

    order_id = str(order_row.get("id", ""))
    recipient_id = _resolve_recipient(client, audience=mapping.audience, order_row=order_row)
    if not recipient_id:
        return None

    payload: dict[str, Any] = {
        "order_id": order_id,
        "order_reference": str(order_row.get("reference") or order_row.get("id") or ""),
    }
    for key in _MONEY_KEYS:
        value = order_row.get(key)
        if isinstance(value, int):
            payload[key] = value
    if extra:
        payload.update(extra)

    return emit_event(
        client,
        event=event,
        entity_id=order_id,
        recipient_id=recipient_id,
        payload=payload,
    )


def emit_payment_start_funnel(
    *,
    checkout_group_id: str,
    customer_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    """Record payment_start when the customer initiates payment."""
    return record_event(
        stage="payment_start",
        checkout_group_id=checkout_group_id,
        customer_id=customer_id,
        snapshot=snapshot,
    )


def emit_order_placed_funnel(
    *,
    checkout_group_id: str,
    customer_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    """Record order_placed when checkout completes into orders."""
    return record_event(
        stage="order_placed",
        checkout_group_id=checkout_group_id,
        customer_id=customer_id,
        snapshot=snapshot,
    )
