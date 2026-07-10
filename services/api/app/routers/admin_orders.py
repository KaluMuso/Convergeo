from __future__ import annotations

import importlib
import re
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.orders.state import (
    ActorRole,
    OrderEvent,
    OrderTransitionError,
    transition_order,
)
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")
_ORDER_STATUSES = frozenset(
    {
        "placed",
        "confirmed",
        "processing",
        "ready",
        "shipped",
        "delivered",
        "completed",
        "cancelled",
    }
)
MANUAL_ESCROW_CONFIRMATION_PHRASE = "MANUAL ESCROW"
MAX_SEARCH_LEN = 120

Courier = Literal["yango", "indrive", "other"]
EscrowOperation = Literal["hold", "release"]


class ServiceRoleClient(Protocol):
    client: Any


orders_router = APIRouter(prefix="/orders", tags=["admin-orders"])


class OrderSearchItem(BaseModel):
    id: UUID
    status: str
    fulfilment: str
    vendor_id: UUID
    vendor_display_name: str
    vendor_slug: str
    customer_id: UUID
    customer_phone: str | None
    created_at: datetime


class OrderItemOut(BaseModel):
    id: UUID
    item_kind: str
    qty: int
    unit_price_ngwee: int
    title_snapshot: str | None


class PaymentOut(BaseModel):
    id: UUID
    rail: str
    amount_ngwee: int
    status: str
    lenco_reference: str
    created_at: datetime


class LedgerPostingOut(BaseModel):
    id: UUID
    account_id: UUID
    amount_ngwee: int


class LedgerTransactionOut(BaseModel):
    id: UUID
    kind: str
    created_at: datetime
    postings: list[LedgerPostingOut]


class TimelineEventOut(BaseModel):
    id: UUID
    actor: UUID | None
    from_status: str | None
    to_status: str | None
    note: str | None
    created_at: datetime


class OrderDetailOut(BaseModel):
    id: UUID
    status: str
    fulfilment: str
    cod: bool
    delivery_fee_ngwee: int
    checkout_group_id: UUID
    vendor_id: UUID
    vendor_display_name: str
    vendor_slug: str
    customer_id: UUID
    customer_phone: str | None
    customer_display_name: str | None
    created_at: datetime
    items: list[OrderItemOut]
    payments: list[PaymentOut]
    ledger: list[LedgerTransactionOut]
    timeline: list[TimelineEventOut]


class DispatchRequest(BaseModel):
    courier: Courier
    courier_other: str | None = Field(default=None, max_length=80)
    tracking_note: str = Field(min_length=1, max_length=500)
    event: OrderEvent

    @model_validator(mode="after")
    def require_other_label(self) -> DispatchRequest:
        if self.courier == "other" and not (self.courier_other and self.courier_other.strip()):
            raise ValueError("courier_other is required when courier is other")
        return self


class InterventionRequest(BaseModel):
    event: OrderEvent
    reason: str = Field(min_length=1, max_length=2000)
    refund_path: bool = False


class EscrowRequest(BaseModel):
    operation: EscrowOperation
    amount_ngwee: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=2000)
    confirmation_phrase: str = Field(min_length=1, max_length=200)


class DispatchResponse(BaseModel):
    order_id: UUID
    from_status: str
    to_status: str
    event: str
    timeline_event_id: str | None


class InterventionResponse(BaseModel):
    order_id: UUID
    from_status: str
    to_status: str
    event: str


class EscrowResponse(BaseModel):
    order_id: UUID
    operation: EscrowOperation
    transaction_id: str
    amount_ngwee: int
    manual: bool
    balance_sum_ngwee: int


class ManualLedgerPosting(BaseModel):
    account_kind: str
    amount_ngwee: int


class ManualLedgerResult(BaseModel):
    transaction_id: str
    template: str
    manual: bool
    postings: list[ManualLedgerPosting]

    @property
    def balance_sum_ngwee(self) -> int:
        return sum(posting.amount_ngwee for posting in self.postings)


def _table(client: ServiceRoleClient, name: str) -> Any:
    return client.client.table(name)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    raise AppError(
        code="internal_error",
        message=f"Invalid timestamp in {value!r}",
        http_status=500,
    )


def _sanitize_search(value: str, *, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise AppError(
            code="validation_error",
            message=f"{field} cannot be empty",
            http_status=422,
        )
    if len(cleaned) > MAX_SEARCH_LEN:
        raise AppError(
            code="validation_error",
            message=f"{field} is too long",
            http_status=422,
            details={"max_length": MAX_SEARCH_LEN},
        )
    if any(char in cleaned for char in ("%", "_", "\\", ";", "--")):
        raise AppError(
            code="validation_error",
            message=f"Invalid characters in {field}",
            http_status=422,
        )
    return cleaned


def _validate_order_id(order_id: str) -> str:
    cleaned = _sanitize_search(order_id, field="order_id")
    if not _UUID_RE.match(cleaned):
        raise AppError(
            code="validation_error",
            message="order_id must be a valid UUID",
            http_status=422,
        )
    return cleaned


def _validate_status(status: str) -> str:
    cleaned = _sanitize_search(status, field="status").lower()
    if cleaned not in _ORDER_STATUSES:
        raise AppError(
            code="validation_error",
            message="Invalid order status",
            http_status=422,
            details={"allowed": sorted(_ORDER_STATUSES)},
        )
    return cleaned


def _validate_phone(phone: str) -> str:
    cleaned = _sanitize_search(phone, field="phone")
    digits = re.sub(r"[\s\-()]", "", cleaned)
    if not _PHONE_RE.match(digits):
        raise AppError(
            code="validation_error",
            message="phone must be 7–15 digits, optional leading +",
            http_status=422,
        )
    return digits


def _load_vendor_map(client: ServiceRoleClient, vendor_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not vendor_ids:
        return {}
    response = (
        _table(client, "vendors")
        .select("id, display_name, slug")
        .in_("id", sorted(vendor_ids))
        .execute()
    )
    rows = response.data or []
    return {str(row["id"]): row for row in rows}


def _load_profile_map(client: ServiceRoleClient, user_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not user_ids:
        return {}
    response = (
        _table(client, "profiles")
        .select("id, phone, display_name")
        .in_("id", sorted(user_ids))
        .execute()
    )
    rows = response.data or []
    return {str(row["id"]): row for row in rows}


def _order_to_search_item(
    row: dict[str, Any],
    *,
    vendors: dict[str, dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
) -> OrderSearchItem:
    vendor = vendors.get(str(row["vendor_id"]), {})
    profile = profiles.get(str(row["customer_id"]), {})
    return OrderSearchItem(
        id=row["id"],
        status=row["status"],
        fulfilment=row["fulfilment"],
        vendor_id=row["vendor_id"],
        vendor_display_name=vendor.get("display_name") or "—",
        vendor_slug=vendor.get("slug") or "—",
        customer_id=row["customer_id"],
        customer_phone=profile.get("phone"),
        created_at=_parse_timestamp(row["created_at"]),
    )


def _search_orders(
    client: ServiceRoleClient,
    *,
    order_id: str | None = None,
    phone: str | None = None,
    vendor: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> list[OrderSearchItem]:
    if not any((order_id, phone, vendor, status, q)):
        raise AppError(
            code="validation_error",
            message="Provide at least one search parameter",
            http_status=422,
        )

    order_rows: list[dict[str, Any]] = []

    if order_id:
        validated_id = _validate_order_id(order_id)
        response = (
            _table(client, "orders").select("*").eq("id", validated_id).limit(1).execute()
        )
        order_rows = list(response.data or [])
    elif q:
        general = _sanitize_search(q, field="q")
        if _UUID_RE.match(general):
            response = _table(client, "orders").select("*").eq("id", general).limit(20).execute()
            order_rows = list(response.data or [])
        elif general.lower() in _ORDER_STATUSES:
            response = (
                _table(client, "orders")
                .select("*")
                .eq("status", general.lower())
                .order("created_at", desc=True)
                .limit(50)
                .execute()
            )
            order_rows = list(response.data or [])
        else:
            order_rows = _search_by_phone_or_vendor(client, phone=general, vendor=general)
    else:
        if phone:
            validated_phone = _validate_phone(phone)
            order_rows = _search_by_phone(client, validated_phone)
        if vendor and not order_rows:
            validated_vendor = _sanitize_search(vendor, field="vendor")
            order_rows = _search_by_vendor(client, validated_vendor)
        if status:
            validated_status = _validate_status(status)
            query = _table(client, "orders").select("*").eq("status", validated_status)
            if order_rows:
                allowed_ids = {str(row["id"]) for row in order_rows}
                order_rows = [row for row in order_rows if row["status"] == validated_status]
                if not order_rows:
                    response = query.in_("id", sorted(allowed_ids)).limit(50).execute()
                    order_rows = list(response.data or [])
            else:
                response = query.order("created_at", desc=True).limit(50).execute()
                order_rows = list(response.data or [])

    vendor_ids = {str(row["vendor_id"]) for row in order_rows}
    customer_ids = {str(row["customer_id"]) for row in order_rows}
    vendors = _load_vendor_map(client, vendor_ids)
    profiles = _load_profile_map(client, customer_ids)
    return [_order_to_search_item(row, vendors=vendors, profiles=profiles) for row in order_rows]


def _search_by_phone(client: ServiceRoleClient, phone: str) -> list[dict[str, Any]]:
    profile_response = (
        _table(client, "profiles")
        .select("id")
        .ilike("phone", f"%{phone}%")
        .limit(50)
        .execute()
    )
    profile_rows = profile_response.data or []
    if not profile_rows:
        return []
    customer_ids = [row["id"] for row in profile_rows]
    order_response = (
        _table(client, "orders")
        .select("*")
        .in_("customer_id", customer_ids)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return list(order_response.data or [])


def _search_by_vendor(client: ServiceRoleClient, vendor_query: str) -> list[dict[str, Any]]:
    vendor_response = (
        _table(client, "vendors")
        .select("id")
        .or_(f"slug.ilike.%{vendor_query}%,display_name.ilike.%{vendor_query}%")
        .limit(50)
        .execute()
    )
    vendor_rows = vendor_response.data or []
    if not vendor_rows:
        return []
    vendor_ids = [row["id"] for row in vendor_rows]
    order_response = (
        _table(client, "orders")
        .select("*")
        .in_("vendor_id", vendor_ids)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return list(order_response.data or [])


def _search_by_phone_or_vendor(
    client: ServiceRoleClient, *, phone: str, vendor: str
) -> list[dict[str, Any]]:
    by_phone = _search_by_phone(client, phone)
    by_vendor = _search_by_vendor(client, vendor)
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for row in by_phone + by_vendor:
        row_id = str(row["id"])
        if row_id not in seen:
            seen.add(row_id)
            merged.append(row)
    return merged[:50]


def _load_order_row(client: ServiceRoleClient, order_id: str) -> dict[str, Any]:
    response = _table(client, "orders").select("*").eq("id", order_id).maybe_single().execute()
    row = response.data
    if not row:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    return cast(dict[str, Any], row)


def _build_order_detail(client: ServiceRoleClient, order_row: dict[str, Any]) -> OrderDetailOut:
    order_id = str(order_row["id"])
    vendor_map = _load_vendor_map(client, {str(order_row["vendor_id"])})
    profile_map = _load_profile_map(client, {str(order_row["customer_id"])})
    vendor = vendor_map.get(str(order_row["vendor_id"]), {})
    profile = profile_map.get(str(order_row["customer_id"]), {})

    items_response = (
        _table(client, "order_items").select("*").eq("order_id", order_id).execute()
    )
    items = [
        OrderItemOut(
            id=row["id"],
            item_kind=row["item_kind"],
            qty=row["qty"],
            unit_price_ngwee=row["unit_price_ngwee"],
            title_snapshot=row.get("title_snapshot"),
        )
        for row in (items_response.data or [])
    ]

    payments_response = (
        _table(client, "payments")
        .select("id, rail, amount_ngwee, status, lenco_reference, created_at")
        .eq("checkout_group_id", order_row["checkout_group_id"])
        .order("created_at", desc=True)
        .execute()
    )
    payments = [
        PaymentOut(
            id=row["id"],
            rail=row["rail"],
            amount_ngwee=row["amount_ngwee"],
            status=row["status"],
            lenco_reference=row["lenco_reference"],
            created_at=_parse_timestamp(row["created_at"]),
        )
        for row in (payments_response.data or [])
    ]

    ledger_response = (
        _table(client, "ledger_transactions")
        .select("id, kind, created_at")
        .eq("order_id", order_id)
        .order("created_at", desc=True)
        .execute()
    )
    ledger_rows = ledger_response.data or []
    txn_ids = [row["id"] for row in ledger_rows]
    postings_by_txn: dict[str, list[LedgerPostingOut]] = {str(txn_id): [] for txn_id in txn_ids}
    if txn_ids:
        postings_response = (
            _table(client, "ledger_postings")
            .select("id, transaction_id, account_id, amount_ngwee")
            .in_("transaction_id", txn_ids)
            .execute()
        )
        for posting in postings_response.data or []:
            txn_key = str(posting["transaction_id"])
            postings_by_txn.setdefault(txn_key, []).append(
                LedgerPostingOut(
                    id=posting["id"],
                    account_id=posting["account_id"],
                    amount_ngwee=posting["amount_ngwee"],
                )
            )

    ledger = [
        LedgerTransactionOut(
            id=row["id"],
            kind=row["kind"],
            created_at=_parse_timestamp(row["created_at"]),
            postings=postings_by_txn.get(str(row["id"]), []),
        )
        for row in ledger_rows
    ]

    timeline_response = (
        _table(client, "order_events")
        .select("id, actor, from_status, to_status, note, created_at")
        .eq("order_id", order_id)
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )
    timeline = [
        TimelineEventOut(
            id=row["id"],
            actor=row.get("actor"),
            from_status=row.get("from_status"),
            to_status=row.get("to_status"),
            note=row.get("note"),
            created_at=_parse_timestamp(row["created_at"]),
        )
        for row in (timeline_response.data or [])
    ]

    return OrderDetailOut(
        id=order_row["id"],
        status=order_row["status"],
        fulfilment=order_row["fulfilment"],
        cod=bool(order_row.get("cod")),
        delivery_fee_ngwee=int(order_row.get("delivery_fee_ngwee") or 0),
        checkout_group_id=order_row["checkout_group_id"],
        vendor_id=order_row["vendor_id"],
        vendor_display_name=vendor.get("display_name") or "—",
        vendor_slug=vendor.get("slug") or "—",
        customer_id=order_row["customer_id"],
        customer_phone=profile.get("phone"),
        customer_display_name=profile.get("display_name"),
        created_at=_parse_timestamp(order_row["created_at"]),
        items=items,
        payments=payments,
        ledger=ledger,
        timeline=timeline,
    )


def _courier_label(courier: Courier, courier_other: str | None) -> str:
    if courier == "yango":
        return "Yango"
    if courier == "indrive":
        return "inDrive"
    return (courier_other or "Other").strip()


def _build_dispatch_note(body: DispatchRequest) -> str:
    label = _courier_label(body.courier, body.courier_other)
    return f"[dispatch] courier={label} | tracking: {body.tracking_note.strip()}"


def enforce_dual_note(*, reason: str, confirmation_phrase: str) -> None:
    """Reject manual escrow ops unless both notes are present and valid."""
    if not reason.strip():
        raise AppError(
            code="validation_error",
            message="reason is required for manual escrow operations",
            http_status=422,
            details={"field": "reason"},
        )
    if not confirmation_phrase.strip():
        raise AppError(
            code="validation_error",
            message="confirmation_phrase is required for manual escrow operations",
            http_status=422,
            details={"field": "confirmation_phrase"},
        )
    if confirmation_phrase.strip() != MANUAL_ESCROW_CONFIRMATION_PHRASE:
        raise AppError(
            code="validation_error",
            message="confirmation_phrase does not match the required phrase",
            http_status=422,
            details={"expected": MANUAL_ESCROW_CONFIRMATION_PHRASE},
        )


def _manual_escrow_template(operation: EscrowOperation) -> str:
    return "manual_escrow_hold" if operation == "hold" else "manual_escrow_release"


def _ledger_template_for_operation(operation: EscrowOperation) -> tuple[Any, dict[str, int]]:
    from app.services.ledger.templates import LedgerTemplate

    if operation == "hold":
        return LedgerTemplate.ESCROW_HOLD, {}
    return LedgerTemplate.REFUND_LANE1, {}


def _ledger_amount_arg(operation: EscrowOperation, amount_ngwee: int) -> dict[str, int]:
    if operation == "hold":
        return {"order_amount_ngwee": amount_ngwee}
    return {"refund_ngwee": amount_ngwee}


def _load_ledger_post_transaction() -> Any | None:
    try:
        module = importlib.import_module("app.services.ledger.engine")
    except ImportError:
        return None
    post_transaction = getattr(module, "post_transaction", None)
    return post_transaction if callable(post_transaction) else None


def _build_manual_escrow_postings(
    operation: EscrowOperation, amount_ngwee: int
) -> list[ManualLedgerPosting]:
    if operation == "hold":
        return [
            ManualLedgerPosting(account_kind="platform_cash", amount_ngwee=amount_ngwee),
            ManualLedgerPosting(account_kind="escrow", amount_ngwee=-amount_ngwee),
        ]
    return [
        ManualLedgerPosting(account_kind="escrow", amount_ngwee=amount_ngwee),
        ManualLedgerPosting(account_kind="platform_cash", amount_ngwee=-amount_ngwee),
    ]


def post_manual_escrow_transaction(
    *,
    order_id: str,
    operation: EscrowOperation,
    amount_ngwee: int,
    reason: str,
    confirmation_phrase: str,
    actor_id: str,
    service_client: ServiceRoleClient,
) -> ManualLedgerResult:
    """Post a balanced manual escrow hold/release via the ledger engine (or local stub)."""
    enforce_dual_note(reason=reason, confirmation_phrase=confirmation_phrase)
    template = _manual_escrow_template(operation)
    idempotency_key = f"manual-{operation}-{order_id}-{amount_ngwee}-{reason.strip()[:40]}"

    post_transaction = _load_ledger_post_transaction()
    if post_transaction is not None:
        ledger_template, _ = _ledger_template_for_operation(operation)
        posted = post_transaction(
            idempotency_key=idempotency_key,
            template=ledger_template,
            order_id=order_id,
            **_ledger_amount_arg(operation, amount_ngwee),
        )
        postings = _build_manual_escrow_postings(operation, amount_ngwee)
        return ManualLedgerResult(
            transaction_id=str(posted.id),
            template=f"{template}|manual",
            manual=True,
            postings=postings,
        )

    # TODO(M08-P05): remove stub once ledger engine is always available in all environments.
    return _stub_post_manual_escrow(
        order_id=order_id,
        operation=operation,
        amount_ngwee=amount_ngwee,
        reason=reason,
        confirmation_phrase=confirmation_phrase,
        actor_id=actor_id,
        service_client=service_client,
        idempotency_key=idempotency_key,
        template=template,
    )


def _stub_post_manual_escrow(
    *,
    order_id: str,
    operation: EscrowOperation,
    amount_ngwee: int,
    reason: str,
    confirmation_phrase: str,
    actor_id: str,
    service_client: ServiceRoleClient,
    idempotency_key: str,
    template: str,
) -> ManualLedgerResult:
    _ = actor_id
    postings = _build_manual_escrow_postings(operation, amount_ngwee)
    balance = sum(posting.amount_ngwee for posting in postings)
    if balance != 0:
        raise AppError(
            code="ledger_imbalance",
            message="Manual escrow postings must balance to zero",
            http_status=500,
            details={"balance_sum_ngwee": balance},
        )

    kind = (
        f"{template}|manual|key={idempotency_key}|"
        f"reason={reason.strip()[:80]}|confirm={confirmation_phrase.strip()}"
    )
    existing = (
        _table(service_client, "ledger_transactions")
        .select("id")
        .eq("kind", kind)
        .eq("order_id", order_id)
        .maybe_single()
        .execute()
    )
    if existing.data:
        return ManualLedgerResult(
            transaction_id=str(existing.data["id"]),
            template=template,
            manual=True,
            postings=postings,
        )

    txn_response = (
        _table(service_client, "ledger_transactions")
        .insert(
            {
                "kind": kind,
                "order_id": order_id,
            }
        )
        .execute()
    )
    txn_rows = txn_response.data or []
    if not txn_rows:
        raise AppError(
            code="ledger_write_failed",
            message="Failed to create manual escrow ledger transaction",
            http_status=500,
        )
    txn_id = str(txn_rows[0]["id"])

    escrow_account = (
        _table(service_client, "ledger_accounts")
        .select("id")
        .eq("kind", "escrow")
        .is_("vendor_id", "null")
        .maybe_single()
        .execute()
    )
    cash_account = (
        _table(service_client, "ledger_accounts")
        .select("id")
        .eq("kind", "platform_cash")
        .is_("vendor_id", "null")
        .maybe_single()
        .execute()
    )
    escrow_id = escrow_account.data["id"] if escrow_account.data else None
    cash_id = cash_account.data["id"] if cash_account.data else None

    for posting in postings:
        account_id = escrow_id if posting.account_kind == "escrow" else cash_id
        if account_id is None:
            continue
        _table(service_client, "ledger_postings").insert(
            {
                "transaction_id": txn_id,
                "account_id": account_id,
                "amount_ngwee": posting.amount_ngwee,
            }
        ).execute()

    return ManualLedgerResult(
        transaction_id=txn_id,
        template=template,
        manual=True,
        postings=postings,
    )


@orders_router.get("/search", response_model=list[OrderSearchItem])
async def search_orders(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    order_id: Annotated[str | None, Query(max_length=MAX_SEARCH_LEN)] = None,
    phone: Annotated[str | None, Query(max_length=MAX_SEARCH_LEN)] = None,
    vendor: Annotated[str | None, Query(max_length=MAX_SEARCH_LEN)] = None,
    status: Annotated[str | None, Query(max_length=32)] = None,
    q: Annotated[str | None, Query(max_length=MAX_SEARCH_LEN)] = None,
) -> list[OrderSearchItem]:
    return _search_orders(
        service_client,
        order_id=order_id,
        phone=phone,
        vendor=vendor,
        status=status,
        q=q,
    )


@orders_router.get("/{order_id}", response_model=OrderDetailOut)
async def get_order_detail(
    order_id: UUID,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> OrderDetailOut:
    row = _load_order_row(service_client, str(order_id))
    return _build_order_detail(service_client, row)


@orders_router.post("/{order_id}/dispatch", response_model=DispatchResponse)
async def manual_dispatch(
    order_id: UUID,
    body: DispatchRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> DispatchResponse:
    order_key = str(order_id)
    before_row = _load_order_row(service_client, order_key)
    before = {"status": before_row["status"]}
    note = _build_dispatch_note(body)

    outcome = transition_order(
        order_id=order_key,
        event=body.event,
        actor_role=ActorRole.ADMIN,
        actor_id=current_user.id,
        note=note,
    )

    from app.services.orders.state import fetch_latest_audit_event  # noqa: PLC0415

    latest = fetch_latest_audit_event(order_key)
    recorder.record(
        action="admin.orders.dispatch",
        entity_type="order",
        entity_id=order_key,
        before=before,
        after={
            "status": outcome.to_status.value,
            "event": outcome.event.value,
            "courier": body.courier,
            "tracking_note": body.tracking_note,
        },
    )
    return DispatchResponse(
        order_id=order_id,
        from_status=outcome.from_status.value,
        to_status=outcome.to_status.value,
        event=outcome.event.value,
        timeline_event_id=latest["id"] if latest else None,
    )


@orders_router.post("/{order_id}/intervene", response_model=InterventionResponse)
async def intervene_order(
    order_id: UUID,
    body: InterventionRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> InterventionResponse:
    order_key = str(order_id)
    before_row = _load_order_row(service_client, order_key)
    before = {"status": before_row["status"]}

    try:
        outcome = transition_order(
            order_id=order_key,
            event=body.event,
            actor_role=ActorRole.ADMIN,
            actor_id=current_user.id,
            note=body.reason.strip(),
            refund_path=body.refund_path,
        )
    except OrderTransitionError as exc:
        raise exc

    recorder.record(
        action="admin.orders.intervene",
        entity_type="order",
        entity_id=order_key,
        before=before,
        after={"status": outcome.to_status.value, "event": outcome.event.value},
    )
    return InterventionResponse(
        order_id=order_id,
        from_status=outcome.from_status.value,
        to_status=outcome.to_status.value,
        event=outcome.event.value,
    )


@orders_router.post("/{order_id}/escrow", response_model=EscrowResponse)
async def manual_escrow(
    order_id: UUID,
    body: EscrowRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> EscrowResponse:
    order_key = str(order_id)
    _load_order_row(service_client, order_key)

    ledger_result = post_manual_escrow_transaction(
        order_id=order_key,
        operation=body.operation,
        amount_ngwee=body.amount_ngwee,
        reason=body.reason,
        confirmation_phrase=body.confirmation_phrase,
        actor_id=current_user.id,
        service_client=service_client,
    )
    if ledger_result.balance_sum_ngwee != 0:
        raise AppError(
            code="ledger_imbalance",
            message="Manual escrow postings must balance to zero",
            http_status=500,
            details={"balance_sum_ngwee": ledger_result.balance_sum_ngwee},
        )

    recorder.record(
        action="admin.orders.escrow",
        entity_type="order",
        entity_id=order_key,
        before=None,
        after={
            "operation": body.operation,
            "amount_ngwee": body.amount_ngwee,
            "transaction_id": ledger_result.transaction_id,
            "manual": ledger_result.manual,
        },
    )
    return EscrowResponse(
        order_id=order_id,
        operation=body.operation,
        transaction_id=ledger_result.transaction_id,
        amount_ngwee=body.amount_ngwee,
        manual=ledger_result.manual,
        balance_sum_ngwee=ledger_result.balance_sum_ngwee,
    )


admin_router.include_router(orders_router)
