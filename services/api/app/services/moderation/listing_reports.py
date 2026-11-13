"""Customer listing-report intake for the shared ``flags`` moderation queue."""

from __future__ import annotations

import re
from typing import Any, Literal
from uuid import UUID

from app.errors import AppError

LISTING_REPORT_REASONS = frozenset(
    {"counterfeit", "prohibited", "scam", "misleading", "other"}
)
ListingReportReason = Literal["counterfeit", "prohibited", "scam", "misleading", "other"]

MAX_DETAIL_LEN = 500
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_report_detail(detail: str | None) -> str | None:
    """Bound + strip control characters from optional free-text detail."""
    if detail is None:
        return None
    cleaned = _CONTROL_CHARS_RE.sub("", detail).strip()
    if not cleaned:
        return None
    return cleaned[:MAX_DETAIL_LEN]


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    rows = _rows(response)
    return rows[0] if rows else None


def _compose_reason(reason: ListingReportReason, detail: str | None) -> str:
    if detail is None:
        return reason
    composed = f"{reason}: {detail}"
    return composed[:MAX_DETAIL_LEN]


def find_open_listing_flag(
    client: Any,
    *,
    listing_id: str,
    reporter_user_id: str,
) -> dict[str, Any] | None:
    """Return an open flag for this reporter+listing, if any (dedupe key)."""
    response = (
        client.table("flags")
        .select("id, entity_type, entity_id, reason, reporter_user_id, status, created_at")
        .eq("entity_type", "listing")
        .eq("entity_id", listing_id)
        .eq("reporter_user_id", reporter_user_id)
        .eq("status", "open")
        .limit(1)
        .execute()
    )
    return _single_row(response)


def assert_listing_reportable(client: Any, listing_id: str) -> dict[str, Any]:
    """Ensure the listing exists; 404 must not leak draft/removed rows distinctly."""
    try:
        UUID(listing_id)
    except ValueError as exc:
        raise AppError(
            code="not_found",
            message="Listing not found",
            http_status=404,
        ) from exc

    row = _single_row(
        client.table("vendor_listings")
        .select("id, vendor_id, status")
        .eq("id", listing_id)
        .maybe_single()
        .execute()
    )
    if row is None or str(row.get("status")) not in {"active", "paused"}:
        raise AppError(
            code="not_found",
            message="Listing not found",
            http_status=404,
        )
    return row


def create_listing_report(
    client: Any,
    *,
    listing_id: str,
    reporter_user_id: str,
    reason: ListingReportReason,
    detail: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Insert a listing flag or return the existing open one.

    Returns ``(flag_row, created)``. Duplicate open reports from the same
    reporter on the same listing are idempotent successes (no flood).
    """
    if reason not in LISTING_REPORT_REASONS:
        raise AppError(
            code="validation_error",
            message="Invalid report reason",
            http_status=422,
            details={"reason": reason},
        )

    assert_listing_reportable(client, listing_id)
    existing = find_open_listing_flag(
        client,
        listing_id=listing_id,
        reporter_user_id=reporter_user_id,
    )
    if existing is not None:
        return existing, False

    clean_detail = sanitize_report_detail(detail)
    payload = {
        "entity_type": "listing",
        "entity_id": listing_id,
        "reason": _compose_reason(reason, clean_detail),
        "reporter_user_id": reporter_user_id,
        "status": "open",
    }
    response = client.table("flags").insert(payload).execute()
    created_row = _single_row(response)
    if created_row is None:
        raced = find_open_listing_flag(
            client,
            listing_id=listing_id,
            reporter_user_id=reporter_user_id,
        )
        if raced is not None:
            return raced, False
        raise AppError(
            code="internal_error",
            message="Could not record listing report",
            http_status=500,
        )

    if clean_detail is not None:
        try:
            client.table("audit_log").insert(
                {
                    "actor": reporter_user_id,
                    "action": "customer.listing_report",
                    "entity_type": "flag",
                    "entity_id": str(created_row["id"]),
                    "before": None,
                    "after": {
                        "listing_id": listing_id,
                        "reason": reason,
                        "detail": clean_detail,
                    },
                }
            ).execute()
        except Exception:
            pass

    return created_row, True
