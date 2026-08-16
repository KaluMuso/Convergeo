"""Event browse ranking signals (strategy §4.2).

Time remains the primary axis. Secondary signals, all derived from real data:

* sell-through ≥ 70% → selling-fast boost (and a visible badge)
* verified organiser (preferred_badge)
* optional distance when the caller supplies coordinates
* optional category affinity from the caller's prior ticket purchases

Past-end events are already excluded by the browse query.
"""

from __future__ import annotations

from datetime import datetime

from app.services.geo.distance import haversine_km

SELLING_FAST_RATIO = 0.70
NEAR_ME_DEFAULT_KM = 25.0


def sell_through_ratio(*, spots_sold: int, spots_total: int) -> float:
    if spots_total <= 0:
        return 0.0
    return min(1.0, max(0.0, spots_sold / spots_total))


def is_selling_fast(*, spots_sold: int, spots_total: int, is_sold_out: bool) -> bool:
    if is_sold_out or spots_total <= 0:
        return False
    return sell_through_ratio(spots_sold=spots_sold, spots_total=spots_total) >= SELLING_FAST_RATIO


def browse_rank_tuple(
    *,
    next_starts_at: datetime,
    spots_sold: int,
    spots_total: int,
    is_sold_out: bool,
    verified: bool,
    event_lat: float | None,
    event_lng: float | None,
    user_lat: float | None,
    user_lng: float | None,
    category: str | None,
    affinity_categories: frozenset[str],
) -> tuple[int, int, int, int, float, datetime]:
    """Lower tuple sorts first (Python default).

    1. In-stock events before sold-out.
    2. Selling-fast before not.
    3. Verified organiser before not.
    4. Category affinity match before not.
    5. Nearer events first when coordinates exist, else a large sentinel.
    6. Sooner start time.
    """
    selling = 0 if is_selling_fast(
        spots_sold=spots_sold, spots_total=spots_total, is_sold_out=is_sold_out
    ) else 1
    distance = 10_000.0
    if (
        user_lat is not None
        and user_lng is not None
        and event_lat is not None
        and event_lng is not None
    ):
        distance = haversine_km(user_lat, user_lng, event_lat, event_lng)
    affinity = 0 if (category is not None and category in affinity_categories) else 1
    return (
        1 if is_sold_out else 0,
        selling,
        0 if verified else 1,
        affinity,
        distance,
        next_starts_at,
    )


def within_near_me_radius(
    *,
    event_lat: float | None,
    event_lng: float | None,
    user_lat: float | None,
    user_lng: float | None,
    radius_km: float,
) -> bool:
    if user_lat is None or user_lng is None:
        return True
    if event_lat is None or event_lng is None:
        return False
    return haversine_km(user_lat, user_lng, event_lat, event_lng) <= radius_km
