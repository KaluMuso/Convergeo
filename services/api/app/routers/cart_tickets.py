"""Unified cart: put event tickets in the cart next to products.

``POST /cart/tickets`` adds (or sets the quantity of) a ticket line after the
same checks as buying the ticket on its own; ``DELETE /cart/tickets/{id}``
removes one. Both return the whole cart. Signed-in buyers only: a ticket is
issued to an account, and capacity is claimed for that account at checkout.
"""

from __future__ import annotations

from typing import Annotated, Any

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit_policies import enforce_registered_policy
from app.core.supabase import get_user_client
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.cart import (
    CartResponse,
    _business_eligible_for_user,
    _cart_response,
    _create_user_cart,
    _fetch_active_cart_by_user,
    _fetch_cart_items,
)
from app.services.cart.store import fetch_listings_for_items
from app.services.cart.tickets import MAX_TICKET_QTY, put_ticket_line, remove_ticket_line
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

router = APIRouter(
    prefix="/cart",
    tags=["cart"],
    dependencies=[Depends(enforce_registered_policy)],
)


class CartTicketInput(BaseModel):
    instance_id: str = Field(min_length=36, max_length=36)
    ticket_type_id: str = Field(min_length=36, max_length=36)
    qty: int = Field(ge=1, le=MAX_TICKET_QTY)
    attendee_names: list[str] | None = Field(default=None, max_length=MAX_TICKET_QTY)
    # Returned only by POST /events/{slug}/access/unlock (private events).
    event_access_proof: str | None = Field(default=None, max_length=2048)

    @field_validator("attendee_names")
    @classmethod
    def _cap_name_lengths(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [str(name).strip()[:120] for name in value]


def _user_cart_id(current_user: CurrentUser, settings: Settings) -> str:
    client = get_user_client(current_user.token, settings)
    cart = _fetch_active_cart_by_user(client, current_user.id)
    if cart is None:
        cart = _create_user_cart(client, current_user.id)
    return str(cart["id"])


def _cart(current_user: CurrentUser, settings: Settings, cart_id: str) -> CartResponse:
    client = get_user_client(current_user.token, settings)
    items = _fetch_cart_items(client, cart_id)
    return _cart_response(
        cart_id=cart_id,
        items=items,
        listings_by_id=fetch_listings_for_items(items),
        business_eligible=_business_eligible_for_user(current_user.id),
        customer_id=current_user.id,
    )


@router.post("/tickets", response_model=CartResponse)
async def put_cart_ticket(
    body: CartTicketInput,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[Any, Depends(get_supabase_client)],
) -> CartResponse:
    cart_id = _user_cart_id(current_user, settings)
    put_ticket_line(
        service,
        customer_id=current_user.id,
        cart_id=cart_id,
        instance_id=body.instance_id.lower(),
        ticket_type_id=body.ticket_type_id.lower(),
        qty=body.qty,
        attendee_names=body.attendee_names,
        event_access_proof=body.event_access_proof,
    )
    return _cart(current_user, settings, cart_id)


@router.delete("/tickets/{line_id}", response_model=CartResponse)
async def delete_cart_ticket(
    line_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CartResponse:
    cart_id = _user_cart_id(current_user, settings)
    if not remove_ticket_line(customer_id=current_user.id, cart_id=cart_id, line_id=line_id):
        raise AppError(
            code="cart.ticket_not_found",
            message="Ticket line not found in your cart",
            http_status=404,
            details={"id": line_id},
        )
    return _cart(current_user, settings, cart_id)
