from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.services.inventory.location_stock import (
    available_qty_at_location,
    is_branch_tracked,
)
from app.services.stock.claim import run_sql_script, sql_uuid

ChangeNoticeKind = Literal["price_changed", "out_of_stock", "qty_reduced"]


@dataclass(frozen=True, slots=True)
class CartLineSnapshot:
    listing_id: str
    qty: int
    unit_price_ngwee: int
    pickup_location_id: str | None = None
    listing_variant_id: str | None = None


@dataclass(frozen=True, slots=True)
class ChangeNotice:
    listing_id: str
    kind: ChangeNoticeKind
    requested_qty: int
    available_qty: int | None
    snapshot_price_ngwee: int
    current_price_ngwee: int | None


@dataclass(frozen=True, slots=True)
class RevalidateResult:
    notices: tuple[ChangeNotice, ...]
    has_changes: bool


def _fetch_listings(listing_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not listing_ids:
        return {}

    id_literals = ", ".join(sql_uuid(listing_id, "listing_id") for listing_id in listing_ids)
    result = run_sql_script(
        f"""
        SELECT id::text, price_ngwee::text, stock_mode, stock_qty::text, status,
               product_class, fulfilment_mode
        FROM public.vendor_listings
        WHERE id IN ({id_literals});
        """
    )
    if not result.ok:
        raise RuntimeError(f"fetch listings failed: {result.error}")

    listings: dict[str, dict[str, Any]] = {}
    for row in result.rows:
        parts = row.split("|")
        if len(parts) != 7:
            continue
        listing_id, price_raw, stock_mode, stock_qty_raw, status, product_class, fulfilment_mode = (
            parts
        )
        stock_qty: int | None
        if stock_qty_raw == "":
            stock_qty = None
        else:
            stock_qty = int(stock_qty_raw)
        listings[listing_id] = {
            "id": listing_id,
            "price_ngwee": int(price_raw),
            "stock_mode": stock_mode,
            "stock_qty": stock_qty,
            "status": status,
            "product_class": product_class,
            "fulfilment_mode": fulfilment_mode,
        }
    return listings


def _fetch_variants(variant_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Price override / own stock / status for the lines' chosen variants."""
    if not variant_ids:
        return {}
    id_literals = ", ".join(
        sql_uuid(variant_id, "listing_variant_id") for variant_id in variant_ids
    )
    result = run_sql_script(
        f"""
        SELECT id::text, listing_id::text, coalesce(price_ngwee::text, ''),
               coalesce(stock_qty::text, ''), status
        FROM public.vendor_listing_variants
        WHERE id IN ({id_literals});
        """
    )
    if not result.ok:
        raise RuntimeError(f"fetch variants failed: {result.error}")
    variants: dict[str, dict[str, Any]] = {}
    for row in result.rows:
        parts = row.split("|")
        if len(parts) != 5:
            continue
        variant_id, listing_id, price_raw, stock_raw, status = parts
        variants[variant_id] = {
            "listing_id": listing_id,
            "price_ngwee": int(price_raw) if price_raw else None,
            "stock_qty": int(stock_raw) if stock_raw else None,
            "status": status,
        }
    return variants


def _apply_variant(
    listing: dict[str, Any],
    variant: dict[str, Any] | None,
    available: int | None,
) -> tuple[int | None, int | None]:
    """Return (current_price, available) for a line seen as its variant."""
    price = listing.get("price_ngwee")
    current_price = price if isinstance(price, int) else None
    if variant is None or variant.get("status") != "active":
        return current_price, 0
    if isinstance(variant.get("price_ngwee"), int):
        current_price = int(variant["price_ngwee"])
    variant_stock = variant.get("stock_qty")
    # available is None only when the listing's stock is not governed at all
    # (always-available / made-to-order); variant stock does not apply then.
    if isinstance(variant_stock, int) and available is not None:
        available = min(available, max(variant_stock, 0))
    return current_price, available


def _available_qty(
    listing: dict[str, Any],
    *,
    pickup_location_id: str | None = None,
) -> int | None:
    if listing.get("status") != "active":
        return 0
    product_class = str(listing.get("product_class") or "A")
    fulfilment_mode = str(listing.get("fulfilment_mode") or "stocked")
    if product_class == "E" or fulfilment_mode == "made_to_order":
        return None
    stock_mode = listing.get("stock_mode")
    if stock_mode == "always_available":
        return None

    listing_id = str(listing["id"])
    if is_branch_tracked(listing_id):
        if pickup_location_id is None:
            return 0
        return available_qty_at_location(listing_id, pickup_location_id)

    stock_qty = listing.get("stock_qty")
    if isinstance(stock_qty, int):
        return max(stock_qty, 0)
    return 0


def revalidate_lines(lines: list[CartLineSnapshot]) -> RevalidateResult:
    listing_ids = [line.listing_id for line in lines]
    listings = _fetch_listings(listing_ids)
    variants = _fetch_variants(
        sorted({line.listing_variant_id for line in lines if line.listing_variant_id})
    )
    notices: list[ChangeNotice] = []

    for line in lines:
        listing = listings.get(line.listing_id)
        if listing is None:
            notices.append(
                ChangeNotice(
                    listing_id=line.listing_id,
                    kind="out_of_stock",
                    requested_qty=line.qty,
                    available_qty=0,
                    snapshot_price_ngwee=line.unit_price_ngwee,
                    current_price_ngwee=None,
                )
            )
            continue

        current_price = listing.get("price_ngwee")
        current_price_ngwee = current_price if isinstance(current_price, int) else None
        available = _available_qty(listing, pickup_location_id=line.pickup_location_id)
        if line.listing_variant_id:
            current_price_ngwee, available = _apply_variant(
                listing, variants.get(line.listing_variant_id), available
            )

        if current_price_ngwee is not None and current_price_ngwee != line.unit_price_ngwee:
            notices.append(
                ChangeNotice(
                    listing_id=line.listing_id,
                    kind="price_changed",
                    requested_qty=line.qty,
                    available_qty=available,
                    snapshot_price_ngwee=line.unit_price_ngwee,
                    current_price_ngwee=current_price_ngwee,
                )
            )

        if available is not None and available <= 0:
            notices.append(
                ChangeNotice(
                    listing_id=line.listing_id,
                    kind="out_of_stock",
                    requested_qty=line.qty,
                    available_qty=0,
                    snapshot_price_ngwee=line.unit_price_ngwee,
                    current_price_ngwee=current_price_ngwee,
                )
            )
            continue

        if available is not None and line.qty > available:
            notices.append(
                ChangeNotice(
                    listing_id=line.listing_id,
                    kind="qty_reduced",
                    requested_qty=line.qty,
                    available_qty=available,
                    snapshot_price_ngwee=line.unit_price_ngwee,
                    current_price_ngwee=current_price_ngwee,
                )
            )

    notice_tuple = tuple(notices)
    return RevalidateResult(notices=notice_tuple, has_changes=bool(notice_tuple))
