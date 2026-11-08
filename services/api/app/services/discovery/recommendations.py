"""Explainable "more from this store" / "similar in this category" recommenders.

Products rank over the in-memory catalogue candidate set (one build per call,
same visibility rules as the PLP: active listing, active vendor, released
product class, demo listings removed, wholesale hidden). Similarity uses the
same category leaf (falling back to its parent), same product class, and a
score blending a Bayesian-damped rating, recent PDP views and price proximity.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from app.routers.catalog import (
    CatalogCandidate,
    CatalogListingItem,
    best_score,
    build_catalog_candidates,
    catalog_item_from_candidate,
)
from app.routers.events_public import EventBrowseItem
from app.routers.services_listings import ServiceBrowseItem

logger = logging.getLogger(__name__)

ProductScope = Literal["store", "category"]
VIEWS_WINDOW_DAYS = 30


def _product_slug(row: CatalogCandidate) -> str | None:
    if row.product and row.product.get("slug"):
        return str(row.product["slug"])
    return None


def _parent(path: str | None) -> str | None:
    if not path or "/" not in path.strip("/"):
        return None
    return path.strip("/").rsplit("/", 1)[0]


def recent_views(
    client: Any, listing_ids: list[str], *, today: date | None = None
) -> dict[str, int]:
    if not listing_ids:
        return {}
    since = ((today or datetime.now(UTC).date()) - timedelta(days=VIEWS_WINDOW_DAYS)).isoformat()
    try:
        response = (
            client.table("listing_analytics")
            .select("listing_id, pdp_views")
            .in_("listing_id", listing_ids[:500])
            .gte("day", since)
            .execute()
        )
    except Exception:
        logger.debug("recommendations views lookup failed", exc_info=True)
        return {}
    totals: dict[str, int] = {}
    for row in getattr(response, "data", None) or []:
        if isinstance(row, dict) and row.get("listing_id"):
            key = str(row["listing_id"])
            totals[key] = totals.get(key, 0) + int(row.get("pdp_views") or 0)
    return totals


def similarity_score(
    row: CatalogCandidate, *, reference_price: int, views: dict[str, int]
) -> float:
    damped = best_score(row)[0]
    view_signal = math.log1p(views.get(row.listing.id, 0))
    price = row.search_doc.price_min_ngwee or 0
    proximity = abs(price - reference_price) / reference_price if reference_price > 0 else 1.0
    stock = 1.0 if row.in_stock else 0.0
    return damped * 2.0 + view_signal - min(proximity, 3.0) * 1.5 + stock * 2.0


def recommend_for_product(
    client: Any,
    slug: str,
    *,
    scope: ProductScope,
    limit: int,
    candidates: list[CatalogCandidate] | None = None,
) -> list[CatalogListingItem] | None:
    """``None`` when the product is not visible (caller answers 404)."""
    pool = candidates if candidates is not None else build_catalog_candidates(client)
    own = [row for row in pool if _product_slug(row) == slug]
    if not own:
        return None
    vendor_ids = {row.listing.vendor_id for row in own}
    own_ids = {row.listing.id for row in own}
    others = [row for row in pool if row.listing.id not in own_ids and _product_slug(row) != slug]

    if scope == "store":
        picks = [row for row in others if row.listing.vendor_id in vendor_ids]
        picks.sort(key=lambda row: (row.in_stock, best_score(row)), reverse=True)
        return [catalog_item_from_candidate(row) for row in picks[:limit]]

    reference = min(own, key=lambda row: row.search_doc.price_min_ngwee or 0)
    reference_price = reference.search_doc.price_min_ngwee or 0
    leaf = reference.search_doc.category_path
    product_class = reference.listing.product_class
    eligible = [
        row
        for row in others
        if row.listing.vendor_id not in vendor_ids and row.listing.product_class == product_class
    ]
    same_leaf = [row for row in eligible if leaf and row.search_doc.category_path == leaf]
    parent = _parent(leaf)
    if len(same_leaf) < limit and parent:
        extra = [
            row
            for row in eligible
            if row not in same_leaf
            and (row.search_doc.category_path or "").startswith(f"{parent}/")
        ]
        same_leaf.extend(extra)
    views = recent_views(client, [row.listing.id for row in same_leaf])
    same_leaf.sort(
        key=lambda row: similarity_score(row, reference_price=reference_price, views=views),
        reverse=True,
    )
    return [catalog_item_from_candidate(row) for row in same_leaf[:limit]]


def recommend_services(
    items: list[ServiceBrowseItem],
    service_id: str,
    *,
    scope: Literal["provider", "category"],
    limit: int,
) -> list[ServiceBrowseItem] | None:
    current = next((item for item in items if item.id == service_id), None)
    if current is None:
        return None
    others = [item for item in items if item.id != service_id]
    if scope == "provider":
        return [item for item in others if item.provider.id == current.provider.id][:limit]
    reference = current.from_price_ngwee or 0
    similar = [
        item
        for item in others
        if item.category == current.category and item.provider.id != current.provider.id
    ]
    similar.sort(
        key=lambda item: (
            not item.provider.preferred_badge,
            abs((item.from_price_ngwee or reference) - reference),
        )
    )
    return similar[:limit]


def recommend_events(
    items: list[EventBrowseItem],
    slug: str,
    *,
    scope: Literal["organiser", "category"],
    limit: int,
    current: EventBrowseItem | None = None,
) -> list[EventBrowseItem] | None:
    current = current or next((item for item in items if item.slug == slug), None)
    if current is None:
        return None
    upcoming = [item for item in items if item.slug != slug and not item.is_sold_out]
    if scope == "organiser":
        picks = [item for item in upcoming if item.organiser.id == current.organiser.id]
    else:
        picks = [
            item
            for item in upcoming
            if item.category == current.category and item.organiser.id != current.organiser.id
        ]
    far_future = datetime.max.replace(tzinfo=UTC)
    picks.sort(key=lambda item: item.next_starts_at or far_future)
    return picks[:limit]
