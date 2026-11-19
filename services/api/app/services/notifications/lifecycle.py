"""Best-effort lifecycle notifications, emitted AFTER the state change has committed.

Each ``notify_*`` helper loads the facts it needs, then enqueues through
``emit_event`` / ``emit_order_lifecycle`` (outbox, ``UNIQUE(dedupe_key)``), so a retry of
the same transition is an idempotent no-op. Every helper swallows and logs any failure:
a notification problem must never roll back or block an order, payment, payout, dispute
or ticket transition that already committed.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.services.notifications.events import emit_event
from app.services.orders.events import emit_order_lifecycle

logger = logging.getLogger(__name__)

_DISPUTE_RESOLUTION_COPY = {
    "resolved_refund": "We refunded you.",
    "resolved_release": "The order stands and the vendor was paid.",
    "resolved_partial": "A partial refund was agreed.",
    "rejected": "The dispute was closed without a refund.",
}


def _site() -> str:
    return os.environ.get("PUBLIC_SITE_URL", "https://vergeo5.com").rstrip("/")


def _short_ref(order_id: str) -> str:
    return str(order_id)[:8].upper()


def _service_client(client: Any | None) -> Any:
    if client is not None:
        return client
    from app.supabase_client import get_supabase_service_client

    return get_supabase_service_client().client


def _one(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _order_row(client: Any, order_id: str) -> dict[str, Any] | None:
    return _one(
        client.table("orders")
        .select("id, vendor_id, customer_id, total_ngwee")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )


def _emit_order_event(
    event: str,
    order_id: str,
    *,
    client: Any | None = None,
    entity_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    try:
        service = _service_client(client)
        row = _order_row(service, order_id)
        if row is None:
            return
        emit_order_lifecycle(
            service,
            event=event,
            order_row={**row, "reference": _short_ref(order_id)},
            extra=extra,
            entity_id=entity_id,
        )
    except Exception:
        logger.warning("notification %s failed for order %s", event, order_id, exc_info=True)


def notify_order_transition(order_id: str, to_status: str, *, client: Any | None = None) -> None:
    """order_cancelled / order_completed after the guarded transition committed."""
    if to_status == "cancelled":
        _emit_order_event("order_cancelled", order_id, client=client)
    elif to_status == "completed":
        _emit_order_event(
            "order_completed",
            order_id,
            client=client,
            extra={"order_url": f"{_site()}/en/account/orders/{order_id}"},
        )


def notify_payment_failed(payment_id: str, *, client: Any | None = None) -> None:
    """payment_failed to the paying customer; one per failed payment attempt."""
    try:
        service = _service_client(client)
        payment = _one(
            service.table("payments")
            .select("id, checkout_group_id, amount_ngwee")
            .eq("id", payment_id)
            .maybe_single()
            .execute()
        )
        if payment is None or not payment.get("checkout_group_id"):
            return
        group = _one(
            service.table("checkout_groups")
            .select("customer_id")
            .eq("id", str(payment["checkout_group_id"]))
            .maybe_single()
            .execute()
        )
        customer_id = group.get("customer_id") if group else None
        amount = payment.get("amount_ngwee")
        if not customer_id or not isinstance(amount, int):
            return
        emit_event(
            service,
            event="payment_failed",
            entity_id=payment_id,
            recipient_id=str(customer_id),
            payload={
                "payment_id": payment_id,
                "checkout_group_id": str(payment["checkout_group_id"]),
                "amount_ngwee": amount,
                "retry_url": f"{_site()}/en/account/orders",
            },
        )
    except Exception:
        logger.warning("payment_failed notification failed for %s", payment_id, exc_info=True)


def _destination_label(vendor: dict[str, Any]) -> str:
    msisdn = str(vendor.get("payout_msisdn") or "")
    rail = str(vendor.get("payout_rail") or "").strip().upper()
    digits = "".join(ch for ch in msisdn if ch.isdigit())
    if len(digits) >= 4:
        return f"{rail + ' ' if rail else ''}number ending {digits[-4:]}"
    return "mobile money number"


def notify_vendor_payout(payout_id: str, *, sent: bool, client: Any | None = None) -> None:
    """payout_sent / payout_failed to the vendor owner. Customer refund payouts are skipped."""
    try:
        service = _service_client(client)
        payout = _one(
            service.table("payouts")
            .select("id, vendor_id, amount_ngwee, resolve_snapshot")
            .eq("id", payout_id)
            .maybe_single()
            .execute()
        )
        if payout is None:
            return
        snapshot = payout.get("resolve_snapshot")
        if isinstance(snapshot, dict) and snapshot.get("kind") == "customer_refund":
            return
        amount = payout.get("amount_ngwee")
        if not payout.get("vendor_id") or not isinstance(amount, int):
            return
        vendor = _one(
            service.table("vendors")
            .select("owner_user_id, payout_msisdn, payout_rail")
            .eq("id", str(payout["vendor_id"]))
            .maybe_single()
            .execute()
        )
        owner = vendor.get("owner_user_id") if vendor else None
        if vendor is None or not owner:
            return
        payload: dict[str, Any] = {
            "payout_id": payout_id,
            "vendor_id": str(payout["vendor_id"]),
            "amount_ngwee": amount,
        }
        if sent:
            payload["destination_label"] = _destination_label(vendor)
        emit_event(
            service,
            event="payout_sent" if sent else "payout_failed",
            entity_id=payout_id,
            recipient_id=str(owner),
            payload=payload,
        )
    except Exception:
        logger.warning("payout notification failed for %s", payout_id, exc_info=True)


def notify_dispute_opened(dispute_id: str, order_id: str, *, client: Any | None = None) -> None:
    _emit_order_event("dispute_opened", order_id, client=client, entity_id=dispute_id)


def notify_dispute_resolved(
    dispute_id: str, order_id: str, status: str, *, client: Any | None = None
) -> None:
    _emit_order_event(
        "dispute_resolved",
        order_id,
        client=client,
        entity_id=dispute_id,
        extra={"resolution_summary": _DISPUTE_RESOLUTION_COPY.get(status, "")}
        if status in _DISPUTE_RESOLUTION_COPY
        else None,
    )


def notify_tickets_issued(order_id: str, event_title: str, *, client: Any | None = None) -> None:
    """ticket_issued: one message per order (dedupe entity = order id)."""
    _emit_order_event(
        "ticket_issued",
        order_id,
        client=client,
        extra={
            "event_title": event_title or "your event",
            "ticket_url": f"{_site()}/en/account/tickets",
        },
    )


__all__ = [
    "notify_dispute_opened",
    "notify_dispute_resolved",
    "notify_order_transition",
    "notify_payment_failed",
    "notify_tickets_issued",
    "notify_vendor_payout",
]
