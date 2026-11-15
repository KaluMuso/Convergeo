"""Readers for the plan trial + annual discount (migration 20261115230000)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.services.vendor_plans.billing import DEFAULT_ANNUAL_DISCOUNT_PCT, parse_ts

logger = logging.getLogger(__name__)

ANNUAL_DISCOUNT_KEY = "plan_annual_discount_pct"


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def load_annual_discount_pct(client: Any) -> int:
    """Admin-editable percent; falls back to the founder default (15) when unreadable."""
    try:
        rows = _rows(
            client.table("platform_config").select("value").eq("key", ANNUAL_DISCOUNT_KEY).execute()
        )
    except Exception:
        logger.warning("annual discount read failed; using default", exc_info=True)
        return DEFAULT_ANNUAL_DISCOUNT_PCT
    if not rows:
        return DEFAULT_ANNUAL_DISCOUNT_PCT
    value = rows[0].get("value")
    if isinstance(value, bool):
        return DEFAULT_ANNUAL_DISCOUNT_PCT
    try:
        pct = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_ANNUAL_DISCOUNT_PCT
    return pct if 0 <= pct <= 90 else DEFAULT_ANNUAL_DISCOUNT_PCT


def load_vendor_trial_end(client: Any, vendor_id: str) -> datetime | None:
    """Trial end of the shop's business (None when unreadable: no trial claimed)."""
    try:
        vendors = _rows(
            client.table("vendors").select("business_id").eq("id", vendor_id).limit(1).execute()
        )
        business_id = vendors[0].get("business_id") if vendors else None
        if not business_id:
            return None
        rows = _rows(
            client.table("vendor_businesses")
            .select("trial_ends_at")
            .eq("id", str(business_id))
            .limit(1)
            .execute()
        )
    except Exception:
        logger.warning("trial read failed", exc_info=True)
        return None
    return parse_ts(rows[0].get("trial_ends_at")) if rows else None
