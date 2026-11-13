"""SLA watch: stalled courier jobs, silent vendors, customer delivered/cancelled messages.

One repeat-safe tick (n8n every 5-15 min -> ``POST /internal/logistics/sla-watch/tick``):

* ops alert per courier job ``accepted`` too long (not collected) or
  ``picked_up`` too long (not delivered) — template ``dispatch_stale_alert``;
* ops alert per ``placed`` order the vendor has not confirmed within
  ``vendor_confirm_sla_minutes`` (default 120) — ``vendor_order_unconfirmed_alert``;
* customer ``order_delivered`` / ``order_cancelled`` messages for orders that
  reached those states recently, through the lifecycle registry (one per order).

Every message goes through the outbox with a duplicate-proof key, so running the
tick twice sends nothing twice. Nothing here changes an order, a job or money.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.services.dispatch import service as dispatch_service
from app.services.dispatch.message import order_reference
from app.services.dispatch.state import json_rows
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.orders.audit import run_sql_script
from app.services.orders.events import emit_order_lifecycle

logger = logging.getLogger(__name__)

ALERT_RECIPIENTS_ENV = "LOGISTICS_ALERT_WHATSAPP_E164"
FOUNDER_PHONE_ENV = "FOUNDER_WHATSAPP_E164"
CUSTOMER_MESSAGE_LOOKBACK_HOURS = 24
VENDOR_UNCONFIRMED_TEMPLATE = "vendor_order_unconfirmed_alert"
DISPATCH_STALE_TEMPLATE = "dispatch_stale_alert"


def alert_recipients() -> list[str]:
    """Operations alert numbers: a small list, not the founder's phone alone."""
    raw = os.environ.get(ALERT_RECIPIENTS_ENV, "") or os.environ.get(FOUNDER_PHONE_ENV, "")
    numbers = [n.strip() for n in raw.split(",") if n.strip().startswith("+")]
    return sorted(set(numbers))


def _config_minutes(key: str, default: int) -> int:
    result = run_sql_script(f"SELECT value::text FROM public.platform_config WHERE key = '{key}';")
    if result.ok and result.rows and result.rows[0].isdigit() and int(result.rows[0]) > 0:
        return int(result.rows[0])
    return default


def list_unconfirmed_vendor_orders() -> list[dict[str, Any]]:
    minutes = _config_minutes("vendor_confirm_sla_minutes", 120)
    rows = json_rows(
        f"""
SELECT json_build_object(
  'order_id', o.id,
  'vendor_name', v.display_name,
  'minutes_waiting', floor(extract(epoch FROM (timezone('utc', now()) - o.created_at)) / 60)::int
)::text
FROM public.orders o
JOIN public.vendors v ON v.id = o.vendor_id
WHERE o.status = 'placed'
  AND o.created_at <= timezone('utc', now()) - interval '{int(minutes)} minutes'
  AND (o.cod OR EXISTS (
    SELECT 1 FROM public.payments p
    WHERE p.checkout_group_id = o.checkout_group_id AND p.status = 'success'))
ORDER BY o.created_at ASC
LIMIT 100;
""",
        context="unconfirmed vendor orders",
    )
    for row in rows:
        row["order_reference"] = order_reference(str(row["order_id"]))
        row["threshold_minutes"] = minutes
    return rows


def _recent_orders(status: str) -> list[dict[str, Any]]:
    return json_rows(
        f"""
SELECT json_build_object(
  'id', o.id, 'customer_id', o.customer_id, 'vendor_id', o.vendor_id,
  'fulfilment', o.fulfilment, 'note', (
    SELECT e.note FROM public.order_events e
    WHERE e.order_id = o.id AND e.to_status = '{status}'
    ORDER BY e.created_at DESC LIMIT 1)
)::text
FROM public.orders o
WHERE o.status = '{status}'
  AND EXISTS (
    SELECT 1 FROM public.order_events e
    WHERE e.order_id = o.id AND e.to_status = '{status}'
      AND e.created_at >= timezone('utc', now())
                          - interval '{CUSTOMER_MESSAGE_LOOKBACK_HOURS} hours')
ORDER BY o.updated_at DESC
LIMIT 200;
""",
        context=f"recent {status} orders",
    )


def _site_url() -> str:
    return os.environ.get("PUBLIC_SITE_URL", "https://vergeo5.com").rstrip("/")


def run_sla_watch(client: Any) -> dict[str, int]:
    """One repeat-safe pass. Returns counts of messages enqueued / skipped (dedupe)."""
    counts = {"ops_enqueued": 0, "ops_skipped": 0, "customer_enqueued": 0, "customer_skipped": 0}
    recipients = alert_recipients()

    def ops(event_type: str, template: str, entity: str, payload: dict[str, Any]) -> None:
        for phone in recipients:
            row = enqueue_outbox_row(
                client,
                event_type=event_type,
                entity_id=f"{entity}:{phone}",
                channel="whatsapp",
                template=template,
                payload={**payload, "to": phone, "phone_e164": phone, "locale": "en"},
            )
            counts["ops_enqueued" if row is not None else "ops_skipped"] += 1

    if dispatch_service.is_courier_dispatch_enabled():
        for job in dispatch_service.list_stale_active():
            ops(
                "dispatch_stale_alert",
                DISPATCH_STALE_TEMPLATE,
                # One alert per job per state.
                f"{job['dispatch_id']}:{job['status']}",
                {
                    "dispatch_id": str(job["dispatch_id"]),
                    "order_reference": str(job["order_reference"]),
                    "courier_name": str(job.get("courier_name") or ""),
                    "minutes_waiting": int(job.get("minutes_waiting") or 0),
                    "status": str(job["status"]),
                },
            )

    for order in list_unconfirmed_vendor_orders():
        ops(
            "vendor_order_unconfirmed_alert",
            VENDOR_UNCONFIRMED_TEMPLATE,
            str(order["order_id"]),
            {
                "order_id": str(order["order_id"]),
                "order_reference": str(order["order_reference"]),
                "vendor_name": str(order.get("vendor_name") or ""),
                "minutes_waiting": int(order.get("minutes_waiting") or 0),
            },
        )

    for status, event in (("delivered", "order_delivered"), ("cancelled", "order_cancelled")):
        for order in _recent_orders(status):
            order_id = str(order["id"])
            extra: dict[str, Any] = {"order_reference": order_reference(order_id)}
            if event == "order_delivered":
                extra["review_url"] = f"{_site_url()}/account/orders/{order_id}"
            else:
                extra["orders_url"] = f"{_site_url()}/account/orders/{order_id}"
            try:
                row = emit_order_lifecycle(
                    client,
                    event=event,
                    order_row={
                        "id": order_id,
                        "reference": extra["order_reference"],
                        "customer_id": order.get("customer_id"),
                        "vendor_id": order.get("vendor_id"),
                    },
                    extra=extra,
                )
            except Exception:
                logger.warning("customer %s message failed", event, exc_info=True)
                row = None
            counts["customer_enqueued" if row is not None else "customer_skipped"] += 1
    return counts
