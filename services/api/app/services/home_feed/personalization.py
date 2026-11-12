"""`For you` foundation: explainable category-affinity scoring.

Signals (signed-in users only, last 60 days, service-role reads):

* recently viewed products (``user_recently_viewed``)  weight 1
* active cart lines (``carts`` / ``cart_items``)       weight 3
* purchased listings (``orders`` -> ``order_item_products``) weight 5

Each signal is mapped to the top-level and leaf ``category_path`` of the listing
it touched. A candidate listing scores ``sum(affinity[path prefix]) + rating``;
already-purchased listings are excluded. Guests (or users with no signal) get
trending, then top-rated.

Plug-in seam for a later recommendation service: implement the
:class:`Recommender` protocol and pass it to :func:`rank_for_you` — the feed
resolver only depends on ``rank(candidates, user_id) -> RankedResult``. A remote
model can therefore replace :class:`CategoryAffinityRecommender` without
touching the feed contract (keep the timeout + fallback-to-trending behaviour).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.routers.catalog import CatalogCandidate

logger = logging.getLogger(__name__)

SIGNAL_WINDOW_DAYS = 60
VIEW_WEIGHT = 1.0
CART_WEIGHT = 3.0
PURCHASE_WEIGHT = 5.0
MAX_SIGNAL_ROWS = 200


@dataclass(frozen=True)
class UserSignals:
    viewed_product_ids: set[str] = field(default_factory=set)
    cart_listing_ids: set[str] = field(default_factory=set)
    purchased_listing_ids: set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not (self.viewed_product_ids or self.cart_listing_ids or self.purchased_listing_ids)


@dataclass(frozen=True)
class RankedResult:
    candidates: list[CatalogCandidate]
    top_categories: list[str]
    personal: bool


class Recommender(Protocol):
    def rank(self, candidates: list[CatalogCandidate], signals: UserSignals) -> RankedResult: ...


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def load_user_signals(client: Any, user_id: str, *, now: datetime | None = None) -> UserSignals:
    """Read the three signal sources; any failing source contributes nothing."""
    since = ((now or datetime.now(UTC)) - timedelta(days=SIGNAL_WINDOW_DAYS)).isoformat()
    viewed: set[str] = set()
    cart: set[str] = set()
    purchased: set[str] = set()
    try:
        rows = _rows(
            client.table("user_recently_viewed")
            .select("product_id")
            .eq("user_id", user_id)
            .gte("viewed_at", since)
            .limit(MAX_SIGNAL_ROWS)
            .execute()
        )
        viewed = {str(row["product_id"]) for row in rows if row.get("product_id")}
    except Exception:
        logger.debug("for_you viewed signal failed", exc_info=True)
    try:
        carts = _rows(
            client.table("carts")
            .select("id")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        cart_ids = [str(row["id"]) for row in carts if row.get("id")]
        if cart_ids:
            items = _rows(
                client.table("cart_items")
                .select("listing_id")
                .in_("cart_id", cart_ids)
                .limit(MAX_SIGNAL_ROWS)
                .execute()
            )
            cart = {str(row["listing_id"]) for row in items if row.get("listing_id")}
    except Exception:
        logger.debug("for_you cart signal failed", exc_info=True)
    try:
        orders = _rows(
            client.table("orders")
            .select("id")
            .eq("customer_id", user_id)
            .gte("created_at", since)
            .limit(MAX_SIGNAL_ROWS)
            .execute()
        )
        order_ids = [str(row["id"]) for row in orders if row.get("id")]
        if order_ids:
            order_items = _rows(
                client.table("order_items")
                .select("id")
                .in_("order_id", order_ids)
                .eq("item_kind", "product")
                .limit(MAX_SIGNAL_ROWS)
                .execute()
            )
            item_ids = [str(row["id"]) for row in order_items if row.get("id")]
            if item_ids:
                products = _rows(
                    client.table("order_item_products")
                    .select("listing_id")
                    .in_("order_item_id", item_ids)
                    .execute()
                )
                purchased = {str(row["listing_id"]) for row in products if row.get("listing_id")}
    except Exception:
        logger.debug("for_you purchase signal failed", exc_info=True)
    return UserSignals(viewed, cart, purchased)


def _path_prefixes(path: str | None) -> list[str]:
    if not path:
        return []
    parts = [part for part in path.strip("/").split("/") if part]
    return ["/".join(parts[: index + 1]) for index in range(len(parts))]


class CategoryAffinityRecommender:
    """Simple, explainable category-affinity ranking (see module docstring)."""

    def rank(self, candidates: list[CatalogCandidate], signals: UserSignals) -> RankedResult:
        if signals.empty:
            return RankedResult([], [], personal=False)
        affinity: dict[str, float] = {}
        for row in candidates:
            weight = 0.0
            if row.listing.product_id and row.listing.product_id in signals.viewed_product_ids:
                weight += VIEW_WEIGHT
            if row.listing.id in signals.cart_listing_ids:
                weight += CART_WEIGHT
            if row.listing.id in signals.purchased_listing_ids:
                weight += PURCHASE_WEIGHT
            if weight:
                for prefix in _path_prefixes(row.search_doc.category_path):
                    affinity[prefix] = affinity.get(prefix, 0.0) + weight
        if not affinity:
            return RankedResult([], [], personal=False)

        def score(row: CatalogCandidate) -> float:
            return sum(
                affinity.get(prefix, 0.0) for prefix in _path_prefixes(row.search_doc.category_path)
            )

        pool = [
            row
            for row in candidates
            if row.in_stock
            and row.listing.id not in signals.purchased_listing_ids
            and score(row) > 0
        ]
        pool.sort(key=lambda row: (score(row), row.rating, row.review_count), reverse=True)
        top = sorted(affinity.items(), key=lambda item: item[1], reverse=True)
        top_categories = [path for path, _ in top if "/" not in path][:3]
        return RankedResult(pool, top_categories, personal=bool(pool))


DEFAULT_RECOMMENDER: Recommender = CategoryAffinityRecommender()


def rank_for_you(
    candidates: list[CatalogCandidate],
    signals: UserSignals,
    recommender: Recommender = DEFAULT_RECOMMENDER,
) -> RankedResult:
    try:
        return recommender.rank(candidates, signals)
    except Exception:
        logger.warning("for_you recommender failed; falling back", exc_info=True)
        return RankedResult([], [], personal=False)
