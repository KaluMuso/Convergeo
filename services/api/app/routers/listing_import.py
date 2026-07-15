from __future__ import annotations

from typing import Annotated, Any

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.kyc.caps import VendorCapLimits, get_vendor_cap_limits
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.listings.csv_import import (
    MAX_CSV_ROWS,
    ImportPreview,
    ImportSummary,
    build_template_csv,
    import_csv_bytes,
    import_listing_rows,
    preview_import_csv_bytes,
    preview_import_rows,
)
from app.services.moderation.prohibited import screen_listing
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from pydantic import Field

router = APIRouter(prefix="/listings", tags=["listing-import"])


class ListingImportRowInput(StrictModel):
    sku: str = Field(min_length=1)
    title: str = Field(min_length=1)
    price_ngwee: int = Field(ge=1)
    stock_mode: str
    condition: str
    stock_qty: int | None = None
    wholesale: bool = False
    moq: int = Field(default=1, ge=1)
    price_tiers: str | None = None
    returnable: bool = False
    return_window_hours: int | None = None
    status: str = "active"
    vendor_id: str | None = None
    product_id: str | None = None


class ListingImportJsonRequest(StrictModel):
    rows: list[ListingImportRowInput] = Field(min_length=1)


class ListingImportRawRequest(StrictModel):
    """Apply already-parsed rows (as string cells) — used by the preview→confirm
    flow so the vendor's chosen product_id round-trips without re-parsing CSV."""

    raw_rows: list[dict[str, str]] = Field(min_length=1, max_length=MAX_CSV_ROWS)


class RowImportResultResponse(StrictModel):
    row: int
    ok: bool
    errors: list[str]
    listing_id: str | None = None


class ListingImportResponse(StrictModel):
    accepted: int
    rejected: int
    rows: list[RowImportResultResponse]


class CanonicalSuggestionResponse(StrictModel):
    product_id: str
    name: str
    score: float


class RowPreviewResponse(StrictModel):
    row: int
    ok: bool
    errors: list[str]
    sku: str | None = None
    title: str | None = None
    price_ngwee: int | None = None
    product_id: str | None = None
    matched_name: str | None = None
    suggestions: list[CanonicalSuggestionResponse] = Field(default_factory=list)
    raw: dict[str, str] = Field(default_factory=dict)


class ImportPreviewResponse(StrictModel):
    total: int
    valid: int
    invalid: int
    rows: list[RowPreviewResponse]


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _load_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, kyc_tier")
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
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def _to_response(summary: ImportSummary) -> ListingImportResponse:
    return ListingImportResponse(
        accepted=summary.accepted,
        rejected=summary.rejected,
        rows=[
            RowImportResultResponse(
                row=row.row,
                ok=row.ok,
                errors=row.errors,
                listing_id=row.listing_id,
            )
            for row in summary.rows
        ],
    )


def _json_row_to_raw(row: ListingImportRowInput) -> dict[str, str]:
    return {
        "sku": row.sku,
        "title": row.title,
        "price_ngwee": str(row.price_ngwee),
        "stock_mode": row.stock_mode,
        "condition": row.condition,
        "stock_qty": str(row.stock_qty) if row.stock_qty is not None else "",
        "wholesale": "true" if row.wholesale else "false",
        "moq": str(row.moq),
        "price_tiers": row.price_tiers or "",
        "returnable": "true" if row.returnable else "false",
        "return_window_hours": (
            str(row.return_window_hours) if row.return_window_hours is not None else ""
        ),
        "status": row.status,
        "vendor_id": row.vendor_id or "",
        "product_id": row.product_id or "",
    }


def _to_preview_response(preview: ImportPreview) -> ImportPreviewResponse:
    return ImportPreviewResponse(
        total=preview.total,
        valid=preview.valid,
        invalid=preview.invalid,
        rows=[
            RowPreviewResponse(
                row=row.row,
                ok=row.ok,
                errors=row.errors,
                sku=row.sku,
                title=row.title,
                price_ngwee=row.price_ngwee,
                product_id=row.product_id,
                matched_name=row.matched_name,
                suggestions=[
                    CanonicalSuggestionResponse(
                        product_id=suggestion.product_id,
                        name=suggestion.name,
                        score=suggestion.score,
                    )
                    for suggestion in row.suggestions
                ],
                raw=row.raw,
            )
            for row in preview.rows
        ],
    )


@router.get("/import/template", response_class=PlainTextResponse)
async def download_import_template(
    _current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
) -> PlainTextResponse:
    return PlainTextResponse(
        content=build_template_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="vergeo5-listings-template.csv"'},
    )


@router.post("/import", response_model=ListingImportResponse)
async def import_listings(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    limits: Annotated[VendorCapLimits, Depends(get_vendor_cap_limits)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ListingImportResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    client = service_client.client
    content_type = request.headers.get("content-type", "")

    if "text/csv" in content_type or "application/csv" in content_type:
        csv_bytes = await request.body()
        summary = import_csv_bytes(
            client,
            vendor_id=vendor_id,
            limits=limits,
            csv_bytes=csv_bytes,
        )
        return _to_response(summary)

    if "application/json" in content_type:
        body = await request.json()
        if isinstance(body, dict) and "raw_rows" in body:
            raw_request = ListingImportRawRequest.model_validate(body)
            # import_listing_rows applies the full per-row validation, prohibited
            # screen, product_id check, cap enforcement, and idempotent upsert.
            summary = import_listing_rows(
                client,
                vendor_id=vendor_id,
                limits=limits,
                rows=raw_request.raw_rows,
            )
            return _to_response(summary)

        payload = ListingImportJsonRequest.model_validate(body)
        for index, row in enumerate(payload.rows, start=1):
            guard = screen_listing(title=row.title)
            if not guard.allowed:
                raise AppError(
                    code="prohibited_listing",
                    message="Import contains a prohibited category or keyword",
                    http_status=422,
                    details={
                        "message_key": "vendor.listings.errors.submitFailed",
                        "row": index,
                        "reason": guard.reason,
                        "matched": guard.matched,
                    },
                )
        raw_rows = [_json_row_to_raw(row) for row in payload.rows]
        summary = import_listing_rows(
            client,
            vendor_id=vendor_id,
            limits=limits,
            rows=raw_rows,
        )
        return _to_response(summary)

    raise AppError(
        code="validation_error",
        message="Provide text/csv body or application/json rows payload",
        http_status=422,
        details={"message_key": "vendor.listings.import.errors.no_payload"},
    )


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def preview_import(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    limits: Annotated[VendorCapLimits, Depends(get_vendor_cap_limits)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ImportPreviewResponse:
    """Dry-run: validate rows and suggest canonical matches. Writes nothing."""
    # Confirms the caller owns a vendor profile (same gate as apply).
    _load_vendor_for_owner(service_client, current_user.id)
    client = service_client.client
    content_type = request.headers.get("content-type", "")

    if "text/csv" in content_type or "application/csv" in content_type:
        csv_bytes = await request.body()
        preview = preview_import_csv_bytes(client, limits=limits, csv_bytes=csv_bytes)
        return _to_preview_response(preview)

    if "application/json" in content_type:
        payload = ListingImportJsonRequest.model_validate(await request.json())
        raw_rows = [_json_row_to_raw(row) for row in payload.rows]
        preview = preview_import_rows(client, limits=limits, rows=raw_rows)
        return _to_preview_response(preview)

    raise AppError(
        code="validation_error",
        message="Provide text/csv body or application/json rows payload",
        http_status=422,
        details={"message_key": "vendor.listings.import.errors.no_payload"},
    )
