"""M18-P05 — mapping an intake draft onto the normal listing seam (D35).

This module is deliberately thin. It does **not** create listings; it translates
an intake draft into the exact ``ListingCreateRequest`` the vendor app would
have produced, so ``vendor_listings.create_listing_for_vendor`` remains the one
implementation of "what it means to create a listing". Anything an intake draft
cannot express — a ``used`` condition, a missing price — is refused here with a
stable reason rather than quietly coerced into something publishable.

Two invariants this file exists to keep:

* **Never active-by-default.** Every request built here carries
  ``publish=False``, so the resolved status is ``draft``. Activation is M18-P06's
  audited, gate-checked admin action and nothing else.
* **Money stays integer ngwee.** Prices pass through untouched; no float, no
  rounding, no currency conversion happens anywhere in the handoff.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from app.errors import AppError
from app.routers.vendor_listings import ListingCreateRequest

# Intake does not carry the complete used-offer evidence contract. Refuse used
# submissions rather than silently relabel them as refurbished.
_CONDITION_MAP: Final[dict[str, str]] = {
    "new": "new",
    "refurbished": "refurbished",
}

# made_to_order/always both mean "do not decrement a counter"; only `tracked`
# carries a quantity through.
_STOCK_MODE_MAP: Final[dict[str, str]] = {
    "tracked": "tracked",
    "made_to_order": "always_available",
    "always": "always_available",
}

REQUIRED_DRAFT_FIELDS: Final[tuple[str, ...]] = ("title", "price_ngwee", "condition")


class DraftNotSubmittable(AppError):
    """The draft cannot become a listing yet. Carries an i18n message key."""

    def __init__(self, reason: str, *, details: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "message_key": f"vendor.intake.errors.{reason}",
            "reason": reason,
        }
        if details:
            payload.update(details)
        super().__init__(
            code="intake_draft_not_submittable",
            message="Intake draft cannot be submitted as a listing",
            http_status=422,
            details=payload,
        )


def missing_fields(draft: dict[str, Any]) -> list[str]:
    """Required-for-submission fields the draft still lacks."""
    return [name for name in REQUIRED_DRAFT_FIELDS if draft.get(name) in (None, "")]


def build_listing_request(
    draft: dict[str, Any], *, product_id: str | None = None
) -> ListingCreateRequest:
    """Translate one ``intake_draft_fields`` row into a listing create request.

    Raises :class:`DraftNotSubmittable` — never returns a half-valid request.
    """
    absent = missing_fields(draft)
    if absent:
        raise DraftNotSubmittable("incomplete_draft", details={"missing": absent})

    title = str(draft["title"]).strip()
    if not title:
        raise DraftNotSubmittable("incomplete_draft", details={"missing": ["title"]})

    price_raw = draft["price_ngwee"]
    if not isinstance(price_raw, int) or isinstance(price_raw, bool):
        # A non-integer price means the draft never went through the ngwee path.
        raise DraftNotSubmittable("invalid_price")
    if price_raw <= 0:
        raise DraftNotSubmittable("invalid_price")

    condition = _CONDITION_MAP.get(str(draft["condition"]))
    if condition is None:
        raise DraftNotSubmittable(
            "unsupported_condition", details={"condition": str(draft["condition"])}
        )

    stock_mode = _STOCK_MODE_MAP.get(str(draft.get("stock_mode") or "always"))
    if stock_mode is None:
        raise DraftNotSubmittable(
            "unsupported_stock_mode", details={"stock_mode": str(draft.get("stock_mode"))}
        )

    stock_qty: int | None = None
    if stock_mode == "tracked":
        quantity = draft.get("quantity")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
            # Tracked stock without a countable quantity is not a listing we can
            # sell honestly; ask rather than guess zero.
            raise DraftNotSubmittable("missing_quantity")
        stock_qty = quantity

    # Normal Class A inventory must have canonical identity even while draft.
    # Only the vendor's explicit choice is used; extraction never guesses a match.
    try:
        selected_product = str(uuid.UUID(product_id)) if product_id else None
    except ValueError as exc:
        raise DraftNotSubmittable("canonical_required") from exc
    if selected_product is None:
        raise DraftNotSubmittable("canonical_required")
    return ListingCreateRequest(
        mode="attach",
        product_id=selected_product,
        title_override=title,
        price_ngwee=price_raw,
        condition=condition,  # type: ignore[arg-type]
        stock_mode=stock_mode,  # type: ignore[arg-type]
        stock_qty=stock_qty,
        publish=False,  # never active-by-default — M18-P06 owns activation
    )
