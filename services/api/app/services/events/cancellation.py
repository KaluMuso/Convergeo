"""Organiser event cancellation side-effects (D3, approach b).

Cancelling an event does **not** move money automatically. It:

  1. flags each paid ticket order for admin mass-refund — the same
     ``audit_log`` signal the escrow sweep uses (``MASS_REFUND_FLAG_ACTION``),
     written immediately at cancel time so the admin refund queue is populated
     now rather than lazily on the sweep's next run; and
  2. notifies every affected buyer and current ticket holder that the event was
     cancelled.

An admin then executes each refund payout via ``services.refunds.execute_refund``
(untouched), so outbound money stays behind a human gate. The escrow sweep
continues to block organiser release for cancelled events and de-dupes against
the same flag, so a failure here is recovered on the next sweep.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.services.escrow.event_release import MASS_REFUND_FLAG_ACTION
from app.services.notifications.events import emit_event
from app.services.orders.state import SYSTEM_ACTOR_ID

EVENT_CANCELLED_EVENT = "event_cancelled"
_SOLD_TICKET_STATUSES = frozenset({"issued", "checked_in"})


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class EventCancellationResult:
    orders_flagged: int
    recipients_notified: int


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _instance_ids(client: Any, event_id: str) -> list[str]:
    resp = client.table("event_instances").select("id").eq("event_id", event_id).execute()
    return [str(row["id"]) for row in _rows(resp) if row.get("id")]


def _format_event_date(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return ""
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return raw.strip()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%d %b %Y, %H:%M UTC")


def _earliest_event_date(client: Any, instance_ids: list[str]) -> str:
    if not instance_ids:
        return ""
    resp = (
        client.table("event_instances")
        .select("starts_at")
        .in_("id", instance_ids)
        .order("starts_at")
        .limit(1)
        .execute()
    )
    rows = _rows(resp)
    if not rows:
        return ""
    return _format_event_date(rows[0].get("starts_at"))


def _refund_detail(refund_status: str) -> str:
    if refund_status == "pending":
        return "Your payment refund is being processed by Vergeo5."
    return "No payment was found on your account for this event."


def _holder_ids(client: Any, instance_ids: list[str]) -> set[str]:
    if not instance_ids:
        return set()
    resp = (
        client.table("tickets")
        .select("holder_user_id, status")
        .in_("instance_id", instance_ids)
        .execute()
    )
    return {
        str(row["holder_user_id"])
        for row in _rows(resp)
        if row.get("holder_user_id") and str(row.get("status") or "") in _SOLD_TICKET_STATUSES
    }


def _paid_orders(client: Any, instance_ids: list[str]) -> list[tuple[str, str]]:
    """[(order_id, customer_id)] for ticket orders on this event with a paid checkout."""
    if not instance_ids:
        return []
    oit = (
        client.table("order_item_tickets")
        .select("order_item_id, instance_id")
        .in_("instance_id", instance_ids)
        .execute()
    )
    order_item_ids = sorted({str(r["order_item_id"]) for r in _rows(oit) if r.get("order_item_id")})
    if not order_item_ids:
        return []
    oi = client.table("order_items").select("id, order_id").in_("id", order_item_ids).execute()
    order_ids = sorted({str(r["order_id"]) for r in _rows(oi) if r.get("order_id")})
    if not order_ids:
        return []
    orders = _rows(
        client.table("orders")
        .select("id, customer_id, checkout_group_id")
        .in_("id", order_ids)
        .execute()
    )
    group_ids = sorted({str(r["checkout_group_id"]) for r in orders if r.get("checkout_group_id")})
    paid_groups: set[str] = set()
    if group_ids:
        pays = (
            client.table("payments")
            .select("checkout_group_id, status")
            .in_("checkout_group_id", group_ids)
            .execute()
        )
        paid_groups = {
            str(r["checkout_group_id"])
            for r in _rows(pays)
            if str(r.get("status") or "") == "success"
        }
    return [
        (str(o["id"]), str(o.get("customer_id") or ""))
        for o in orders
        if str(o.get("checkout_group_id") or "") in paid_groups
    ]


def _already_flagged(client: Any, order_id: str) -> bool:
    resp = (
        client.table("audit_log")
        .select("id")
        .eq("entity_type", "order")
        .eq("entity_id", order_id)
        .eq("action", MASS_REFUND_FLAG_ACTION)
        .execute()
    )
    return bool(_rows(resp))


def _flag_refund(client: Any, *, order_id: str, event_id: str) -> bool:
    """Write the admin mass-refund flag for an order (idempotent). Returns True if new."""
    if _already_flagged(client, order_id):
        return False
    client.table("audit_log").insert(
        {
            "actor": SYSTEM_ACTOR_ID,
            "action": MASS_REFUND_FLAG_ACTION,
            "entity_type": "order",
            "entity_id": order_id,
            "before": None,
            "after": {"event_id": event_id, "order_id": order_id, "reason": "event_cancelled"},
        }
    ).execute()
    return True


def _notify(
    client: Any,
    *,
    event_id: str,
    event_title: str,
    event_date: str,
    recipient_id: str,
    refund_status: str,
) -> None:
    emit_event(
        client,
        event=EVENT_CANCELLED_EVENT,
        entity_id=f"{event_id}:{recipient_id}",
        recipient_id=recipient_id,
        payload={
            "event_id": event_id,
            "event_title": event_title,
            "event_date": event_date,
            "refund_status": refund_status,
            "refund_detail": _refund_detail(refund_status),
        },
    )


def process_event_cancellation(
    service_client: ServiceRoleClient, *, event_id: str, event_title: str
) -> EventCancellationResult:
    """Flag paid orders for admin refund and notify buyers + holders. Idempotent."""
    client = service_client.client
    instance_ids = _instance_ids(client, event_id)
    orders = _paid_orders(client, instance_ids)
    event_date = _earliest_event_date(client, instance_ids)
    paid_buyers = {customer_id for _, customer_id in orders if customer_id}

    flagged = 0
    for order_id, _customer_id in orders:
        if _flag_refund(client, order_id=order_id, event_id=event_id):
            flagged += 1

    recipients = {customer_id for _, customer_id in orders if customer_id}
    recipients |= _holder_ids(client, instance_ids)
    for recipient_id in sorted(recipients):
        refund_status = "pending" if recipient_id in paid_buyers else "none"
        _notify(
            client,
            event_id=event_id,
            event_title=event_title,
            event_date=event_date,
            recipient_id=recipient_id,
            refund_status=refund_status,
        )

    return EventCancellationResult(orders_flagged=flagged, recipients_notified=len(recipients))
