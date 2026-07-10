"""Dispute endpoints — customer open/view, vendor respond/view, admin resolve."""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.disputes.service import (
    DisputeRecord,
    ResolveDecision,
    escalate_to_review,
    get_dispute_for_party,
    list_vendor_disputes,
    open_dispute,
    resolve,
    vendor_respond,
)
from fastapi import APIRouter, Depends
from pydantic import Field

router = APIRouter(prefix="/disputes", tags=["disputes"])

ORDER_EVIDENCE_BUCKET = "order-evidence"
MAX_EVIDENCE_BYTES = 10_485_760


class _ServiceRoleClient(Protocol):
    client: Any


class OpenDisputeRequest(StrictModel):
    evidence_paths: list[str] = Field(default_factory=list, max_length=8)
    description: str = Field(default="", max_length=2000)


class OpenDisputeResponse(StrictModel):
    dispute_id: str
    order_id: str
    status: str
    created: bool


class DisputeAuditEntry(StrictModel):
    from_status: str | None
    to_status: str
    note: str | None
    actor: str | None
    at: str


class DisputeResponse(StrictModel):
    id: str
    order_id: str
    opener_user_id: str
    status: str
    evidence_paths: list[str]
    vendor_response: str | None
    admin_decision: str | None
    created_at: str
    updated_at: str
    timeline: list[DisputeAuditEntry]


class VendorRespondRequest(StrictModel):
    response_text: str = Field(min_length=1, max_length=4000)
    evidence_paths: list[str] = Field(default_factory=list, max_length=8)


class EscalateRequest(StrictModel):
    note: str = Field(min_length=1, max_length=2000)


class ResolveRequest(StrictModel):
    decision: ResolveDecision
    admin_decision: str = Field(min_length=1, max_length=4000)
    customer_momo: str = Field(min_length=8, max_length=20)
    customer_rail: Literal["mtn", "airtel", "zamtel"] = "mtn"
    partial_refund_ngwee: int | None = Field(default=None, ge=1)


class EvidenceSignRequest(StrictModel):
    file_size_bytes: int = Field(ge=1)
    content_type: Literal[
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    ]


class EvidenceSignResponse(StrictModel):
    bucket: str
    path: str
    token: str
    signed_url: str


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
        .select("id, owner_user_id")
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
        )
    return row


def _load_order_customer_id(service_client: _ServiceRoleClient, order_id: str) -> str:
    response = (
        service_client.client.table("orders")
        .select("customer_id")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    return str(row["customer_id"])


def _assert_evidence_path_owned(
    path: str,
    *,
    customer_id: str,
    order_id: str,
    role_prefix: str = "evidence",
) -> None:
    expected_prefix = f"orders/{customer_id}/{order_id}/"
    normalized = path.replace("\\", "/").lstrip("/")
    if not normalized.startswith(expected_prefix) or ".." in normalized:
        raise AppError(
            code="validation_error",
            message="Evidence path must belong to this order",
            http_status=422,
            details={"path": path},
        )
    if role_prefix == "vendor" and "/vendor-" not in normalized:
        raise AppError(
            code="validation_error",
            message="Vendor evidence path must use vendor- prefix",
            http_status=422,
            details={"path": path},
        )


def _content_extension(content_type: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "application/pdf": "pdf",
    }[content_type]


def _extract_signed_upload(result: Any, *, path: str) -> tuple[str, str]:
    def _get(key_snake: str, key_camel: str) -> str | None:
        if isinstance(result, dict):
            value = result.get(key_snake, result.get(key_camel))
        else:
            value = getattr(result, key_snake, None) or getattr(result, key_camel, None)
        return value if isinstance(value, str) and value else None

    signed_url = _get("signed_url", "signedUrl")
    token = _get("token", "token")
    if not signed_url or not token:
        raise AppError(
            code="storage_error",
            message="Storage did not return a usable signed upload URL",
            http_status=502,
            details={"path": path},
        )
    return signed_url, token


def _load_dispute_timeline(
    service_client: _ServiceRoleClient,
    dispute_id: str,
) -> list[DisputeAuditEntry]:
    response = (
        service_client.client.table("audit_log")
        .select("before, after, actor, at")
        .eq("entity_type", "dispute")
        .eq("entity_id", dispute_id)
        .order("at", desc=False)
        .execute()
    )
    entries: list[DisputeAuditEntry] = []
    for row in _rows(response):
        before = row.get("before") if isinstance(row.get("before"), dict) else {}
        after = row.get("after") if isinstance(row.get("after"), dict) else {}
        from_status = before.get("status") if isinstance(before, dict) else None
        to_status = after.get("status") if isinstance(after, dict) else "open"
        note = after.get("note") if isinstance(after, dict) else None
        entries.append(
            DisputeAuditEntry(
                from_status=str(from_status) if from_status else None,
                to_status=str(to_status),
                note=str(note) if note else None,
                actor=str(row["actor"]) if row.get("actor") else None,
                at=str(row.get("at", "")),
            )
        )
    return entries


def _to_response(
    service_client: _ServiceRoleClient,
    record: DisputeRecord,
) -> DisputeResponse:
    return DisputeResponse(
        id=record.id,
        order_id=record.order_id,
        opener_user_id=record.opener_user_id,
        status=record.status,
        evidence_paths=record.evidence_paths,
        vendor_response=record.vendor_response,
        admin_decision=record.admin_decision,
        created_at=record.created_at,
        updated_at=record.updated_at,
        timeline=_load_dispute_timeline(service_client, record.id),
    )


@router.post("/orders/{order_id}", response_model=OpenDisputeResponse)
async def customer_open_dispute(
    order_id: str,
    body: OpenDisputeRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OpenDisputeResponse:
    for path in body.evidence_paths:
        _assert_evidence_path_owned(
            path,
            customer_id=current_user.id,
            order_id=order_id,
        )

    note = body.description.strip() or "Customer opened dispute"
    result = open_dispute(
        service_client,
        order_id=order_id,
        opener_user_id=current_user.id,
        evidence_paths=body.evidence_paths,
        note=note,
    )
    return OpenDisputeResponse(
        dispute_id=result.dispute_id,
        order_id=result.order_id,
        status=result.status,
        created=result.created,
    )


@router.get("/orders/{order_id}", response_model=DisputeResponse)
async def get_dispute_by_order(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> DisputeResponse:
    from app.services.disputes.state import load_dispute_by_order

    snapshot = load_dispute_by_order(service_client, order_id)
    if snapshot is None:
        raise AppError(code="not_found", message="Dispute not found", http_status=404)

    vendor_id: str | None = None
    if "vendor" in current_user.roles:
        try:
            vendor = _load_vendor_for_owner(service_client, current_user.id)
            vendor_id = str(vendor["id"])
        except AppError:
            vendor_id = None

    record = get_dispute_for_party(
        service_client,
        dispute_id=snapshot.id,
        user_id=current_user.id,
        is_admin="admin" in current_user.roles,
        vendor_id=vendor_id,
    )
    return _to_response(service_client, record)


@router.get("/{dispute_id}", response_model=DisputeResponse)
async def get_dispute(
    dispute_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> DisputeResponse:
    vendor_id: str | None = None
    if "vendor" in current_user.roles:
        try:
            vendor = _load_vendor_for_owner(service_client, current_user.id)
            vendor_id = str(vendor["id"])
        except AppError:
            vendor_id = None

    record = get_dispute_for_party(
        service_client,
        dispute_id=dispute_id,
        user_id=current_user.id,
        is_admin="admin" in current_user.roles,
        vendor_id=vendor_id,
    )
    return _to_response(service_client, record)


@router.get("/vendor/mine", response_model=list[DisputeResponse])
async def list_my_vendor_disputes(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> list[DisputeResponse]:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    records = list_vendor_disputes(service_client, vendor_id=str(vendor["id"]))
    return [_to_response(service_client, record) for record in records]


@router.post("/{dispute_id}/respond", response_model=DisputeResponse)
async def vendor_respond_to_dispute(
    dispute_id: str,
    body: VendorRespondRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> DisputeResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    from app.services.disputes.state import load_dispute_snapshot

    snapshot = load_dispute_snapshot(service_client, dispute_id)
    if snapshot is None:
        raise AppError(code="not_found", message="Dispute not found", http_status=404)

    customer_id = _load_order_customer_id(service_client, snapshot.order_id)
    for path in body.evidence_paths:
        _assert_evidence_path_owned(
            path,
            customer_id=customer_id,
            order_id=snapshot.order_id,
            role_prefix="vendor",
        )

    record = vendor_respond(
        service_client,
        dispute_id=dispute_id,
        vendor_id=str(vendor["id"]),
        vendor_user_id=current_user.id,
        response_text=body.response_text,
        evidence_paths=body.evidence_paths,
    )
    return _to_response(service_client, record)


@router.post("/{dispute_id}/escalate", response_model=DisputeResponse)
async def admin_escalate_dispute(
    dispute_id: str,
    body: EscalateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> DisputeResponse:
    record = escalate_to_review(
        service_client,
        dispute_id=dispute_id,
        admin_user_id=current_user.id,
        note=body.note,
    )
    return _to_response(service_client, record)


@router.post("/{dispute_id}/resolve", response_model=DisputeResponse)
async def admin_resolve_dispute(
    dispute_id: str,
    body: ResolveRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> DisputeResponse:
    record = resolve(
        service_client,
        dispute_id=dispute_id,
        admin_user_id=current_user.id,
        decision=body.decision,
        admin_decision=body.admin_decision,
        customer_momo=body.customer_momo,
        customer_rail=body.customer_rail,
        partial_refund_ngwee=body.partial_refund_ngwee,
    )
    return _to_response(service_client, record)


@router.post("/vendor/orders/{order_id}/evidence/sign", response_model=EvidenceSignResponse)
async def sign_vendor_evidence_upload(
    order_id: str,
    body: EvidenceSignRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> EvidenceSignResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    response = (
        service_client.client.table("orders")
        .select("customer_id, vendor_id")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    order_row = _single_row(response)
    if order_row is None or str(order_row.get("vendor_id")) != str(vendor["id"]):
        raise AppError(code="not_found", message="Order not found", http_status=404)

    if body.file_size_bytes > MAX_EVIDENCE_BYTES:
        raise AppError(
            code="file_too_large",
            message="Evidence file exceeds the maximum allowed upload size",
            http_status=400,
            details={"file_size_bytes": body.file_size_bytes, "max_bytes": MAX_EVIDENCE_BYTES},
        )

    customer_id = str(order_row["customer_id"])
    extension = _content_extension(body.content_type)
    path = (
        f"orders/{customer_id}/{order_id}/vendor-evidence-{int(time.time())}.{extension}"
    )

    try:
        result = (
            service_client.client.storage.from_(ORDER_EVIDENCE_BUCKET).create_signed_upload_url(path)
        )
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            code="storage_error",
            message="Could not create a signed upload URL",
            http_status=502,
            details={"path": path},
        ) from exc

    signed_url, token = _extract_signed_upload(result, path=path)
    return EvidenceSignResponse(
        bucket=ORDER_EVIDENCE_BUCKET,
        path=path,
        token=token,
        signed_url=signed_url,
    )
