from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.disputes.service import ResolveDecision, resolve
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator

ORDER_EVIDENCE_BUCKET = "order-evidence"
SIGNED_URL_TTL_SECONDS = 300

SLA_ON_TRACK_HOURS = 24
SLA_DUE_SOON_HOURS = 48

OPEN_QUEUE_STATUSES = frozenset({"open", "vendor_responded", "under_review"})

SlaBadge = Literal["on_track", "due_soon", "overdue"]
EvidenceSide = Literal["customer", "vendor"]
AdminDecisionType = Literal["full_refund", "partial_refund", "release"]

disputes_router = APIRouter(prefix="/disputes", tags=["admin-disputes"])


class ServiceRoleClient(Protocol):
    client: Any


class DisputeQueueItem(BaseModel):
    id: UUID
    order_id: UUID
    status: str
    vendor_display_name: str
    vendor_slug: str
    customer_phone: str | None
    order_total_ngwee: int
    created_at: datetime
    updated_at: datetime
    sla_badge: SlaBadge
    age_hours: float


class SignedEvidenceUrl(BaseModel):
    path: str
    side: EvidenceSide
    signed_url: str | None
    expires_at: datetime | None
    ttl_seconds: int


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


class OrderContextOut(BaseModel):
    id: UUID
    status: str
    fulfilment: str
    delivery_fee_ngwee: int
    order_total_ngwee: int
    vendor_display_name: str
    vendor_slug: str
    customer_phone: str | None
    customer_display_name: str | None
    items: list[OrderItemOut]
    payments: list[PaymentOut]
    ledger: list[LedgerTransactionOut]


class DisputeDetailOut(BaseModel):
    id: UUID
    order_id: UUID
    status: str
    opener_user_id: UUID
    vendor_response: str | None
    admin_decision: str | None
    created_at: datetime
    updated_at: datetime
    sla_badge: SlaBadge
    age_hours: float
    evidence: list[SignedEvidenceUrl]
    evidence_available: bool
    order: OrderContextOut
    decidable: bool


class DecideDisputeRequest(BaseModel):
    decision: AdminDecisionType
    note: str = Field(max_length=4000)
    partial_refund_ngwee: int | None = Field(default=None, ge=1)
    customer_momo: str = Field(min_length=8, max_length=20)
    customer_rail: Literal["mtn", "airtel", "zamtel"] = "mtn"

    @model_validator(mode="after")
    def require_partial_amount(self) -> DecideDisputeRequest:
        if self.decision == "partial_refund" and self.partial_refund_ngwee is None:
            raise ValueError("partial_refund_ngwee is required for partial_refund decision")
        return self


class DecideDisputeResponse(BaseModel):
    dispute_id: UUID
    order_id: UUID
    status: str
    decision: AdminDecisionType
    admin_decision: str


def _table(client: ServiceRoleClient, name: str) -> Any:
    return client.client.table(name)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        if not data:
            return None
        first = data[0]
        return first if isinstance(first, dict) else None
    return None


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise AppError(
        code="internal_error",
        message="Invalid timestamp in dispute record",
        http_status=500,
    )


def compute_sla_badge(
    reference_at: datetime, *, now: datetime | None = None
) -> tuple[SlaBadge, float]:
    current = now or datetime.now(UTC)
    if reference_at.tzinfo is None:
        reference_at = reference_at.replace(tzinfo=UTC)
    age = current - reference_at
    age_hours = age.total_seconds() / 3600.0
    if age_hours < SLA_ON_TRACK_HOURS:
        return "on_track", age_hours
    if age_hours < SLA_DUE_SOON_HOURS:
        return "due_soon", age_hours
    return "overdue", age_hours


def classify_evidence_side(path: str) -> EvidenceSide:
    normalized = path.replace("\\", "/").lower()
    if "/vendor-" in normalized or "vendor-evidence" in normalized:
        return "vendor"
    return "customer"


def sign_evidence_documents(
    service_client: ServiceRoleClient,
    paths: list[str],
    *,
    now: datetime | None = None,
) -> tuple[list[SignedEvidenceUrl], bool]:
    reference = now or datetime.now(UTC)
    documents: list[SignedEvidenceUrl] = []
    evidence_available = True

    storage = getattr(service_client.client, "storage", None)
    if storage is None:
        evidence_available = False
        for path in paths:
            documents.append(
                SignedEvidenceUrl(
                    path=path,
                    side=classify_evidence_side(path),
                    signed_url=None,
                    expires_at=None,
                    ttl_seconds=SIGNED_URL_TTL_SECONDS,
                )
            )
        return documents, evidence_available

    bucket = storage.from_(ORDER_EVIDENCE_BUCKET)
    for path in paths:
        signed_url: str | None = None
        expires_at: datetime | None = None
        try:
            result = bucket.create_signed_url(path, SIGNED_URL_TTL_SECONDS)
            if isinstance(result, dict):
                signed_url = (
                    result.get("signedURL")
                    or result.get("signedUrl")
                    or result.get("signed_url")
                )
                expires_in = result.get("expires_in") or result.get("expiresIn")
                if isinstance(expires_in, int | float):
                    expires_at = reference + timedelta(seconds=int(expires_in))
                else:
                    expires_at = reference + timedelta(seconds=SIGNED_URL_TTL_SECONDS)
        except Exception:
            evidence_available = False
            signed_url = None
            expires_at = None

        documents.append(
            SignedEvidenceUrl(
                path=path,
                side=classify_evidence_side(path),
                signed_url=str(signed_url) if signed_url else None,
                expires_at=expires_at,
                ttl_seconds=SIGNED_URL_TTL_SECONDS,
            )
        )

    return documents, evidence_available


def _load_dispute_row(service_client: ServiceRoleClient, dispute_id: str) -> dict[str, Any]:
    row = _single_row(
        _table(service_client, "disputes")
        .select(
            "id, order_id, opener_user_id, status, evidence_paths, "
            "vendor_response, admin_decision, created_at, updated_at"
        )
        .eq("id", dispute_id)
        .maybe_single()
        .execute()
    )
    if row is None:
        raise AppError(code="not_found", message="Dispute not found", http_status=404)
    return row


def _load_order_row(service_client: ServiceRoleClient, order_id: str) -> dict[str, Any]:
    row = _single_row(
        _table(service_client, "orders").select("*").eq("id", order_id).maybe_single().execute()
    )
    if row is None:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    return row


def _load_vendor_row(service_client: ServiceRoleClient, vendor_id: str) -> dict[str, Any]:
    row = _single_row(
        _table(service_client, "vendors")
        .select("id, display_name, slug")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    return row or {}


def _load_profile_row(service_client: ServiceRoleClient, user_id: str) -> dict[str, Any]:
    row = _single_row(
        _table(service_client, "profiles")
        .select("id, phone, display_name")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    return row or {}


def _order_items_total(service_client: ServiceRoleClient, order_id: str) -> int:
    response = (
        _table(service_client, "order_items")
        .select("qty, unit_price_ngwee")
        .eq("order_id", order_id)
        .execute()
    )
    total = 0
    for row in _rows(response):
        qty = row.get("qty", 0)
        unit = row.get("unit_price_ngwee", 0)
        if isinstance(qty, int) and isinstance(unit, int):
            total += qty * unit
    return total


def compute_order_total_ngwee(service_client: ServiceRoleClient, order_row: dict[str, Any]) -> int:
    order_id = str(order_row["id"])
    items_total = _order_items_total(service_client, order_id)
    delivery_fee = int(order_row.get("delivery_fee_ngwee") or 0)
    return items_total + delivery_fee


def _build_order_context(
    service_client: ServiceRoleClient, order_row: dict[str, Any]
) -> OrderContextOut:
    order_id = str(order_row["id"])
    vendor = _load_vendor_row(service_client, str(order_row["vendor_id"]))
    profile = _load_profile_row(service_client, str(order_row["customer_id"]))

    items_response = (
        _table(service_client, "order_items")
        .select("*")
        .eq("order_id", order_id)
        .execute()
    )
    items = [
        OrderItemOut(
            id=row["id"],
            item_kind=row["item_kind"],
            qty=row["qty"],
            unit_price_ngwee=row["unit_price_ngwee"],
            title_snapshot=row.get("title_snapshot"),
        )
        for row in _rows(items_response)
    ]

    payments_response = (
        _table(service_client, "payments")
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
        for row in _rows(payments_response)
    ]

    ledger_response = (
        _table(service_client, "ledger_transactions")
        .select("id, kind, created_at")
        .eq("order_id", order_id)
        .order("created_at", desc=True)
        .execute()
    )
    ledger_rows = _rows(ledger_response)
    txn_ids = [row["id"] for row in ledger_rows]
    postings_by_txn: dict[str, list[LedgerPostingOut]] = {str(txn_id): [] for txn_id in txn_ids}
    if txn_ids:
        postings_response = (
            _table(service_client, "ledger_postings")
            .select("id, transaction_id, account_id, amount_ngwee")
            .in_("transaction_id", txn_ids)
            .execute()
        )
        for posting in _rows(postings_response):
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

    order_total = compute_order_total_ngwee(service_client, order_row)

    return OrderContextOut(
        id=order_row["id"],
        status=order_row["status"],
        fulfilment=order_row["fulfilment"],
        delivery_fee_ngwee=int(order_row.get("delivery_fee_ngwee") or 0),
        order_total_ngwee=order_total,
        vendor_display_name=vendor.get("display_name") or "—",
        vendor_slug=vendor.get("slug") or "—",
        customer_phone=profile.get("phone"),
        customer_display_name=profile.get("display_name"),
        items=items,
        payments=payments,
        ledger=ledger,
    )


def _map_admin_decision(decision: AdminDecisionType) -> ResolveDecision:
    mapping: dict[AdminDecisionType, ResolveDecision] = {
        "full_refund": "resolved_refund",
        "partial_refund": "resolved_partial",
        "release": "resolved_release",
    }
    return mapping[decision]


def _validate_decide_request(
    body: DecideDisputeRequest,
    *,
    order_total_ngwee: int,
) -> None:
    if not body.note.strip():
        raise AppError(
            code="validation_error",
            message="note is required for dispute decisions",
            http_status=400,
            details={"field": "note"},
        )
    if body.decision == "partial_refund":
        partial = body.partial_refund_ngwee
        if partial is None:
            raise AppError(
                code="validation_error",
                message="partial_refund_ngwee is required for partial_refund decision",
                http_status=422,
            )
        if partial > order_total_ngwee:
            raise AppError(
                code="validation_error",
                message="partial_refund_ngwee cannot exceed order total",
                http_status=422,
                details={
                    "partial_refund_ngwee": partial,
                    "order_total_ngwee": order_total_ngwee,
                },
            )


def _sort_queue_items(
    items: list[DisputeQueueItem],
    *,
    sort: Literal["age", "value"],
) -> list[DisputeQueueItem]:
    if sort == "value":
        return sorted(
            items,
            key=lambda item: (-item.order_total_ngwee, item.created_at),
        )
    return sorted(
        items,
        key=lambda item: (item.created_at, -item.order_total_ngwee),
    )


@disputes_router.get("", response_model=list[DisputeQueueItem])
async def list_dispute_queue(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    sort: Annotated[Literal["age", "value"], Query()] = "age",
) -> list[DisputeQueueItem]:
    response = (
        _table(service_client, "disputes")
        .select("id, order_id, status, created_at, updated_at")
        .in_("status", sorted(OPEN_QUEUE_STATUSES))
        .execute()
    )
    items: list[DisputeQueueItem] = []
    for row in _rows(response):
        order_row = _load_order_row(service_client, str(row["order_id"]))
        vendor = _load_vendor_row(service_client, str(order_row["vendor_id"]))
        profile = _load_profile_row(service_client, str(order_row["customer_id"]))
        created_at = _parse_timestamp(row["created_at"])
        sla_badge, age_hours = compute_sla_badge(created_at)
        order_total = compute_order_total_ngwee(service_client, order_row)
        items.append(
            DisputeQueueItem(
                id=row["id"],
                order_id=row["order_id"],
                status=str(row["status"]),
                vendor_display_name=vendor.get("display_name") or "—",
                vendor_slug=vendor.get("slug") or "—",
                customer_phone=profile.get("phone"),
                order_total_ngwee=order_total,
                created_at=created_at,
                updated_at=_parse_timestamp(row["updated_at"]),
                sla_badge=sla_badge,
                age_hours=round(age_hours, 2),
            )
        )
    return _sort_queue_items(items, sort=sort)


@disputes_router.get("/{dispute_id}", response_model=DisputeDetailOut)
async def get_dispute_detail(
    dispute_id: UUID,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> DisputeDetailOut:
    row = _load_dispute_row(service_client, str(dispute_id))
    order_row = _load_order_row(service_client, str(row["order_id"]))
    order_context = _build_order_context(service_client, order_row)

    paths_raw = row.get("evidence_paths")
    paths = [str(path) for path in paths_raw] if isinstance(paths_raw, list) else []
    evidence, evidence_available = sign_evidence_documents(service_client, paths)

    created_at = _parse_timestamp(row["created_at"])
    sla_badge, age_hours = compute_sla_badge(created_at)
    status = str(row["status"])
    admin_decision = row.get("admin_decision")

    return DisputeDetailOut(
        id=row["id"],
        order_id=row["order_id"],
        status=status,
        opener_user_id=row["opener_user_id"],
        vendor_response=(
            str(row["vendor_response"]) if row.get("vendor_response") is not None else None
        ),
        admin_decision=str(admin_decision) if isinstance(admin_decision, str) else None,
        created_at=created_at,
        updated_at=_parse_timestamp(row["updated_at"]),
        sla_badge=sla_badge,
        age_hours=round(age_hours, 2),
        evidence=evidence,
        evidence_available=evidence_available,
        order=order_context,
        decidable=status in OPEN_QUEUE_STATUSES,
    )


@disputes_router.post("/{dispute_id}/decide", response_model=DecideDisputeResponse)
async def decide_dispute(
    dispute_id: UUID,
    body: DecideDisputeRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> DecideDisputeResponse:
    dispute_row = _load_dispute_row(service_client, str(dispute_id))
    order_row = _load_order_row(service_client, str(dispute_row["order_id"]))
    order_total = compute_order_total_ngwee(service_client, order_row)

    _validate_decide_request(body, order_total_ngwee=order_total)

    before = {
        "dispute": {
            "id": dispute_row["id"],
            "status": dispute_row["status"],
            "admin_decision": dispute_row.get("admin_decision"),
        }
    }

    resolve_decision = _map_admin_decision(body.decision)
    record = resolve(
        service_client,
        dispute_id=str(dispute_id),
        admin_user_id=current_user.id,
        decision=resolve_decision,
        admin_decision=body.note.strip(),
        customer_momo=body.customer_momo,
        customer_rail=body.customer_rail,
        partial_refund_ngwee=body.partial_refund_ngwee,
    )

    after = {
        "dispute": {
            "id": record.id,
            "status": record.status,
            "admin_decision": record.admin_decision,
            "decision": body.decision,
        }
    }
    recorder.record(
        action="admin.disputes.decide",
        entity_type="dispute",
        entity_id=dispute_id,
        before=before,
        after=after,
    )

    return DecideDisputeResponse(
        dispute_id=UUID(record.id),
        order_id=UUID(record.order_id),
        status=record.status,
        decision=body.decision,
        admin_decision=record.admin_decision or body.note.strip(),
    )


admin_router.include_router(disputes_router)
