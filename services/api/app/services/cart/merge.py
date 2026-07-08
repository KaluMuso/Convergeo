from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.cart.totals import select_unit_price_ngwee, validate_moq


@dataclass(frozen=True, slots=True)
class MergeConflict:
    listing_id: str
    code: str
    message_key: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MergedCartItem:
    listing_id: str
    qty: int
    unit_price_ngwee: int
    wholesale: bool


def merge_cart_items(
    *,
    user_items: list[dict[str, Any]],
    guest_items: list[dict[str, Any]],
    listings_by_id: dict[str, dict[str, Any]],
) -> tuple[list[MergedCartItem], list[MergeConflict]]:
    """Merge guest + user cart lines: qty-sum duplicates, refresh prices, surface conflicts."""
    merged: dict[str, dict[str, Any]] = {}

    for source_items in (user_items, guest_items):
        for item in source_items:
            listing_id = str(item["listing_id"])
            merged.setdefault(
                listing_id,
                {
                    "qty": 0,
                    "wholesale": bool(item.get("wholesale", False)),
                },
            )
            merged[listing_id]["qty"] += int(item["qty"])
            if item.get("wholesale"):
                merged[listing_id]["wholesale"] = True

    result: list[MergedCartItem] = []
    conflicts: list[MergeConflict] = []

    for listing_id, aggregate in merged.items():
        listing = listings_by_id.get(listing_id)
        qty = int(aggregate["qty"])
        wholesale = bool(aggregate["wholesale"])

        if listing is None:
            conflicts.append(
                MergeConflict(
                    listing_id=listing_id,
                    code="cart.listing_unavailable",
                    message_key="cart.listing_unavailable",
                    details={"listing_id": listing_id, "retry": False},
                )
            )
            continue

        if listing.get("status") != "active":
            conflicts.append(
                MergeConflict(
                    listing_id=listing_id,
                    code="cart.listing_inactive",
                    message_key="cart.listing_inactive",
                    details={"listing_id": listing_id, "status": listing.get("status")},
                )
            )
            continue

        moq = int(listing.get("moq", 1))
        if wholesale and qty < moq:
            conflicts.append(
                MergeConflict(
                    listing_id=listing_id,
                    code="cart.moq_violation",
                    message_key="cart.moq_violation",
                    details={"moq": moq, "qty": qty, "retry": True},
                )
            )
            continue

        base_price = int(listing["price_ngwee"])
        tiers = listing.get("price_tiers")
        price_tiers = tiers if isinstance(tiers, list) else None
        unit_price = select_unit_price_ngwee(
            base_price_ngwee=base_price,
            wholesale=wholesale,
            qty=qty,
            price_tiers=price_tiers,
        )

        old_user = next(
            (i for i in user_items if str(i["listing_id"]) == listing_id),
            None,
        )
        if old_user is not None and int(old_user.get("unit_price_ngwee", 0)) != unit_price:
            conflicts.append(
                MergeConflict(
                    listing_id=listing_id,
                    code="cart.price_changed",
                    message_key="cart.price_changed",
                    details={
                        "previous_unit_price_ngwee": int(old_user["unit_price_ngwee"]),
                        "current_unit_price_ngwee": unit_price,
                    },
                )
            )

        result.append(
            MergedCartItem(
                listing_id=listing_id,
                qty=qty,
                unit_price_ngwee=unit_price,
                wholesale=wholesale,
            )
        )

    return result, conflicts


def validate_item_qty_for_listing(
    *,
    listing: dict[str, Any],
    qty: int,
) -> tuple[int, bool]:
    """Return refreshed unit price and wholesale flag; raises AppError on MOQ violation."""
    wholesale = bool(listing.get("wholesale", False))
    moq = int(listing.get("moq", 1))
    validate_moq(wholesale=wholesale, moq=moq, qty=qty)

    tiers = listing.get("price_tiers")
    price_tiers = tiers if isinstance(tiers, list) else None
    unit_price = select_unit_price_ngwee(
        base_price_ngwee=int(listing["price_ngwee"]),
        wholesale=wholesale,
        qty=qty,
        price_tiers=price_tiers,
    )
    return unit_price, wholesale
