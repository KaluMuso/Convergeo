from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.errors import AppError
from app.services.cart.totals import select_unit_price_ngwee, validate_moq
from app.services.rfq.listing_cart_authority import (
    is_rfq_pinned_line,
    validate_rfq_pinned_line_authority,
)


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
    rfq_thread_id: str | None = None


def _find_item_for_listing(items: list[dict[str, Any]], listing_id: str) -> dict[str, Any] | None:
    for item in items:
        if str(item["listing_id"]) == listing_id:
            return item
    return None


def _validate_rfq_merge_line(
    item: dict[str, Any],
    listing_id: str,
    *,
    customer_id: str | None,
    rfq_threads_by_id: dict[str, dict[str, Any]] | None,
) -> tuple[int, str | None, str | None, dict[str, Any]]:
    """Return (quote_price, rfq_thread_id, conflict_code, conflict_details)."""
    thread_id = str(item["rfq_thread_id"]).strip()
    stored_price = int(item["unit_price_ngwee"])
    if customer_id is None or rfq_threads_by_id is None:
        return stored_price, thread_id, None, {}

    authority, conflict_code, conflict_details = validate_rfq_pinned_line_authority(
        rfq_thread_id=thread_id,
        customer_id=customer_id,
        listing_id=listing_id,
        stored_unit_price_ngwee=stored_price,
        thread=rfq_threads_by_id.get(thread_id),
    )
    if conflict_code is not None:
        return stored_price, thread_id, conflict_code, conflict_details
    assert authority is not None
    return authority.quote_price_ngwee, thread_id, None, {}


def _merge_rfq_duplicate(
    *,
    listing_id: str,
    user_item: dict[str, Any],
    guest_item: dict[str, Any],
    customer_id: str | None,
    rfq_threads_by_id: dict[str, dict[str, Any]] | None,
) -> tuple[dict[str, Any] | None, MergeConflict | None]:
    user_thread = str(user_item["rfq_thread_id"]).strip()
    guest_thread = str(guest_item["rfq_thread_id"]).strip()
    if user_thread != guest_thread:
        return None, MergeConflict(
            listing_id=listing_id,
            code="cart.rfq_merge_conflict",
            message_key="cart.rfq_merge_conflict",
            details={
                "listing_id": listing_id,
                "user_rfq_thread_id": user_thread,
                "guest_rfq_thread_id": guest_thread,
                "retry": True,
            },
        )

    qty = int(user_item["qty"]) + int(guest_item["qty"])
    merged_item = {**user_item, "qty": qty}
    price, thread_id, conflict_code, conflict_details = _validate_rfq_merge_line(
        merged_item,
        listing_id,
        customer_id=customer_id,
        rfq_threads_by_id=rfq_threads_by_id,
    )
    if conflict_code is not None:
        return None, MergeConflict(
            listing_id=listing_id,
            code=conflict_code,
            message_key=conflict_code,
            details=conflict_details,
        )
    return {**merged_item, "unit_price_ngwee": price, "rfq_thread_id": thread_id}, None


def _resolve_rfq_vs_ordinary(
    *,
    listing_id: str,
    rfq_item: dict[str, Any],
    ordinary_item: dict[str, Any],
    customer_id: str | None,
    rfq_threads_by_id: dict[str, dict[str, Any]] | None,
) -> tuple[dict[str, Any] | None, list[MergeConflict]]:
    price, thread_id, conflict_code, conflict_details = _validate_rfq_merge_line(
        rfq_item,
        listing_id,
        customer_id=customer_id,
        rfq_threads_by_id=rfq_threads_by_id,
    )
    if conflict_code is not None:
        return None, [
            MergeConflict(
                listing_id=listing_id,
                code=conflict_code,
                message_key=conflict_code,
                details=conflict_details,
            )
        ]

    conflicts: list[MergeConflict] = []
    if int(ordinary_item["qty"]) > 0:
        conflicts.append(
            MergeConflict(
                listing_id=listing_id,
                code="cart.rfq_merge_conflict",
                message_key="cart.rfq_merge_conflict",
                details={
                    "listing_id": listing_id,
                    "rfq_thread_id": thread_id,
                    "ordinary_qty_dropped": int(ordinary_item["qty"]),
                    "retry": True,
                },
            )
        )

    return (
        {
            **rfq_item,
            "qty": int(rfq_item["qty"]),
            "unit_price_ngwee": price,
            "rfq_thread_id": thread_id,
        },
        conflicts,
    )


def _append_merged_rfq_item(
    *,
    listing_id: str,
    listing: dict[str, Any],
    item: dict[str, Any],
    customer_id: str | None,
    rfq_threads_by_id: dict[str, dict[str, Any]] | None,
    result: list[MergedCartItem],
    conflicts: list[MergeConflict],
) -> None:
    if listing.get("status") != "active":
        conflicts.append(
            MergeConflict(
                listing_id=listing_id,
                code="cart.listing_inactive",
                message_key="cart.listing_inactive",
                details={"listing_id": listing_id, "status": listing.get("status")},
            )
        )
        return

    price, thread_id, conflict_code, conflict_details = _validate_rfq_merge_line(
        item,
        listing_id,
        customer_id=customer_id,
        rfq_threads_by_id=rfq_threads_by_id,
    )
    if conflict_code is not None:
        conflicts.append(
            MergeConflict(
                listing_id=listing_id,
                code=conflict_code,
                message_key=conflict_code,
                details=conflict_details,
            )
        )
        return

    qty = int(item["qty"])
    result.append(
        MergedCartItem(
            listing_id=listing_id,
            qty=qty,
            unit_price_ngwee=price,
            wholesale=False,
            rfq_thread_id=thread_id,
        )
    )


def merge_cart_items(
    *,
    user_items: list[dict[str, Any]],
    guest_items: list[dict[str, Any]],
    listings_by_id: dict[str, dict[str, Any]],
    business_eligible: bool = False,
    customer_id: str | None = None,
    rfq_threads_by_id: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[MergedCartItem], list[MergeConflict]]:
    """Merge guest + user cart lines: qty-sum duplicates, refresh prices, surface conflicts.

    The wholesale flag is re-derived from the listing AND ``business_eligible`` — never
    trusted from the stored line.

    RFQ-pinned lines keep their authoritative accepted quote price (via
    ``listing_cart_authority``) and never silently re-price to listing tiers.
    """
    listing_ids: set[str] = set()
    for item in user_items + guest_items:
        listing_ids.add(str(item["listing_id"]))

    result: list[MergedCartItem] = []
    conflicts: list[MergeConflict] = []

    for listing_id in listing_ids:
        user_item = _find_item_for_listing(user_items, listing_id)
        guest_item = _find_item_for_listing(guest_items, listing_id)
        user_rfq = user_item is not None and is_rfq_pinned_line(user_item)
        guest_rfq = guest_item is not None and is_rfq_pinned_line(guest_item)

        if user_rfq and guest_rfq:
            assert user_item is not None and guest_item is not None
            merged_rfq, rfq_conflict = _merge_rfq_duplicate(
                listing_id=listing_id,
                user_item=user_item,
                guest_item=guest_item,
                customer_id=customer_id,
                rfq_threads_by_id=rfq_threads_by_id,
            )
            if rfq_conflict is not None:
                conflicts.append(rfq_conflict)
                continue
            listing = listings_by_id.get(listing_id)
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
            assert merged_rfq is not None
            _append_merged_rfq_item(
                listing_id=listing_id,
                listing=listing,
                item=merged_rfq,
                customer_id=customer_id,
                rfq_threads_by_id=rfq_threads_by_id,
                result=result,
                conflicts=conflicts,
            )
            continue

        if user_rfq or guest_rfq:
            rfq_item = user_item if user_rfq else guest_item
            ordinary_item = guest_item if user_rfq else user_item
            assert rfq_item is not None
            if ordinary_item is not None and not is_rfq_pinned_line(ordinary_item):
                resolved, mixed_conflicts = _resolve_rfq_vs_ordinary(
                    listing_id=listing_id,
                    rfq_item=rfq_item,
                    ordinary_item=ordinary_item,
                    customer_id=customer_id,
                    rfq_threads_by_id=rfq_threads_by_id,
                )
                conflicts.extend(mixed_conflicts)
                if resolved is None:
                    continue
                listing = listings_by_id.get(listing_id)
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
                _append_merged_rfq_item(
                    listing_id=listing_id,
                    listing=listing,
                    item=resolved,
                    customer_id=customer_id,
                    rfq_threads_by_id=rfq_threads_by_id,
                    result=result,
                    conflicts=conflicts,
                )
                continue

            listing = listings_by_id.get(listing_id)
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
            _append_merged_rfq_item(
                listing_id=listing_id,
                listing=listing,
                item=rfq_item,
                customer_id=customer_id,
                rfq_threads_by_id=rfq_threads_by_id,
                result=result,
                conflicts=conflicts,
            )
            continue

        # Ordinary lines — aggregate qty across user + guest.
        qty = 0
        if user_item is not None:
            qty += int(user_item["qty"])
        if guest_item is not None:
            qty += int(guest_item["qty"])

        listing = listings_by_id.get(listing_id)

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

        if listing.get("wholesale") and not business_eligible:
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

        wholesale = bool(listing.get("wholesale", False)) and business_eligible
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

        if user_item is not None and int(user_item.get("unit_price_ngwee", 0)) != unit_price:
            conflicts.append(
                MergeConflict(
                    listing_id=listing_id,
                    code="cart.price_changed",
                    message_key="cart.price_changed",
                    details={
                        "previous_unit_price_ngwee": int(user_item["unit_price_ngwee"]),
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
    business_eligible: bool = False,
) -> tuple[int, bool]:
    """Return refreshed unit price and wholesale flag; raises AppError on MOQ violation.

    Wholesale pricing/MOQ only apply when the buyer is a verified business
    (``business_eligible``); otherwise the line is priced at retail regardless of the
    listing's wholesale flag.
    """
    wholesale = bool(listing.get("wholesale", False)) and business_eligible
    min_steps = int(listing.get("min_steps") or 1)
    if qty < min_steps:
        raise AppError(
            code="cart.min_steps_violation",
            message="Quantity is below the minimum number of sale increments",
            http_status=400,
            details={"min_steps": min_steps, "qty": qty, "retry": True},
        )
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
