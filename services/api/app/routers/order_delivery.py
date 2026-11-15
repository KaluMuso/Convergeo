"""Courier delivery status for the order's customer and vendor (courier dispatch v1).

* ``GET /account/orders/{order_id}/delivery`` — the ORDER OWNER only. Includes the
  6-digit handover code while the dispatch is in flight (chain of custody v1:
  the customer gives it to the rider on delivery).
* ``GET /vendor/orders/{order_id}/delivery`` — the order's vendor owner only.
  Assigned courier + status timeline; NEVER the handover code.

Authorization is checked against the order row before any dispatch data is
read; a non-owner gets the same 404 as a missing order (no existence oracle).
Both return ``enabled=false`` with no dispatch while the ``courier_dispatch``
flag is off.

Pay at the door (flag ``pay_at_door``): with the flag on, a COD order's
handover code is withheld until the order is paid. ``/door-payment`` lets the
order owner see the state, send the mobile-money prompt to their phone once the
rider is at the door, and re-check the status.
"""

from __future__ import annotations

from typing import Annotated, Any

from app.core.auth import CurrentUser, get_current_user, require_role
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.dispatch import service as dispatch_service
from app.services.dispatch.state import DispatchRow, fetch_latest_dispatch_for_order
from app.services.orders.state import sql_uuid
from app.services.payments import door as door_payments
from app.services.payments.registry import LENCO_PROVIDER
from app.services.payments.registry import get as get_payment_strategy
from fastapi import APIRouter, Depends
from pydantic import Field

router = APIRouter(tags=["order-delivery"])


class DeliveryStepOut(StrictModel):
    status: str
    at: str


class CustomerDispatchOut(StrictModel):
    status: str
    courier_name: str
    courier_reference: str | None
    cod_amount_ngwee: int
    timeline: list[DeliveryStepOut]
    handover_code: str | None


class VendorDispatchOut(StrictModel):
    status: str
    courier_name: str
    courier_reference: str | None
    cod_amount_ngwee: int
    timeline: list[DeliveryStepOut]


class CustomerDeliveryResponse(StrictModel):
    enabled: bool
    dispatch: CustomerDispatchOut | None


class VendorDeliveryResponse(StrictModel):
    enabled: bool
    dispatch: VendorDispatchOut | None


def _not_found() -> AppError:
    return AppError(code="not_found", message="Order not found", http_status=404)


def _validated_order_id(order_id: str) -> str:
    try:
        sql_uuid(order_id, "order_id")
    except ValueError as exc:
        raise _not_found() from exc
    return order_id


def _timeline(view: dict[str, Any]) -> list[DeliveryStepOut]:
    return [
        DeliveryStepOut(status=str(step["status"]), at=str(step["at"]))
        for step in view.get("timeline") or []
        if isinstance(step, dict) and step.get("at")
    ]


@router.get("/account/orders/{order_id}/delivery", response_model=CustomerDeliveryResponse)
def get_customer_order_delivery(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CustomerDeliveryResponse:
    owners = dispatch_service.order_owner_and_vendor(_validated_order_id(order_id))
    if owners is None or owners[0] != current_user.id:
        raise _not_found()
    if not dispatch_service.is_courier_dispatch_enabled():
        return CustomerDeliveryResponse(enabled=False, dispatch=None)
    view = dispatch_service.party_dispatch_view(order_id, include_handover_code=True)
    if view is None:
        return CustomerDeliveryResponse(enabled=True, dispatch=None)
    return CustomerDeliveryResponse(
        enabled=True,
        dispatch=CustomerDispatchOut(
            status=str(view["status"]),
            courier_name=str(view.get("courier_name") or ""),
            courier_reference=view.get("courier_reference"),
            cod_amount_ngwee=int(view.get("cod_amount_ngwee") or 0),
            timeline=_timeline(view),
            handover_code=view.get("handover_code"),
        ),
    )


@router.get("/vendor/orders/{order_id}/delivery", response_model=VendorDeliveryResponse)
def get_vendor_order_delivery(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
) -> VendorDeliveryResponse:
    owners = dispatch_service.order_owner_and_vendor(_validated_order_id(order_id))
    if owners is None or not owners[2] or owners[2] != current_user.id:
        raise _not_found()
    if not dispatch_service.is_courier_dispatch_enabled():
        return VendorDeliveryResponse(enabled=False, dispatch=None)
    view = dispatch_service.party_dispatch_view(order_id, include_handover_code=False)
    if view is None:
        return VendorDeliveryResponse(enabled=True, dispatch=None)
    return VendorDeliveryResponse(
        enabled=True,
        dispatch=VendorDispatchOut(
            status=str(view["status"]),
            courier_name=str(view.get("courier_name") or ""),
            courier_reference=view.get("courier_reference"),
            cod_amount_ngwee=int(view.get("cod_amount_ngwee") or 0),
            timeline=_timeline(view),
        ),
    )


# ---------------------------------------------------------------------------
# Pay at the door (flag ``pay_at_door``, default OFF)
# ---------------------------------------------------------------------------


class DoorPaymentOut(StrictModel):
    """Customer projection. Never includes phone numbers or Lenco references."""

    enabled: bool
    state: str
    amount_ngwee: int
    arrived: bool
    settled_via: str | None
    attempts_used: int
    attempts_allowed: int
    latest_failure_reason: str | None
    can_request: bool


class DoorPaymentRequestIn(StrictModel):
    # Optional: another MTN/Airtel number (wrong number, Zamtel, someone else pays).
    phone: str | None = Field(default=None, min_length=9, max_length=20)


def _door_out(status: door_payments.DoorStatus) -> DoorPaymentOut:
    return DoorPaymentOut(
        enabled=status.enabled,
        state=status.state,
        amount_ngwee=status.amount_ngwee,
        arrived=status.arrived,
        settled_via=status.settled_via,
        attempts_used=status.attempts_used,
        attempts_allowed=status.attempts_allowed,
        latest_failure_reason=status.latest_failure_reason,
        can_request=status.can_request,
    )


def _owned_door_dispatch(order_id: str, user_id: str) -> DispatchRow | None:
    owners = dispatch_service.order_owner_and_vendor(_validated_order_id(order_id))
    if owners is None or owners[0] != user_id:
        raise _not_found()
    if not (
        dispatch_service.is_courier_dispatch_enabled() and door_payments.is_pay_at_door_enabled()
    ):
        return None
    return fetch_latest_dispatch_for_order(order_id)


@router.get("/account/orders/{order_id}/door-payment", response_model=DoorPaymentOut)
def get_door_payment(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> DoorPaymentOut:
    dispatch = _owned_door_dispatch(order_id, current_user.id)
    if dispatch is None:
        return _door_out(door_payments.disabled_status(enabled=False))
    return _door_out(door_payments.door_status(dispatch))


@router.post("/account/orders/{order_id}/door-payment", response_model=DoorPaymentOut)
async def request_door_payment(
    order_id: str,
    body: DoorPaymentRequestIn,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> DoorPaymentOut:
    """Pay now on your phone: prompt for the order total once the rider is at the door."""
    dispatch = _owned_door_dispatch(order_id, current_user.id)
    if dispatch is None:
        door_payments.require_pay_at_door_enabled()
        raise _not_found()
    status = await door_payments.request_door_payment(
        dispatch_id=dispatch.id,
        actor_id=current_user.id,
        actor_role="customer",
        phone=body.phone,
        strategy=get_payment_strategy(LENCO_PROVIDER),
    )
    return _door_out(status)


@router.post("/account/orders/{order_id}/door-payment/poll", response_model=DoorPaymentOut)
async def poll_door_payment(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> DoorPaymentOut:
    """Ask Lenco for the latest status (safe to repeat after a dropped connection)."""
    dispatch = _owned_door_dispatch(order_id, current_user.id)
    if dispatch is None:
        return _door_out(door_payments.disabled_status(enabled=False))
    status = await door_payments.poll_door_payment(
        dispatch_id=dispatch.id, strategy=get_payment_strategy(LENCO_PROVIDER)
    )
    return _door_out(status)
