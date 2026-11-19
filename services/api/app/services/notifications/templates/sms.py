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
        f"Convergeo: order {ref} is confirmed. Total K{_amount(p, 'total_ngwee', 'amount_ngwee')}. "
        "Your money is held safely by Convergeo until delivery."
    )


def _payment_received(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    return (
        f"Convergeo: payment of K{_amount(p, 'amount_ngwee', 'total_ngwee')} received for order "
        f"{ref}. Held safely by Convergeo until delivery."
    )


def _order_shipped(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    info = _text(p, "tracking_info")
    return f"Convergeo: order {ref} is on its way.{(' ' + info) if info else ''}"


def _order_ready_pickup(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    details = _text(p, "pickup_details")
    return f"Convergeo: order {ref} is ready for pickup.{(' ' + details) if details else ''}"


def _order_delivered(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    return f"Convergeo: order {ref} was delivered. Thank you for shopping with Convergeo!"


def _vendor_new_order(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "a new order")
    title = _text(p, "product_title", "an item")
    qty = _text(p, "quantity", "1")
    return f"Convergeo: new order {ref} — {qty} x {title}. Open the vendor app to accept it."


def _rfq_job_broadcast(p: Mapping[str, Any]) -> str:
    category = _text(p, "category", "a job")
    area = _text(p, "service_area", "your area")
    return f"Convergeo: a customer needs {category} near {area}. Open Convergeo to send a quote."


def _service_quote_accepted(p: Mapping[str, Any]) -> str:
    deposit = _amount(p, "deposit_ngwee")
    total = _amount(p, "total_job_ngwee")
    return (
        f"Convergeo: your quote was accepted! Deposit of K{deposit} (job total K{total}) "
        "is secured in Convergeo escrow. Open Convergeo to start the job."
    )


def _event_cancelled(p: Mapping[str, Any]) -> str:
    title = _text(p, "event_title", "your event")
    event_date = _text(p, "event_date", "the scheduled date")
    refund_detail = _text(p, "refund_detail")
    return f'Convergeo: "{title}" on {event_date} cancelled. {refund_detail}'.strip()


def _event_schedule_changed(p: Mapping[str, Any]) -> str:
    title = _text(p, "event_title", "your event")
    event_date = _text(p, "event_date", "see the app")
    venue = _text(p, "venue", "see the app")
    return (
        f'Convergeo: "{title}" details updated. Date: {event_date}. Venue: {venue}. '
        "Check the app for details."
    )


def _courier_dispatch_request(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "a delivery")
    pickup = _text(p, "pickup_line", "see WhatsApp")
    cod = _text(p, "cod_line", "")
    return f"Convergeo job {ref}. Pickup: {pickup}. {cod}".strip()


def _dispatch_stale_alert(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "a dispatch")
    courier = _text(p, "courier_name", "the courier")
    minutes = _text(p, "minutes_waiting", "45")
    return f"Convergeo ops: {ref} with {courier} not accepted after {minutes} min."


def _order_cancelled(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    return f"Convergeo: order {ref} was cancelled. If you paid, we will handle your refund."


def _payment_failed(p: Mapping[str, Any]) -> str:
    amount = _amount(p, "amount_ngwee", "total_ngwee")
    return f"Convergeo: your payment of K{amount} did not go through. Open the app to try again."


def _order_completed(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    return f"Convergeo: order {ref} is complete. Thank you for shopping with us!"


def _ticket_issued(p: Mapping[str, Any]) -> str:
    title = _text(p, "event_title", "your event")
    return f'Convergeo: your ticket for "{title}" is ready. Open My tickets to show the QR.'


def _dispute_opened(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "an order")
    return f"Convergeo: a dispute was opened on order {ref}. Open the vendor app to respond."


def _dispute_resolved(p: Mapping[str, Any]) -> str:
    ref = _text(p, "order_reference", "your order")
    return f"Convergeo: the dispute on order {ref} is resolved. Open the app to see the outcome."


def _payout_sent(p: Mapping[str, Any]) -> str:
    amount = _amount(p, "amount_ngwee")
    dest = _text(p, "destination_label", "mobile money number")
    return f"Convergeo: your payout of K{amount} is on its way to your {dest}."


def _payout_failed(p: Mapping[str, Any]) -> str:
    amount = _amount(p, "amount_ngwee")
    return (
        f"Convergeo: your payout of K{amount} could not be sent. "
        "Check your payout number in the vendor app."
    )


def _rfq_quoted(p: Mapping[str, Any]) -> str:
    price = _amount(p, "quote_price_ngwee")
    return f"Convergeo: you received a quote of K{price}. Open the app to review it."


def _gift_recipient_notice(p: Mapping[str, Any]) -> str:
    sender = _text(p, "sender_name", "A friend")
    shop = _text(p, "shop_name", "a shop")
    return (
        f"Convergeo: {sender} sent you a gift from {shop}. We will message you about "
        "delivery or pickup only. Reply STOP to opt out."
    )


def _gift_ready_pickup(p: Mapping[str, Any]) -> str:
    shop = _text(p, "shop_name", "the shop")
    pin = _text(p, "pickup_pin")
    return f"Convergeo: your gift is ready to collect at {shop}. Pickup PIN {pin}. Do not share it."


def _birthday_greeting(p: Mapping[str, Any]) -> str:
    code = _text(p, "coupon_code")
    days = _text(p, "valid_days", "14")
    return (
        f"Convergeo: happy birthday! Use code {code} for K{_amount(p, 'amount_ngwee')} off "
        f"orders of K{_amount(p, 'min_spend_ngwee')} or more, valid {days} days. "
        "Reply STOP to opt out."
    )


SMS_TEMPLATES: dict[str, Callable[[Mapping[str, Any]], str]] = {
    "order_confirmed": _order_confirmed,
    "payment_received": _payment_received,
    "order_shipped": _order_shipped,
    "order_ready_pickup": _order_ready_pickup,
    "order_delivered": _order_delivered,
    "vendor_new_order": _vendor_new_order,
    "rfq_job_broadcast": _rfq_job_broadcast,
    "rfq_quoted": _rfq_quoted,
    "service_quote_accepted": _service_quote_accepted,
    "event_cancelled": _event_cancelled,
    "event_schedule_changed": _event_schedule_changed,
    "courier_dispatch_request": _courier_dispatch_request,
    "dispatch_stale_alert": _dispatch_stale_alert,
    "order_cancelled": _order_cancelled,
    "payment_failed": _payment_failed,
    "order_completed": _order_completed,
    "ticket_issued": _ticket_issued,
    "dispute_opened": _dispute_opened,
    "dispute_resolved": _dispute_resolved,
    "payout_sent": _payout_sent,
    "payout_failed": _payout_failed,
    "gift_recipient_notice": _gift_recipient_notice,
    "gift_ready_pickup": _gift_ready_pickup,
    "birthday_greeting": _birthday_greeting,
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
