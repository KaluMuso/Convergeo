"""Pure signal rules. No I/O; every function is deterministic given ``now``."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta

from app.services.signals.models import (
    DEAL_MIN_PERCENT,
    FAST_DELIVERY_MAX_LEAD_DAYS,
    LOW_STOCK_MAX_QTY,
    NEAR_YOU_KM,
    NEW_WINDOW_DAYS,
    SIGNAL_BADGE_ORDER,
    TOP_RATED_MIN_RATING,
    TOP_RATED_MIN_REVIEWS,
    MarketFacts,
    SignalBadge,
    SignalFacts,
    SignalInput,
    SignalRibbon,
)

_EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def deal_percent(price_ngwee: int, compare_at_ngwee: int | None, *, in_stock: bool) -> int | None:
    """Whole-percent saving; integer math only (money never touches float)."""
    if not in_stock or compare_at_ngwee is None or compare_at_ngwee <= price_ngwee:
        return None
    percent = ((compare_at_ngwee - price_ngwee) * 100 + compare_at_ngwee // 2) // compare_at_ngwee
    return percent if percent >= DEAL_MIN_PERCENT else None


def ribbon_for(*, preferred: bool, tier: int | None) -> SignalRibbon | None:
    """One ribbon: Preferred beats Verified Business (T2+) beats ID verified (T1)."""
    if preferred:
        return "preferred"
    if tier is not None and tier >= 2:
        return "verified_business"
    if tier == 1:
        return "verified_id"
    return None


def market_facts_from_rows(
    rows: Iterable[tuple[str, int]],
) -> MarketFacts:
    """``rows`` = (vendor_id, price_ngwee) of *in-stock* retail listings of one product.

    ``seller_count`` is distinct shops; ``lowest`` is the cheapest of them.
    """
    vendors: set[str] = set()
    lowest: int | None = None
    for vendor_id, price in rows:
        vendors.add(vendor_id)
        lowest = price if lowest is None else min(lowest, price)
    return MarketFacts(seller_count=len(vendors), lowest_price_ngwee=lowest)


def compute_facts(
    item: SignalInput,
    *,
    market: MarketFacts | None,
    now: datetime,
    user_lat: float | None = None,
    user_lng: float | None = None,
) -> SignalFacts:
    deal = deal_percent(item.price_ngwee, item.compare_at_ngwee, in_stock=item.in_stock)
    ribbon = ribbon_for(preferred=item.vendor_preferred, tier=item.vendor_tier)

    distance_km: float | None = None
    if (
        user_lat is not None
        and user_lng is not None
        and item.lat is not None
        and item.lng is not None
    ):
        distance_km = round(haversine_km(user_lat, user_lng, item.lat, item.lng), 1)

    seller_count: int | None = None
    lowest: int | None = None
    multi_seller = market is not None and market.seller_count >= 2
    if multi_seller and market is not None:
        seller_count = market.seller_count
        lowest = market.lowest_price_ngwee

    earned: set[SignalBadge] = set()
    # Nothing is promoted on a listing that cannot be bought right now.
    if item.in_stock:
        if multi_seller and lowest is not None and item.price_ngwee <= lowest:
            earned.add("cheapest")
        if distance_km is not None and distance_km <= NEAR_YOU_KM:
            earned.add("near_you")
        if item.made_in_zambia:
            earned.add("made_in_zambia")
        if item.review_count >= TOP_RATED_MIN_REVIEWS and item.rating >= TOP_RATED_MIN_RATING:
            earned.add("top_rated")
        if (
            item.fulfilment_mode == "stocked"
            and item.delivery_available
            and item.lead_time_days is not None
            and item.lead_time_days <= FAST_DELIVERY_MAX_LEAD_DAYS
        ):
            earned.add("fast_delivery")
        if (
            item.stock_mode == "tracked"
            and item.stock_qty is not None
            and 0 < item.stock_qty <= LOW_STOCK_MAX_QTY
        ):
            earned.add("low_stock")
        if item.created_at is not None and now - item.created_at <= timedelta(days=NEW_WINDOW_DAYS):
            earned.add("new")

    return SignalFacts(
        ribbon=ribbon,
        badges_all=tuple(b for b in SIGNAL_BADGE_ORDER if b in earned),
        seller_count=seller_count,
        lowest_price_ngwee=lowest,
        deal_percent=deal,
        distance_km=distance_km,
        verified=ribbon is not None,
        made_in_zambia=item.made_in_zambia,
        in_stock=item.in_stock,
        rating=item.rating,
        review_count=item.review_count,
    )


def compute_all(
    items: Iterable[SignalInput],
    *,
    markets: Mapping[str, MarketFacts],
    now: datetime,
    user_lat: float | None = None,
    user_lng: float | None = None,
) -> dict[str, SignalFacts]:
    out: dict[str, SignalFacts] = {}
    for item in items:
        market = markets.get(item.product_id) if item.product_id else None
        out[item.listing_id] = compute_facts(
            item, market=market, now=now, user_lat=user_lat, user_lng=user_lng
        )
    return out
