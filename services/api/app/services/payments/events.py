"""Thin payment-lifecycle emitter: resolve the paying customer, then emit."""

from __future__ import annotations

from typing import Any

from app.services.notifications.events import emit_event

# Money fields (integer ngwee) copied into the notification payload when present.
_MONEY_KEYS: tuple[str, ...] = ("amount_ngwee", "total_ngwee")


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _resolve_customer(client: Any, checkout_group_id: str) -> str | None:
    response = (
        client.table("checkout_groups")
        .select("customer_id")
        .eq("id", checkout_group_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None
    customer_id = row.get("customer_id")
    return str(customer_id) if customer_id else None


def emit_payment_lifecycle(
    client: Any,
    *,
    event: str,
    payment_row: dict[str, Any],
) -> dict[str, Any] | None:
    """Emit the customer-facing notification for a payment lifecycle event."""
    checkout_group_id = payment_row.get("checkout_group_id")
    if not checkout_group_id:
        return None
    recipient_id = _resolve_customer(client, str(checkout_group_id))
    if not recipient_id:
        return None

    payment_id = str(payment_row.get("id", ""))
    payload: dict[str, Any] = {
        "payment_id": payment_id,
        "checkout_group_id": str(checkout_group_id),
    }
    reference = payment_row.get("reference") or payment_row.get("order_reference")
    if reference:
        payload["order_reference"] = str(reference)
    for key in _MONEY_KEYS:
        value = payment_row.get(key)
        if isinstance(value, int):
            payload[key] = value

    return emit_event(
        client,
        event=event,
        entity_id=str(checkout_group_id),
        recipient_id=recipient_id,
        payload=payload,
    )
