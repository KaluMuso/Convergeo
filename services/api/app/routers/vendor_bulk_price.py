from __future__ import annotations

from typing import Annotated, Any, Literal

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit_policies import enforce_registered_policy
from app.deps import get_supabase_client
from app.errors import AppError, field_value_error
from app.schemas.base import StrictModel
from app.services.branches.context import scope_owner_vendor_query
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.listings.bulk_price import (
    MAX_BULK_LISTINGS,
    BulkPriceRow,
    build_bulk_price_rows,
)
from fastapi import APIRouter, Depends
from pydantic import Field

router = APIRouter(
    prefix="/vendor/listings/bulk-price",
    tags=["vendor-listings"],
    dependencies=[Depends(enforce_registered_policy)],
)

AdjustmentKind = Literal["delta_ngwee", "percent_bps"]


class BulkPriceRequest(StrictModel):
    listing_ids: list[str] = Field(min_length=1, max_length=MAX_BULK_LISTINGS)
    adjustment_kind: AdjustmentKind
    adjustment_value: int


class BulkPriceApplyRequest(BulkPriceRequest):
    operation_id: str = Field(
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )


class BulkPriceLine(StrictModel):
    listing_id: str
    title: str
    old_price_ngwee: int | None
    new_price_ngwee: int | None
    skip_reason: str | None
    warnings: list[str]


class BulkPricePreviewResponse(StrictModel):
    lines: list[BulkPriceLine]


class BulkPriceApplyResponse(StrictModel):
    batch_id: str
    operation_id: str
    applied_count: int
    skipped_count: int
    idempotent_replay: bool
    lines: list[BulkPriceLine]


def _load_vendor(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        scope_owner_vendor_query(
            service_client.client.table("vendors")
            .select("id, owner_user_id, status")
            .eq("owner_user_id", owner_user_id)
        )
        .maybe_single()
        .execute()
    )
    row = getattr(response, "data", None)
    if not isinstance(row, dict):
        raise AppError(
            status_code=403,
            code="vendor_not_found",
            message_key="vendor.errors.notFound",
        )
    return row


def _load_listings(
    service_client: ServiceRoleClient,
  listing_ids: list[str],
) -> dict[str, dict[str, Any]]:
    if not listing_ids:
        return {}
    response = (
        service_client.client.table("vendor_listings")
        .select(
            "id, vendor_id, status, price_ngwee, price_tiers, title_override, "
            "products(name, category_path)"
        )
        .in_("id", listing_ids)
        .execute()
    )
    rows = getattr(response, "data", None)
    if not isinstance(rows, list):
        return {}
    return {str(row["id"]): row for row in rows if isinstance(row, dict) and row.get("id")}


def _serialize_lines(rows: list[BulkPriceRow]) -> list[BulkPriceLine]:
    return [
        BulkPriceLine(
            listing_id=row.listing_id,
            title=row.title,
            old_price_ngwee=row.old_price_ngwee,
            new_price_ngwee=row.new_price_ngwee,
            skip_reason=row.skip_reason,
            warnings=row.warnings,
        )
        for row in rows
    ]


def _preview_rows(
    *,
    service_client: ServiceRoleClient,
    vendor_id: str,
    body: BulkPriceRequest,
) -> list[BulkPriceRow]:
    unique_ids = list(dict.fromkeys(body.listing_ids))
    if len(unique_ids) > MAX_BULK_LISTINGS:
        raise field_value_error("listing_ids", "At most 200 listings", "too_many_listings")
    listings = _load_listings(service_client, unique_ids)
    return build_bulk_price_rows(
        listing_ids=unique_ids,
        listings_by_id=listings,
        vendor_id=vendor_id,
        adjustment_kind=body.adjustment_kind,
        adjustment_value=body.adjustment_value,
    )


@router.post("/preview", response_model=BulkPricePreviewResponse)
async def preview_bulk_price(
    body: BulkPriceRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BulkPricePreviewResponse:
    vendor = _load_vendor(service_client, current_user.id)
    rows = _preview_rows(
        service_client=service_client,
        vendor_id=str(vendor["id"]),
        body=body,
    )
    return BulkPricePreviewResponse(lines=_serialize_lines(rows))


@router.post("/apply", response_model=BulkPriceApplyResponse)
async def apply_bulk_price(
    body: BulkPriceApplyRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BulkPriceApplyResponse:
    vendor = _load_vendor(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    existing = (
        service_client.client.table("vendor_price_change_batches")
        .select("id, operation_id")
        .eq("vendor_id", vendor_id)
        .eq("operation_id", body.operation_id)
        .maybe_single()
        .execute()
    )
    existing_row = getattr(existing, "data", None)
    if isinstance(existing_row, dict):
        items = (
            service_client.client.table("vendor_price_change_batch_items")
            .select(
                "listing_id, old_price_ngwee, new_price_ngwee, skip_reason, warnings, applied"
            )
            .eq("batch_id", existing_row["id"])
            .execute()
        )
        item_rows = getattr(items, "data", None) or []
        lines = [
            BulkPriceLine(
                listing_id=str(row["listing_id"]),
                title="",
                old_price_ngwee=row.get("old_price_ngwee"),
                new_price_ngwee=row.get("new_price_ngwee"),
                skip_reason=row.get("skip_reason"),
                warnings=list(row.get("warnings") or []),
            )
            for row in item_rows
            if isinstance(row, dict)
        ]
        applied_count = sum(1 for line in lines if line.skip_reason is None)
        return BulkPriceApplyResponse(
            batch_id=str(existing_row["id"]),
            operation_id=body.operation_id,
            applied_count=applied_count,
            skipped_count=len(lines) - applied_count,
            idempotent_replay=True,
            lines=lines,
        )

    preview_rows = _preview_rows(
        service_client=service_client,
        vendor_id=vendor_id,
        body=body,
    )
    batch_insert = (
        service_client.client.table("vendor_price_change_batches")
        .insert(
            {
                "vendor_id": vendor_id,
                "operation_id": body.operation_id,
                "adjustment_kind": body.adjustment_kind,
                "adjustment_value": body.adjustment_value,
                "listing_count": len(preview_rows),
            }
        )
        .execute()
    )
    batch_rows = getattr(batch_insert, "data", None)
    if not isinstance(batch_rows, list) or not batch_rows:
        raise AppError(
            status_code=500,
            code="bulk_price_batch_failed",
            message="Batch insert failed",
        )
    batch_id = str(batch_rows[0]["id"])

    applied_count = 0
    skipped_count = 0
    for row in preview_rows:
        if row.applied and row.new_price_ngwee is not None:
            service_client.client.table("vendor_listings").update(
                {"price_ngwee": row.new_price_ngwee}
            ).eq("id", row.listing_id).eq("vendor_id", vendor_id).execute()
            applied_count += 1
        else:
            skipped_count += 1
        service_client.client.table("vendor_price_change_batch_items").insert(
            {
                "batch_id": batch_id,
                "listing_id": row.listing_id,
                "old_price_ngwee": row.old_price_ngwee,
                "new_price_ngwee": row.new_price_ngwee,
                "applied": row.applied,
                "skip_reason": row.skip_reason,
                "warnings": row.warnings,
            }
        ).execute()

    service_client.client.table("vendor_price_change_batches").update(
        {"applied_count": applied_count, "skipped_count": skipped_count}
    ).eq("id", batch_id).execute()

    return BulkPriceApplyResponse(
        batch_id=batch_id,
        operation_id=body.operation_id,
        applied_count=applied_count,
        skipped_count=skipped_count,
        idempotent_replay=False,
        lines=_serialize_lines(preview_rows),
    )