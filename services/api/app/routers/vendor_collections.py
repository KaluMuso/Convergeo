"""Vendor storefront collections — CRUD and listing assignment.

Every route re-checks collection ownership against the authenticated vendor.
Cross-vendor listing links are refused here and by ``storefront_collection_items_guard``.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.vendor_orders import _load_vendor_for_owner
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends
from pydantic import Field, field_validator

router = APIRouter(prefix="/vendor/collections", tags=["vendor-collections"])

COLLECTIONS_TABLE = "vendor_storefront_collections"
ITEMS_TABLE = "vendor_storefront_collection_items"
LISTINGS_TABLE = "vendor_listings"

SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")
MAX_ITEMS_PER_COLLECTION = 50
RATE_LIMIT_PER_MINUTE = 60

CollectionStatus = Literal["active", "draft"]


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class CollectionItemOut(StrictModel):
    listing_id: str
    title: str | None
    price_ngwee: int
    sort_order: int


class CollectionOut(StrictModel):
    id: str
    title: str
    slug: str
    sort_order: int
    status: CollectionStatus
    items: list[CollectionItemOut] = Field(default_factory=list)


class CollectionListResponse(StrictModel):
    items: list[CollectionOut]


class CollectionCreateRequest(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=2, max_length=80)
    sort_order: int = Field(default=0, ge=0)
    status: CollectionStatus = "active"

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not SLUG_PATTERN.fullmatch(normalized):
            raise ValueError("slug must be lowercase letters, numbers, and hyphens only")
        return normalized


class CollectionUpdateRequest(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=80)
    sort_order: int | None = Field(default=None, ge=0)
    status: CollectionStatus | None = None

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not SLUG_PATTERN.fullmatch(normalized):
            raise ValueError("slug must be lowercase letters, numbers, and hyphens only")
        return normalized


class CollectionItemsRequest(StrictModel):
    listing_ids: list[str] = Field(min_length=1, max_length=MAX_ITEMS_PER_COLLECTION)


class CollectionItemsResponse(StrictModel):
    collection_id: str
    items: list[CollectionItemOut]


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    rows = _rows(response)
    return rows[0] if rows else None


def _rate_limit(service_client: _ServiceRoleClient, *, scope: str, key: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=scope,
        key=key,
        window=timedelta(minutes=1),
        limit=RATE_LIMIT_PER_MINUTE,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="vendor.collections.errors.rateLimited",
            message="Too many collection requests",
        )


def _own_collection(
    service_client: _ServiceRoleClient, *, collection_id: str, vendor_id: str
) -> dict[str, Any]:
    row = _single_row(
        service_client.client.table(COLLECTIONS_TABLE)
        .select("*")
        .eq("id", collection_id)
        .maybe_single()
        .execute()
    )
    if row is None or str(row.get("vendor_id")) != vendor_id:
        raise AppError(
            code="collection_not_found",
            message="Collection not found",
            http_status=404,
            details={"message_key": "vendor.collections.errors.notFound"},
        )
    return row


def _listing_title(row: dict[str, Any]) -> str | None:
    override = row.get("title_override")
    if isinstance(override, str) and override.strip():
        return override.strip()
    product = row.get("products")
    if isinstance(product, dict):
        name = product.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _load_items(
    service_client: _ServiceRoleClient, *, collection_id: str
) -> list[CollectionItemOut]:
    rows = _rows(
        service_client.client.table(ITEMS_TABLE)
        .select(
            "listing_id, sort_order, vendor_listings(title_override, price_ngwee, products(name))"
        )
        .eq("collection_id", collection_id)
        .order("sort_order")
        .order("listing_id")
        .execute()
    )
    items: list[CollectionItemOut] = []
    for row in rows:
        listing = row.get("vendor_listings")
        if not isinstance(listing, dict):
            continue
        items.append(
            CollectionItemOut(
                listing_id=str(row["listing_id"]),
                title=_listing_title(listing),
                price_ngwee=int(listing.get("price_ngwee") or 0),
                sort_order=int(row.get("sort_order") or 0),
            )
        )
    return items


def _to_collection_out(
    row: dict[str, Any], *, items: list[CollectionItemOut] | None = None
) -> CollectionOut:
    return CollectionOut(
        id=str(row["id"]),
        title=str(row["title"]),
        slug=str(row["slug"]),
        sort_order=int(row.get("sort_order") or 0),
        status=row.get("status") or "active",
        items=items if items is not None else [],
    )


def _assert_own_listings(
    service_client: _ServiceRoleClient, *, vendor_id: str, listing_ids: list[str]
) -> None:
    unique_ids = list(dict.fromkeys(listing_ids))
    rows = _rows(
        service_client.client.table(LISTINGS_TABLE)
        .select("id, vendor_id")
        .in_("id", unique_ids)
        .execute()
    )
    found = {str(row["id"]): str(row.get("vendor_id")) for row in rows}
    for listing_id in unique_ids:
        owner = found.get(listing_id)
        if owner is None:
            raise AppError(
                code="listing_not_found",
                message="Listing not found",
                http_status=404,
                details={"message_key": "vendor.collections.errors.listingNotFound"},
            )
        if owner != vendor_id:
            raise AppError(
                code="listing_forbidden",
                message="Listing does not belong to this vendor",
                http_status=403,
                details={"message_key": "vendor.collections.errors.listingForbidden"},
            )


@router.get("", response_model=CollectionListResponse)
def list_collections(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CollectionListResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    rows = _rows(
        service_client.client.table(COLLECTIONS_TABLE)
        .select("*")
        .eq("vendor_id", vendor_id)
        .order("sort_order")
        .order("id")
        .execute()
    )
    items: list[CollectionOut] = []
    for row in rows:
        collection_id = str(row["id"])
        items.append(
            _to_collection_out(row, items=_load_items(service_client, collection_id=collection_id))
        )
    return CollectionListResponse(items=items)


@router.post("", response_model=CollectionOut)
def create_collection(
    body: CollectionCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CollectionOut:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    _rate_limit(service_client, scope="vendor_collections_write", key=vendor_id)

    row = _single_row(
        service_client.client.table(COLLECTIONS_TABLE)
        .insert(
            {
                "vendor_id": vendor_id,
                "title": body.title.strip(),
                "slug": body.slug,
                "sort_order": body.sort_order,
                "status": body.status,
            }
        )
        .execute()
    )
    if row is None:
        raise AppError(
            code="collection_create_failed",
            message="Could not create collection",
            http_status=500,
        )
    return _to_collection_out(row)


@router.get("/{collection_id}", response_model=CollectionOut)
def get_collection(
    collection_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CollectionOut:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    row = _own_collection(
        service_client, collection_id=collection_id, vendor_id=str(vendor["id"])
    )
    return _to_collection_out(
        row, items=_load_items(service_client, collection_id=collection_id)
    )


@router.patch("/{collection_id}", response_model=CollectionOut)
def update_collection(
    collection_id: str,
    body: CollectionUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CollectionOut:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    _rate_limit(service_client, scope="vendor_collections_write", key=vendor_id)
    _own_collection(service_client, collection_id=collection_id, vendor_id=vendor_id)

    patch: dict[str, Any] = {}
    if body.title is not None:
        patch["title"] = body.title.strip()
    if body.slug is not None:
        patch["slug"] = body.slug
    if body.sort_order is not None:
        patch["sort_order"] = body.sort_order
    if body.status is not None:
        patch["status"] = body.status
    if not patch:
        existing = _own_collection(service_client, collection_id=collection_id, vendor_id=vendor_id)
        return _to_collection_out(
            existing, items=_load_items(service_client, collection_id=collection_id)
        )

    updated = _single_row(
        service_client.client.table(COLLECTIONS_TABLE)
        .update(patch)
        .eq("id", collection_id)
        .eq("vendor_id", vendor_id)
        .execute()
    )
    if updated is None:
        raise AppError(
            code="collection_update_failed",
            message="Could not update collection",
            http_status=500,
        )
    return _to_collection_out(
        updated, items=_load_items(service_client, collection_id=collection_id)
    )


@router.delete("/{collection_id}")
def delete_collection(
    collection_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, bool]:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    _rate_limit(service_client, scope="vendor_collections_write", key=vendor_id)
    _own_collection(service_client, collection_id=collection_id, vendor_id=vendor_id)

    service_client.client.table(COLLECTIONS_TABLE).delete().eq("id", collection_id).eq(
        "vendor_id", vendor_id
    ).execute()
    return {"deleted": True}


@router.put("/{collection_id}/items", response_model=CollectionItemsResponse)
def assign_collection_items(
    collection_id: str,
    body: CollectionItemsRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CollectionItemsResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    _rate_limit(service_client, scope="vendor_collections_write", key=vendor_id)
    _own_collection(service_client, collection_id=collection_id, vendor_id=vendor_id)

    unique_ids = list(dict.fromkeys(body.listing_ids))
    _assert_own_listings(service_client, vendor_id=vendor_id, listing_ids=unique_ids)

    service_client.client.table(ITEMS_TABLE).delete().eq("collection_id", collection_id).execute()

    payload = [
        {"collection_id": collection_id, "listing_id": lid, "sort_order": index}
        for index, lid in enumerate(unique_ids)
    ]
    if payload:
        service_client.client.table(ITEMS_TABLE).insert(payload).execute()

    items = _load_items(service_client, collection_id=collection_id)
    return CollectionItemsResponse(collection_id=collection_id, items=items)
