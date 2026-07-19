from __future__ import annotations

from typing import Any

from postgrest.exceptions import APIError

DEFAULT_CHANNEL_ORDER: tuple[str, ...] = ("whatsapp", "sms", "email")

# Postgres unique_violation SQLSTATE — raised when the UNIQUE(dedupe_key) index
# rejects a re-enqueue of an already-queued (event, entity, channel) notification.
_UNIQUE_VIOLATION = "23505"


def build_dedupe_key(event_type: str, entity_id: str, channel: str) -> str:
    """Stable idempotency key: one outbox row per event per channel."""
    return f"{event_type}:{entity_id}:{channel}"


def split_dedupe_key(dedupe_key: str) -> tuple[str, str]:
    """Inverse of build_dedupe_key: recover (event_type, entity_id); channel dropped.

    event_type and channel never contain ':', but entity_id may (e.g. the RFQ
    ``{job_id}:{vendor_id}`` key), so the middle segments rejoin into entity_id.
    Returns ("", "") for a malformed key.
    """
    parts = dedupe_key.split(":")
    if len(parts) < 3:
        return "", ""
    return parts[0], ":".join(parts[1:-1])


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
    try:
        response = client.table("notification_outbox").insert(row).execute()
    except APIError as exc:
        # A concurrent/retried enqueue of the same (event, entity, channel) hit the
        # UNIQUE(dedupe_key) index. That is the idempotent no-op this function
        # promises ("Returns inserted row or None on collision") — never a crash of
        # the surrounding request (e.g. an order status transition).
        if getattr(exc, "code", None) == _UNIQUE_VIOLATION:
            return None
        raise
    data = response.data
    if isinstance(data, list) and data:
        inserted = data[0]
        if isinstance(inserted, dict):
            return inserted
    if isinstance(data, dict):
        return data
    return None
