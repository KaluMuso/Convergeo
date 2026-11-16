"""Offer loading for the pricing engine (W8) — service-role reads, fail closed.

Everything here returns "no offers" when the ``bundles`` flag is off, missing,
or the read fails: offers can only ever lower a price, so failing closed means
the customer pays list price and nothing breaks.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from app.services.offers.engine import (
    DEFAULT_MAX_DISCOUNT_PCT,
    OfferDef,
    OfferItemDef,
)

logger = logging.getLogger(__name__)

FLAG = "bundles"
MAX_DISCOUNT_KEY = "bundles_max_discount_pct"
MAX_ACTIVE_KEY = "bundles_max_active_offers_per_vendor"
DEFAULT_MAX_ACTIVE_OFFERS = 20
OFFER_COLUMNS = (
    "id, vendor_id, offer_type, status, title, starts_at, ends_at, buy_qty, get_qty, "
    "bundle_pricing, addon_percent_off, bundle_price_ngwee, buy_n, pay_m, "
    "gift_stock_total, gift_stock_reserved, max_applications_per_order, "
    "per_customer_limit, paused_by_admin"
)
ITEM_COLUMNS = "offer_id, role, item_kind, listing_id, service_id, event_id, qty, sort_order"


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def offers_enabled(client: Any) -> bool:
    """``feature_flags.bundles`` — False on any error or missing row."""
    try:
        response = (
            client.table("feature_flags")
            .select("enabled")
            .eq("flag", FLAG)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.warning("offers.flag_read_failed", exc_info=True)
        return False
    rows = _rows(response)
    return bool(rows) and rows[0].get("enabled") is True


def _config_int(client: Any, key: str, default: int, *, lo: int, hi: int) -> int:
    try:
        rows = _rows(
            client.table("platform_config").select("value").eq("key", key).maybe_single().execute()
        )
    except Exception:
        return default
    if not rows:
        return default
    raw = rows[0].get("value")
    if isinstance(raw, str) and raw.strip().isdigit():
        raw = int(raw.strip())
    if isinstance(raw, bool) or not isinstance(raw, int):
        return default
    return max(lo, min(hi, raw))


def max_discount_pct(client: Any) -> int:
    return _config_int(client, MAX_DISCOUNT_KEY, DEFAULT_MAX_DISCOUNT_PCT, lo=1, hi=95)


def max_active_offers(client: Any) -> int:
    return _config_int(client, MAX_ACTIVE_KEY, DEFAULT_MAX_ACTIVE_OFFERS, lo=1, hi=500)


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def offer_is_live(row: dict[str, Any], now: datetime) -> bool:
    if row.get("status") != "active" or row.get("paused_by_admin") is True:
        return False
    starts = _parse_ts(row.get("starts_at"))
    ends = _parse_ts(row.get("ends_at"))
    if starts is None or starts > now:
        return False
    return ends is None or ends > now


def _opt_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def item_ref(item: dict[str, Any]) -> str | None:
    for key in ("listing_id", "service_id", "event_id"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def build_offer_def(
    row: dict[str, Any],
    items: Iterable[dict[str, Any]],
    *,
    reward_listing: dict[str, Any] | None = None,
) -> OfferDef:
    defs: list[OfferItemDef] = []
    for item in sorted(items, key=lambda i: (int(i.get("sort_order") or 0), str(item_ref(i)))):
        ref = item_ref(item)
        if ref is None:
            continue
        defs.append(
            OfferItemDef(
                role=item["role"],
                item_kind=item["item_kind"],
                ref_id=ref,
                qty=int(item.get("qty") or 1),
            )
        )
    total = _opt_int(row.get("gift_stock_total"))
    reserved = _opt_int(row.get("gift_stock_reserved")) or 0
    reward_price: int | None = None
    reward_title: str | None = None
    if reward_listing is not None:
        reward_price = _opt_int(reward_listing.get("price_ngwee"))
        title = reward_listing.get("title_override")
        if not isinstance(title, str) or not title.strip():
            product = reward_listing.get("products")
            title = product.get("name") if isinstance(product, dict) else None
        reward_title = title.strip() if isinstance(title, str) and title.strip() else None
    return OfferDef(
        id=str(row["id"]),
        vendor_id=str(row["vendor_id"]),
        offer_type=row["offer_type"],
        title=str(row.get("title") or ""),
        items=tuple(defs),
        buy_qty=_opt_int(row.get("buy_qty")),
        get_qty=_opt_int(row.get("get_qty")),
        bundle_pricing=row.get("bundle_pricing"),
        addon_percent_off=_opt_int(row.get("addon_percent_off")),
        bundle_price_ngwee=_opt_int(row.get("bundle_price_ngwee")),
        buy_n=_opt_int(row.get("buy_n")),
        pay_m=_opt_int(row.get("pay_m")),
        gift_available=None if total is None else max(0, total - reserved),
        max_applications_per_order=_opt_int(row.get("max_applications_per_order")) or 1,
        reward_unit_price_ngwee=reward_price,
        reward_title=reward_title,
    )


def _load_items(client: Any, offer_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not offer_ids:
        return {}
    by_offer: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(
        client.table("offer_items").select(ITEM_COLUMNS).in_("offer_id", offer_ids).execute()
    ):
        by_offer.setdefault(str(row.get("offer_id")), []).append(row)
    return by_offer


def _load_reward_listings(
    client: Any, items_by_offer: dict[str, list[dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    ids = sorted(
        {
            str(item["listing_id"])
            for items in items_by_offer.values()
            for item in items
            if item.get("role") == "reward" and isinstance(item.get("listing_id"), str)
        }
    )
    if not ids:
        return {}
    rows = _rows(
        client.table("vendor_listings")
        .select("id, vendor_id, price_ngwee, status, title_override, products(name)")
        .in_("id", ids)
        .execute()
    )
    return {str(row["id"]): row for row in rows if row.get("status") == "active"}


def load_live_offer_rows(
    client: Any,
    *,
    vendor_ids: Iterable[str] | None = None,
    offer_ids: Iterable[str] | None = None,
    now: datetime | None = None,
) -> list[OfferDef]:
    """Live offers (active, in window, not admin-paused) with their items."""
    moment = now or datetime.now(UTC)
    query = client.table("offers").select(OFFER_COLUMNS).eq("status", "active")
    if vendor_ids is not None:
        vendors = sorted(set(vendor_ids))
        if not vendors:
            return []
        query = query.in_("vendor_id", vendors)
    if offer_ids is not None:
        ids = sorted(set(offer_ids))
        if not ids:
            return []
        query = query.in_("id", ids)
    rows = [row for row in _rows(query.execute()) if offer_is_live(row, moment)]
    items_by_offer = _load_items(client, [str(row["id"]) for row in rows])
    rewards = _load_reward_listings(client, items_by_offer)
    defs: list[OfferDef] = []
    for row in rows:
        items = items_by_offer.get(str(row["id"]), [])
        reward_listing = None
        for item in items:
            if item.get("role") == "reward" and isinstance(item.get("listing_id"), str):
                reward_listing = rewards.get(str(item["listing_id"]))
                if reward_listing is None or str(reward_listing.get("vendor_id")) != str(
                    row["vendor_id"]
                ):
                    reward_listing = None
        defs.append(build_offer_def(row, items, reward_listing=reward_listing))
    return defs


def customer_offer_use_counts(
    client: Any, *, customer_id: str, offer_ids: Iterable[str]
) -> dict[str, int]:
    """Orders (not cancelled) per offer for one customer — per-customer limit."""
    ids = sorted(set(offer_ids))
    if not ids:
        return {}
    rows = _rows(
        client.table("order_items")
        .select("offer_id, order_id, orders!inner(customer_id, status)")
        .in_("offer_id", ids)
        .eq("orders.customer_id", customer_id)
        .neq("orders.status", "cancelled")
        .execute()
    )
    seen: dict[str, set[str]] = {}
    for row in rows:
        seen.setdefault(str(row.get("offer_id")), set()).add(str(row.get("order_id")))
    return {offer_id: len(orders) for offer_id, orders in seen.items()}


def load_offers_for_pricing(
    client: Any, vendor_ids: Iterable[str], *, customer_id: str | None = None
) -> tuple[list[OfferDef], int] | None:
    """(live offers, max discount pct) or None when the flag is off / read fails.

    With ``customer_id`` an offer whose per-customer limit that customer has
    already used up is dropped, so cart, checkout and placement agree.
    """
    if not offers_enabled(client):
        return None
    try:
        offers = load_live_offer_rows(client, vendor_ids=vendor_ids)
        if customer_id is not None and offers:
            limits = per_customer_limits(client, [o.id for o in offers])
            if limits:
                used = customer_offer_use_counts(
                    client, customer_id=customer_id, offer_ids=list(limits)
                )
                offers = [o for o in offers if used.get(o.id, 0) < limits.get(o.id, 1 << 30)]
        cap = max_discount_pct(client)
    except Exception:
        logger.warning("offers.load_failed", exc_info=True)
        return None
    return offers, cap


def per_customer_limits(client: Any, offer_ids: Iterable[str]) -> dict[str, int]:
    ids = sorted(set(offer_ids))
    if not ids:
        return {}
    rows = _rows(client.table("offers").select("id, per_customer_limit").in_("id", ids).execute())
    return {
        str(row["id"]): int(row["per_customer_limit"])
        for row in rows
        if isinstance(row.get("per_customer_limit"), int)
    }
