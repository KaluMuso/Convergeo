"""Busy mode: one admin-set level (0-4) that pauses nice-to-have features.

The level lives in ``platform_config`` under ``busy_mode_level`` and is read with a
30-second in-process cache (per API worker). It is an *overlay*: it never rewrites
``feature_flags`` or other settings, so returning to level 0 restores everything
exactly as it was.

Levels (see the busy-day readiness doc):

* 0 Normal: nothing paused.
* 1 Watch: nothing paused in the app (operators pause n8n digests by hand).
* 2 Light: clips autoplay, live counts and recommendation rails paused
  (customer app hides them).
* 3 Lean: also Ask Vergeo, the personalised home feed and search typeahead.
* 4 Protect: also the clips feed.

HARD RULE: cart, checkout, payments, orders, webhooks and auth can never be paused
by busy mode. :class:`Feature` has no member for them, and importing this module from
those code paths is blocked by ``tests/test_busy_mode.py``.
"""

from __future__ import annotations

import logging
import time
from enum import StrEnum
from typing import Any, Final

logger = logging.getLogger(__name__)

LEVEL_KEY: Final = "busy_mode_level"
MIN_LEVEL: Final = 0
MAX_LEVEL: Final = 4
CACHE_TTL_SECONDS: Final = 30.0

#: Surfaces busy mode must never touch. Checked at import and in tests.
PROTECTED_SURFACES: Final = frozenset(
    {"cart", "checkout", "payments", "orders", "webhooks", "auth", "payouts", "refunds"}
)

LEVEL_LABELS: Final[dict[int, str]] = {
    0: "normal",
    1: "watch",
    2: "light",
    3: "lean",
    4: "protect",
}


class Feature(StrEnum):
    CLIPS_AUTOPLAY = "clips_autoplay"
    LIVE_COUNTS = "live_counts"
    RECOMMENDATION_RAILS = "recommendation_rails"
    ASK_VERGEO = "ask_vergeo"
    PERSONALISED_FEED = "personalised_feed"
    SEARCH_SUGGEST = "search_suggest"
    CLIPS_FEED = "clips_feed"


#: Lowest level at which each feature is paused.
FEATURE_MIN_LEVEL: Final[dict[Feature, int]] = {
    Feature.CLIPS_AUTOPLAY: 2,
    Feature.LIVE_COUNTS: 2,
    Feature.RECOMMENDATION_RAILS: 2,
    Feature.ASK_VERGEO: 3,
    Feature.PERSONALISED_FEED: 3,
    Feature.SEARCH_SUGGEST: 3,
    Feature.CLIPS_FEED: 4,
}

assert not ({f.value for f in FEATURE_MIN_LEVEL} & PROTECTED_SURFACES)  # noqa: S101
assert set(FEATURE_MIN_LEVEL) == set(Feature)  # noqa: S101

_cache: tuple[float, int] | None = None


def clamp_level(value: Any) -> int:
    """Coerce a stored value to a valid level; anything odd means 0 (normal)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return MIN_LEVEL
    if value < MIN_LEVEL or value > MAX_LEVEL:
        return MIN_LEVEL
    return value


def paused_features(level: int) -> list[str]:
    return sorted(f.value for f, minimum in FEATURE_MIN_LEVEL.items() if level >= minimum)


def is_paused(feature: Feature, level: int) -> bool:
    return level >= FEATURE_MIN_LEVEL[feature]


def clear_cache() -> None:
    global _cache
    _cache = None


def _read_level(service_client: Any) -> int:
    response = (
        service_client.client.table("platform_config")
        .select("value")
        .eq("key", LEVEL_KEY)
        .maybe_single()
        .execute()
    )
    data = getattr(response, "data", None)
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        return MIN_LEVEL
    return clamp_level(data.get("value"))


def get_level(service_client: Any) -> int:
    """Current level, cached 30 s. A read error keeps the last known value (or 0)."""
    global _cache
    now = time.monotonic()
    if _cache is not None and _cache[0] > now:
        return _cache[1]
    try:
        level = _read_level(service_client)
    except Exception:  # noqa: BLE001
        logger.warning("busy mode level read failed; keeping last known value")
        stale = _cache[1] if _cache is not None else MIN_LEVEL
        _cache = (now + CACHE_TTL_SECONDS, stale)
        return stale
    _cache = (now + CACHE_TTL_SECONDS, level)
    return level


def feature_paused(service_client: Any, feature: Feature) -> bool:
    return is_paused(feature, get_level(service_client))
