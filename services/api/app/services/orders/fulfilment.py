"""Server-authoritative fulfilment and delivery fees for ``POST /orders``.

The buyer chooses delivery or pickup per vendor at the fulfilment step, which
records those choices on the checkout group. When the order is placed, each
vendor group's fulfilment type and delivery fee are recomputed from that record,
the buyer's saved address and the live zone/fee rules. The ``groups`` a client
sends are only compared with the result: a request that declares delivery at
the pickup fee, or moves fees between vendors, is refused rather than trusted.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.errors import AppError
from app.services.cart.totals import line_total_ngwee
from app.services.logistics.delivery_pricing import GroupDeliveryPrice
from app.services.orders.create import CartLineInput, Fulfilment, VendorFulfilmentInput

FULFILMENT_NOT_CONFIRMED = "orders.fulfilment_not_confirmed"
FULFILMENT_MISMATCH = "orders.fulfilment_mismatch"


@dataclass(frozen=True, slots=True)
class StoredChoice:
    vendor_id: str
    fulfilment: Fulfilment
    delivery_zone: str | None
    #: Live area-pair fee quoted at the fulfilment step (None: zone fee applies).
    area_fee_ngwee: int | None = None
    area_quoted_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DeclaredGroup:
    vendor_id: str
    fulfilment: str
    delivery_zone: str | None
    delivery_fee_ngwee: int
    subtotal_ngwee: int


def _not_confirmed() -> AppError:
    return AppError(
        code=FULFILMENT_NOT_CONFIRMED,
        message="Choose delivery or pickup again before placing the order",
        http_status=409,
        details={"redirect_to": "fulfilment", "retry": False},
    )


def _mismatch(vendor_id: str | None, field: str) -> AppError:
    details: dict[str, Any] = {"redirect_to": "fulfilment", "field": field, "retry": False}
    if vendor_id is not None:
        details["vendor_id"] = vendor_id
    return AppError(
        code=FULFILMENT_MISMATCH,
        message="Fulfilment or delivery fee does not match the checkout session",
        http_status=409,
        details=details,
    )


def parse_stored_choices(raw: object) -> dict[str, StoredChoice]:
    """Read ``checkout_groups.fulfilment_choices``; a missing or bad record refuses."""
    if not isinstance(raw, list) or not raw:
        raise _not_confirmed()
    choices: dict[str, StoredChoice] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            raise _not_confirmed()
        vendor_id = entry.get("vendor_id")
        fulfilment = entry.get("fulfilment")
        zone = entry.get("delivery_zone")
        if not isinstance(vendor_id, str) or fulfilment not in ("delivery", "pickup"):
            raise _not_confirmed()
        if zone is not None and not isinstance(zone, str):
            raise _not_confirmed()
        if vendor_id in choices:
            raise _not_confirmed()
        area_fee, quoted_at = _stored_area_quote(entry)
        choices[vendor_id] = StoredChoice(
            vendor_id=vendor_id,
            fulfilment="delivery" if fulfilment == "delivery" else "pickup",
            delivery_zone=zone,
            area_fee_ngwee=area_fee,
            area_quoted_at=quoted_at,
        )
    return choices


def _stored_area_quote(entry: Mapping[str, Any]) -> tuple[int | None, datetime | None]:
    fee = entry.get("area_fee_ngwee")
    raw_at = entry.get("area_quoted_at")
    if fee is None and raw_at is None:
        return None, None
    if isinstance(fee, bool) or not isinstance(fee, int) or fee < 0 or not isinstance(raw_at, str):
        raise _not_confirmed()
    try:
        quoted_at = datetime.fromisoformat(raw_at)
    except ValueError as exc:
        raise _not_confirmed() from exc
    if quoted_at.tzinfo is None:
        raise _not_confirmed()
    return fee, quoted_at


def stored_area_fees(
    choices: Mapping[str, StoredChoice], *, now: datetime, ttl_minutes: int
) -> dict[str, int] | None:
    """Area-pair fees fixed at the fulfilment step, or None when the zone fee applies.

    The price shown at checkout holds for ``ttl_minutes``; after that the buyer
    confirms fulfilment again (never a silent re-price at order time).
    """
    quoted = {
        v: c
        for v, c in choices.items()
        if c.fulfilment == "delivery" and c.area_fee_ngwee is not None
    }
    if not quoted:
        return None
    for choice in quoted.values():
        assert choice.area_quoted_at is not None
        if now - choice.area_quoted_at > timedelta(minutes=ttl_minutes):
            raise _not_confirmed()
    return {v: int(c.area_fee_ngwee or 0) for v, c in quoted.items()}


def needs_delivery(choices: Mapping[str, StoredChoice]) -> bool:
    return any(choice.fulfilment == "delivery" for choice in choices.values())


def authoritative_vendor_groups(
    *,
    cart_lines: Sequence[CartLineInput],
    stored_choices: Mapping[str, StoredChoice],
    declared_groups: Sequence[DeclaredGroup],
    address_zone: str | None,
    compute_fee: Callable[[int, str | None], int],
    pricing: Mapping[str, GroupDeliveryPrice] | None = None,
) -> list[VendorFulfilmentInput]:
    """Recompute every vendor group server-side; refuse a request that disagrees.

    ``address_zone`` is the zone of the order's delivery address under today's
    rules (``None`` when no delivery group exists). ``compute_fee`` prices one
    group from its cart-derived subtotal and zone. ``pricing`` (logistics
    phase 1) carries who pays delivery per vendor; when given, the customer fee
    and funding come from it so both checkout steps agree byte for byte.
    """
    subtotals: dict[str, int] = {}
    for line in cart_lines:
        subtotals[line.vendor_id] = subtotals.get(line.vendor_id, 0) + line_total_ngwee(
            line.qty, line.unit_price_ngwee
        )

    if set(stored_choices) != set(subtotals):
        # The cart's vendors changed after the fulfilment step was confirmed.
        raise _not_confirmed()

    declared: dict[str, DeclaredGroup] = {}
    for group in declared_groups:
        if group.vendor_id in declared:
            raise _mismatch(group.vendor_id, "vendor_id")
        declared[group.vendor_id] = group
    if set(declared) != set(subtotals):
        raise _mismatch(None, "groups")

    authoritative: list[VendorFulfilmentInput] = []
    for vendor_id in sorted(subtotals):
        choice = stored_choices[vendor_id]
        subtotal = subtotals[vendor_id]
        if choice.fulfilment == "delivery":
            if address_zone is None or address_zone != choice.delivery_zone:
                # The saved address no longer prices into the zone the buyer was quoted.
                raise _mismatch(vendor_id, "delivery_zone")
            zone: str | None = address_zone
            price = pricing.get(vendor_id) if pricing is not None else None
            fee = price.customer_fee_ngwee if price is not None else compute_fee(subtotal, zone)
        else:
            zone = None
            fee = 0
            price = None
        claim = declared[vendor_id]
        if claim.fulfilment != choice.fulfilment:
            raise _mismatch(vendor_id, "fulfilment")
        if (claim.delivery_zone or None) != zone:
            raise _mismatch(vendor_id, "delivery_zone")
        if claim.delivery_fee_ngwee != fee:
            raise _mismatch(vendor_id, "delivery_fee_ngwee")
        if claim.subtotal_ngwee != subtotal:
            # Same code the session-total checks use: the cart moved under the buyer.
            raise AppError(
                code="orders.totals_mismatch",
                message="Vendor group subtotal mismatch",
                http_status=409,
                details={"vendor_id": vendor_id},
            )
        authoritative.append(
            VendorFulfilmentInput(
                vendor_id=vendor_id,
                fulfilment=choice.fulfilment,
                delivery_zone=zone,
                delivery_fee_ngwee=fee,
                subtotal_ngwee=subtotal,
                delivery_funding=price.funding if price is not None else "customer",
                delivery_funded_ngwee=price.funded_ngwee if price is not None else 0,
            )
        )
    return authoritative
