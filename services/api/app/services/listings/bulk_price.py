from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from app.services.catalog.listing_price_review import listing_price_review_flags

AdjustmentKind = Literal["delta_ngwee", "percent_bps"]
MAX_BULK_LISTINGS = 200

SKIP_TIER_PRICING = "tier_pricing"
SKIP_NOT_FOUND = "not_found"
SKIP_NOT_OWNED = "not_owned"
SKIP_REMOVED = "removed_status"
SKIP_INVALID_PRICE = "invalid_new_price"


@dataclass(frozen=True, slots=True)
class BulkPriceRow:
    listing_id: str
    title: str
    old_price_ngwee: int | None
    new_price_ngwee: int | None
    applied: bool
    skip_reason: str | None
    warnings: list[str]


def _has_tier_pricing(price_tiers: Any) -> bool:
    if not isinstance(price_tiers, list):
        return False
    return len(price_tiers) > 0


def compute_new_price_ngwee(
    *,
    old_price_ngwee: int,
    adjustment_kind: AdjustmentKind,
    adjustment_value: int,
) -> int:
    if adjustment_kind == "delta_ngwee":
        return old_price_ngwee + adjustment_value
    scaled = (Decimal(old_price_ngwee) * (Decimal(10_000) + Decimal(adjustment_value))) / Decimal(
        10_000
    )
    return int(scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_bulk_price_rows(
    *,
    listing_ids: list[str],
    listings_by_id: dict[str, dict[str, Any]],
    vendor_id: str,
    adjustment_kind: AdjustmentKind,
    adjustment_value: int,
) -> list[BulkPriceRow]:
    rows: list[BulkPriceRow] = []
    for listing_id in listing_ids[:MAX_BULK_LISTINGS]:
        listing = listings_by_id.get(listing_id)
        if listing is None:
            rows.append(
                BulkPriceRow(
                    listing_id=listing_id,
                    title="",
                    old_price_ngwee=None,
                    new_price_ngwee=None,
                    applied=False,
                    skip_reason=SKIP_NOT_FOUND,
                    warnings=[],
                )
            )
            continue
        product = listing.get("products")
        product_name = product.get("name") if isinstance(product, dict) else None
        title = str(listing.get("title_override") or product_name or "")
        if str(listing.get("vendor_id")) != vendor_id:
            rows.append(
                BulkPriceRow(
                    listing_id=listing_id,
                    title=title,
                    old_price_ngwee=None,
                    new_price_ngwee=None,
                    applied=False,
                    skip_reason=SKIP_NOT_OWNED,
                    warnings=[],
                )
            )
            continue
        if listing.get("status") == "removed":
            rows.append(
                BulkPriceRow(
                    listing_id=listing_id,
                    title=title,
                    old_price_ngwee=None,
                    new_price_ngwee=None,
                    applied=False,
                    skip_reason=SKIP_REMOVED,
                    warnings=[],
                )
            )
            continue
        if _has_tier_pricing(listing.get("price_tiers")):
            old = listing.get("price_ngwee")
            rows.append(
                BulkPriceRow(
                    listing_id=listing_id,
                    title=title,
                    old_price_ngwee=int(old) if isinstance(old, int) else None,
                    new_price_ngwee=None,
                    applied=False,
                    skip_reason=SKIP_TIER_PRICING,
                    warnings=[],
                )
            )
            continue
        old_price = listing.get("price_ngwee")
        if not isinstance(old_price, int) or old_price < 0:
            rows.append(
                BulkPriceRow(
                    listing_id=listing_id,
                    title=title,
                    old_price_ngwee=None,
                    new_price_ngwee=None,
                    applied=False,
                    skip_reason=SKIP_INVALID_PRICE,
                    warnings=[],
                )
            )
            continue
        new_price = compute_new_price_ngwee(
            old_price_ngwee=old_price,
            adjustment_kind=adjustment_kind,
            adjustment_value=adjustment_value,
        )
        if new_price <= 0:
            rows.append(
                BulkPriceRow(
                    listing_id=listing_id,
                    title=title,
                    old_price_ngwee=old_price,
                    new_price_ngwee=None,
                    applied=False,
                    skip_reason=SKIP_INVALID_PRICE,
                    warnings=[],
                )
            )
            continue
        category_path = None
        product = listing.get("products")
        if isinstance(product, dict):
            category_path = product.get("category_path")
        warnings = listing_price_review_flags(
            price_ngwee=new_price,
            category_path=category_path if isinstance(category_path, str) else None,
            title=title or None,
        )
        rows.append(
            BulkPriceRow(
                listing_id=listing_id,
                title=title,
                old_price_ngwee=old_price,
                new_price_ngwee=new_price,
                applied=True,
                skip_reason=None,
                warnings=warnings,
            )
        )
    return rows