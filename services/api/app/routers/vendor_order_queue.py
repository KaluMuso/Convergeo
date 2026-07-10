"""Vendor order queue + daily-driver dashboard (M12-P07)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol
from zoneinfo import ZoneInfo

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.routers.vendor_orders import (
    VendorActionName,
    _available_vendor_actions,
    _load_vendor_for_owner,
)
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/vendor/orders", tags=["vendor-orders"])

LUSAKA_TZ = ZoneInfo("Africa/Lusaka")
CONFIRM_SLA_HOURS = 2

QueueStatusFilter = Literal[
    "all",
    "needs_action",
    "placed",
    "confirmed",
    "processing",
    "ready",
    "shipped",
    "delivered",
    "completed",
    "cancelled",
]

NEEDS_ACTION_STATUSES = frozenset({"placed", "confirmed", "processing"})


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class OrderQueueItem(StrictModel):
    id: str
    status: str
    fulfilment: str
    total_ngwee: int
    item_count: int
    preview_title: str
    created_at: str
    available_actions: list[VendorActionName]
    urgency: int


class VendorDashboardResponse(StrictModel):
    takings_ngwee: int
    takings_date: str
    needs_action: list[OrderQueueItem]
    queue_counts: dict[str, int]


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def lusaka_day_bounds(
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return UTC instants for the start (inclusive) and end (exclusive) of today in Lusaka."""
    instant = now or datetime.now(tz=UTC)
    lusaka_now = instant.astimezone(LUSAKA_TZ)
    lusaka_start = lusaka_now.replace(hour=0, minute=0, second=0, microsecond=0)
    lusaka_end = lusaka_start + timedelta(days=1)
    return lusaka_start.astimezone(UTC), lusaka_end.astimezone(UTC)


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _order_items_subtotal(items: list[dict[str, Any]]) -> int:
    total = 0
    for row in items:
        total += int(row["qty"]) * int(row["unit_price_ngwee"])
    return total


def _order_total_ngwee(*, items: list[dict[str, Any]], delivery_fee_ngwee: int) -> int:
    return _order_items_subtotal(items) + int(delivery_fee_ngwee)


def _preview_title(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Order"
    title = items[0].get("title_snapshot")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return "Order"


def _needs_action_for_order(*, status: str, fulfilment: str) -> bool:
    actions = _available_vendor_actions(status=status, fulfilment=fulfilment)
    return bool(actions)


def compute_urgency(*, status: str, created_at: datetime, now: datetime) -> int:
    """Lower urgency value sorts earlier. Placed orders breach SLA first."""
    age_seconds = max(0, int((now - created_at).total_seconds()))
    if status == "placed":
        sla_seconds = CONFIRM_SLA_HOURS * 3600
        if age_seconds >= sla_seconds:
            return 0
        return 100 + age_seconds
    if status == "confirmed":
        return 1_000 + age_seconds
    if status == "processing":
        return 2_000 + age_seconds
    return 9_000 + age_seconds


def sort_needs_action(orders: list[OrderQueueItem]) -> list[OrderQueueItem]:
    return sorted(orders, key=lambda row: (row.urgency, row.created_at))


def compute_takings_ngwee(
    *,
    confirmed_events: list[dict[str, Any]],
    order_totals: dict[str, int],
    day_start_utc: datetime,
    day_end_utc: datetime,
) -> int:
    """Sum order totals confirmed within today's Lusaka window (inclusive start, exclusive end)."""
    total = 0
    seen: set[str] = set()
    for event in confirmed_events:
        order_id = str(event["order_id"])
        if order_id in seen:
            continue
        created_at = _parse_timestamp(str(event["created_at"]))
        if day_start_utc <= created_at < day_end_utc:
            total += order_totals.get(order_id, 0)
            seen.add(order_id)
    return total


def _load_vendor_orders(service_client: _ServiceRoleClient, vendor_id: str) -> list[dict[str, Any]]:
    response = (
        service_client.client.table("orders")
        .select("id, status, fulfilment, delivery_fee_ngwee, created_at")
        .eq("vendor_id", vendor_id)
        .order("created_at", desc=True)
        .execute()
    )
    return _rows(response)


def _load_items_by_order(
    service_client: _ServiceRoleClient,
    order_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    if not order_ids:
        return {}
    response = (
        service_client.client.table("order_items")
        .select("order_id, qty, unit_price_ngwee, title_snapshot, created_at")
        .in_("order_id", order_ids)
        .execute()
    )
    grouped: dict[str, list[dict[str, Any]]] = {order_id: [] for order_id in order_ids}
    for row in _rows(response):
        grouped.setdefault(str(row["order_id"]), []).append(row)
    return grouped


def _load_confirm_events(
    service_client: _ServiceRoleClient,
    order_ids: list[str],
) -> list[dict[str, Any]]:
    if not order_ids:
        return []
    response = (
        service_client.client.table("order_events")
        .select("order_id, created_at, to_status")
        .in_("order_id", order_ids)
        .eq("to_status", "confirmed")
        .order("created_at", desc=False)
        .execute()
    )
    return _rows(response)


def _build_queue_item(
    *,
    order_row: dict[str, Any],
    items: list[dict[str, Any]],
    now: datetime,
) -> OrderQueueItem:
    order_id = str(order_row["id"])
    status = str(order_row["status"])
    fulfilment = str(order_row["fulfilment"])
    return OrderQueueItem(
        id=order_id,
        status=status,
        fulfilment=fulfilment,
        total_ngwee=_order_total_ngwee(
            items=items,
            delivery_fee_ngwee=int(order_row.get("delivery_fee_ngwee") or 0),
        ),
        item_count=len(items),
        preview_title=_preview_title(items),
        created_at=str(order_row["created_at"]),
        available_actions=_available_vendor_actions(status=status, fulfilment=fulfilment),
        urgency=compute_urgency(
            status=status,
            created_at=_parse_timestamp(str(order_row["created_at"])),
            now=now,
        ),
    )


def _queue_counts(orders: list[OrderQueueItem]) -> dict[str, int]:
    counts = {
        "all": len(orders),
        "needs_action": 0,
        "placed": 0,
        "confirmed": 0,
        "processing": 0,
        "ready": 0,
        "shipped": 0,
    }
    for order in orders:
        if order.status in counts:
            counts[order.status] += 1
        if _needs_action_for_order(status=order.status, fulfilment=order.fulfilment):
            counts["needs_action"] += 1
    return counts


def _filter_orders(
    orders: list[OrderQueueItem],
    *,
    status: QueueStatusFilter,
) -> list[OrderQueueItem]:
    if status == "all":
        return orders
    if status == "needs_action":
        return [
            order
            for order in orders
            if _needs_action_for_order(status=order.status, fulfilment=order.fulfilment)
        ]
    return [order for order in orders if order.status == status]


def _build_dashboard(
    service_client: _ServiceRoleClient,
    vendor_id: str,
) -> VendorDashboardResponse:
    now = datetime.now(tz=UTC)
    day_start, day_end = lusaka_day_bounds(now=now)
    lusaka_today = now.astimezone(LUSAKA_TZ).date().isoformat()

    order_rows = _load_vendor_orders(service_client, vendor_id)
    order_ids = [str(row["id"]) for row in order_rows]
    items_by_order = _load_items_by_order(service_client, order_ids)

    queue_items = [
        _build_queue_item(
            order_row=row,
            items=items_by_order.get(str(row["id"]), []),
            now=now,
        )
        for row in order_rows
    ]

    order_totals = {item.id: item.total_ngwee for item in queue_items}
    confirm_events = _load_confirm_events(service_client, order_ids)
    takings = compute_takings_ngwee(
        confirmed_events=confirm_events,
        order_totals=order_totals,
        day_start_utc=day_start,
        day_end_utc=day_end,
    )

    needs_action = sort_needs_action(
        [
            item
            for item in queue_items
            if _needs_action_for_order(status=item.status, fulfilment=item.fulfilment)
        ]
    )

    return VendorDashboardResponse(
        takings_ngwee=takings,
        takings_date=lusaka_today,
        needs_action=needs_action[:10],
        queue_counts=_queue_counts(queue_items),
    )


@router.get("/dashboard", response_model=VendorDashboardResponse)
def get_vendor_dashboard(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorDashboardResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    return _build_dashboard(service_client, str(vendor["id"]))


@router.get("/queue", response_model=list[OrderQueueItem])
def list_vendor_orders_queue(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[QueueStatusFilter, Query()] = "needs_action",
) -> list[OrderQueueItem]:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    all_orders_response = (
        service_client.client.table("orders")
        .select("id, status, fulfilment, delivery_fee_ngwee, created_at")
        .eq("vendor_id", str(vendor["id"]))
        .order("created_at", desc=True)
        .execute()
    )
    order_rows = _rows(all_orders_response)
    order_ids = [str(row["id"]) for row in order_rows]
    items_by_order = _load_items_by_order(service_client, order_ids)
    now = datetime.now(tz=UTC)
    queue_items = [
        _build_queue_item(
            order_row=row,
            items=items_by_order.get(str(row["id"]), []),
            now=now,
        )
        for row in order_rows
    ]
    filtered = _filter_orders(queue_items, status=status)
    if status == "needs_action":
        return sort_needs_action(filtered)
    return filtered
