"""Vendor barcode lookup and assignment (scanner screen of the vendor mobile app).

Both endpoints are scoped to the authenticated vendor's own listings: a barcode that
exists on another vendor's listing is indistinguishable from one that does not exist.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit_policies import enforce_registered_policy
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.vendor_orders import _load_vendor_for_owner
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends
from pydantic import Field, field_validator

router = APIRouter(
    prefix="/vendor/listings",
    tags=["vendor-listings"],
    dependencies=[Depends(enforce_registered_policy)],
)

BARCODE_PATTERN = re.compile(r"^[0-9A-Za-z\-]{4,64}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_COLUMNS = (
    "id, vendor_id, title_override, price_ngwee, status, stock_mode, stock_qty, barcode, "
    "products(name)"
)


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class BarcodeListing(StrictModel):
    listing_id: str
    title: str
    price_ngwee: int
    status: str
    stock_mode: str
    stock_qty: int | None
    barcode: str | None


class SetBarcodeRequest(StrictModel):
    #: ``null`` clears the barcode.
    barcode: str | None = Field(default=None, max_length=64)

    @field_validator("barcode")
    @classmethod
    def valid_barcode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not BARCODE_PATTERN.match(value):
            raise ValueError("barcode must be 4 to 64 letters, digits or dashes")
        return value


def _first(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _serialize(row: dict[str, Any]) -> BarcodeListing:
    product = row.get("products")
    product_name = product.get("name") if isinstance(product, dict) else None
    title = row.get("title_override") or product_name or ""
    return BarcodeListing(
        listing_id=str(row["id"]),
        title=str(title),
        price_ngwee=int(row["price_ngwee"]),
        status=str(row["status"]),
        stock_mode=str(row.get("stock_mode") or ""),
        stock_qty=row.get("stock_qty"),
        barcode=row.get("barcode"),
    )


@router.get("/by-barcode/{barcode}", response_model=BarcodeListing)
def lookup_by_barcode(
    barcode: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> BarcodeListing:
    code = barcode.strip()
    if not BARCODE_PATTERN.match(code):
        raise AppError(code="not_found", message="No product with this barcode", http_status=404)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    row = _first(
        service_client.client.table("vendor_listings")
        .select(_COLUMNS)
        .eq("vendor_id", str(vendor["id"]))
        .eq("barcode", code)
        .maybe_single()
        .execute()
    )
    if row is None:
        raise AppError(code="not_found", message="No product with this barcode", http_status=404)
    return _serialize(row)


@router.put("/{listing_id}/barcode", response_model=BarcodeListing)
def set_listing_barcode(
    listing_id: str,
    body: SetBarcodeRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> BarcodeListing:
    if not _UUID.match(listing_id):
        raise AppError(code="not_found", message="Listing not found", http_status=404)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    listing = _first(
        service_client.client.table("vendor_listings")
        .select(_COLUMNS)
        .eq("id", listing_id)
        .eq("vendor_id", vendor_id)
        .maybe_single()
        .execute()
    )
    if listing is None:
        # Foreign and missing listings look the same: never confirm another vendor's id.
        raise AppError(code="not_found", message="Listing not found", http_status=404)
    if body.barcode is not None:
        clash = _first(
            service_client.client.table("vendor_listings")
            .select("id")
            .eq("vendor_id", vendor_id)
            .eq("barcode", body.barcode)
            .maybe_single()
            .execute()
        )
        if clash is not None and str(clash["id"]) != listing_id:
            raise AppError(
                code="conflict",
                message="Another product already uses this barcode",
                http_status=409,
                details={"message_key": "vendor.listings.barcode.taken"},
            )
    updated = _first(
        service_client.client.table("vendor_listings")
        .update({"barcode": body.barcode})
        .eq("id", listing_id)
        .eq("vendor_id", vendor_id)
        .execute()
    )
    return _serialize({**listing, **(updated or {}), "barcode": body.barcode})
