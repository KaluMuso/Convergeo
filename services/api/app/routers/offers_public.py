"""Public offer reads for cards and the PDP (W8, flag `bundles`).

Only live offers whose items are all products (so the cart can honour them)
and, for gift offers, whose gift pool is not empty are shown — an offer the
checkout would not apply is never advertised. Flag off → empty responses.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Annotated, Any

from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.schemas.offers import (
    OfferBadgesResponse,
    PublicOfferItemOut,
    PublicOfferOut,
    PublicOffersResponse,
)
from app.services.offers.badges import advertisable, badge_for, listing_badges_unchecked
from app.services.offers.engine import OfferDef, PricingLine, price_cart
from app.services.offers.manage import listing_title
from app.services.offers.store import (
    load_live_offer_rows,
    max_discount_pct,
    offers_enabled,
)
from fastapi import APIRouter, Depends, Query, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/offers", tags=["offers"])

RATE_SCOPE = "offers_public_read_ip"
RATE_LIMIT_PER_MINUTE = 240
MAX_BADGE_IDS = 60
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _rate_limit(request: Request, supabase: Any) -> None:
    try:
        allowed, retry_after = bump_rate_counter(
            scope=RATE_SCOPE,
            key=get_client_ip(request),
            window=timedelta(minutes=1),
            limit=RATE_LIMIT_PER_MINUTE,
            client=supabase.client,
        )
    except Exception:
        # Read-only and cache-friendly: a limiter outage must not blank the PDP.
        logger.warning("offers.rate_limit_unavailable", exc_info=True)
        return
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="catalog.offers.errors.rateLimited",
            message="Too many offer requests",
        )


def _offers_touching(client: Any, listing_ids: list[str]) -> list[OfferDef]:
    item_rows = _rows(
        client.table("offer_items").select("offer_id").in_("listing_id", listing_ids).execute()
    )
    offer_ids = sorted({str(row["offer_id"]) for row in item_rows if row.get("offer_id")})
    if not offer_ids:
        return []
    return [o for o in load_live_offer_rows(client, offer_ids=offer_ids) if advertisable(o)]


@router.get("/badges", response_model=OfferBadgesResponse)
def offer_badges(
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    listing_ids: Annotated[str, Query(max_length=MAX_BADGE_IDS * 37)] = "",
) -> OfferBadgesResponse:
    ids = [i.strip().lower() for i in listing_ids.split(",") if _UUID_RE.match(i.strip().lower())]
    ids = list(dict.fromkeys(ids))[:MAX_BADGE_IDS]
    if not ids or not offers_enabled(supabase.client):
        return OfferBadgesResponse(badges={})
    _rate_limit(request, supabase)
    badges = listing_badges_unchecked(supabase.client, ids)
    return OfferBadgesResponse(badges=badges)


@router.get("/listing/{listing_id}", response_model=PublicOffersResponse)
def offers_for_listing(
    listing_id: str,
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> PublicOffersResponse:
    listing_key = listing_id.strip().lower()
    if not _UUID_RE.match(listing_key) or not offers_enabled(supabase.client):
        return PublicOffersResponse(offers=[])
    _rate_limit(request, supabase)
    client = supabase.client
    offers = [
        o
        for o in _offers_touching(client, [listing_key])
        if any(i.ref_id == listing_key and i.role != "reward" for i in o.items)
    ]
    if not offers:
        return PublicOffersResponse(offers=[])
    ref_ids = sorted({i.ref_id for o in offers for i in o.items})
    listings = {
        str(row["id"]): row
        for row in _rows(
            client.table("vendor_listings")
            .select(
                "id, vendor_id, price_ngwee, status, title_override, products(name, slug), "
                "listing_images(cloudinary_public_id, position)"
            )
            .in_("id", ref_ids)
            .execute()
        )
        if row.get("status") == "active"
    }
    cap = max_discount_pct(client)
    out: list[PublicOfferOut] = []
    for offer in sorted(offers, key=lambda o: o.id):
        items: list[PublicOfferItemOut] = []
        complete = True
        for item in offer.items:
            row = listings.get(item.ref_id)
            if row is None or str(row.get("vendor_id")) != offer.vendor_id:
                complete = False
                break
            product = row.get("products") if isinstance(row.get("products"), dict) else {}
            images = sorted(
                (
                    img
                    for img in (row.get("listing_images") or [])
                    if isinstance(img, dict) and isinstance(img.get("cloudinary_public_id"), str)
                ),
                key=lambda img: int(img.get("position") or 0),
            )
            items.append(
                PublicOfferItemOut(
                    role=item.role,
                    listing_id=item.ref_id,
                    qty=item.qty,
                    title=listing_title(row),
                    unit_price_ngwee=int(row["price_ngwee"]),
                    image_public_id=images[0]["cloudinary_public_id"] if images else None,
                    product_slug=product.get("slug") if isinstance(product, dict) else None,
                )
            )
        if not complete:
            continue
        # Price the smallest basket that triggers the offer once (same engine).
        basket: list[PricingLine] = []
        for index, item_out in enumerate(items):
            if item_out.role == "reward":
                continue
            qty = item_out.qty
            if offer.offer_type == "bxgy" and item_out.role == "trigger":
                if basket:
                    continue
                qty = (offer.buy_qty or 1) * item_out.qty
            elif offer.offer_type == "free_gift" and item_out.role == "trigger":
                if basket:
                    continue
            elif offer.offer_type == "buy_n_pay_m":
                if basket:
                    continue
                qty = offer.buy_n or 1
            basket.append(
                PricingLine(
                    key=f"b{index}",
                    listing_id=item_out.listing_id,
                    vendor_id=offer.vendor_id,
                    qty=qty,
                    unit_price_ngwee=item_out.unit_price_ngwee,
                )
            )
        if not basket:
            continue
        priced = price_cart(basket, [offer], max_discount_pct=cap)
        if not priced.applications:
            continue
        list_total = sum(o.list_total_ngwee for o in priced.lines.values())
        pay = priced.subtotal_ngwee
        out.append(
            PublicOfferOut(
                id=offer.id,
                vendor_id=offer.vendor_id,
                offer_type=offer.offer_type,
                title=offer.title,
                ends_at=None,
                badge=badge_for(offer),
                items=items,
                list_total_ngwee=list_total,
                pay_ngwee=pay,
                savings_ngwee=list_total - pay,
                gift_qty=sum(g.qty for g in priced.gifts),
                gift_value_ngwee=priced.gift_value_ngwee,
            )
        )
    return PublicOffersResponse(offers=out)
