"""Customer-scoped payment status polling and retry for checkout pending UX."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import NgweeInt, StrictModel
from app.services.payments.base import (
    PaymentStrategy,
)
from app.services.payments.initiate import InitiatePaymentRequest, initiate_checkout_payment
from app.services.payments.state import PaymentStatus
from fastapi import APIRouter, Depends, Query
from pydantic import Field

router = APIRouter(prefix="/payments", tags=["payments"])

WAITING_STATUSES = frozenset(
    {
        PaymentStatus.INITIATED.value,
        PaymentStatus.USSD_PUSHED.value,
        PaymentStatus.PAY_OFFLINE.value,
    }
)
RETRYABLE_STATUSES = frozenset(
    {
        PaymentStatus.FAILED.value,
        PaymentStatus.EXPIRED.value,
        PaymentStatus.CANCELLED.value,
    }
)
PaymentStatusLiteral = Literal[
    "initiated",
    "ussd_pushed",
    "pay_offline",
    "success",
    "failed",
    "expired",
    "cancelled",
    "cod",
]


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class ProductContextLine(StrictModel):
    order_item_id: str
    item_kind: Literal["product"] = "product"
    listing_id: str


class IdentifiedProductContextLine(ProductContextLine):
    product_id: str


class ProductContextOrder(StrictModel):
    order_id: str
    lines: list[IdentifiedProductContextLine | ProductContextLine] = Field(min_length=1)


class ServiceContextLink(StrictModel):
    job_id: str
    obligation_id: str
    leg: Literal["deposit", "balance"]
    order_id: str
    obligation_amount_ngwee: NgweeInt
    current_payment_id: str


class TicketContextLine(StrictModel):
    order_item_id: str
    ticket_type_id: str
    instance_id: str
    qty: int
    unit_price_ngwee: NgweeInt


class TicketContextOrder(StrictModel):
    order_id: str
    lines: list[TicketContextLine] = Field(min_length=1)


class CheckoutContextBase(StrictModel):
    version: Literal[1] = 1
    buyer_id: str
    payment_id: str
    checkout_group_id: str
    order_ids: list[str] = Field(min_length=1)
    rail: Literal["mtn", "airtel", "zamtel", "card"]
    cod: Literal[False] = False
    amount_ngwee: NgweeInt
    # Application collection intent, not a payments.currency column or provider hint.
    currency: Literal["ZMW"] = "ZMW"


class ProductCheckoutContext(CheckoutContextBase):
    kind: Literal["product"] = "product"
    orders: list[ProductContextOrder] = Field(min_length=1)


class ServiceCheckoutContext(CheckoutContextBase):
    kind: Literal["service"] = "service"
    service: ServiceContextLink


class TicketCheckoutContext(CheckoutContextBase):
    kind: Literal["ticket"] = "ticket"
    ticket: TicketContextOrder


CheckoutContext = Annotated[
    ProductCheckoutContext | ServiceCheckoutContext | TicketCheckoutContext,
    Field(discriminator="kind"),
]


class PaymentStatusResponse(StrictModel):
    checkout_group_id: str
    payment_id: str | None
    status: PaymentStatusLiteral
    amount_ngwee: NgweeInt
    rail: str | None = None
    cod: bool
    order_id: str
    payer_phone: str | None = None
    checkout_context: CheckoutContext | None = None


class PaymentRetryRequest(StrictModel):
    checkout_group_id: str
    payer_number: str | None = Field(default=None, max_length=20)
    # Preferred MoMo rail for first initiate when no prior payment row exists.
    rail: Literal["mtn", "airtel"] | None = None


class PaymentRetryResponse(StrictModel):
    checkout_group_id: str
    payment_id: str
    status: PaymentStatusLiteral
    order_count: int


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _load_checkout_group(
    service: ServiceRoleClient,
    checkout_group_id: str,
) -> dict[str, Any] | None:
    response = (
        service.client.table("checkout_groups")
        .select("id, customer_id, total_ngwee, status")
        .eq("id", checkout_group_id)
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def _assert_group_owner(group: dict[str, Any] | None, customer_id: str) -> dict[str, Any]:
    if group is None:
        raise AppError(
            code="not_found",
            message="Checkout group not found",
            http_status=404,
            details={"checkout_group_id": "unknown"},
        )
    if str(group.get("customer_id")) != customer_id:
        raise AppError(
            code="forbidden",
            message="You do not have access to this checkout group",
            http_status=403,
        )
    return group


def _load_orders_for_group(
    service: ServiceRoleClient,
    checkout_group_id: str,
) -> list[dict[str, Any]]:
    response = (
        service.client.table("orders")
        .select("id, cod, customer_id")
        .eq("checkout_group_id", checkout_group_id)
        .order("created_at", desc=False)
        .execute()
    )
    rows = _rows(response)
    if rows:
        return rows
    obligation = _single_row(
        service.client.table("service_payment_obligations")
        .select("order_id")
        .eq("checkout_group_id", checkout_group_id)
        .maybe_single()
        .execute()
    )
    if obligation:
        return _rows(
            service.client.table("orders")
            .select("id, cod, customer_id")
            .eq("id", obligation["order_id"])
            .execute()
        )
    return []


def _load_latest_payment(
    service: ServiceRoleClient,
    checkout_group_id: str,
) -> dict[str, Any] | None:
    response = (
        service.client.table("payments")
        .select("id, checkout_group_id, status, amount_ngwee, rail, raw, created_at, updated_at")
        .eq("checkout_group_id", checkout_group_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    return rows[0] if rows else None


def _load_payment_by_id(
    service: ServiceRoleClient,
    payment_id: str,
) -> dict[str, Any] | None:
    response = (
        service.client.table("payments")
        .select(
            "id, checkout_group_id, status, amount_ngwee, rail, provider, raw, "
            "created_at, updated_at"
        )
        .eq("id", payment_id)
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def _extract_payer_phone(payment: dict[str, Any] | None) -> str | None:
    if payment is None:
        return None
    raw = payment.get("raw")
    if not isinstance(raw, dict):
        return None
    for key in ("payer_phone", "phone", "payer_number"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    collection = raw.get("collection")
    if isinstance(collection, dict):
        phone = collection.get("phone")
        if isinstance(phone, str) and phone.strip():
            return phone.strip()
    return None


def _build_status_response(
    *,
    group: dict[str, Any],
    orders: list[dict[str, Any]],
    payment: dict[str, Any] | None,
) -> PaymentStatusResponse:
    checkout_group_id = str(group["id"])
    if not orders:
        raise AppError(
            code="orders.not_found",
            message="No orders found for this checkout group",
            http_status=404,
            details={"checkout_group_id": checkout_group_id},
        )

    cod = any(bool(order.get("cod")) for order in orders)
    order_id = str(orders[0]["id"])
    total_raw = group.get("total_ngwee", 0)
    amount_ngwee = int(total_raw) if isinstance(total_raw, int) else 0

    if cod:
        return PaymentStatusResponse(
            checkout_group_id=checkout_group_id,
            payment_id=None,
            status="cod",
            amount_ngwee=amount_ngwee,
            rail=None,
            cod=True,
            order_id=order_id,
            payer_phone=None,
        )

    if payment is None:
        raise AppError(
            code="payment.not_found",
            message="No payment found for this checkout group",
            http_status=404,
            details={"checkout_group_id": checkout_group_id},
        )

    payment_amount = payment.get("amount_ngwee")
    if isinstance(payment_amount, int) and payment_amount > 0:
        amount_ngwee = payment_amount

    status_raw = payment.get("status")
    status = str(status_raw) if isinstance(status_raw, str) else PaymentStatus.INITIATED.value

    return PaymentStatusResponse(
        checkout_group_id=checkout_group_id,
        payment_id=str(payment["id"]),
        status=status,  # type: ignore[arg-type]
        amount_ngwee=amount_ngwee,
        rail=str(payment["rail"]) if payment.get("rail") is not None else None,
        cod=False,
        order_id=order_id,
        payer_phone=_extract_payer_phone(payment),
    )



# The context is navigation evidence, never authority to initiate/resume or fund a job.
# Reads request exact counts: a truncated PostgREST result is not a complete binding.
_CONTEXT_MAX_INTEGER = 2**53 - 1
_CONTEXT_ORDER_COLUMNS = (
    "id, checkout_group_id, customer_id, vendor_id, cod, delivery_fee_ngwee, "
    "platform_fee_ngwee, commission_snapshot, updated_at"
)
_CONTEXT_GROUP_COLUMNS = (
    "id, customer_id, subtotal_ngwee, delivery_fee_ngwee, platform_fee_ngwee, "
    "total_ngwee, status, updated_at"
)
_CONTEXT_PAYMENT_COLUMNS = (
    "id, checkout_group_id, status, amount_ngwee, rail, provider, created_at, updated_at"
)
_CONTEXT_OBLIGATION_COLUMNS = "id, order_id, job_id, checkout_group_id, leg, amount_ngwee"
# These obligation identity columns have an existing immutable-identity trigger.
# Mutable acknowledgements are deliberately outside this navigation projection.
_CONTEXT_PRODUCT_GRAPH = (
    "order_item_id, listing_id, product_id, "
    "listing:vendor_listings(id,vendor_id,product_id,updated_at)"
)
_CONTEXT_TICKET_GRAPH = (
    "order_item_id, ticket_type_id, instance_id, "
    "ticket_type:ticket_types(id,event_id,kind,updated_at,"
    "event:events(id,organiser_vendor_id,updated_at)),"
    "instance:event_instances(id,event_id,updated_at,"
    "event:events(id,organiser_vendor_id,updated_at))"
)
_CONTEXT_SERVICE_GRAPH = (
    "order_item_id, job_id, quote_id, job:jobs(id,customer_id,updated_at),"
    "quote:job_quotes(id,job_id,provider_vendor_id,amount_ngwee,status,updated_at)"
)
_CONTEXT_ITEM_GRAPH = (
    "id,order_id,item_kind,qty,unit_price_ngwee,updated_at,"
    f"product_detail:order_item_products({_CONTEXT_PRODUCT_GRAPH}),"
    f"ticket_detail:order_item_tickets({_CONTEXT_TICKET_GRAPH}),"
    f"service_detail:order_item_services({_CONTEXT_SERVICE_GRAPH})"
)


def _context_error() -> AppError:
    return AppError(
        code="payment.context_unavailable",
        message="Payment checkout context is unavailable",
        http_status=409,
    )


def _context_require(condition: bool) -> None:
    if not condition:
        raise _context_error()


def _context_id(value: Any) -> str:
    if not isinstance(value, str):
        raise _context_error()
    try:
        result = str(UUID(value))
    except ValueError:
        raise _context_error() from None
    _context_require(result == value)
    return result


def _context_integer(value: Any, *, minimum: int = 1) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= _CONTEXT_MAX_INTEGER
    ):
        raise _context_error()
    return value


def _context_one(rows: list[dict[str, Any]]) -> dict[str, Any]:
    _context_require(len(rows) == 1)
    return rows[0]


def _context_version(row: dict[str, Any]) -> None:
    value = row.get("updated_at")
    if not isinstance(value, str):
        raise _context_error()
    try:
        version = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _context_error() from None
    _context_require(version.tzinfo is not None)


def _context_embedded(
    value: Any, identity: str, required: tuple[str, ...] = ()
) -> dict[str, Any]:
    if (
        not isinstance(value, dict) or value.get("id") != identity
        or any(field not in value for field in required)
    ):
        raise _context_error()
    _context_version(value)
    return value


def _context_selection_names(columns: str) -> list[str]:
    """Top-level PostgREST result names, retaining embedded relationship objects."""
    depth = 0
    start = 0
    selections: list[str] = []
    for index, char in enumerate(columns + ","):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            _context_require(depth >= 0)
        elif char == "," and depth == 0:
            selections.append(columns[start:index].strip())
            start = index + 1
    _context_require(depth == 0)
    return [selection.split("(", 1)[0].split(":", 1)[0].strip()
            for selection in selections]


class _ContextReader:
    """Select-only journal; recheck every binding before returning a projection.

    Embedded relationship graphs share one select-statement snapshot. Mutation
    tokens also detect observed ABA changes in versioned rows. The journal is
    not an atomic snapshot of every graph, nor a cross-request transaction.
    The existing resume/verify endpoints retain their own financial checks.
    """

    def __init__(self, service: ServiceRoleClient) -> None:
        self.service = service
        self.journal: list[
            tuple[str, str, str, str | list[str], str, list[dict[str, Any]]]
        ] = []

    def _query(
        self, table: str, columns: str, field: str, values: str | list[str], key: str
    ) -> list[dict[str, Any]]:
        query = self.service.client.table(table).select(columns, count="exact")
        query = query.eq(field, values) if isinstance(values, str) else query.in_(field, values)
        response = query.order(key).execute()
        data = getattr(response, "data", None)
        count = getattr(response, "count", None)
        if not isinstance(data, list) or type(count) is not int or count != len(data):
            raise _context_error()
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        names = _context_selection_names(columns)
        for row in data:
            if not isinstance(row, dict) or any(name not in row for name in names):
                raise _context_error()
            identity = _context_id(row.get(key))
            if "updated_at" in names:
                _context_version(row)
            _context_require(identity not in seen)
            seen.add(identity)
            _context_require(
                row.get(field) == values
                if isinstance(values, str)
                else row.get(field) in values
            )
            rows.append({name: deepcopy(row[name]) for name in names})
        return rows

    def read(
        self,
        table: str,
        columns: str,
        field: str,
        values: str | list[str],
        *,
        key: str = "id",
    ) -> list[dict[str, Any]]:
        for prior_table, prior_columns, prior_field, prior_values, prior_key, prior in self.journal:
            if (table, columns, field, values, key) == (
                prior_table, prior_columns, prior_field, prior_values, prior_key
            ):
                return deepcopy(prior)
        rows = self._query(table, columns, field, values, key)
        self.journal.append((table, columns, field, values, key, deepcopy(rows)))
        return rows

    def verify(self) -> None:
        for table, columns, field, values, key, before in self.journal:
            _context_require(self._query(table, columns, field, values, key) == before)


def _context_orders_owned(orders: list[dict[str, Any]], buyer_id: str) -> None:
    for order in orders:
        if order.get("customer_id") != buyer_id:
            raise AppError(
                code="forbidden", message="You do not have access to this checkout group",
                http_status=403,
            )
        _context_id(order.get("vendor_id"))
        _context_require(order.get("cod") is False)
        _context_id(order.get("checkout_group_id"))


def _context_items(
    reader: _ContextReader, orders: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    order_ids = [_context_id(order.get("id")) for order in orders]
    _context_require(bool(order_ids))
    items = reader.read(
        "order_items", _CONTEXT_ITEM_GRAPH, "order_id", order_ids
    )
    _context_require({item["order_id"] for item in items} == set(order_ids))
    for item in items:
        _context_integer(item.get("qty"))
        _context_integer(item.get("unit_price_ngwee"))
    return items


def _context_extensions(
    items: list[dict[str, Any]], domain: str
) -> dict[str, dict[str, Any]]:
    # All three one-to-one extensions were embedded in the same item select.
    # Their presence/absence must not be assembled from separate snapshots.
    selected: dict[str, dict[str, Any]] = {}
    for item in items:
        for kind in ("product", "ticket", "service"):
            detail = item.get(kind + "_detail")
            if kind == domain:
                if not isinstance(detail, dict) or detail.get("order_item_id") != item["id"]:
                    raise _context_error()
                required = {
                    "product": ("listing_id", "product_id", "listing"),
                    "ticket": ("ticket_type_id", "instance_id", "ticket_type", "instance"),
                    "service": ("job_id", "quote_id", "job", "quote"),
                }[kind]
                _context_require(all(field in detail for field in required))
                selected[item["id"]] = detail
            else:
                _context_require(detail is None)
    return selected


def _product_context(
    reader: _ContextReader, orders: list[dict[str, Any]], common: dict[str, Any],
    items: list[dict[str, Any]],
) -> ProductCheckoutContext:
    _context_require(all(item.get("item_kind") == "product" for item in items))
    extensions = _context_extensions(items, "product")
    total = 0
    output: list[ProductContextOrder] = []
    for order in orders:
        lines: list[IdentifiedProductContextLine | ProductContextLine] = []
        total += _context_integer(order.get("delivery_fee_ngwee"), minimum=0)
        for item in items:
            if item["order_id"] != order["id"]:
                continue
            detail = extensions[item["id"]]
            listing = _context_embedded(
                detail.get("listing"), _context_id(detail["listing_id"]),
                ("vendor_id", "product_id"),
            )
            _context_require(listing.get("vendor_id") == order["vendor_id"])
            _context_require(detail.get("product_id") == listing.get("product_id"))
            line = ProductContextLine(
                order_item_id=item["id"], listing_id=detail["listing_id"]
            )
            if detail["product_id"] is not None:
                line = IdentifiedProductContextLine(
                    **line.model_dump(), product_id=_context_id(detail["product_id"])
                )
            lines.append(line)
            total += item["qty"] * item["unit_price_ngwee"]
        output.append(ProductContextOrder(order_id=order["id"], lines=lines))
    _context_require(_context_integer(total) == common["amount_ngwee"])
    return ProductCheckoutContext(**common, orders=output)


def _ticket_context(
    reader: _ContextReader, orders: list[dict[str, Any]], common: dict[str, Any],
    items: list[dict[str, Any]], group: dict[str, Any],
) -> TicketCheckoutContext:
    _context_require(len(orders) == 1)
    order = orders[0]
    _context_require(len(items) == 1 and items[0].get("item_kind") == "ticket")
    item = items[0]
    detail = _context_extensions(items, "ticket")[item["id"]]
    ticket_type_id = _context_id(detail.get("ticket_type_id"))
    instance_id = _context_id(detail.get("instance_id"))
    # These two edges are selected together, not assembled from independent
    # ticket-type and instance reads that can splice an ABA reparenting race.
    ticket_type = _context_embedded(
        detail.get("ticket_type"), ticket_type_id, ("event_id", "kind", "event")
    )
    instance = _context_embedded(detail.get("instance"), instance_id, ("event_id", "event"))
    event_id = _context_id(instance.get("event_id"))
    _context_require(ticket_type.get("event_id") == event_id)
    _context_require(
        isinstance(ticket_type.get("kind"), str) and ticket_type["kind"] in {"fixed", "tier"}
    )
    event = _context_embedded(instance.get("event"), event_id, ("organiser_vendor_id",))
    type_event = _context_embedded(ticket_type.get("event"), event_id, ("organiser_vendor_id",))
    _context_require(type_event == event)
    _context_require(event.get("organiser_vendor_id") == order["vendor_id"])
    _context_require(_context_integer(order.get("delivery_fee_ngwee"), minimum=0) == 0)
    subtotal = _context_integer(item["qty"] * item["unit_price_ngwee"])
    fee = _context_integer(group.get("platform_fee_ngwee"), minimum=0)
    _context_require(_context_integer(order.get("platform_fee_ngwee"), minimum=0) == fee)
    _context_require(_context_integer(group.get("subtotal_ngwee")) == subtotal)
    _context_require(_context_integer(group.get("delivery_fee_ngwee"), minimum=0) == 0)
    snapshot = order.get("commission_snapshot")
    if not isinstance(snapshot, dict):
        raise _context_error()
    _context_require(_context_integer(snapshot.get("platform_fee_ngwee"), minimum=0) == fee)
    payer = snapshot.get("fee_payer")
    _context_require(isinstance(payer, str) and payer in {"buyer", "organiser"})
    _context_require(payer != "organiser" or fee == 0)
    lines = snapshot.get("lines")
    if not isinstance(lines, list) or len(lines) != 1 or not isinstance(lines[0], dict):
        raise _context_error()
    _context_integer(lines[0].get("qty"))
    _context_integer(lines[0].get("unit_price_ngwee"))
    _context_integer(lines[0].get("line_total_ngwee"))
    _context_require(all(lines[0].get(key) == value for key, value in (
        ("ticket_type_id", ticket_type_id), ("instance_id", instance_id),
        ("qty", item["qty"]), ("unit_price_ngwee", item["unit_price_ngwee"]),
        ("line_total_ngwee", subtotal),
    )))
    _context_require(_context_integer(subtotal + fee) == common["amount_ngwee"])
    return TicketCheckoutContext(
        **common,
        ticket=TicketContextOrder(order_id=order["id"], lines=[TicketContextLine(
            order_item_id=item["id"], ticket_type_id=ticket_type_id, instance_id=instance_id,
            qty=item["qty"], unit_price_ngwee=item["unit_price_ngwee"],
        )]),
    )


def _service_context(
    reader: _ContextReader, direct_orders: list[dict[str, Any]], obligation: dict[str, Any],
    common: dict[str, Any],
) -> ServiceCheckoutContext:
    order_id = _context_id(obligation.get("order_id"))
    job_id = _context_id(obligation.get("job_id"))
    leg: Literal["deposit", "balance"]
    if obligation.get("leg") == "deposit":
        leg = "deposit"
    elif obligation.get("leg") == "balance":
        leg = "balance"
    else:
        raise _context_error()
    _context_require(_context_integer(obligation.get("amount_ngwee")) == common["amount_ngwee"])
    order = _context_one(reader.read("orders", _CONTEXT_ORDER_COLUMNS, "id", order_id))
    _context_orders_owned([order], common["buyer_id"])
    _context_require(_context_integer(order.get("delivery_fee_ngwee"), minimum=0) == 0)
    original_group = _context_one(reader.read(
        "checkout_groups", _CONTEXT_GROUP_COLUMNS,
        "id", order["checkout_group_id"],
    ))
    _assert_group_owner(original_group, common["buyer_id"])
    original_orders = reader.read(
        "orders", _CONTEXT_ORDER_COLUMNS, "checkout_group_id", original_group["id"]
    )
    _context_orders_owned(original_orders, common["buyer_id"])
    _context_require([row["id"] for row in original_orders] == [order_id])
    _context_require(
        [row["id"] for row in direct_orders] == [order_id]
        if leg == "deposit" else not direct_orders
    )
    _context_require(
        (order["checkout_group_id"] == common["checkout_group_id"]) == (leg == "deposit")
    )
    obligations = reader.read(
        "service_payment_obligations", _CONTEXT_OBLIGATION_COLUMNS, "order_id", order_id
    )
    by_leg: dict[str, dict[str, Any]] = {}
    for linked in obligations:
        linked_leg = str(linked.get("leg"))
        _context_require(linked_leg in {"deposit", "balance"} and linked_leg not in by_leg)
        _context_require(linked.get("job_id") == job_id)
        by_leg[linked_leg] = linked
        linked_group = _context_one(reader.read(
            "checkout_groups", _CONTEXT_GROUP_COLUMNS,
            "id", _context_id(linked.get("checkout_group_id")),
        ))
        _assert_group_owner(linked_group, common["buyer_id"])
        _context_require(
            _context_integer(linked_group.get("total_ngwee"))
            == _context_integer(linked.get("amount_ngwee"))
        )
        _context_require(
            (linked_group["id"] == original_group["id"]) == (linked_leg == "deposit")
        )
    _context_require("deposit" in by_leg and by_leg.get(str(leg)) == obligation)
    items = _context_items(reader, [order])
    _context_require(all(
        item.get("item_kind") in {"service_deposit", "service_balance"} for item in items
    ))
    extensions = _context_extensions(items, "service")
    item_legs: set[str] = set()
    quote_ids: set[str] = set()
    quote: dict[str, Any] | None = None
    for item in items:
        item_leg = str(item["item_kind"]).removeprefix("service_")
        _context_require(item_leg not in item_legs and item_leg in by_leg)
        item_legs.add(item_leg)
        _context_require(item["qty"] == 1)
        _context_require(item["unit_price_ngwee"] == by_leg[item_leg]["amount_ngwee"])
        detail = extensions[item["id"]]
        _context_require(detail.get("job_id") == job_id)
        quote_id = _context_id(detail.get("quote_id"))
        quote_ids.add(quote_id)
        job = _context_embedded(detail.get("job"), job_id, ("customer_id",))
        if job.get("customer_id") != common["buyer_id"]:
            raise AppError(code="forbidden", message="You do not have access to this job",
                           http_status=403)
        linked_quote = _context_embedded(
            detail.get("quote"), quote_id,
            ("job_id", "provider_vendor_id", "amount_ngwee", "status"),
        )
        _context_require(quote is None or quote == linked_quote)
        quote = linked_quote
    _context_require("deposit" in item_legs and len(quote_ids) == 1)
    quote_id = next(iter(quote_ids))
    if quote is None:
        raise _context_error()
    _context_require(
        quote.get("job_id") == job_id and quote.get("provider_vendor_id") == order["vendor_id"]
        and quote.get("status") == "accepted"
    )
    total = _context_integer(sum(_context_integer(row["amount_ngwee"]) for row in obligations))
    _context_require(_context_integer(quote.get("amount_ngwee")) == total)
    snapshot = order.get("commission_snapshot")
    if not isinstance(snapshot, dict):
        raise _context_error()
    _context_require(snapshot.get("job_id") == job_id and snapshot.get("quote_id") == quote_id)
    _context_require(snapshot.get("basis") == "total_job_value")
    lines = snapshot.get("lines")
    if not isinstance(lines, list) or len(lines) != 1 or not isinstance(lines[0], dict):
        raise _context_error()
    _context_require(_context_integer(lines[0].get("line_total_ngwee")) == total)
    _context_require(lines[0].get("qty") == 1)
    _context_require(_context_integer(lines[0].get("unit_price_ngwee")) == total)
    attempts = reader.read(
        "payments", "id, checkout_group_id, created_at, updated_at", "checkout_group_id",
        common["checkout_group_id"],
    )
    dated: list[tuple[datetime, str]] = []
    for attempt in attempts:
        stamp = attempt.get("created_at")
        if not isinstance(stamp, str):
            raise _context_error()
        try:
            created = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            raise _context_error() from None
        _context_require(created.tzinfo is not None)
        dated.append((created, attempt["id"]))
    _context_require(bool(dated))
    newest = max(stamp for stamp, _ in dated)
    _context_require([identity for stamp, identity in dated if stamp == newest]
                     == [common["payment_id"]])
    common["order_ids"] = [order_id]
    return ServiceCheckoutContext(**common, service=ServiceContextLink(
        job_id=job_id, obligation_id=obligation["id"], leg=leg, order_id=order_id,
        obligation_amount_ngwee=obligation["amount_ngwee"],
        current_payment_id=common["payment_id"],
    ))


def _load_checkout_context(
    service: ServiceRoleClient, buyer_id: str, payment: dict[str, Any],
    group: dict[str, Any], status: PaymentStatusResponse,
) -> CheckoutContext:
    reader = _ContextReader(service)
    buyer_id = _context_id(buyer_id)
    payment_id = _context_id(payment.get("id"))
    group_id = _context_id(payment.get("checkout_group_id"))
    current = _context_one(reader.read("payments", _CONTEXT_PAYMENT_COLUMNS, "id", payment_id))
    owned_group = _context_one(reader.read(
        "checkout_groups", _CONTEXT_GROUP_COLUMNS, "id", group_id
    ))
    _assert_group_owner(owned_group, buyer_id)
    _context_require(all(
        current.get(key) == payment.get(key)
        for key in (
            "id", "checkout_group_id", "status", "amount_ngwee", "rail", "provider",
            "created_at", "updated_at",
        )
    ))
    _context_require(all(
        owned_group.get(key) == group.get(key)
        for key in ("id", "customer_id", "total_ngwee", "status")
    ))
    amount = _context_integer(current.get("amount_ngwee"))
    _context_require(amount == _context_integer(owned_group.get("total_ngwee")))
    _context_require(current.get("provider") == "lenco")
    _context_require(
        isinstance(current.get("rail"), str)
        and current["rail"] in {"mtn", "airtel", "zamtel", "card"}
    )
    _context_require(
        status.payment_id == payment_id and status.checkout_group_id == group_id
        and status.amount_ngwee == amount and status.rail == current["rail"] and not status.cod
        and status.status == current.get("status")
    )
    orders = reader.read("orders", _CONTEXT_ORDER_COLUMNS, "checkout_group_id", group_id)
    _context_orders_owned(orders, buyer_id)
    obligations = reader.read(
        "service_payment_obligations", _CONTEXT_OBLIGATION_COLUMNS, "checkout_group_id", group_id
    )
    common: dict[str, Any] = dict(
        buyer_id=buyer_id, payment_id=payment_id, checkout_group_id=group_id,
        order_ids=[row["id"] for row in orders], rail=current["rail"], amount_ngwee=amount,
    )
    context: CheckoutContext
    if obligations:
        context = _service_context(reader, orders, _context_one(obligations), common)
    else:
        items = _context_items(reader, orders)
        _context_require(all(isinstance(item.get("item_kind"), str) for item in items))
        kinds = {item["item_kind"] for item in items}
        if kinds == {"product"}:
            context = _product_context(reader, orders, common, items)
        elif kinds == {"ticket"}:
            context = _ticket_context(reader, orders, common, items, owned_group)
        else:
            raise _context_error()
    _context_require(status.order_id in context.order_ids)
    reader.verify()
    return context


async def _create_retry_payment_attempt(
    service: ServiceRoleClient,
    *,
    request: InitiatePaymentRequest,
    actor_id: str,
    strategy: PaymentStrategy | None = None,
) -> tuple[str, PaymentStatus]:
    result = await initiate_checkout_payment(service, request, actor_id=actor_id, strategy=strategy)
    return result.payment_id, result.status


@router.get("/status", response_model=PaymentStatusResponse)
async def get_payment_status(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    group: str | None = Query(default=None, min_length=1),
    payment: str | None = Query(default=None, min_length=1),
) -> PaymentStatusResponse:
    if not group and not payment:
        raise AppError(
            code="validation_error",
            message="Provide group or payment query parameter",
            http_status=422,
            details={"fields": ["group", "payment"]},
        )

    checkout_group_id: str
    latest_payment: dict[str, Any] | None

    if payment:
        _context_id(payment)
        payment_row = _load_payment_by_id(service, payment)
        if payment_row is None:
            raise AppError(
                code="not_found",
                message="Payment not found",
                http_status=404,
                details={"payment_id": payment},
            )
        _context_require(payment_row.get("id") == payment)
        _context_integer(payment_row.get("amount_ngwee"))
        _context_require(
            isinstance(payment_row.get("status"), str)
            and payment_row["status"] in {state.value for state in PaymentStatus}
        )
        checkout_group_id = _context_id(payment_row.get("checkout_group_id"))
        group_row = _assert_group_owner(
            _load_checkout_group(service, checkout_group_id),
            current_user.id,
        )
        latest_payment = payment_row
        _context_integer(group_row.get("total_ngwee"))
        if group is not None and group != checkout_group_id:
            raise _context_error()
    else:
        assert group is not None
        checkout_group_id = group
        group_row = _assert_group_owner(
            _load_checkout_group(service, checkout_group_id),
            current_user.id,
        )
        latest_payment = _load_latest_payment(service, checkout_group_id)

    orders = _load_orders_for_group(service, checkout_group_id)
    for order in orders:
        if str(order.get("customer_id")) != current_user.id:
            raise AppError(
                code="forbidden",
                message="You do not have access to this checkout group",
                http_status=403,
            )

    response = _build_status_response(group=group_row, orders=orders, payment=latest_payment)
    if payment:
        assert latest_payment is not None
        response.checkout_context = _load_checkout_context(
            service, current_user.id, latest_payment, group_row, response
        )
    return response


@router.post("/retry", response_model=PaymentRetryResponse)
async def retry_payment(
    body: PaymentRetryRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PaymentRetryResponse:
    group = _assert_group_owner(
        _load_checkout_group(service, body.checkout_group_id),
        current_user.id,
    )
    orders = _load_orders_for_group(service, body.checkout_group_id)
    if not orders:
        raise AppError(
            code="orders.not_found",
            message="No orders found for this checkout group",
            http_status=404,
        )
    if any(bool(order.get("cod")) for order in orders):
        raise AppError(
            code="payment.cod_no_retry",
            message="Cash on delivery orders do not require payment retry",
            http_status=409,
        )

    order_count = len(orders)
    latest = _load_latest_payment(service, body.checkout_group_id)
    if latest is not None:
        status = str(latest.get("status") or "")
        if status in WAITING_STATUSES:
            raise AppError(
                code="payment.in_progress",
                message="A payment attempt is already in progress",
                http_status=409,
                details={"payment_id": str(latest["id"]), "status": status},
            )
        if status not in RETRYABLE_STATUSES and status != PaymentStatus.SUCCESS.value:
            raise AppError(
                code="payment.not_retryable",
                message="Payment cannot be retried in its current state",
                http_status=409,
                details={"status": status},
            )
        if status == PaymentStatus.SUCCESS.value:
            raise AppError(
                code="payment.already_successful",
                message="Payment already succeeded",
                http_status=409,
            )

    payer_phone = body.payer_number or _extract_payer_phone(latest)
    if not payer_phone:
        raise AppError(
            code="checkout.payer_number_required",
            message="Payer mobile number is required to retry payment",
            http_status=422,
            details={"field": "payer_number"},
        )

    if latest and latest.get("rail"):
        rail = str(latest["rail"])
    elif body.rail in {"mtn", "airtel"}:
        rail = body.rail
    else:
        rail = "mtn"
    total_raw = group.get("total_ngwee", 0)
    amount_ngwee = int(total_raw) if isinstance(total_raw, int) else 0
    first_order_id = str(orders[0]["id"])

    payment_id, new_status = await _create_retry_payment_attempt(
        service,
        request=InitiatePaymentRequest(
            checkout_group_id=body.checkout_group_id,
            amount_ngwee=amount_ngwee,
            rail=rail,
            phone=payer_phone,
            order_id=first_order_id,
        ),
        actor_id=current_user.id,
    )

    orders_after = _load_orders_for_group(service, body.checkout_group_id)
    if len(orders_after) != order_count:
        raise AppError(
            code="orders.duplicate_detected",
            message="Retry must not create duplicate orders",
            http_status=500,
            details={"before": order_count, "after": len(orders_after)},
        )

    return PaymentRetryResponse(
        checkout_group_id=body.checkout_group_id,
        payment_id=payment_id,
        status=new_status.value,
        order_count=order_count,
    )
