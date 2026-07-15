from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.orders.events import emit_order_lifecycle
from app.services.orders.state import (
    ActorRole,
    OrderEvent,
    OrderStatus,
    OrderTransitionError,
    resolve_transition,
    transition_order,
)
from app.services.pickup import issue_pickup_tokens
from fastapi import APIRouter, Depends
from pydantic import Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vendor/orders", tags=["vendor-orders"])

VendorActionName = Literal["confirm", "reject", "pack", "ship", "ready_for_pickup"]

ACTION_EVENT_MAP: dict[VendorActionName, OrderEvent] = {
    "confirm": OrderEvent.CONFIRM,
    "reject": OrderEvent.REJECT,
    "pack": OrderEvent.START_PROCESSING,
    "ship": OrderEvent.SHIP,
    "ready_for_pickup": OrderEvent.READY_FOR_PICKUP,
}

STATUS_NOTIFICATION_TEMPLATE = "order_status_changed"
REFUND_NOTIFICATION_TEMPLATE = "order_refund_required"


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class RejectRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=2000)


class ShipRequest(StrictModel):
    tracking_note: str = Field(min_length=1, max_length=2000)


class OrderItemSummary(StrictModel):
    id: str
    title: str
    qty: int
    unit_price_ngwee: int


class OrderEventSummary(StrictModel):
    id: str
    from_status: str | None
    to_status: str
    note: str | None
    created_at: str
    actor: str | None


class OrderDetailResponse(StrictModel):
    id: str
    status: str
    fulfilment: str
    cod: bool
    paid: bool
    delivery_fee_ngwee: int
    created_at: str
    customer_id: str
    items: list[OrderItemSummary]
    timeline: list[OrderEventSummary]
    available_actions: list[VendorActionName]


class OrderActionResponse(StrictModel):
    order_id: str
    from_status: str
    to_status: str
    event: str
    available_actions: list[VendorActionName]


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _load_vendor_for_owner(
    service_client: _ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, archetype")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def _load_order_row(service_client: _ServiceRoleClient, order_id: str) -> dict[str, Any]:
    response = (
        service_client.client.table("orders")
        .select(
            "id, checkout_group_id, vendor_id, customer_id, status, fulfilment, "
            "cod, delivery_fee_ngwee, created_at"
        )
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    return row


def _assert_vendor_owns_order(*, vendor_id: str, order_row: dict[str, Any]) -> None:
    if str(order_row.get("vendor_id")) != vendor_id:
        raise AppError(
            code="forbidden",
            message="Vendor may only act on their own orders",
            http_status=403,
            details={"message_key": "vendor.orders.errors.forbidden"},
        )


def _order_has_successful_payment(
    service_client: _ServiceRoleClient,
    checkout_group_id: str,
) -> bool:
    response = (
        service_client.client.table("payments")
        .select("id")
        .eq("checkout_group_id", checkout_group_id)
        .eq("status", "success")
        .limit(1)
        .execute()
    )
    return bool(_rows(response))


def _is_paid_order(service_client: _ServiceRoleClient, order_row: dict[str, Any]) -> bool:
    if bool(order_row.get("cod")):
        return False
    checkout_group_id = str(order_row["checkout_group_id"])
    return _order_has_successful_payment(service_client, checkout_group_id)


def _available_vendor_actions(
    *,
    status: str,
    fulfilment: str,
) -> list[VendorActionName]:
    actions: list[VendorActionName] = []
    for action_name, event in ACTION_EVENT_MAP.items():
        result = resolve_transition(
            from_status=OrderStatus(status),
            event=event,
            actor_role=ActorRole.VENDOR,
            fulfilment=fulfilment,  # type: ignore[arg-type]
        )
        if result.permitted:
            actions.append(action_name)
    return actions


def _load_order_items(service_client: _ServiceRoleClient, order_id: str) -> list[OrderItemSummary]:
    response = (
        service_client.client.table("order_items")
        .select("id, qty, unit_price_ngwee, title_snapshot")
        .eq("order_id", order_id)
        .execute()
    )
    items: list[OrderItemSummary] = []
    for row in _rows(response):
        title = row.get("title_snapshot")
        items.append(
            OrderItemSummary(
                id=str(row["id"]),
                title=str(title).strip() if isinstance(title, str) and title.strip() else "Item",
                qty=int(row["qty"]),
                unit_price_ngwee=int(row["unit_price_ngwee"]),
            )
        )
    return items


def _load_order_timeline(
    service_client: _ServiceRoleClient,
    order_id: str,
) -> list[OrderEventSummary]:
    response = (
        service_client.client.table("order_events")
        .select("id, from_status, to_status, note, created_at, actor")
        .eq("order_id", order_id)
        .order("created_at", desc=False)
        .execute()
    )
    timeline: list[OrderEventSummary] = []
    for row in _rows(response):
        timeline.append(
            OrderEventSummary(
                id=str(row["id"]),
                from_status=str(row["from_status"]) if row.get("from_status") else None,
                to_status=str(row["to_status"]),
                note=str(row["note"]) if row.get("note") else None,
                created_at=str(row["created_at"]),
                actor=str(row["actor"]) if row.get("actor") else None,
            )
        )
    return timeline


def _enqueue_status_notification(
    service_client: _ServiceRoleClient,
    *,
    order_id: str,
    customer_id: str,
    from_status: str,
    to_status: str,
    note: str,
) -> None:
    enqueue_outbox_row(
        service_client.client,
        event_type="order-status-changed",
        entity_id=order_id,
        channel="whatsapp",
        template=STATUS_NOTIFICATION_TEMPLATE,
        payload={
            "order_id": order_id,
            "customer_id": customer_id,
            "from_status": from_status,
            "to_status": to_status,
            "note": note,
        },
    )


def _enqueue_refund_notification(
    service_client: _ServiceRoleClient,
    *,
    order_id: str,
    customer_id: str,
    reason: str,
) -> None:
    enqueue_outbox_row(
        service_client.client,
        event_type="order-refund-required",
        entity_id=order_id,
        channel="whatsapp",
        template=REFUND_NOTIFICATION_TEMPLATE,
        payload={
            "order_id": order_id,
            "customer_id": customer_id,
            "reason": reason,
        },
    )


def _build_order_detail(
    service_client: _ServiceRoleClient,
    order_row: dict[str, Any],
) -> OrderDetailResponse:
    order_id = str(order_row["id"])
    status = str(order_row["status"])
    fulfilment = str(order_row["fulfilment"])
    paid = _is_paid_order(service_client, order_row)
    return OrderDetailResponse(
        id=order_id,
        status=status,
        fulfilment=fulfilment,
        cod=bool(order_row.get("cod")),
        paid=paid,
        delivery_fee_ngwee=int(order_row.get("delivery_fee_ngwee") or 0),
        created_at=str(order_row["created_at"]),
        customer_id=str(order_row["customer_id"]),
        items=_load_order_items(service_client, order_id),
        timeline=_load_order_timeline(service_client, order_id),
        available_actions=_available_vendor_actions(status=status, fulfilment=fulfilment),
    )


def _execute_vendor_action(
    *,
    service_client: _ServiceRoleClient,
    vendor_id: str,
    actor_user_id: str,
    order_row: dict[str, Any],
    event: OrderEvent,
    note: str,
) -> OrderActionResponse:
    order_id = str(order_row["id"])
    from_status = str(order_row["status"])
    fulfilment = str(order_row["fulfilment"])
    customer_id = str(order_row["customer_id"])

    paid = _is_paid_order(service_client, order_row)
    refund_path = event == OrderEvent.REJECT and paid

    try:
        outcome = transition_order(
            order_id=order_id,
            event=event,
            actor_role=ActorRole.VENDOR,
            actor_id=actor_user_id,
            note=note,
            refund_path=refund_path,
        )
    except OrderTransitionError as exc:
        raise AppError(
            code=exc.code,
            message=exc.message,
            http_status=exc.http_status,
            details=exc.details,
        ) from exc

    _enqueue_status_notification(
        service_client,
        order_id=order_id,
        customer_id=customer_id,
        from_status=from_status,
        to_status=outcome.to_status.value,
        note=note,
    )
    if refund_path:
        _enqueue_refund_notification(
            service_client,
            order_id=order_id,
            customer_id=customer_id,
            reason=note,
        )

    return OrderActionResponse(
        order_id=order_id,
        from_status=outcome.from_status.value,
        to_status=outcome.to_status.value,
        event=outcome.event.value,
        available_actions=_available_vendor_actions(
            status=outcome.to_status.value,
            fulfilment=fulfilment,
        ),
    )


@router.get("/{order_id}", response_model=OrderDetailResponse)
def get_vendor_order(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OrderDetailResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    order_row = _load_order_row(service_client, order_id)
    _assert_vendor_owns_order(vendor_id=str(vendor["id"]), order_row=order_row)
    return _build_order_detail(service_client, order_row)


@router.post("/{order_id}/confirm", response_model=OrderActionResponse)
def confirm_vendor_order(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OrderActionResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    order_row = _load_order_row(service_client, order_id)
    _assert_vendor_owns_order(vendor_id=str(vendor["id"]), order_row=order_row)
    return _execute_vendor_action(
        service_client=service_client,
        vendor_id=str(vendor["id"]),
        actor_user_id=current_user.id,
        order_row=order_row,
        event=OrderEvent.CONFIRM,
        note="Order confirmed by vendor",
    )


@router.post("/{order_id}/reject", response_model=OrderActionResponse)
def reject_vendor_order(
    order_id: str,
    body: RejectRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OrderActionResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    order_row = _load_order_row(service_client, order_id)
    _assert_vendor_owns_order(vendor_id=str(vendor["id"]), order_row=order_row)
    return _execute_vendor_action(
        service_client=service_client,
        vendor_id=str(vendor["id"]),
        actor_user_id=current_user.id,
        order_row=order_row,
        event=OrderEvent.REJECT,
        note=body.reason.strip(),
    )


@router.post("/{order_id}/pack", response_model=OrderActionResponse)
def pack_vendor_order(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OrderActionResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    order_row = _load_order_row(service_client, order_id)
    _assert_vendor_owns_order(vendor_id=str(vendor["id"]), order_row=order_row)
    return _execute_vendor_action(
        service_client=service_client,
        vendor_id=str(vendor["id"]),
        actor_user_id=current_user.id,
        order_row=order_row,
        event=OrderEvent.START_PROCESSING,
        note="Order processing started",
    )


@router.post("/{order_id}/ship", response_model=OrderActionResponse)
def ship_vendor_order(
    order_id: str,
    body: ShipRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OrderActionResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    order_row = _load_order_row(service_client, order_id)
    _assert_vendor_owns_order(vendor_id=str(vendor["id"]), order_row=order_row)
    return _execute_vendor_action(
        service_client=service_client,
        vendor_id=str(vendor["id"]),
        actor_user_id=current_user.id,
        order_row=order_row,
        event=OrderEvent.SHIP,
        note=body.tracking_note.strip(),
    )


@router.post("/{order_id}/ready-for-pickup", response_model=OrderActionResponse)
def ready_for_pickup_vendor_order(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OrderActionResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    order_row = _load_order_row(service_client, order_id)
    _assert_vendor_owns_order(vendor_id=str(vendor["id"]), order_row=order_row)
    action = _execute_vendor_action(
        service_client=service_client,
        vendor_id=str(vendor["id"]),
        actor_user_id=current_user.id,
        order_row=order_row,
        event=OrderEvent.READY_FOR_PICKUP,
        note="Order ready for pickup",
    )

    # Order is now `ready`. For pickup fulfilment, mint the QR + PIN and notify
    # the customer. Never fail the (already-committed) transition on issuance or
    # notification problems — log and move on.
    if str(order_row.get("fulfilment")) == "pickup":
        try:
            issue_result = issue_pickup_tokens(order_id=order_id)
            emit_order_lifecycle(
                service_client.client,
                event="order_ready_pickup",
                order_row=order_row,
                # `pickup_details` is the template's dynamic slot ({{2}} — "pickup
                # details / QR link"); it MUST be present or the WhatsApp render
                # raises. Carry the single-use PIN so the customer receives it;
                # pin/qr also kept for the in-app (M09-P05) + email paths.
                extra={
                    "pickup_details": f"PIN {issue_result.pin}",
                    "pickup_pin": issue_result.pin,
                    "pickup_qr_token": issue_result.qr_token,
                },
            )
        except Exception:
            logger.warning(
                "Pickup token issuance / notification failed after ready transition",
                extra={"order_id": order_id},
                exc_info=True,
            )

    return action
