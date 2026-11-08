"""Owner-scoped read of a server-created checkout group (paid tickets, service deposits).

``POST /tickets/checkout`` and ``POST /jobs/{job}/quotes/{quote}/accept`` create a
checkout group + order up front and hand the buyer to ``/checkout?group=<id>``. That
page needs a read model of the group to render the summary and go straight to rail
selection. Amounts come verbatim from the group row: the client never computes them.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import NgweeInt, StrictModel
from app.services.payments.gate import payments_enabled
from fastapi import APIRouter, Depends, Path

router = APIRouter(prefix="/checkout", tags=["checkout"])

UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
CLOSED_GROUP_STATUSES = frozenset({"expired", "abandoned", "cancelled"})
READ_LIMIT_PER_MINUTE = 60

GroupKind = Literal["ticket", "service_deposit", "order"]
OnlineMethod = Literal["momo", "card"]


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class CheckoutGroupLine(StrictModel):
    order_item_id: str
    item_kind: str
    title: str | None = None
    qty: int
    unit_price_ngwee: NgweeInt
    line_total_ngwee: NgweeInt
    ticket_type_name: str | None = None


class CheckoutGroupEvent(StrictModel):
    event_id: str
    title: str
    slug: str | None = None
    venue: str | None = None
    starts_at: str | None = None


class CheckoutGroupService(StrictModel):
    job_id: str
    quote_id: str | None = None
    vendor_id: str
    vendor_name: str
    category: str | None = None


class CheckoutGroupSummaryResponse(StrictModel):
    checkout_group_id: str
    kind: GroupKind
    status: str
    expired: bool
    payable: bool
    order_id: str
    subtotal_ngwee: NgweeInt
    delivery_fee_ngwee: NgweeInt
    platform_fee_ngwee: NgweeInt
    total_ngwee: NgweeInt
    lines: list[CheckoutGroupLine]
    event: CheckoutGroupEvent | None = None
    service: CheckoutGroupService | None = None
    available_methods: list[OnlineMethod]


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _str_or_none(value: object) -> str | None:
    return str(value) if value not in (None, "") else None


def _rate_limit_read(user_id: str, service: ServiceRoleClient) -> None:
    allowed, retry_after = bump_rate_counter(
        scope="checkout_group_read_user",
        key=user_id,
        window=timedelta(minutes=1),
        limit=READ_LIMIT_PER_MINUTE,
        client=service.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="checkout.group.rateLimited",
            message="Too many checkout requests",
        )


def _select_in(
    service: ServiceRoleClient, table: str, columns: str, column: str, ids: list[str]
) -> list[dict[str, Any]]:
    if not ids:
        return []
    return _rows(service.client.table(table).select(columns).in_(column, ids).execute())


def _load_owned_group(
    service: ServiceRoleClient, group_id: str, customer_id: str
) -> dict[str, Any]:
    # select("*") tolerates databases that predate checkout_groups.platform_fee_ngwee.
    rows = _rows(
        service.client.table("checkout_groups").select("*").eq("id", group_id).limit(1).execute()
    )
    group = rows[0] if rows else None
    if group is None:
        raise AppError(
            code="checkout.group_not_found",
            message="Checkout not found",
            http_status=404,
        )
    if str(group.get("customer_id")) != customer_id:
        raise AppError(
            code="forbidden",
            message="You do not have access to this checkout",
            http_status=403,
        )
    return group


def _event_for(
    service: ServiceRoleClient, item_ids: list[str]
) -> tuple[CheckoutGroupEvent | None, dict[str, str]]:
    links = _select_in(
        service,
        "order_item_tickets",
        "order_item_id, ticket_type_id, instance_id",
        "order_item_id",
        item_ids,
    )
    type_ids = sorted({str(r["ticket_type_id"]) for r in links if r.get("ticket_type_id")})
    instance_ids = sorted({str(r["instance_id"]) for r in links if r.get("instance_id")})
    types = {
        str(r["id"]): r
        for r in _select_in(service, "ticket_types", "id, name, event_id", "id", type_ids)
    }
    instances = {
        str(r["id"]): r
        for r in _select_in(
            service, "event_instances", "id, event_id, starts_at", "id", instance_ids
        )
    }
    tier_by_item = {
        str(link["order_item_id"]): str(types[str(link["ticket_type_id"])].get("name") or "")
        for link in links
        if str(link.get("ticket_type_id")) in types
    }
    event_ids = sorted(
        {str(r["event_id"]) for r in [*types.values(), *instances.values()] if r.get("event_id")}
    )
    events = _select_in(service, "events", "id, title, slug, venue", "id", event_ids)
    if not events:
        return None, tier_by_item
    event = events[0]
    starts_at = next(
        (
            _str_or_none(inst.get("starts_at"))
            for inst in instances.values()
            if str(inst.get("event_id")) == str(event.get("id"))
        ),
        None,
    )
    return (
        CheckoutGroupEvent(
            event_id=str(event["id"]),
            title=str(event.get("title") or ""),
            slug=_str_or_none(event.get("slug")),
            venue=_str_or_none(event.get("venue")),
            starts_at=starts_at,
        ),
        tier_by_item,
    )


def _service_for(
    service: ServiceRoleClient, item_ids: list[str], vendor_id: str
) -> CheckoutGroupService | None:
    links = _select_in(
        service, "order_item_services", "order_item_id, job_id, quote_id", "order_item_id", item_ids
    )
    if not links:
        return None
    link = links[0]
    job_id = str(link.get("job_id") or "")
    jobs = _select_in(service, "jobs", "id, category", "id", [job_id] if job_id else [])
    vendors = _select_in(service, "vendors", "id, display_name", "id", [vendor_id])
    return CheckoutGroupService(
        job_id=job_id,
        quote_id=_str_or_none(link.get("quote_id")),
        vendor_id=vendor_id,
        vendor_name=str(vendors[0].get("display_name") or "") if vendors else "",
        category=_str_or_none(jobs[0].get("category")) if jobs else None,
    )


@router.get("/groups/{group_id}", response_model=CheckoutGroupSummaryResponse)
async def get_checkout_group(
    group_id: Annotated[str, Path(pattern=UUID_PATTERN)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> CheckoutGroupSummaryResponse:
    """Summary of the caller's own ticket / service-deposit checkout group."""
    _rate_limit_read(current_user.id, service)
    group = _load_owned_group(service, group_id, current_user.id)

    orders = _rows(
        service.client.table("orders")
        .select("id, customer_id, vendor_id, cod")
        .eq("checkout_group_id", group_id)
        .execute()
    )
    if any(str(order.get("customer_id")) != current_user.id for order in orders):
        raise AppError(
            code="forbidden",
            message="You do not have access to this checkout",
            http_status=403,
        )
    if not orders:
        raise AppError(
            code="checkout.group_not_payable",
            message="This checkout has no order to pay",
            http_status=409,
        )
    order = orders[0]
    items = _select_in(
        service,
        "order_items",
        "id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot",
        "order_id",
        [str(o["id"]) for o in orders],
    )
    item_ids = [str(item["id"]) for item in items]
    kinds = {str(item.get("item_kind") or "") for item in items}
    kind: GroupKind
    if kinds == {"ticket"}:
        kind = "ticket"
    elif "service_deposit" in kinds:
        kind = "service_deposit"
    else:
        kind = "order"

    event: CheckoutGroupEvent | None = None
    tier_by_item: dict[str, str] = {}
    service_info: CheckoutGroupService | None = None
    if kind == "ticket":
        event, tier_by_item = _event_for(service, item_ids)
    elif kind == "service_deposit":
        service_info = _service_for(service, item_ids, str(order.get("vendor_id") or ""))

    status = str(group.get("status") or "pending")
    expired = status in CLOSED_GROUP_STATUSES
    cod = any(bool(o.get("cod")) for o in orders)
    online_open = payments_enabled() and not cod
    lines = [
        CheckoutGroupLine(
            order_item_id=str(item["id"]),
            item_kind=str(item.get("item_kind") or ""),
            title=_str_or_none(item.get("title_snapshot")),
            qty=_int(item.get("qty")),
            unit_price_ngwee=_int(item.get("unit_price_ngwee")),
            line_total_ngwee=_int(item.get("qty")) * _int(item.get("unit_price_ngwee")),
            ticket_type_name=tier_by_item.get(str(item["id"])) or None,
        )
        for item in items
    ]
    return CheckoutGroupSummaryResponse(
        checkout_group_id=group_id,
        kind=kind,
        status=status,
        expired=expired,
        payable=status == "pending" and not cod,
        order_id=str(order["id"]),
        subtotal_ngwee=_int(group.get("subtotal_ngwee")),
        delivery_fee_ngwee=_int(group.get("delivery_fee_ngwee")),
        platform_fee_ngwee=_int(group.get("platform_fee_ngwee")),
        total_ngwee=_int(group.get("total_ngwee")),
        lines=lines,
        event=event,
        service=service_info,
        available_methods=["momo", "card"] if online_open else [],
    )
