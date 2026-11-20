"""Build the ticket-lane order of a unified checkout (pure, integer ngwee).

Turns priced ticket cart lines plus the session's capacity holds into the
``TicketOrderInput`` that ``create_orders_atomic`` places next to the goods
orders. A ticket line an offer discounted is split into at most two order
lines with whole-ngwee unit prices (same rule as product lines), and its claim
ids and attendee names are shared out over those lines in order, so every
order line owns exactly ``qty`` claims.
"""

from __future__ import annotations

from app.errors import AppError
from app.services.cart.tickets import (
    TicketCartLine,
    TicketHold,
    build_ticket_commission_snapshot,
    ticket_platform_fee_ngwee,
)
from app.services.offers.apply import split_ticket_line
from app.services.orders.create import TicketOrderInput, TicketOrderLineInput


def build_ticket_order(
    lines: list[TicketCartLine],
    holds: dict[str, TicketHold],
) -> TicketOrderInput | None:
    """``holds`` maps cart ticket line id -> its hold (see ``match_holds``)."""
    if not lines:
        return None
    vendors = {line.vendor_id for line in lines}
    if len(vendors) != 1 or len({line.instance_id for line in lines}) != 1:
        raise AppError(
            code="cart.tickets_one_event",
            message="Your cart already has tickets for another event or date",
            http_status=409,
            details={"message_key": "cart.tickets.oneEvent", "redirect_to": "cart"},
        )
    order_lines: list[TicketOrderLineInput] = []
    snapshot_lines: list[tuple[TicketCartLine, int, int]] = []
    for line in lines:
        hold = holds[line.id]
        claims = list(hold.ticket_ids)
        names = list(line.attendee_names) if line.attendee_names else None
        offset = 0
        for qty, unit in split_ticket_line(line):
            order_lines.append(
                TicketOrderLineInput(
                    cart_ticket_item_id=line.id,
                    ticket_type_id=line.ticket_type_id,
                    instance_id=line.instance_id,
                    qty=qty,
                    unit_price_ngwee=unit,
                    title_snapshot=line.title,
                    ticket_ids=tuple(claims[offset : offset + qty]),
                    attendee_names=tuple(names[offset : offset + qty]) if names else None,
                    offer_id=line.offer_id,
                    offer_snapshot=line.offer_snapshot,
                    list_unit_price_ngwee=line.unit_price_ngwee if line.offer_id else None,
                    offer_discount_ngwee=qty * (line.unit_price_ngwee - unit)
                    if line.offer_id
                    else 0,
                )
            )
            snapshot_lines.append((line, qty, unit))
            offset += qty
    platform_fee = ticket_platform_fee_ngwee(lines)
    return TicketOrderInput(
        vendor_id=next(iter(vendors)),
        lines=tuple(order_lines),
        platform_fee_ngwee=platform_fee,
        commission_snapshot=build_ticket_commission_snapshot(
            lines=snapshot_lines,
            claim_ids=[tid for line in lines for tid in holds[line.id].ticket_ids],
            platform_fee=platform_fee,
        ),
    )
