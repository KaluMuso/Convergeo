"""Glue between the offer engine and cart / checkout / order placement (W8)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

from app.errors import AppError
from app.services.cart.grouping import CartLineView
from app.services.cart.tickets import TicketCartLine, with_pricing
from app.services.offers.allocation import split_line_units
from app.services.offers.engine import (
    GiftOutcome,
    OfferApplication,
    PricedCart,
    PricingLine,
    price_cart,
)
from app.services.offers.store import load_offers_for_pricing
from app.services.orders.create import CartLineInput

logger = logging.getLogger(__name__)

GIFT_KEY_PREFIX = "gift:"


@dataclass(frozen=True, slots=True)
class OfferPricing:
    priced: PricedCart

    def gifts_for_vendor(self, vendor_id: str) -> list[GiftOutcome]:
        return [gift for gift in self.priced.gifts if gift.vendor_id == vendor_id]

    def applications_for_vendor(self, vendor_id: str) -> list[OfferApplication]:
        return [a for a in self.priced.applications if a.vendor_id == vendor_id]


TICKET_KEY_PREFIX = "ticket:"


def ticket_key(line: TicketCartLine) -> str:
    return f"{TICKET_KEY_PREFIX}{line.id}"


def price_line_views(
    views: list[CartLineView],
    client: Any,
    *,
    customer_id: str | None = None,
) -> tuple[list[CartLineView], OfferPricing | None]:
    """Re-price cart views with live offers; unchanged views when flag is off."""
    priced_views, _tickets, pricing = price_unified(views, [], client, customer_id=customer_id)
    return priced_views, pricing


def price_unified(
    views: list[CartLineView],
    ticket_lines: list[TicketCartLine],
    client: Any,
    *,
    customer_id: str | None = None,
) -> tuple[list[CartLineView], list[TicketCartLine], OfferPricing | None]:
    """Price product views and event-ticket lines together (one engine pass).

    Ticket lines enter the engine as ``item_kind="event"`` keyed by event id,
    so an offer mixing a product and an event ticket (bundle / buy N pay M)
    prices across both kinds with one exact allocation. Unchanged inputs when
    the flag is off or nothing applies.
    """
    eligible = [v for v in views if not v.is_rfq_quote and v.qty > 0 and v.unit_price_ngwee > 0]
    tickets = [t for t in ticket_lines if t.available and t.qty > 0 and t.unit_price_ngwee > 0]
    if not eligible and not tickets:
        return views, ticket_lines, None
    vendor_ids = {v.vendor_id for v in eligible} | {t.vendor_id for t in tickets}
    loaded = load_offers_for_pricing(client, vendor_ids, customer_id=customer_id)
    if loaded is None:
        return views, ticket_lines, None
    offers, cap = loaded
    if not offers:
        return views, ticket_lines, None
    lines = [
        PricingLine(
            key=v.id,
            listing_id=v.listing_id,
            vendor_id=v.vendor_id,
            qty=v.qty,
            unit_price_ngwee=v.unit_price_ngwee,
        )
        for v in eligible
    ] + [
        PricingLine(
            key=ticket_key(t),
            listing_id=t.event_id,
            vendor_id=t.vendor_id,
            qty=t.qty,
            unit_price_ngwee=t.unit_price_ngwee,
            item_kind="event",
        )
        for t in tickets
    ]
    priced = price_cart(lines, offers, max_discount_pct=cap)
    if not priced.applications:
        return views, ticket_lines, None
    snapshots = {a.offer_id: a.snapshot for a in priced.applications}
    out: list[CartLineView] = []
    for view in views:
        outcome = priced.lines.get(view.id)
        if outcome is None or outcome.offer_id is None:
            out.append(view)
            continue
        out.append(
            replace(
                view,
                line_total_ngwee=outcome.final_total_ngwee,
                list_line_total_ngwee=outcome.list_total_ngwee,
                offer_id=outcome.offer_id,
            )
        )
    out_tickets: list[TicketCartLine] = []
    for line in ticket_lines:
        outcome = priced.lines.get(ticket_key(line))
        if outcome is None or outcome.offer_id is None:
            out_tickets.append(line)
            continue
        out_tickets.append(
            with_pricing(
                line,
                line_total_ngwee=outcome.final_total_ngwee,
                offer_id=outcome.offer_id,
                offer_snapshot={
                    **snapshots.get(outcome.offer_id, {}),
                    "line_list_total_ngwee": outcome.list_total_ngwee,
                    "line_final_total_ngwee": outcome.final_total_ngwee,
                    "line_qty": line.qty,
                },
            )
        )
    return out, out_tickets, OfferPricing(priced=priced)


def split_ticket_line(line: TicketCartLine) -> list[tuple[int, int]]:
    """(qty, unit price) order lines for a ticket cart line; exact total, >= 1 ngwee each."""
    if line.offer_id is None:
        return [(line.qty, line.unit_price_ngwee)]
    parts = split_line_units(line.total_ngwee, line.qty)
    if any(unit <= 0 for _, unit in parts):
        raise AppError(
            code="offers.invalid_allocation",
            message="Offer pricing produced an invalid line",
            http_status=409,
            details={"cart_ticket_item_id": line.id, "retry": True},
        )
    return parts


def gift_key(gift: GiftOutcome) -> str:
    return f"{GIFT_KEY_PREFIX}{gift.offer_id}:{gift.listing_id}"


def expand_cart_lines_for_order(
    cart_lines: list[CartLineInput],
    client: Any,
    *,
    customer_id: str,
) -> tuple[list[CartLineInput], PricedCart | None]:
    """Price ``cart_lines`` and expand them into order lines (see CartLineInput).

    Returns the input unchanged when the flag is off or no offer applies.
    """
    expanded, _tickets, priced = expand_unified_for_order(
        cart_lines, [], client, customer_id=customer_id
    )
    return expanded, priced


def expand_unified_for_order(
    cart_lines: list[CartLineInput],
    ticket_lines: list[TicketCartLine],
    client: Any,
    *,
    customer_id: str,
) -> tuple[list[CartLineInput], list[TicketCartLine], PricedCart | None]:
    """Placement pricing for products and event tickets in one engine pass.

    Product lines come back expanded into order lines (split / gift lines);
    ticket lines come back carrying their discounted total and offer snapshot
    (``split_ticket_line`` turns them into order lines).
    """
    eligible = [line for line in cart_lines if line.qty > 0 and line.unit_price_ngwee > 0]
    tickets = [t for t in ticket_lines if t.available and t.qty > 0 and t.unit_price_ngwee > 0]
    if not eligible and not tickets:
        return cart_lines, ticket_lines, None
    vendor_ids = {line.vendor_id for line in eligible} | {t.vendor_id for t in tickets}
    loaded = load_offers_for_pricing(client, vendor_ids, customer_id=customer_id)
    if loaded is None:
        return cart_lines, ticket_lines, None
    offers, cap = loaded
    if not offers:
        return cart_lines, ticket_lines, None
    priced = price_cart(
        [
            PricingLine(
                key=line.cart_item_id,
                listing_id=line.listing_id,
                vendor_id=line.vendor_id,
                qty=line.qty,
                unit_price_ngwee=line.unit_price_ngwee,
            )
            for line in eligible
        ]
        + [
            PricingLine(
                key=ticket_key(t),
                listing_id=t.event_id,
                vendor_id=t.vendor_id,
                qty=t.qty,
                unit_price_ngwee=t.unit_price_ngwee,
                item_kind="event",
            )
            for t in tickets
        ],
        offers,
        max_discount_pct=cap,
    )
    if not priced.applications:
        return cart_lines, ticket_lines, None
    snapshots = {a.offer_id: a.snapshot for a in priced.applications}
    priced_tickets: list[TicketCartLine] = []
    for line in ticket_lines:
        outcome = priced.lines.get(ticket_key(line))
        if outcome is None or outcome.offer_id is None:
            priced_tickets.append(line)
            continue
        priced_tickets.append(
            with_pricing(
                line,
                line_total_ngwee=outcome.final_total_ngwee,
                offer_id=outcome.offer_id,
                offer_snapshot={
                    **snapshots.get(outcome.offer_id, {}),
                    "line_list_total_ngwee": outcome.list_total_ngwee,
                    "line_final_total_ngwee": outcome.final_total_ngwee,
                    "line_qty": line.qty,
                },
            )
        )
    return expand_priced_lines(cart_lines, priced), priced_tickets, priced


def expand_priced_lines(cart_lines: list[CartLineInput], priced: PricedCart) -> list[CartLineInput]:
    """Pure expansion: split discounted lines, append gift lines after their parent."""
    snapshots = {a.offer_id: a.snapshot for a in priced.applications}
    gifts_by_parent: dict[str, list[GiftOutcome]] = {}
    for gift in priced.gifts:
        gifts_by_parent.setdefault(gift.parent_key, []).append(gift)
    expanded: list[CartLineInput] = []
    for line in cart_lines:
        outcome = priced.lines.get(line.cart_item_id)
        if outcome is None or outcome.offer_id is None:
            expanded.append(line)
        else:
            snapshot = {
                **snapshots.get(outcome.offer_id, {}),
                "line_list_total_ngwee": outcome.list_total_ngwee,
                "line_final_total_ngwee": outcome.final_total_ngwee,
                "line_qty": line.qty,
            }
            parts = split_line_units(outcome.final_total_ngwee, line.qty)
            if any(unit <= 0 for _, unit in parts):
                # Engine guarantees >= 1 ngwee per paid unit; never place a 0 paid line.
                raise AppError(
                    code="offers.invalid_allocation",
                    message="Offer pricing produced an invalid line",
                    http_status=409,
                    details={"listing_id": line.listing_id, "retry": True},
                )
            for index, (qty, unit) in enumerate(parts):
                expanded.append(
                    replace(
                        line,
                        qty=qty,
                        unit_price_ngwee=unit,
                        consumes_reservation=index == 0,
                        reservation_qty=line.qty if index == 0 else 0,
                        offer_id=outcome.offer_id,
                        offer_snapshot=snapshot,
                        list_unit_price_ngwee=line.unit_price_ngwee,
                        offer_discount_ngwee=qty * (line.unit_price_ngwee - unit),
                    )
                )
        for gift in gifts_by_parent.get(line.cart_item_id, []):
            expanded.append(
                CartLineInput(
                    cart_item_id=gift_key(gift),
                    listing_id=gift.listing_id,
                    vendor_id=gift.vendor_id,
                    qty=gift.qty,
                    unit_price_ngwee=0,
                    title_snapshot=gift.title,
                    consumes_reservation=False,
                    reservation_qty=0,
                    offer_id=gift.offer_id,
                    offer_snapshot={
                        **snapshots.get(gift.offer_id, {}),
                        "gift": True,
                        "reference_unit_price_ngwee": gift.reference_unit_price_ngwee,
                    },
                    list_unit_price_ngwee=gift.reference_unit_price_ngwee,
                    offer_discount_ngwee=gift.qty * gift.reference_unit_price_ngwee,
                    is_offer_gift=True,
                    offer_parent_cart_item_id=line.cart_item_id,
                )
            )
    return expanded
