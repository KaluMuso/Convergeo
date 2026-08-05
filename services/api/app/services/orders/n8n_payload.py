"""Build n8n webhook payloads for order lifecycle events."""

from __future__ import annotations

from typing import Any

from app.services.orders.create import CreatedOrder


def mask_phone_e164(phone: str) -> str:
    """Mask a phone for outbound webhooks — last 3 digits visible."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 4:
        return phone
    visible = digits[-3:]
    country = digits[:3] if len(digits) > 9 else digits[:2]
    return f"+{country} ••• ••{visible}"


def mask_display_name(name: str | None) -> str | None:
    if not name or not name.strip():
        return None
    trimmed = name.strip()
    if len(trimmed) == 1:
        return "*"
    return f"{trimmed[0]}***"


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    return None


def load_customer_mask(client: Any, customer_id: str) -> dict[str, Any]:
    response = (
        client.table("profiles")
        .select("phone, display_name")
        .eq("id", customer_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    phone = str(row.get("phone") or "") if row else ""
    display_name = row.get("display_name") if row else None
    masked: dict[str, Any] = {"id": customer_id}
    if phone:
        masked["masked_phone"] = mask_phone_e164(phone)
    masked_name = mask_display_name(display_name if isinstance(display_name, str) else None)
    if masked_name:
        masked["masked_name"] = masked_name
    return masked


def build_order_created_payload(
    *,
    order: CreatedOrder,
    checkout_group_id: str,
    customer: dict[str, Any],
) -> dict[str, Any]:
    items = [
        {
            "order_item_id": item.order_item_id,
            "listing_id": item.listing_id,
            "qty": item.qty,
            "unit_price_ngwee": item.unit_price_ngwee,
            "line_total_ngwee": item.line_total_ngwee,
        }
        for item in order.items
    ]
    return {
        "order_id": order.order_id,
        "checkout_group_id": checkout_group_id,
        "vendor_id": order.vendor_id,
        "fulfilment": order.fulfilment,
        "cod": order.cod,
        "subtotal_ngwee": order.subtotal_ngwee,
        "delivery_fee_ngwee": order.delivery_fee_ngwee,
        "customer": customer,
        "items": items,
    }
