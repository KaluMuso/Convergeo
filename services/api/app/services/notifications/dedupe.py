from __future__ import annotations

from typing import Any

DEFAULT_CHANNEL_ORDER: tuple[str, ...] = ("whatsapp", "sms", "email")


def build_dedupe_key(event_type: str, entity_id: str, channel: str) -> str:
    """Stable idempotency key: one outbox row per event per channel."""
    return f"{event_type}:{entity_id}:{channel}"


def is_pending_dispatch(row: dict[str, Any]) -> bool:
    """Return True when a row is eligible for adapter invocation."""
    status = row.get("status")
    if status == "sent":
        return False
    if status == "failed":
        return False
    if status != "pending":
        return False
    payload = row.get("payload")
    if isinstance(payload, dict) and payload.get("_delivered"):
        return False
    return True


def enqueue_outbox_row(
    client: Any,
    *,
    event_type: str,
    entity_id: str,
    channel: str,
    template: str | None,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Insert-or-skip by UNIQUE(dedupe_key). Returns inserted row or None on collision."""
    dedupe_key = build_dedupe_key(event_type, entity_id, channel)
    row = {
        "dedupe_key": dedupe_key,
        "channel": channel,
        "template": template,
        "payload": payload,
        "status": "pending",
    }
    response = client.table("notification_outbox").insert(row).execute()
    data = response.data
    if isinstance(data, list) and data:
        inserted = data[0]
        if isinstance(inserted, dict):
            return inserted
    if isinstance(data, dict):
        return data
    return None
