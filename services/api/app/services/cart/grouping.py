from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FREE_DELIVERY_THRESHOLD_NGEWEE = 20_000


@dataclass(frozen=True, slots=True)
class CartLineView:
    id: str
    listing_id: str
    vendor_id: str
    qty: int
    unit_price_ngwee: int
    wholesale: bool
    line_total_ngwee: int
    title_override: str | None


@dataclass(frozen=True, slots=True)
class VendorGroupView:
    vendor_id: str
    items: tuple[CartLineView, ...]
    subtotal_ngwee: int
    delivery_eligible: bool


def group_by_vendor(
    lines: list[CartLineView],
    *,
    free_delivery_threshold_ngwee: int = FREE_DELIVERY_THRESHOLD_NGEWEE,
) -> list[VendorGroupView]:
    """Group cart lines by vendor with per-group subtotal and delivery eligibility."""
    by_vendor: dict[str, list[CartLineView]] = {}
    for line in lines:
        by_vendor.setdefault(line.vendor_id, []).append(line)

    groups: list[VendorGroupView] = []
    for vendor_id in sorted(by_vendor):
        items = tuple(by_vendor[vendor_id])
        subtotal = sum(item.line_total_ngwee for item in items)
        groups.append(
            VendorGroupView(
                vendor_id=vendor_id,
                items=items,
                subtotal_ngwee=subtotal,
                delivery_eligible=subtotal >= free_delivery_threshold_ngwee,
            )
        )
    return groups


def listing_vendor_map(listings: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(row["id"]): str(row["vendor_id"])
        for row in listings
        if isinstance(row.get("id"), str) and isinstance(row.get("vendor_id"), str)
    }
