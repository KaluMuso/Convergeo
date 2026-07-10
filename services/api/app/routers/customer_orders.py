from __future__ import annotations

from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import NgweeInt, StrictModel
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/account/orders", tags=["customer-orders"])

TimelineStepKey = Literal[
    "placed",
    "payment_held",
    "payment_cod",
    "confirmed",
    "processing",
    "ready",
    "shipped",
    "delivered",
    "completed",
    "cancelled",
    "refunded",
]

TimelineStepState = Literal["completed", "current", "upcoming", "skipped"]

EscrowCopyKey = Literal["held", "released", "refunded", "cod", "none"]

PICKUP_PATH: tuple[str, ...] = (
    "placed",
    "payment",
    "confirmed",
    "processing",
    "ready",
    "delivered",
    "completed",
)

DELIVERY_PATH: tuple[str, ...] = (
    "placed",
    "payment",
    "confirmed",
    "processing",
    "shipped",
    "delivered",
    "completed",
)

STATUS_RANK: dict[str, int] = {
    "placed": 0,
    "confirmed": 1,
    "processing": 2,
    "ready": 3,
    "shipped": 3,
    "delivered": 4,
    "completed": 5,
    "cancelled": -1,
}


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class OrderItemSummary(StrictModel):
    id: str
    title: str
    qty: int
    unit_price_ngwee: NgweeInt


class TimelineStepOut(StrictModel):
    step_key: TimelineStepKey
    state: TimelineStepState
    occurred_at: str | None = None
    escrow_copy_key: EscrowCopyKey = "none"


class PickupCredentialsOut(StrictModel):
    qr_token: str | None = None
    pin: str | None = None
    stub: bool = True


class InvoiceLinkOut(StrictModel):
    invoice_id: str | None = None
    download_url: str | None = None
    stub: bool = True


class OrderSummaryOut(StrictModel):
    id: str
    vendor_id: str
    vendor_name: str
    status: str
    fulfilment: str
    cod: bool
    paid: bool
    payment_mode: Literal["cod", "prepaid"]
    total_ngwee: NgweeInt
    item_count: int
    created_at: str


class CheckoutGroupOut(StrictModel):
    checkout_group_id: str
    created_at: str
    total_ngwee: NgweeInt
    orders: list[OrderSummaryOut]


class OrderListResponse(StrictModel):
    groups: list[CheckoutGroupOut]


class OrderDetailResponse(StrictModel):
    id: str
    checkout_group_id: str
    vendor_id: str
    vendor_name: str
    status: str
    fulfilment: str
    cod: bool
    paid: bool
    payment_mode: Literal["cod", "prepaid"]
    delivery_fee_ngwee: NgweeInt
    subtotal_ngwee: NgweeInt
    total_ngwee: NgweeInt
    created_at: str
    items: list[OrderItemSummary]
    timeline: list[TimelineStepOut]
    pickup: PickupCredentialsOut | None = None
    invoice: InvoiceLinkOut | None = None
    related_orders: list[OrderSummaryOut]


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


def _payment_mode(*, cod: bool) -> Literal["cod", "prepaid"]:
    return "cod" if cod else "prepaid"


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


def _order_has_refund(service_client: _ServiceRoleClient, order_id: str) -> bool:
    response = (
        service_client.client.table("refunds")
        .select("id")
        .eq("order_id", order_id)
        .limit(1)
        .execute()
    )
    return bool(_rows(response))


def _load_vendor_names(
    service_client: _ServiceRoleClient,
    vendor_ids: set[str],
) -> dict[str, str]:
    if not vendor_ids:
        return {}
    response = (
        service_client.client.table("vendors")
        .select("id, display_name")
        .in_("id", sorted(vendor_ids))
        .execute()
    )
    names: dict[str, str] = {}
    for row in _rows(response):
        names[str(row["id"])] = str(row.get("display_name") or "Vendor")
    return names


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


def _sum_items_ngwee(items: list[OrderItemSummary]) -> int:
    return sum(item.qty * item.unit_price_ngwee for item in items)


def _event_timestamps(events: list[dict[str, Any]]) -> dict[str, str]:
    timestamps: dict[str, str] = {}
    for event in events:
        to_status = str(event.get("to_status") or "")
        created_at = str(event.get("created_at") or "")
        if to_status and created_at and to_status not in timestamps:
            timestamps[to_status] = created_at
    return timestamps


def _payment_step_key(*, cod: bool) -> TimelineStepKey:
    return "payment_cod" if cod else "payment_held"


def _fulfilment_path(fulfilment: str) -> tuple[str, ...]:
    return PICKUP_PATH if fulfilment == "pickup" else DELIVERY_PATH


def _resolve_step_key(path_key: str, *, cod: bool) -> TimelineStepKey:
    if path_key == "payment":
        return _payment_step_key(cod=cod)
    return path_key  # type: ignore[return-value]


def _escrow_copy_for_step(step_key: TimelineStepKey) -> EscrowCopyKey:
    if step_key == "payment_held":
        return "held"
    if step_key == "payment_cod":
        return "cod"
    if step_key == "completed":
        return "released"
    if step_key == "refunded":
        return "refunded"
    return "none"


def _status_occurred_at(
    *,
    step_key: TimelineStepKey,
    status: str,
    event_times: dict[str, str],
    created_at: str,
) -> str | None:
    if step_key in {"payment_held", "payment_cod"}:
        return event_times.get("placed", created_at)
    if step_key == "placed":
        return event_times.get("placed", created_at)
    if step_key == "cancelled":
        return event_times.get("cancelled")
    if step_key == "refunded":
        return event_times.get("cancelled")
    status_for_step = {
        "confirmed": "confirmed",
        "processing": "processing",
        "ready": "ready",
        "shipped": "shipped",
        "delivered": "delivered",
        "completed": "completed",
    }.get(step_key)
    if status_for_step:
        return event_times.get(status_for_step)
    return None


def build_customer_timeline(
    *,
    status: str,
    fulfilment: str,
    cod: bool,
    paid: bool,
    refunded: bool,
    created_at: str,
    events: list[dict[str, Any]],
) -> list[TimelineStepOut]:
    """Map order state + audit events to customer-friendly timeline steps."""
    path = _fulfilment_path(fulfilment)
    event_times = _event_timestamps(events)
    if "placed" not in event_times:
        event_times["placed"] = created_at

    cancellation_point = "placed"
    for event in reversed(events):
        if str(event.get("to_status")) == "cancelled":
            cancellation_point = str(event.get("from_status") or "placed")
            break

    current_rank = STATUS_RANK.get(status, 0)
    if status == "cancelled":
        current_rank = STATUS_RANK.get(cancellation_point, 0)

    steps: list[TimelineStepOut] = []

    for path_key in path:
        step_key = _resolve_step_key(path_key, cod=cod)
        if path_key == "payment":
            step_state: TimelineStepState
            if status == "cancelled" and current_rank < 1:
                step_state = "skipped"
            elif current_rank > 0 or paid or cod:
                step_state = "completed"
            elif status == "placed":
                step_state = "current" if not cod and not paid else "completed"
            else:
                step_state = "upcoming"
        else:
            rank = STATUS_RANK.get(path_key, 0)
            if status == "cancelled":
                if rank < current_rank:
                    step_state = "completed"
                elif rank == current_rank:
                    step_state = "current"
                else:
                    step_state = "skipped"
            elif rank < current_rank:
                step_state = "completed"
            elif rank == current_rank:
                step_state = "current"
            else:
                step_state = "upcoming"

        steps.append(
            TimelineStepOut(
                step_key=step_key,
                state=step_state,
                occurred_at=_status_occurred_at(
                    step_key=step_key,
                    status=status,
                    event_times=event_times,
                    created_at=created_at,
                ),
                escrow_copy_key=_escrow_copy_for_step(step_key),
            )
        )

    if status == "cancelled":
        steps.append(
            TimelineStepOut(
                step_key="cancelled",
                state="completed",
                occurred_at=event_times.get("cancelled"),
                escrow_copy_key="none",
            )
        )
        if paid or refunded:
            steps.append(
                TimelineStepOut(
                    step_key="refunded",
                    state="completed" if refunded else "current",
                    occurred_at=event_times.get("cancelled"),
                    escrow_copy_key="refunded",
                )
            )

    return steps


def _load_order_events(service_client: _ServiceRoleClient, order_id: str) -> list[dict[str, Any]]:
    response = (
        service_client.client.table("order_events")
        .select("id, from_status, to_status, note, created_at, actor")
        .eq("order_id", order_id)
        .order("created_at", desc=False)
        .execute()
    )
    return _rows(response)


def _load_order_row(service_client: _ServiceRoleClient, order_id: str) -> dict[str, Any] | None:
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
    return _single_row(response)


def _assert_customer_owns_order(
    order_row: dict[str, Any] | None,
    customer_id: str,
) -> dict[str, Any]:
    if order_row is None or str(order_row.get("customer_id")) != customer_id:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    return order_row


def _build_order_summary(
    *,
    order_row: dict[str, Any],
    vendor_name: str,
    items: list[OrderItemSummary],
    paid: bool,
) -> OrderSummaryOut:
    subtotal = _sum_items_ngwee(items)
    delivery_fee = int(order_row.get("delivery_fee_ngwee") or 0)
    cod = bool(order_row.get("cod"))
    return OrderSummaryOut(
        id=str(order_row["id"]),
        vendor_id=str(order_row["vendor_id"]),
        vendor_name=vendor_name,
        status=str(order_row["status"]),
        fulfilment=str(order_row["fulfilment"]),
        cod=cod,
        paid=paid,
        payment_mode=_payment_mode(cod=cod),
        total_ngwee=subtotal + delivery_fee,
        item_count=sum(item.qty for item in items),
        created_at=str(order_row["created_at"]),
    )


def _load_pickup_credentials(
    service_client: _ServiceRoleClient,
    order_row: dict[str, Any],
) -> PickupCredentialsOut | None:
    status = str(order_row.get("status"))
    fulfilment = str(order_row.get("fulfilment"))
    if status != "ready" or fulfilment != "pickup":
        return None

    # M09-P03 fields — read when present; stub gracefully when unmerged.
    qr_token: str | None = None
    pin: str | None = None
    try:
        extended = (
            service_client.client.table("orders")
            .select("pickup_qr_token, pickup_pin")
            .eq("id", str(order_row["id"]))
            .maybe_single()
            .execute()
        )
        row = _single_row(extended)
        if isinstance(row, dict):
            raw_qr = row.get("pickup_qr_token")
            raw_pin = row.get("pickup_pin")
            qr_token = str(raw_qr) if isinstance(raw_qr, str) and raw_qr.strip() else None
            pin = str(raw_pin) if isinstance(raw_pin, str) and raw_pin.strip() else None
    except Exception:
        qr_token = None
        pin = None

    return PickupCredentialsOut(
        qr_token=qr_token,
        pin=pin,
        stub=qr_token is None and pin is None,
    )


def _load_invoice_link(
    service_client: _ServiceRoleClient,
    order_id: str,
) -> InvoiceLinkOut | None:
    response = (
        service_client.client.table("invoices")
        .select("id, series, no")
        .eq("order_id", order_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return None
    invoice_id = str(rows[0]["id"])
    return InvoiceLinkOut(
        invoice_id=invoice_id,
        download_url=f"/account/orders/{order_id}/invoice",
        stub=True,
    )


def _build_order_detail(
    service_client: _ServiceRoleClient,
    order_row: dict[str, Any],
    *,
    vendor_name: str,
    related_orders: list[OrderSummaryOut],
) -> OrderDetailResponse:
    order_id = str(order_row["id"])
    items = _load_order_items(service_client, order_id)
    paid = _is_paid_order(service_client, order_row)
    refunded = _order_has_refund(service_client, order_id)
    events = _load_order_events(service_client, order_id)
    cod = bool(order_row.get("cod"))
    subtotal = _sum_items_ngwee(items)
    delivery_fee = int(order_row.get("delivery_fee_ngwee") or 0)

    return OrderDetailResponse(
        id=order_id,
        checkout_group_id=str(order_row["checkout_group_id"]),
        vendor_id=str(order_row["vendor_id"]),
        vendor_name=vendor_name,
        status=str(order_row["status"]),
        fulfilment=str(order_row["fulfilment"]),
        cod=cod,
        paid=paid,
        payment_mode=_payment_mode(cod=cod),
        delivery_fee_ngwee=delivery_fee,
        subtotal_ngwee=subtotal,
        total_ngwee=subtotal + delivery_fee,
        created_at=str(order_row["created_at"]),
        items=items,
        timeline=build_customer_timeline(
            status=str(order_row["status"]),
            fulfilment=str(order_row["fulfilment"]),
            cod=cod,
            paid=paid,
            refunded=refunded,
            created_at=str(order_row["created_at"]),
            events=events,
        ),
        pickup=_load_pickup_credentials(service_client, order_row),
        invoice=_load_invoice_link(service_client, order_id),
        related_orders=related_orders,
    )


@router.get("", response_model=OrderListResponse)
def list_customer_orders(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OrderListResponse:
    response = (
        service_client.client.table("orders")
        .select(
            "id, checkout_group_id, vendor_id, customer_id, status, fulfilment, "
            "cod, delivery_fee_ngwee, created_at"
        )
        .eq("customer_id", current_user.id)
        .order("created_at", desc=True)
        .execute()
    )
    order_rows = _rows(response)
    if not order_rows:
        return OrderListResponse(groups=[])

    vendor_ids = {str(row["vendor_id"]) for row in order_rows}
    vendor_names = _load_vendor_names(service_client, vendor_ids)

    checkout_groups: dict[str, list[dict[str, Any]]] = {}
    for row in order_rows:
        group_id = str(row["checkout_group_id"])
        checkout_groups.setdefault(group_id, []).append(row)

    groups: list[CheckoutGroupOut] = []
    for group_id, rows in checkout_groups.items():
        summaries: list[OrderSummaryOut] = []
        group_total = 0
        group_created_at = rows[0]["created_at"]
        for row in rows:
            items = _load_order_items(service_client, str(row["id"]))
            paid = _is_paid_order(service_client, row)
            summary = _build_order_summary(
                order_row=row,
                vendor_name=vendor_names.get(str(row["vendor_id"]), "Vendor"),
                items=items,
                paid=paid,
            )
            summaries.append(summary)
            group_total += summary.total_ngwee
            if str(row["created_at"]) > str(group_created_at):
                group_created_at = row["created_at"]

        groups.append(
            CheckoutGroupOut(
                checkout_group_id=group_id,
                created_at=str(group_created_at),
                total_ngwee=group_total,
                orders=summaries,
            )
        )

    groups.sort(key=lambda group: group.created_at, reverse=True)
    return OrderListResponse(groups=groups)


@router.get("/{order_id}", response_model=OrderDetailResponse)
def get_customer_order(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OrderDetailResponse:
    order_row = _load_order_row(service_client, order_id)
    order_row = _assert_customer_owns_order(order_row, current_user.id)

    group_response = (
        service_client.client.table("orders")
        .select(
            "id, checkout_group_id, vendor_id, customer_id, status, fulfilment, "
            "cod, delivery_fee_ngwee, created_at"
        )
        .eq("checkout_group_id", str(order_row["checkout_group_id"]))
        .eq("customer_id", current_user.id)
        .execute()
    )
    related_rows = _rows(group_response)
    vendor_ids = {str(row["vendor_id"]) for row in related_rows}
    vendor_names = _load_vendor_names(service_client, vendor_ids)

    related_summaries: list[OrderSummaryOut] = []
    for row in related_rows:
        items = _load_order_items(service_client, str(row["id"]))
        paid = _is_paid_order(service_client, row)
        related_summaries.append(
            _build_order_summary(
                order_row=row,
                vendor_name=vendor_names.get(str(row["vendor_id"]), "Vendor"),
                items=items,
                paid=paid,
            )
        )

    return _build_order_detail(
        service_client,
        order_row,
        vendor_name=vendor_names.get(str(order_row["vendor_id"]), "Vendor"),
        related_orders=related_summaries,
    )
