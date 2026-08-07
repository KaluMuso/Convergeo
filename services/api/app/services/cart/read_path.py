"""Cart read-path access filtering and server-derived presentation for GET cart.

Checkout re-derivation (`checkout._rederive_line_prices`) and cart merge
(`merge_cart_items`) already enforce wholesale visibility on their paths. This
module closes the GET /cart gap: stored lines must not leak wholesale-only
listings or stale tier prices to ineligible callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.errors import AppError
from app.services.cart.merge import MergeConflict, validate_item_qty_for_listing
from app.services.rfq.listing_cart_authority import (
    is_rfq_pinned_line,
    validate_rfq_pinned_line_authority,
)


def listing_cart_access_conflict(
    listing_id: str,
    listing: dict[str, Any] | None,
    *,
    business_eligible: bool,
) -> MergeConflict | None:
    """Return a non-disclosing conflict when the line must not be shown, else None.

    Mirrors ``merge_cart_items`` and ``checkout._rederive_line_prices`` wholesale
    gating so add / read / checkout stay aligned (CAN-CAT-003, CAN-ORD-003).
    """
    if listing is None:
        return MergeConflict(
            listing_id=listing_id,
            code="cart.listing_unavailable",
            message_key="cart.listing_unavailable",
            details={"listing_id": listing_id, "retry": False},
        )

    # D36 — wholesale-only listings are omitted from consumer surfaces. Reuse the
    # same conflict as a missing id so the response does not confirm B2B stock.
    if listing.get("wholesale") and not business_eligible:
        return MergeConflict(
            listing_id=listing_id,
            code="cart.listing_unavailable",
            message_key="cart.listing_unavailable",
            details={"listing_id": listing_id, "retry": False},
        )

    if listing.get("status") != "active":
        return MergeConflict(
            listing_id=listing_id,
            code="cart.listing_inactive",
            message_key="cart.listing_inactive",
            details={"listing_id": listing_id, "status": listing.get("status")},
        )

    return None


@dataclass(frozen=True, slots=True)
class PreparedCartRead:
    """Cart lines safe to present plus conflicts for omitted lines."""

    items: list[dict[str, Any]]
    conflicts: list[MergeConflict]


def prepare_cart_items_for_read(
    items: list[dict[str, Any]],
    listings_by_id: dict[str, dict[str, Any]],
    *,
    business_eligible: bool,
    customer_id: str | None = None,
    rfq_threads_by_id: dict[str, dict[str, Any]] | None = None,
) -> PreparedCartRead:
    """Filter inaccessible lines and derive current prices for the read path.

    RFQ-pinned lines keep their authoritative accepted quote price and bypass
    wholesale omission (accepted-quote semantics). When ``customer_id`` and thread
    rows are supplied, RFQ party ownership and accepted status are enforced.
    """
    accessible: list[dict[str, Any]] = []
    conflicts: list[MergeConflict] = []

    for item in items:
        listing_id = str(item["listing_id"])
        listing = listings_by_id.get(listing_id)
        rfq_pinned = is_rfq_pinned_line(item)

        if not rfq_pinned:
            access_conflict = listing_cart_access_conflict(
                listing_id,
                listing,
                business_eligible=business_eligible,
            )
            if access_conflict is not None:
                conflicts.append(access_conflict)
                continue

        if rfq_pinned:
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
                        details={
                            "listing_id": listing_id,
                            "status": listing.get("status"),
                        },
                    )
                )
                continue

            if customer_id is not None and rfq_threads_by_id is not None:
                thread_id = str(item["rfq_thread_id"]).strip()
                _, conflict_code, conflict_details = validate_rfq_pinned_line_authority(
                    rfq_thread_id=thread_id,
                    customer_id=customer_id,
                    listing_id=listing_id,
                    stored_unit_price_ngwee=int(item["unit_price_ngwee"]),
                    thread=rfq_threads_by_id.get(thread_id),
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
                    continue

            accessible.append(dict(item))
            continue

        # listing is present and access-checked above.
        assert listing is not None
        try:
            fresh_price, fresh_wholesale = validate_item_qty_for_listing(
                listing=listing,
                qty=int(item["qty"]),
                business_eligible=business_eligible,
            )
        except AppError as exc:
            conflicts.append(
                MergeConflict(
                    listing_id=listing_id,
                    code=exc.code,
                    message_key=exc.code,
                    details=dict(exc.details),
                )
            )
            continue

        presented = dict(item)
        presented["unit_price_ngwee"] = fresh_price
        presented["wholesale"] = fresh_wholesale
        accessible.append(presented)

    return PreparedCartRead(items=accessible, conflicts=conflicts)
