"""Payment ops alerts routed through the existing ops pipeline (no new channel).

* Structured ``alert`` log field at ERROR level: the same convention the money
  paths already use (``lenco_fee_unparseable``, ``lenco_webhook_*``), consumed by
  the ops alert pipeline.
* Admin-visible record: an ``audit_log`` row (entity ``payment``) for conditions
  the DB does not already record. Late collections are already recorded by the
  ``apply_prepaid_collection_success`` RPC in ``payment_collection_exceptions``
  plus ``audit_log`` (``payment.collection_exception``), so they only log.

``notification_outbox`` is deliberately NOT used: its channel CHECK allows only
whatsapp/sms/email and there is no configured ops recipient/template for these.
Failures here are logged, never swallowed, and never break payment processing.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

STALE_INITIATED_ACTION = "payment.stale_initiated_not_found"
LATE_COLLECTION_ALERT = "payment_late_collection"
STALE_INITIATED_ALERT = "payment_stale_initiated_not_found"


def alert_late_collection(
    *,
    payment_id: str,
    checkout_group_id: str,
    amount_ngwee: int,
    reference: str,
) -> None:
    """Page ops via the structured alert log; the RPC already wrote the exception row."""
    logger.error(
        "payment late collection recorded; needs ops review (payment_collection_exceptions)",
        extra={
            "alert": LATE_COLLECTION_ALERT,
            "payment_id": payment_id,
            "checkout_group_id": checkout_group_id,
            "amount_ngwee": amount_ngwee,
            "reference": reference,
        },
    )


def alert_stale_initiated_not_found(
    client: Any,
    *,
    payment: dict[str, Any],
    actor_id: str,
) -> None:
    """Structured alert + one deduped admin-visible audit_log row per payment."""
    payment_id = str(payment.get("id", ""))
    detail = {
        "payment_id": payment_id,
        "checkout_group_id": payment.get("checkout_group_id"),
        "amount_ngwee": payment.get("amount_ngwee"),
        "reference": payment.get("lenco_reference"),
    }
    logger.error(
        "stale INITIATED payment not found at provider; checkout is held, needs ops review",
        extra={"alert": STALE_INITIATED_ALERT, **detail},
    )
    try:
        existing = (
            client.table("audit_log")
            .select("id")
            .eq("entity_type", "payment")
            .eq("entity_id", payment_id)
            .eq("action", STALE_INITIATED_ACTION)
            .execute()
        )
        if getattr(existing, "data", None):
            return
        client.table("audit_log").insert(
            {
                "actor": actor_id,
                "action": STALE_INITIATED_ACTION,
                "entity_type": "payment",
                "entity_id": payment_id,
                "before": None,
                "after": {**detail, "needs_review": True},
            }
        ).execute()
    except Exception:
        logger.exception("stale initiated audit_log write failed for payment %s", payment_id)
