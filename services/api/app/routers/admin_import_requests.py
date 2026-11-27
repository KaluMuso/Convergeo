"""Admin queue for vendor import requests (docs/plan/vendor-sourcing-hub.md).

Mounted under the audited, admin-guarded ``/admin`` router. Admins read every
request and reply with a landed-cost ESTIMATE (ngwee lines). This is data only:
nothing here creates an order, a payment or a ledger row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import ADMIN_WRITE
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.routers.vendor_sourcing import (
    REQUEST_COLUMNS,
    ImportRequestOut,
    QuoteOut,
    latest_quotes,
    quote_from_row,
    request_from_row,
    rows_of,
)
from app.schemas.base import NgweeInt, StrictModel
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

import_router = APIRouter(prefix="/import-requests", tags=["admin-import-requests"])

MAX_LINE_NGWEE: Final = 100_000_000_000
RequestStatus = Literal["submitted", "in_review", "quoted", "closed", "cancelled"]
#: Admin-driven transitions. ``cancelled`` is vendor-only; ``closed`` is terminal.
ADMIN_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "submitted": frozenset({"in_review", "closed"}),
    "in_review": frozenset({"closed"}),
    "quoted": frozenset({"in_review", "closed"}),
}
QUOTABLE: Final = frozenset({"submitted", "in_review", "quoted"})


class AdminImportRequestOut(ImportRequestOut):
    vendor_id: str
    vendor_name: str | None = None


class StatusBody(StrictModel):
    to: Literal["in_review", "closed"]


class QuoteBody(StrictModel):
    partner_label: str | None = Field(default=None, max_length=80)
    product_ngwee: NgweeInt = Field(le=MAX_LINE_NGWEE)
    freight_ngwee: NgweeInt = Field(le=MAX_LINE_NGWEE)
    duty_ngwee: NgweeInt = Field(le=MAX_LINE_NGWEE)
    clearing_ngwee: NgweeInt = Field(le=MAX_LINE_NGWEE)
    other_ngwee: NgweeInt = Field(default=0, le=MAX_LINE_NGWEE)
    lead_time_days: int | None = Field(default=None, ge=1, le=365)
    valid_until: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class QuoteCreated(BaseModel):
    request: AdminImportRequestOut
    quote: QuoteOut


def _limit(client: Any, actor_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=ADMIN_WRITE.scope,
        key=f"import-requests:{actor_id}",
        window=ADMIN_WRITE.window,
        limit=ADMIN_WRITE.limit,
        client=client,
    )
    if not allowed:
        raise_rate_limited(retry_after=retry_after, message_key="admin.common.rateLimited")


def _load(client: Any, request_id: UUID) -> dict[str, Any]:
    rows = rows_of(
        client.table("import_requests").select(REQUEST_COLUMNS).eq("id", str(request_id)).execute()
    )
    if not rows:
        raise AppError(code="not_found", message="Import request not found", http_status=404)
    return rows[0]


def _enrich(client: Any, rows: list[dict[str, Any]]) -> list[AdminImportRequestOut]:
    quotes = latest_quotes(client, [str(r["id"]) for r in rows])
    vendor_ids = sorted({str(r["vendor_id"]) for r in rows})
    names: dict[str, str] = {}
    if vendor_ids:
        for v in rows_of(
            client.table("vendors").select("id, display_name").in_("id", vendor_ids).execute()
        ):
            names[str(v["id"])] = str(v.get("display_name") or "")
    return [
        AdminImportRequestOut(
            **request_from_row(r, quotes.get(str(r["id"]))).model_dump(),
            vendor_id=str(r["vendor_id"]),
            vendor_name=names.get(str(r["vendor_id"])),
        )
        for r in rows
    ]


@import_router.get("", response_model=list[AdminImportRequestOut])
def list_import_requests(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[RequestStatus | None, Query()] = None,
) -> list[AdminImportRequestOut]:
    client: Any = service_client.client
    query = client.table("import_requests").select(REQUEST_COLUMNS)
    if status is not None:
        query = query.eq("status", status)
    rows = rows_of(query.order("created_at", desc=True).limit(200).execute())
    return _enrich(client, rows)


@import_router.post("/{request_id}/status", response_model=AdminImportRequestOut)
def set_import_request_status(
    request_id: UUID,
    body: StatusBody,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AdminImportRequestOut:
    client: Any = service_client.client
    _limit(client, user.id)
    before = _load(client, request_id)
    current = str(before["status"])
    if body.to not in ADMIN_TRANSITIONS.get(current, frozenset()):
        raise AppError(
            code="import_request.invalid_transition",
            message=f"Cannot move an import request from {current} to {body.to}",
            http_status=409,
            details={"message_key": "admin.importRequests.errors.invalidTransition"},
        )
    # The from-state is asserted inside the UPDATE so a concurrent change loses.
    updated = rows_of(
        client.table("import_requests")
        .update({"status": body.to})
        .eq("id", str(request_id))
        .eq("status", current)
        .execute()
    )
    if not updated:
        raise AppError(
            code="import_request.conflict",
            message="Import request changed, reload and retry",
            http_status=409,
        )
    after = {**before, "status": body.to}
    recorder.record(
        action=f"import_request.{body.to}",
        entity_type="import_request",
        entity_id=str(request_id),
        before={"status": current},
        after={"status": body.to},
    )
    return _enrich(client, [after])[0]


@import_router.post("/{request_id}/quotes", response_model=QuoteCreated, status_code=201)
def create_import_quote(
    request_id: UUID,
    body: QuoteBody,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> QuoteCreated:
    client: Any = service_client.client
    _limit(client, user.id)
    before = _load(client, request_id)
    current = str(before["status"])
    if current not in QUOTABLE:
        raise AppError(
            code="import_request.invalid_transition",
            message=f"Cannot quote an import request that is {current}",
            http_status=409,
            details={"message_key": "admin.importRequests.errors.invalidTransition"},
        )
    payload = {
        "request_id": str(request_id),
        "quoted_by": user.id,
        "partner_label": body.partner_label.strip() if body.partner_label else None,
        "product_ngwee": body.product_ngwee,
        "freight_ngwee": body.freight_ngwee,
        "duty_ngwee": body.duty_ngwee,
        "clearing_ngwee": body.clearing_ngwee,
        "other_ngwee": body.other_ngwee,
        "lead_time_days": body.lead_time_days,
        "valid_until": body.valid_until.isoformat() if body.valid_until else None,
        "notes": body.notes.strip() if body.notes else None,
        "is_estimate": True,
    }
    created = rows_of(client.table("import_request_quotes").insert(payload).execute())
    if not created:
        raise AppError(code="internal_error", message="Could not save quote", http_status=500)
    if current != "quoted":
        client.table("import_requests").update({"status": "quoted"}).eq("id", str(request_id)).eq(
            "status", current
        ).execute()
    quote_row = created[0]
    if "total_ngwee" not in quote_row:  # generated column; keep the response total exact
        quote_row = {
            **quote_row,
            "total_ngwee": body.product_ngwee
            + body.freight_ngwee
            + body.duty_ngwee
            + body.clearing_ngwee
            + body.other_ngwee,
        }
    quote_row.setdefault("created_at", before["updated_at"])
    recorder.record(
        action="import_request.quote",
        entity_type="import_request",
        entity_id=str(request_id),
        before={"status": current},
        after={
            "status": "quoted",
            "quote_id": str(quote_row.get("id")),
            "total_ngwee": quote_row["total_ngwee"],
        },
    )
    enriched = _enrich(client, [{**before, "status": "quoted"}])[0]
    return QuoteCreated(request=enriched, quote=quote_from_row(quote_row))


admin_router.include_router(import_router)
