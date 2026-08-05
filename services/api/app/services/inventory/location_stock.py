"""Per-branch stock resolution for cart validation and checkout claims (R02-P08)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.errors import AppError
from app.services.db import run_sql_script
from app.services.geo.distance import haversine_km

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

FulfilmentMode = Literal["pickup", "delivery"]


def _sql_uuid(value: str, field: str) -> str:
    if not _UUID_RE.match(value):
        raise ValueError(f"Invalid UUID for {field}")
    UUID(value)
    return f"'{value}'::uuid"


@dataclass(frozen=True, slots=True)
class BranchStockRow:
    location_id: str
    stock_qty: int
    lat: float
    lng: float
    status: str


def is_branch_tracked(listing_id: str) -> bool:
    """True when listing_location_stock rows exist and are authoritative."""
    listing_sql = _sql_uuid(listing_id, "listing_id")
    result = run_sql_script(
        f"""
        SELECT EXISTS (
          SELECT 1 FROM public.listing_location_stock
          WHERE listing_id = {listing_sql}
        )::text;
        """
    )
    if not result.ok or not result.rows:
        raise RuntimeError(f"branch-tracked check failed: {result.error}")
    return result.rows[0].lower() in {"t", "true"}


def fetch_branch_stock_rows(listing_id: str) -> tuple[BranchStockRow, ...]:
    listing_sql = _sql_uuid(listing_id, "listing_id")
    result = run_sql_script(
        f"""
        SELECT
          lls.location_id::text,
          lls.stock_qty::text,
          loc.lat::text,
          loc.lng::text,
          loc.status
        FROM public.listing_location_stock lls
        JOIN public.vendor_locations loc ON loc.id = lls.location_id
        WHERE lls.listing_id = {listing_sql};
        """
    )
    if not result.ok:
        raise RuntimeError(f"fetch branch stock failed: {result.error}")

    rows: list[BranchStockRow] = []
    for row in result.rows:
        parts = row.split("|")
        if len(parts) != 5:
            continue
        location_id, stock_raw, lat_raw, lng_raw, status = parts
        rows.append(
            BranchStockRow(
                location_id=location_id,
                stock_qty=int(stock_raw),
                lat=float(lat_raw),
                lng=float(lng_raw),
                status=status,
            )
        )
    return tuple(rows)


def available_qty_at_location(listing_id: str, location_id: str) -> int:
    if not is_branch_tracked(listing_id):
        return _legacy_available_qty(listing_id)
    listing_sql = _sql_uuid(listing_id, "listing_id")
    location_sql = _sql_uuid(location_id, "location_id")
    result = run_sql_script(
        f"""
        SELECT lls.stock_qty::text
        FROM public.listing_location_stock lls
        JOIN public.vendor_locations loc ON loc.id = lls.location_id
        WHERE lls.listing_id = {listing_sql}
          AND lls.location_id = {location_sql}
          AND loc.status = 'active';
        """
    )
    if not result.ok:
        raise RuntimeError(f"branch stock lookup failed: {result.error}")
    if not result.rows:
        return 0
    return max(int(result.rows[0]), 0)


def _legacy_available_qty(listing_id: str) -> int:
    listing_sql = _sql_uuid(listing_id, "listing_id")
    result = run_sql_script(
        f"""
        SELECT stock_qty::text
        FROM public.vendor_listings
        WHERE id = {listing_sql} AND status = 'active';
        """
    )
    if not result.ok or not result.rows:
        return 0
    raw = result.rows[0]
    if raw == "":
        return 0
    return max(int(raw), 0)


def _validate_location_belongs_to_listing(listing_id: str, location_id: str) -> None:
    listing_sql = _sql_uuid(listing_id, "listing_id")
    location_sql = _sql_uuid(location_id, "location_id")
    result = run_sql_script(
        f"""
        SELECT EXISTS (
          SELECT 1
          FROM public.listing_location_stock lls
          JOIN public.vendor_locations loc ON loc.id = lls.location_id
          JOIN public.vendor_listings vl ON vl.id = lls.listing_id
          WHERE lls.listing_id = {listing_sql}
            AND lls.location_id = {location_sql}
            AND loc.vendor_id = vl.vendor_id
            AND loc.status = 'active'
        )::text;
        """
    )
    if not result.ok or not result.rows or result.rows[0].lower() not in {"t", "true"}:
        raise AppError(
            code="cart.invalid_pickup_location",
            message="Selected branch is not valid for this listing",
            http_status=400,
            details={
                "message_key": "cart.invalid_pickup_location",
                "listing_id": listing_id,
                "location_id": location_id,
                "retry": False,
            },
        )


def nearest_branch_location_id(
    listing_id: str,
    *,
    lat: float,
    lng: float,
) -> str | None:
    """Return the nearest active branch carrying this listing (may have zero stock)."""
    branches = fetch_branch_stock_rows(listing_id)
    active = [row for row in branches if row.status == "active"]
    if not active:
        return None
    nearest = min(active, key=lambda row: haversine_km(lat, lng, row.lat, row.lng))
    return nearest.location_id


def resolve_stock_location_id(
    listing_id: str,
    *,
    pickup_location_id: str | None = None,
    fulfilment: FulfilmentMode | None = None,
    delivery_lat: float | None = None,
    delivery_lng: float | None = None,
) -> str | None:
    """Resolve which branch governs stock for this cart/checkout line.

    Returns ``None`` for legacy pooled listings (no branch rows).
    Raises AppError when branch-tracked but the location cannot be determined.
    """
    if not is_branch_tracked(listing_id):
        return None

    if pickup_location_id:
        _validate_location_belongs_to_listing(listing_id, pickup_location_id)
        return pickup_location_id

    if fulfilment == "delivery" and delivery_lat is not None and delivery_lng is not None:
        nearest = nearest_branch_location_id(listing_id, lat=delivery_lat, lng=delivery_lng)
        if nearest is None:
            raise AppError(
                code="cart.no_branch_available",
                message="No active branch found for this listing",
                http_status=400,
                details={
                    "message_key": "cart.no_branch_available",
                    "listing_id": listing_id,
                    "retry": False,
                },
            )
        return nearest

    raise AppError(
        code="cart.pickup_location_required",
        message="A pickup branch must be selected for this listing",
        http_status=400,
        details={
            "message_key": "cart.pickup_location_required",
            "listing_id": listing_id,
            "retry": False,
        },
    )


def validate_branch_stock_qty(
    listing: dict[str, Any],
    qty: int,
    *,
    location_id: str | None,
) -> None:
    """Raise AppError when tracked stock at the resolved branch is insufficient."""
    listing_id = str(listing.get("id", ""))
    stock_mode = str(listing.get("stock_mode") or "tracked")
    if stock_mode != "tracked":
        return

    product_class = str(listing.get("product_class") or "A")
    fulfilment_mode = str(listing.get("fulfilment_mode") or "stocked")
    if product_class == "E" or fulfilment_mode == "made_to_order":
        return

    if location_id is None:
        stock_qty = listing.get("stock_qty")
        if isinstance(stock_qty, int) and qty > stock_qty:
            raise AppError(
                code="cart.insufficient_stock",
                message="Requested quantity exceeds available stock",
                http_status=400,
                details={
                    "message_key": "cart.insufficient_stock",
                    "listing_id": listing_id,
                    "available_qty": max(stock_qty, 0),
                    "requested_qty": qty,
                    "retry": True,
                },
            )
        return

    available = available_qty_at_location(listing_id, location_id)
    if qty > available:
        raise AppError(
            code="cart.insufficient_stock",
            message="Requested quantity exceeds available stock at this branch",
            http_status=400,
            details={
                "message_key": "cart.insufficient_stock",
                "listing_id": listing_id,
                "location_id": location_id,
                "available_qty": available,
                "requested_qty": qty,
                "retry": True,
            },
        )
