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
"""

from __future__ import annotations

from typing import Annotated, Any

from app.core.auth import CurrentUser, get_current_user, require_role
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.dispatch import service as dispatch_service
from app.services.orders.state import sql_uuid
from fastapi import APIRouter, Depends

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
