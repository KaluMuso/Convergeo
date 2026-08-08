"""Helpers for recording prohibited listing attempts into the moderation queue."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

PROHIBITED_ATTEMPT_REASON = "prohibited_listing_attempt"
#: Collapse repeated create/update retries for the same matched term.
DEDUPE_WINDOW = timedelta(hours=24)
MAX_TITLE_LEN = 200
MAX_MATCHED_LEN = 120


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _reason_key(*, policy_reason: str, matched: str | None) -> str:
    matched_part = (matched or "").strip()[:MAX_MATCHED_LEN] or "unknown"
    policy = (policy_reason or "keyword").strip()[:64]
    return f"{PROHIBITED_ATTEMPT_REASON}:{policy}:{matched_part}"


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _has_recent_open_duplicate(
    client: Any,
    *,
    vendor_id: str,
    reason_key: str,
) -> bool:
    """True when an open flag for this vendor+matched term exists in the window."""
    cutoff = datetime.now(UTC) - DEDUPE_WINDOW
    try:
        response = (
            client.table("flags")
            .select("id, reason, status, created_at")
            .eq("entity_type", "prohibited")
            .eq("entity_id", vendor_id)
            .eq("reason", reason_key)
            .eq("status", "open")
            .limit(5)
            .execute()
        )
    except Exception:
        logger.warning(
            "prohibited_listing_flag_dedupe_read_failed",
            exc_info=True,
            extra={"vendor_id": vendor_id},
        )
        return False

    for row in _rows(response):
        created = _parse_timestamp(row.get("created_at"))
        if created is None or created >= cutoff:
            return True
    return False


def record_prohibited_listing_attempt(
    client: Any,
    *,
    vendor_id: str,
    title: str | None,
    reason: str,
    matched: str | None,
    reporter_user_id: str | None = None,
    listing_id: str | None = None,
) -> bool:
    """Insert an auditable ``prohibited`` flag for admin review (best-effort).

    Returns ``True`` when a new flag row was written, ``False`` when skipped
    (dedupe / missing reporter / insert failure). Never raises — listing create
    / update must still return the original policy rejection.
    """
    if not reporter_user_id:
        logger.info(
            "prohibited_listing_flag_skipped_no_reporter",
            extra={"vendor_id": vendor_id, "reason": reason},
        )
        return False

    reason_key = _reason_key(policy_reason=reason, matched=matched)
    if _has_recent_open_duplicate(client, vendor_id=vendor_id, reason_key=reason_key):
        return False

    payload = {
        "entity_type": "prohibited",
        # Pre-listing rejections have no listing row — entity_id is the vendor.
        "entity_id": vendor_id,
        "reason": reason_key,
        "reporter_user_id": reporter_user_id,
        "status": "open",
    }
    try:
        response = client.table("flags").insert(payload).execute()
    except Exception:
        logger.warning(
            "prohibited_listing_flag_insert_failed",
            exc_info=True,
            extra={"vendor_id": vendor_id, "reason": reason},
        )
        return False

    rows = _rows(response)
    flag_id = str(rows[0]["id"]) if rows and rows[0].get("id") else None

    try:
        client.table("audit_log").insert(
            {
                "actor": reporter_user_id,
                "action": "vendor.prohibited_listing_attempt",
                "entity_type": "vendor",
                "entity_id": vendor_id,
                "before": None,
                "after": {
                    "flag_id": flag_id,
                    "matched": (matched or "")[:MAX_MATCHED_LEN] or None,
                    "title": (title or "")[:MAX_TITLE_LEN] or None,
                    "policy_reason": reason,
                    "listing_id": listing_id,
                    "source": "listing_screen",
                },
            }
        ).execute()
    except Exception:
        logger.warning(
            "prohibited_listing_flag_audit_failed",
            exc_info=True,
            extra={"vendor_id": vendor_id},
        )

    return True
