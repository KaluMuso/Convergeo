"""Admin: flash-deal scheduling and product Q&A moderation (audited, ``ads.manage``
for deals, ``products.manage`` for Q&A)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator

retention_admin_router = APIRouter(tags=["admin-retention"])

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
DEAL_COLUMNS = (
    "id, listing_id, deal_price_ngwee, reference_price_ngwee, starts_at, ends_at, position, "
    "enabled, updated_at"
)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _validation(message: str) -> AppError:
    return AppError(code="validation_error", message=message, http_status=422)


class FlashDealIn(BaseModel):
    model_config = {"extra": "forbid"}

    listing_id: str
    deal_price_ngwee: int = Field(gt=0, le=10_000_000_000)
    reference_price_ngwee: int | None = Field(default=None, gt=0, le=10_000_000_000)
    starts_at: datetime
    ends_at: datetime
    position: int = Field(default=0, ge=0, le=10_000)
    enabled: bool = True

    @field_validator("listing_id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not UUID_RE.match(value):
            raise ValueError("listing_id must be a UUID")
        return value

    @model_validator(mode="after")
    def _window(self) -> FlashDealIn:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class FlashDealPatch(BaseModel):
    model_config = {"extra": "forbid"}

    deal_price_ngwee: int | None = Field(default=None, gt=0, le=10_000_000_000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    position: int | None = Field(default=None, ge=0, le=10_000)
    enabled: bool | None = None


class FlashDealOut(BaseModel):
    id: str
    listing_id: str
    deal_price_ngwee: int
    reference_price_ngwee: int
    starts_at: str
    ends_at: str
    position: int
    enabled: bool
    live: bool


def _deal_out(row: dict[str, Any], *, now: datetime) -> FlashDealOut:
    starts = datetime.fromisoformat(str(row["starts_at"]).replace("Z", "+00:00"))
    ends = datetime.fromisoformat(str(row["ends_at"]).replace("Z", "+00:00"))
    return FlashDealOut(
        id=str(row["id"]),
        listing_id=str(row["listing_id"]),
        deal_price_ngwee=int(row["deal_price_ngwee"]),
        reference_price_ngwee=int(row["reference_price_ngwee"]),
        starts_at=str(row["starts_at"]),
        ends_at=str(row["ends_at"]),
        position=int(row.get("position") or 0),
        enabled=bool(row.get("enabled", True)),
        live=bool(row.get("enabled", True)) and starts <= now < ends,
    )


@retention_admin_router.get("/flash-deals", response_model=list[FlashDealOut])
async def list_flash_deals(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> list[FlashDealOut]:
    rows = _rows(
        supabase.client.table("flash_deals")
        .select(DEAL_COLUMNS)
        .order("starts_at", desc=True)
        .execute()
    )
    now = datetime.now(UTC)
    return [_deal_out(row, now=now) for row in rows]


@retention_admin_router.post("/flash-deals", response_model=FlashDealOut, status_code=201)
async def create_flash_deal(
    body: FlashDealIn,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> FlashDealOut:
    listing = _rows(
        supabase.client.table("vendor_listings")
        .select("id, price_ngwee, compare_at_ngwee")
        .eq("id", body.listing_id)
        .eq("status", "active")
        .execute()
    )
    if not listing:
        raise AppError(code="not_found", message="Listing not found", http_status=404)
    # Reference ("was") price defaults to the higher of compare-at and live price.
    live = int(listing[0]["price_ngwee"])
    compare_at = listing[0].get("compare_at_ngwee")
    reference = body.reference_price_ngwee or max(live, int(compare_at or 0))
    if body.deal_price_ngwee >= reference:
        raise _validation("deal_price_ngwee must be below the reference price")
    row = {
        **body.model_dump(mode="json"),
        "reference_price_ngwee": reference,
        "created_by": user.id,
        "updated_by": user.id,
    }
    created = _rows(supabase.client.table("flash_deals").insert(row).execute())
    if not created:
        raise AppError(code="internal_error", message="Could not create deal", http_status=500)
    out = _deal_out(created[0], now=datetime.now(UTC))
    recorder.record(
        action="deals.flash.create",
        entity_type="flash_deal",
        entity_id=out.id,
        before=None,
        after=out.model_dump(mode="json"),
    )
    return out


@retention_admin_router.patch("/flash-deals/{deal_id}", response_model=FlashDealOut)
async def update_flash_deal(
    deal_id: UUID,
    body: FlashDealPatch,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> FlashDealOut:
    before = _rows(
        supabase.client.table("flash_deals").select(DEAL_COLUMNS).eq("id", str(deal_id)).execute()
    )
    if not before:
        raise AppError(code="not_found", message="Deal not found", http_status=404)
    fields = body.model_dump(mode="json", exclude_none=True)
    merged = {**before[0], **fields}
    starts = datetime.fromisoformat(str(merged["starts_at"]).replace("Z", "+00:00"))
    ends = datetime.fromisoformat(str(merged["ends_at"]).replace("Z", "+00:00"))
    if ends <= starts:
        raise _validation("ends_at must be after starts_at")
    if int(merged["deal_price_ngwee"]) >= int(merged["reference_price_ngwee"]):
        raise _validation("deal_price_ngwee must be below the reference price")
    now = datetime.now(UTC)
    if not fields:
        return _deal_out(before[0], now=now)
    fields["updated_by"] = user.id
    updated = _rows(
        supabase.client.table("flash_deals").update(fields).eq("id", str(deal_id)).execute()
    )
    if not updated:
        raise AppError(code="internal_error", message="Could not update deal", http_status=500)
    out = _deal_out(updated[0], now=now)
    recorder.record(
        action="deals.flash.update",
        entity_type="flash_deal",
        entity_id=str(deal_id),
        before=_deal_out(before[0], now=now).model_dump(mode="json"),
        after=out.model_dump(mode="json"),
    )
    return out


class ModerateIn(BaseModel):
    model_config = {"extra": "forbid"}

    status: Literal["published", "hidden"]
    reason: str | None = Field(default=None, max_length=500)


@retention_admin_router.post("/qa/{kind}/{item_id}/moderate", status_code=200)
async def moderate_qa(
    kind: Literal["questions", "answers"],
    item_id: UUID,
    body: ModerateIn,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> dict[str, str]:
    table = "product_questions" if kind == "questions" else "product_answers"
    before = _rows(
        supabase.client.table(table).select("id, status").eq("id", str(item_id)).execute()
    )
    if not before:
        raise AppError(code="not_found", message="Item not found", http_status=404)
    fields: dict[str, Any] = {"status": body.status}
    if body.status == "published":
        fields["flag_count"] = 0
    supabase.client.table(table).update(fields).eq("id", str(item_id)).execute()
    recorder.record(
        action=f"qa.{kind}.moderate",
        entity_type=table,
        entity_id=str(item_id),
        before={"status": before[0].get("status")},
        after={"status": body.status, "reason": body.reason},
    )
    return {"id": str(item_id), "status": body.status}


admin_router.include_router(retention_admin_router)
