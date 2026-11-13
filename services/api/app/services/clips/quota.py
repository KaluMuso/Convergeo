"""M17-P06 — the per-tier weekly clip allowance.

Follows the ``services/kyc/caps.py`` pattern rather than forking it: the limit is
**read from ``platform_config``**, not hardcoded, so the founder can change a
vendor's allowance without a deploy. The module is separate from ``caps.py``
because that module's cache and dataclasses are shaped around listings, orders
and payouts — three concerns a clip allowance does not share — and widening them
for a fourth would couple the two lifecycles.

The count is a **trailing seven-day window**, not a calendar week. A calendar
week means a vendor who posts three clips on Sunday evening gets three more on
Monday morning, which is not what "3 per week" means to anyone.

Rejected clips still count. Otherwise the cheapest way to get unlimited uploads
would be to upload things that get rejected, and the transcode credits those
clips burn are spent either way — which is the cost the cap exists to bound.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Protocol

from app.errors import AppError

logger = logging.getLogger(__name__)

CLIPS_TABLE: Final = "video_clips"
CONFIG_TABLE: Final = "platform_config"

#: platform_config key holding a tier → weekly allowance map.
WEEKLY_CAP_KEY: Final = "clip_weekly_caps"

#: Used only when the config row is missing or unreadable. Matches the spec's
#: "free tier 3 clips/week"; higher tiers are more trusted, not unlimited.
DEFAULT_WEEKLY_CAPS: Final[dict[str, int]] = {"1": 3, "2": 10, "3": 30}

WINDOW = timedelta(days=7)


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def load_weekly_caps(service_client: ServiceRoleClient) -> dict[str, int]:
    """Read the tier → allowance map. Falls back to the documented defaults."""
    try:
        response = (
            service_client.client.table(CONFIG_TABLE)
            .select("value")
            .eq("key", WEEKLY_CAP_KEY)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.warning("clip weekly cap config unreadable; using defaults")
        return dict(DEFAULT_WEEKLY_CAPS)

    rows = _rows(response)
    if not rows:
        return dict(DEFAULT_WEEKLY_CAPS)

    raw = rows[0].get("value")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("clip weekly cap config is not valid JSON; using defaults")
            return dict(DEFAULT_WEEKLY_CAPS)
    if not isinstance(raw, dict):
        return dict(DEFAULT_WEEKLY_CAPS)

    caps: dict[str, int] = {}
    for tier, value in raw.items():
        try:
            caps[str(tier)] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return caps or dict(DEFAULT_WEEKLY_CAPS)


def weekly_cap_for_tier(service_client: ServiceRoleClient, tier: int) -> int:
    caps = load_weekly_caps(service_client)
    if str(tier) in caps:
        return caps[str(tier)]
    # An unknown tier gets the most restrictive configured allowance rather than
    # an accidental "unlimited".
    return min(caps.values()) if caps else DEFAULT_WEEKLY_CAPS["1"]


def count_clips_in_window(
    service_client: ServiceRoleClient, *, vendor_id: str, now: datetime | None = None
) -> int:
    """Clips this vendor created in the trailing seven days, any status."""
    reference = now or datetime.now(UTC)
    since = (reference - WINDOW).isoformat()
    rows = _rows(
        service_client.client.table(CLIPS_TABLE)
        .select("id")
        .eq("vendor_id", vendor_id)
        .gte("created_at", since)
        .execute()
    )
    return len(rows)


def remaining_quota(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    tier: int,
    now: datetime | None = None,
) -> tuple[int, int]:
    """``(remaining, cap)`` — what the studio shows and the API enforces."""
    cap = weekly_cap_for_tier(service_client, tier)
    used = count_clips_in_window(service_client, vendor_id=vendor_id, now=now)
    return max(0, cap - used), cap


def enforce_clip_weekly_cap(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    tier: int,
    now: datetime | None = None,
) -> None:
    """Refuse an upload that would exceed the tier allowance.

    Raised as a 403 with the cap in ``details`` so the studio can say *why* and
    *when it resets*, rather than showing a generic failure the vendor cannot act
    on. Mirrors ``caps._raise_cap_error``'s shape (``message_key`` + details) so
    the client renders it the same way as the listing cap.
    """
    remaining, cap = remaining_quota(
        service_client, vendor_id=vendor_id, tier=tier, now=now
    )
    if remaining > 0:
        return
    raise AppError(
        code="clip_cap_exceeded",
        message="Vendor cap enforcement blocked this action",
        http_status=403,
        details={
            "message_key": "vendor.clips.errors.weeklyCap",
            "weekly_cap": cap,
            "kyc_tier": tier,
            "window_days": WINDOW.days,
        },
    )
