"""Batched, fail-soft loading for product signals.

Every public function swallows read errors and degrades to "no signal": a
signals outage must never break the listing, search or home surface that asked.
Query budget per surface (cold): <= 1 listing/vendor query, 1 market query per
uncached product batch, 1 kyc_records query, 1 reviews join, 1 MiZ probe.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from app.core.ttl_cache import get_cached_json, set_cached_json
from app.services.db_chunk import chunked_in_query, unique_preserve_order
from app.services.kyc.eligibility import load_approved_tiers_for_client
from app.services.listings.availability import is_listing_available
from app.services.listings.demo import fetch_demo_listing_ids
from app.services.signals.models import ListingSignals, MarketFacts, SignalFacts, SignalInput
from app.services.signals.rules import (
    compute_all,
    market_facts_from_rows,
    parse_timestamp,
)

logger = logging.getLogger(__name__)

MARKET_CACHE_PREFIX = "signals:market:v1:"
MARKET_CACHE_TTL_SECONDS = 60
TIER_CACHE_PREFIX = "signals:tier:v1:"
TIER_CACHE_TTL_SECONDS = 120

#: Seconds to remember that ``made_in_zambia_status`` does not exist yet (PR #973
#: not deployed) so we do not fire a failing probe on every request.
MIZ_ABSENT_BACKOFF_SECONDS = 600.0
_miz_absent_until: float = 0.0

_LISTING_SELECT = (
    "id,vendor_id,product_id,price_ngwee,compare_at_ngwee,product_class,stock_mode,stock_qty,"
    "min_steps,moq,fulfilment_mode,lead_time_days,vendor_capacity_per_week,wholesale,created_at,"
    "vendors!inner(id,status,preferred_badge,vendor_locations(lat,lng))"
)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _nested(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, dict) else None


def _first_coords(vendor: dict[str, Any]) -> tuple[float | None, float | None]:
    locations = vendor.get("vendor_locations")
    if isinstance(locations, dict):
        locations = [locations]
    for loc in locations if isinstance(locations, list) else []:
        if isinstance(loc, dict) and loc.get("lat") is not None and loc.get("lng") is not None:
            try:
                return float(loc["lat"]), float(loc["lng"])
            except (TypeError, ValueError):
                continue
    return None, None


def _row_in_stock(row: dict[str, Any]) -> bool:
    return is_listing_available(
        str(row.get("stock_mode") or ""),
        row.get("stock_qty"),
        min_steps=int(row.get("min_steps") or 1),
        moq=int(row.get("moq") or 1),
        product_class=str(row.get("product_class") or "A"),
        fulfilment_mode=str(row.get("fulfilment_mode") or "stocked"),
        vendor_capacity_per_week=row.get("vendor_capacity_per_week"),
    )


def load_made_in_zambia_approved(client: Any, listing_ids: Sequence[str]) -> set[str]:
    """Listings whose Made in Zambia claim an admin approved (PR #973).

    Absent column (migration not applied) or any read error => empty set, and the
    probe is backed off for :data:`MIZ_ABSENT_BACKOFF_SECONDS`.
    """
    global _miz_absent_until
    if not listing_ids or time.monotonic() < _miz_absent_until:
        return set()
    try:
        rows = chunked_in_query(
            list(listing_ids),
            run=lambda chunk: (
                client.table("vendor_listings")
                .select("id")
                .in_("id", chunk)
                .eq("made_in_zambia_status", "approved")
                .execute()
            ),
        )
    except Exception:
        _miz_absent_until = time.monotonic() + MIZ_ABSENT_BACKOFF_SECONDS
        logger.info("signals.made_in_zambia_unavailable", exc_info=True)
        return set()
    return {str(r["id"]) for r in rows if r.get("id")}


def load_approved_tiers(client: Any, vendor_ids: Iterable[str]) -> dict[str, int]:
    """vendor_id -> highest *approved* KYC tier (cached 2 min; fail-soft)."""
    ids = unique_preserve_order(str(v) for v in vendor_ids)
    out: dict[str, int] = {}
    missing: list[str] = []
    for vendor_id in ids:
        cached = get_cached_json(f"{TIER_CACHE_PREFIX}{vendor_id}")
        if isinstance(cached, dict) and "tier" in cached:
            if isinstance(cached["tier"], int):
                out[vendor_id] = cached["tier"]
        else:
            missing.append(vendor_id)
    if missing:
        try:
            fresh = load_approved_tiers_for_client(client, missing)
        except Exception:
            logger.info("signals.tiers_unavailable", exc_info=True)
            return out
        for vendor_id in missing:
            tier = fresh.get(vendor_id)
            set_cached_json(
                f"{TIER_CACHE_PREFIX}{vendor_id}",
                {"tier": tier},
                ttl_seconds=TIER_CACHE_TTL_SECONDS,
            )
            if tier is not None:
                out[vendor_id] = tier
    return out


def _fetch_product_rows(client: Any, product_ids: Sequence[str]) -> list[dict[str, Any]]:
    rows = chunked_in_query(
        list(product_ids),
        run=lambda chunk: (
            client.table("vendor_listings")
            .select(_LISTING_SELECT)
            .in_("product_id", chunk)
            .eq("status", "active")
            .eq("vendors.status", "active")
            .execute()
        ),
    )
    retail = [r for r in rows if not r.get("wholesale")]
    demo = fetch_demo_listing_ids(client, [str(r["id"]) for r in retail if r.get("id")])
    return [r for r in retail if str(r.get("id")) not in demo]


def load_market_facts(client: Any, product_ids: Iterable[str]) -> dict[str, MarketFacts]:
    """Per canonical product: distinct in-stock shops and their lowest price (cached 60 s)."""
    ids = unique_preserve_order(str(p) for p in product_ids if p)
    out: dict[str, MarketFacts] = {}
    missing: list[str] = []
    for product_id in ids:
        cached = get_cached_json(f"{MARKET_CACHE_PREFIX}{product_id}")
        if isinstance(cached, dict) and isinstance(cached.get("n"), int):
            low = cached.get("low")
            out[product_id] = MarketFacts(cached["n"], low if isinstance(low, int) else None)
        else:
            missing.append(product_id)
    if not missing:
        return out
    try:
        rows = _fetch_product_rows(client, missing)
    except Exception:
        logger.info("signals.market_unavailable", exc_info=True)
        return out
    by_product: dict[str, list[tuple[str, int]]] = {pid: [] for pid in missing}
    for row in rows:
        pid = str(row.get("product_id") or "")
        if pid in by_product and _row_in_stock(row):
            by_product[pid].append((str(row["vendor_id"]), int(row["price_ngwee"])))
    for pid, pairs in by_product.items():
        facts = market_facts_from_rows(pairs)
        out[pid] = facts
        set_cached_json(
            f"{MARKET_CACHE_PREFIX}{pid}",
            {"n": facts.seller_count, "low": facts.lowest_price_ngwee},
            ttl_seconds=MARKET_CACHE_TTL_SECONDS,
        )
    return out


def _ratings(client: Any, listing_ids: list[str]) -> dict[str, tuple[float, int]]:
    try:
        # Lazy import: routers.catalog imports this package.
        from app.routers.catalog import _fetch_listing_ratings

        return _fetch_listing_ratings(client, listing_ids)
    except Exception:
        logger.info("signals.ratings_unavailable", exc_info=True)
        return {}


def _inputs_from_rows(client: Any, rows: list[dict[str, Any]]) -> list[SignalInput]:
    listing_ids = [str(r["id"]) for r in rows if r.get("id")]
    vendors = [_nested(r.get("vendors")) or {} for r in rows]
    tiers = load_approved_tiers(client, [str(v.get("id")) for v in vendors if v.get("id")])
    miz = load_made_in_zambia_approved(client, listing_ids)
    ratings = _ratings(client, listing_ids)
    # Lazy import (circular): the Lusaka delivery radius lives with the comparison router.
    from app.routers.comparison import is_lusaka_delivery_available

    inputs: list[SignalInput] = []
    for row, vendor in zip(rows, vendors, strict=True):
        if not row.get("id") or not vendor.get("id"):
            continue
        lat, lng = _first_coords(vendor)
        rating, count = ratings.get(str(row["id"]), (0.0, 0))
        compare_at = row.get("compare_at_ngwee")
        inputs.append(
            SignalInput(
                listing_id=str(row["id"]),
                product_id=str(row["product_id"]) if row.get("product_id") else None,
                vendor_id=str(vendor["id"]),
                price_ngwee=int(row["price_ngwee"]),
                compare_at_ngwee=int(compare_at) if isinstance(compare_at, int) else None,
                in_stock=_row_in_stock(row),
                stock_mode=str(row.get("stock_mode") or ""),
                stock_qty=row.get("stock_qty") if isinstance(row.get("stock_qty"), int) else None,
                fulfilment_mode=str(row.get("fulfilment_mode") or "stocked"),
                lead_time_days=row.get("lead_time_days")
                if isinstance(row.get("lead_time_days"), int)
                else None,
                created_at=parse_timestamp(row.get("created_at")),
                rating=rating,
                review_count=count,
                lat=lat,
                lng=lng,
                delivery_available=is_lusaka_delivery_available(lat, lng),
                vendor_preferred=bool(vendor.get("preferred_badge")),
                vendor_tier=tiers.get(str(vendor["id"])),
                made_in_zambia=str(row["id"]) in miz,
            )
        )
    return inputs


def facts_for_inputs(
    client: Any,
    inputs: list[SignalInput],
    *,
    user_lat: float | None = None,
    user_lng: float | None = None,
    now: datetime | None = None,
) -> dict[str, SignalFacts]:
    """Compute facts for already-built inputs (adds the cached market lookup)."""
    markets = load_market_facts(client, [i.product_id for i in inputs if i.product_id])
    return compute_all(
        inputs,
        markets=markets,
        now=now or datetime.now(UTC),
        user_lat=user_lat,
        user_lng=user_lng,
    )


def build_signals_for_listing_ids(
    client: Any,
    listing_ids: Iterable[str],
    *,
    user_lat: float | None = None,
    user_lng: float | None = None,
    now: datetime | None = None,
) -> dict[str, SignalFacts]:
    """Facts keyed by lower-cased listing id (fail-soft: ``{}`` on any read error)."""
    ids = unique_preserve_order(str(i).lower() for i in listing_ids if i)
    if not ids:
        return {}
    try:
        rows = chunked_in_query(
            ids,
            run=lambda chunk: (
                client.table("vendor_listings")
                .select(_LISTING_SELECT)
                .in_("id", chunk)
                .eq("status", "active")
                .eq("vendors.status", "active")
                .execute()
            ),
        )
        facts = facts_for_inputs(
            client, _inputs_from_rows(client, rows), user_lat=user_lat, user_lng=user_lng, now=now
        )
    except Exception:
        logger.warning("signals.listing_build_failed", exc_info=True)
        return {}
    return {k.lower(): v for k, v in facts.items()}


def build_signals_for_product_ids(
    client: Any,
    product_ids: Iterable[str],
    *,
    user_lat: float | None = None,
    user_lng: float | None = None,
    now: datetime | None = None,
) -> dict[str, SignalFacts]:
    """Facts for a canonical product card = those of its cheapest in-stock seller.

    ``cheapest`` is dropped (the card already says "from K..."); ``seller_count`` and
    ``lowest_price_ngwee`` carry the "Available in N shops" line.
    """
    ids = unique_preserve_order(str(i).lower() for i in product_ids if i)
    if not ids:
        return {}
    try:
        rows = _fetch_product_rows(client, ids)
        best: dict[str, dict[str, Any]] = {}
        for row in sorted(rows, key=lambda r: (int(r["price_ngwee"]), str(r["id"]))):
            pid = str(row.get("product_id") or "").lower()
            if pid and pid not in best and _row_in_stock(row):
                best[pid] = row
        inputs = _inputs_from_rows(client, list(best.values()))
        facts = facts_for_inputs(client, inputs, user_lat=user_lat, user_lng=user_lng, now=now)
        by_listing = {i.listing_id: i for i in inputs}
    except Exception:
        logger.warning("signals.product_build_failed", exc_info=True)
        return {}
    out: dict[str, SignalFacts] = {}
    for listing_id, fact in facts.items():
        product_id = by_listing[listing_id].product_id
        if product_id:
            badges = tuple(b for b in fact.badges_all if b != "cheapest")
            out[product_id.lower()] = SignalFacts(
                ribbon=fact.ribbon,
                badges_all=badges,
                seller_count=fact.seller_count,
                lowest_price_ngwee=fact.lowest_price_ngwee,
                deal_percent=fact.deal_percent,
                distance_km=fact.distance_km,
                verified=fact.verified,
                made_in_zambia=fact.made_in_zambia,
                in_stock=fact.in_stock,
                rating=fact.rating,
                review_count=fact.review_count,
            )
    return out


def attach_catalog_signals(
    client: Any,
    items: Sequence[Any],
    *,
    user_lat: float | None = None,
    user_lng: float | None = None,
) -> None:
    """Set ``item.signals`` on catalog cards (home feed, stream) by listing id; fail-soft."""
    if not items:
        return
    facts = build_signals_for_listing_ids(
        client, [i.id for i in items], user_lat=user_lat, user_lng=user_lng
    )
    for item in items:
        fact = facts.get(str(item.id).lower())
        item.signals = fact.to_wire() if fact is not None else None


__all__ = [
    "ListingSignals",
    "attach_catalog_signals",
    "build_signals_for_listing_ids",
    "build_signals_for_product_ids",
    "facts_for_inputs",
    "load_approved_tiers",
    "load_made_in_zambia_approved",
    "load_market_facts",
]
