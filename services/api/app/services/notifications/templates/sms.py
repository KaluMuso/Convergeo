"""Per-event SMS body rendering for the Africa's Talking fallback channel.

Mirrors the WhatsApp template registry: one renderer per notification template id,
producing a short plain-text body from the outbox payload (the same payload the
WhatsApp template used). Used when a WhatsApp send fails over to SMS. Bodies are
kept link-free and concise; the adapter GSM-7-truncates to a single segment.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.services.payments.money import ngwee_to_major_str


def _text(payload: Mapping[str, Any], key: str, default: str = "") -> str:
    value = payload.get(key)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _amount(payload: Mapping[str, Any], *keys: str) -> str:
    """First present integer-ngwee field → major-unit string (e.g. '1,234.56')."""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, int):
            return ngwee_to_major_str(value)
    return "0.00"


def _order_confirmed(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    return (
        f"Vergeo5: order {ref} is confirmed. Total K{_amount(p, 'total_ngwee', 'amount_ngwee')}. "
        "Your money is held safely by Vergeo5 until delivery."
    )


def _payment_received(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    return (
        f"Vergeo5: payment of K{_amount(p, 'amount_ngwee', 'total_ngwee')} received for order "
        f"{ref}. Held safely by Vergeo5 until delivery."
    )


def _order_shipped(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    info = _text(p, "tracking_info")
    return f"Vergeo5: order {ref} is on its way.{(' ' + info) if info else ''}"


def _order_ready_pickup(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    details = _text(p, "pickup_details")
    return f"Vergeo5: order {ref} is ready for pickup.{(' ' + details) if details else ''}"


def _order_delivered(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    return f"Vergeo5: order {ref} was delivered. Thank you for shopping with Vergeo5!"


def _vendor_new_order(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "a new order")
    title = _text(p, "product_title", "an item")
    qty = _text(p, "quantity", "1")
    return f"Vergeo5: new order {ref} — {qty} x {title}. Open the vendor app to accept it."


def _rfq_job_broadcast(p: Mapping[str, Any]) -> str:
    category = _text(p, "category", "a job")
    area = _text(p, "service_area", "your area")
    return f"Vergeo5: a customer needs {category} near {area}. Open Vergeo5 to send a quote."


def _event_cancelled(p: Mapping[str, Any]) -> str:
    title = _text(p, "event_title", "your event")
    event_date = _text(p, "event_date", "the scheduled date")
    refund_detail = _text(p, "refund_detail")
    return f'Vergeo5: "{title}" on {event_date} cancelled. {refund_detail}'.strip()


def _event_schedule_changed(p: Mapping[str, Any]) -> str:
    title = _text(p, "event_title", "your event")
    event_date = _text(p, "event_date", "a new date")
    return f'Vergeo5: "{title}" rescheduled to {event_date}. Check the app for details.'


SMS_TEMPLATES: dict[str, Callable[[Mapping[str, Any]], str]] = {
    "order_confirmed": _order_confirmed,
    "payment_received": _payment_received,
    "order_shipped": _order_shipped,
    "order_ready_pickup": _order_ready_pickup,
    "order_delivered": _order_delivered,
    "vendor_new_order": _vendor_new_order,
    "rfq_job_broadcast": _rfq_job_broadcast,
    "event_cancelled": _event_cancelled,
    "event_schedule_changed": _event_schedule_changed,
}


def render_sms_body(template: str | None, payload: Mapping[str, Any]) -> str | None:
    """Render the SMS body for a template id, or None when unregistered/empty."""
    if not template:
        return None
    renderer = SMS_TEMPLATES.get(template)
    if renderer is None:
        return None
    body = renderer(payload).strip()
    return body or None
