"""Offer badges for listing cards, computed server-side (W8, flag `bundles`).

One helper feeds every surface that shows a card — category pages
(``GET /offers/badges``), the home feed and "Popular now" stream, search
results and the vendor storefront — so they all advertise exactly the offers
checkout will honour. Fail closed: flag off, a read error or no offer means
"no badge", never an error on the surface that asked.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from app.schemas.offers import OfferBadgeOut
from app.services.offers.engine import OfferDef
from app.services.offers.store import load_live_offer_rows, offers_enabled

logger = logging.getLogger(__name__)

#: Upper bound on ids per lookup (one ``in_`` filter, short URLs).
MAX_BADGE_IDS = 200


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def advertisable(offer: OfferDef) -> bool:
    """Only offers the unified checkout applies, with gift stock left."""
    if not offer.cart_applicable:
        return False
    if offer.offer_type in ("bxgy", "free_gift"):
        return bool(offer.gift_available) and offer.reward_unit_price_ngwee is not None
    return True


def badge_for(offer: OfferDef) -> OfferBadgeOut:
    return OfferBadgeOut(
        offer_id=offer.id,
        offer_type=offer.offer_type,
        buy_qty=offer.buy_qty,
        get_qty=offer.get_qty,
        buy_n=offer.buy_n,
        pay_m=offer.pay_m,
        addon_percent_off=offer.addon_percent_off,
        bundle_pricing=offer.bundle_pricing,
    )


def _badges_from_offers(
    offers: Iterable[OfferDef], wanted: set[str], *, kind: str = "product"
) -> dict[str, OfferBadgeOut]:
    badges: dict[str, OfferBadgeOut] = {}
    for offer in sorted(offers, key=lambda o: o.id):
        if not advertisable(offer):
            continue
        # Badge the item the customer buys (never the free reward).
        for item in offer.items:
            if (
                item.role != "reward"
                and item.item_kind == kind
                and item.ref_id in wanted
                and item.ref_id not in badges
            ):
                badges[item.ref_id] = badge_for(offer)
    return badges


def _clean_ids(ids: Iterable[str]) -> list[str]:
    out: list[str] = []
    for raw in ids:
        value = str(raw).strip().lower()
        if len(value) == 36 and value not in out:
            out.append(value)
        if len(out) >= MAX_BADGE_IDS:
            break
    return out


def listing_badges_unchecked(client: Any, listing_ids: Iterable[str]) -> dict[str, OfferBadgeOut]:
    """Badges per listing id; caller already checked the flag. Raises on read errors."""
    ids = _clean_ids(listing_ids)
    if not ids:
        return {}
    item_rows = _rows(
        client.table("offer_items").select("offer_id").in_("listing_id", ids).execute()
    )
    offer_ids = sorted({str(row["offer_id"]) for row in item_rows if row.get("offer_id")})
    if not offer_ids:
        return {}
    return _badges_from_offers(load_live_offer_rows(client, offer_ids=offer_ids), set(ids))


def listing_badges(client: Any, listing_ids: Iterable[str]) -> dict[str, OfferBadgeOut]:
    """Badges per listing id (fail closed)."""
    ids = _clean_ids(listing_ids)
    if not ids:
        return {}
    try:
        if not offers_enabled(client):
            return {}
        return listing_badges_unchecked(client, ids)
    except Exception:
        logger.warning("offers.badges_failed", exc_info=True)
        return {}


def vendor_listing_badges(client: Any, vendor_id: str) -> dict[str, OfferBadgeOut]:
    """Badges for one vendor's storefront: that vendor's live offers only (fail closed)."""
    try:
        if not offers_enabled(client):
            return {}
        offers = load_live_offer_rows(client, vendor_ids=[vendor_id])
        wanted = {
            item.ref_id
            for offer in offers
            for item in offer.items
            if item.item_kind == "product"
        }
        return _badges_from_offers(offers, wanted)
    except Exception:
        logger.warning("offers.badges_failed", exc_info=True)
        return {}


def product_badges(client: Any, product_ids: Iterable[str]) -> dict[str, OfferBadgeOut]:
    """Badges per canonical product id: a live offer on any active listing of it."""
    ids = _clean_ids(product_ids)
    if not ids:
        return {}
    try:
        if not offers_enabled(client):
            return {}
        listing_rows = _rows(
            client.table("vendor_listings")
            .select("id, product_id, status")
            .in_("product_id", ids)
            .eq("status", "active")
            .execute()
        )
        product_of = {
            str(row["id"]).lower(): str(row["product_id"]).lower()
            for row in listing_rows
            if row.get("id") and row.get("product_id")
        }
        by_listing = listing_badges_unchecked(client, list(product_of))
    except Exception:
        logger.warning("offers.badges_failed", exc_info=True)
        return {}
    out: dict[str, OfferBadgeOut] = {}
    for listing_id in sorted(by_listing):
        product_id = product_of.get(listing_id)
        if product_id is not None and product_id not in out:
            out[product_id] = by_listing[listing_id]
    return out
