from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.services.stock.claim import run_sql_script, sql_uuid

ChangeNoticeKind = Literal["price_changed", "out_of_stock", "qty_reduced"]


@dataclass(frozen=True, slots=True)
class CartLineSnapshot:
    listing_id: str
    qty: int
    unit_price_ngwee: int


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
        SELECT id::text, price_ngwee::text, stock_mode, stock_qty::text, status
        FROM public.vendor_listings
        WHERE id IN ({id_literals});
        """
    )
    if not result.ok:
        raise RuntimeError(f"fetch listings failed: {result.error}")

    listings: dict[str, dict[str, Any]] = {}
    for row in result.rows:
        parts = row.split("|")
        if len(parts) != 5:
            continue
        listing_id, price_raw, stock_mode, stock_qty_raw, status = parts
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
        }
    return listings


def _available_qty(listing: dict[str, Any]) -> int | None:
    if listing.get("status") != "active":
        return 0
    stock_mode = listing.get("stock_mode")
    if stock_mode == "always_available":
        return None
    stock_qty = listing.get("stock_qty")
    if isinstance(stock_qty, int):
        return max(stock_qty, 0)
    return 0


def revalidate_lines(lines: list[CartLineSnapshot]) -> RevalidateResult:
    listing_ids = [line.listing_id for line in lines]
    listings = _fetch_listings(listing_ids)
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
        available = _available_qty(listing)

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
