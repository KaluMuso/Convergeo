"""Product-class guards shared by listing create and cart mutations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.errors import AppError
from app.services.inventory.location_stock import validate_branch_stock_qty


def is_made_to_order_listing(listing: dict[str, Any]) -> bool:
    product_class = str(listing.get("product_class") or "A")
    if product_class == "E":
        return True
    return str(listing.get("fulfilment_mode") or "stocked") == "made_to_order"


def is_used_class_listing(listing: dict[str, Any]) -> bool:
    product_class = str(listing.get("product_class") or "A")
    if product_class == "D":
        return True
    return str(listing.get("condition") or "") == "used"


def listing_lead_time_days(listing: dict[str, Any]) -> int | None:
    if not is_made_to_order_listing(listing):
        return None
    raw = listing.get("lead_time_days")
    if isinstance(raw, int) and raw > 0:
        return raw
    return None


QUOTE_REQUIRED_PRICING_MODES = frozenset({"quote_only", "range"})


def listing_requires_accepted_quote(listing: dict[str, Any]) -> bool:
    """Range and quote-only listings cannot enter checkout at the listed price."""
    return str(listing.get("pricing_mode") or "fixed") in QUOTE_REQUIRED_PRICING_MODES


def validate_listing_purchasable_for_cart(
    *,
    listing: dict[str, Any],
    qty: int,
    evidence_image_count: int,
    weekly_committed_qty: int = 0,
    location_id: str | None = None,
    customer_released: bool = True,
    has_accepted_quote: bool = False,
) -> None:
    """Raise AppError when a listing fails class-specific cart rules."""
    product_class = str(listing.get("product_class") or "A")
    if product_class in {"C", "D", "E"} and not customer_released:
        raise AppError(
            code="cart.product_class_release_gated",
            message=f"Product Class {product_class} is not available to customers yet",
            http_status=403,
            details={
                "message_key": "cart.product_class_release_gated",
                "listing_id": str(listing.get("id", "")),
                "product_class": product_class,
                "retry": False,
            },
        )

    if listing_requires_accepted_quote(listing) and not has_accepted_quote:
        raise AppError(
            code="cart.quote_required",
            message="This listing requires an accepted vendor quote before purchase",
            http_status=400,
            details={
                "message_key": "cart.quote_required",
                "listing_id": str(listing.get("id", "")),
                "pricing_mode": str(listing.get("pricing_mode") or "fixed"),
                "retry": False,
            },
        )

    if is_used_class_listing(listing):
        condition = str(listing.get("condition") or "")
        if condition == "new":
            raise AppError(
                code="cart.class_d_invalid_condition",
                message="Used listings cannot be sold as new",
                http_status=400,
                details={
                    "message_key": "cart.class_d_invalid_condition",
                    "listing_id": str(listing.get("id", "")),
                    "retry": False,
                },
            )
        if evidence_image_count < 1:
            raise AppError(
                code="cart.class_d_missing_evidence",
                message="Used listings require photographic evidence before purchase",
                http_status=400,
                details={
                    "message_key": "cart.class_d_missing_evidence",
                    "listing_id": str(listing.get("id", "")),
                    "retry": False,
                },
            )

    if is_made_to_order_listing(listing):
        lead_time = listing_lead_time_days(listing)
        if lead_time is None:
            raise AppError(
                code="cart.class_e_missing_lead_time",
                message="Made-to-order listing is missing lead time",
                http_status=400,
                details={
                    "message_key": "cart.class_e_missing_lead_time",
                    "listing_id": str(listing.get("id", "")),
                    "retry": False,
                },
            )
        if str(listing.get("product_class") or "A") == "E":
            capacity = listing.get("vendor_capacity_per_week")
            if not isinstance(capacity, int) or capacity <= 0:
                raise AppError(
                    code="cart.class_e_missing_capacity",
                    message="Made-to-order listing is missing weekly capacity",
                    http_status=400,
                    details={
                        "message_key": "cart.class_e_missing_capacity",
                        "listing_id": str(listing.get("id", "")),
                        "retry": False,
                    },
                )
            remaining = capacity - weekly_committed_qty
            if qty > remaining:
                raise AppError(
                    code="cart.class_e_capacity_exceeded",
                    message="Weekly made-to-order capacity exceeded",
                    http_status=400,
                    details={
                        "message_key": "cart.class_e_capacity_exceeded",
                        "listing_id": str(listing.get("id", "")),
                        "capacity_per_week": capacity,
                        "remaining": max(remaining, 0),
                        "requested_qty": qty,
                        "retry": True,
                    },
                )
        return

    validate_branch_stock_qty(listing, qty, location_id=location_id)


def iso_week_start_utc() -> datetime:
    now = datetime.now(UTC)
    week_start = now - timedelta(days=now.weekday())
    return week_start.replace(hour=0, minute=0, second=0, microsecond=0)


def count_weekly_committed_qty(client: Any, listing_id: str) -> int:
    """Sum qty for this listing on non-cancelled orders placed since ISO week start."""
    week_start = iso_week_start_utc().isoformat()
    order_items = (
        client.table("order_item_products")
        .select("order_items!inner(qty, orders!inner(status, created_at))")
        .eq("listing_id", listing_id)
        .gte("order_items.orders.created_at", week_start)
        .execute()
    )
    rows = order_items.data if isinstance(order_items.data, list) else []
    cancelled = frozenset({"cancelled", "refunded"})
    total = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        order_item = row.get("order_items")
        if isinstance(order_item, list):
            order_item = order_item[0] if order_item else None
        if not isinstance(order_item, dict):
            continue
        order = order_item.get("orders")
        if isinstance(order, list):
            order = order[0] if order else None
        if not isinstance(order, dict):
            continue
        status = str(order.get("status") or "")
        if status in cancelled:
            continue
        qty = order_item.get("qty")
        if isinstance(qty, int):
            total += qty
    return total


def count_listing_images(client: Any, listing_id: str) -> int:
    response = (
        client.table("listing_images")
        .select("id", count="exact")
        .eq("listing_id", listing_id)
        .execute()
    )
    count = getattr(response, "count", None)
    if isinstance(count, int):
        return count
    rows = response.data if isinstance(response.data, list) else []
    return len(rows)
