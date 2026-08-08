"""Helpers for recording prohibited listing attempts into the moderation queue."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def record_prohibited_listing_attempt(
    client: Any,
    *,
    vendor_id: str,
    title: str | None,
    reason: str,
    matched: str | None,
    reporter_user_id: str | None = None,
) -> None:
    """Insert an auditable ``prohibited`` flag for admin review (best-effort)."""
    payload = {
        "entity_type": "prohibited",
        "entity_id": vendor_id,
        "reason": reason,
        "details": {
            "matched": matched,
            "title": (title or "")[:200],
            "source": "listing_screen",
        },
    }
    if reporter_user_id:
        payload["reporter_user_id"] = reporter_user_id
    try:
        client.table("flags").insert(payload).execute()
    except Exception:
        logger.warning(
            "prohibited_listing_flag_insert_failed",
            exc_info=True,
            extra={"vendor_id": vendor_id, "reason": reason},
        )
