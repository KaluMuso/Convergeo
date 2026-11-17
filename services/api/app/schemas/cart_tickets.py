"""Wire shape of an event-ticket line in the unified cart and checkout."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.services.cart.tickets import TicketCartLine


class TicketLineOut(BaseModel):
    """An event-ticket line of the unified checkout (its own order lane)."""

    id: str
    item_type: Literal["event_ticket"] = "event_ticket"
    event_id: str
    event_title: str
    event_slug: str | None = None
    ticket_type_id: str
    type_name: str
    instance_id: str
    starts_at: str | None = None
    vendor_id: str
    qty: int
    unit_price_ngwee: int
    line_total_ngwee: int
    #: List total before an offer; None when no offer priced the line.
    list_line_total_ngwee: int | None = None
    offer_id: str | None = None


def ticket_line_out(line: TicketCartLine) -> TicketLineOut:
    return TicketLineOut(
        id=line.id,
        event_id=line.event_id,
        event_title=line.event_title,
        event_slug=line.event_slug,
        ticket_type_id=line.ticket_type_id,
        type_name=line.type_name,
        instance_id=line.instance_id,
        starts_at=line.starts_at,
        vendor_id=line.vendor_id,
        qty=line.qty,
        unit_price_ngwee=line.unit_price_ngwee,
        line_total_ngwee=line.total_ngwee,
        list_line_total_ngwee=line.list_total_ngwee if line.offer_id else None,
        offer_id=line.offer_id,
    )
