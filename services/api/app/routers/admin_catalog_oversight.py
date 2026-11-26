"""Bounded read-only service and inventory oversight for restricted operators."""

from __future__ import annotations

from typing import Annotated, Any

from app.core.auth import CurrentUser, require_role
from app.deps import SupabaseServiceClient, get_supabase_client
from app.services.admin_people import MAX_TERM_LEN, clean_search_term
from app.services.service_packages import state as package_state
from fastapi import APIRouter, Depends, Query
from postgrest.types import CountMethod

router = APIRouter(prefix="/admin", tags=["admin-catalog-oversight"])

MAX_PAGE = 100
_STATUS_PATTERN = r"^[a-z_]{1,32}$"


def _page(items: list[dict[str, Any]], total: Any, offset: int, limit: int) -> dict[str, Any]:
    counted = total if isinstance(total, int) and not isinstance(total, bool) else None
    more = offset + limit < counted if counted is not None else len(items) == limit
    return {"items": items, "total": counted, "next_offset": offset + limit if more else None}


@router.get("/services")
def list_services(
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
    q: Annotated[str | None, Query(max_length=MAX_TERM_LEN)] = None,
    status: Annotated[str | None, Query(pattern=_STATUS_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, Any]:
    query = service.client.table("services").select(
        "id,vendor_id,title,category,status,created_at,from_price_ngwee,vendors(display_name)",
        count=CountMethod.exact,
    )
    term = clean_search_term(q)
    if term is not None:
        query = query.ilike("title", f"%{term}%")
    if status is not None:
        query = query.eq("status", status)
    response = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    items = [_service_oversight_row(row) for row in package_state.rows(response)]
    return _page(_with_packages(service, items), getattr(response, "count", None), offset, limit)


def _vendor_display_name(row: dict[str, Any]) -> str | None:
    vendors = row.get("vendors")
    if isinstance(vendors, dict):
        name = vendors.get("display_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _service_oversight_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = {key: value for key, value in row.items() if key != "vendors"}
    cleaned["vendor_display_name"] = _vendor_display_name(row)
    return cleaned


def _with_packages(
    service: SupabaseServiceClient, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach every package (any status) so admin sees what customers are offered."""
    ids = [str(item["id"]) for item in items if isinstance(item, dict) and item.get("id")]
    grouped: dict[str, list[dict[str, Any]]] = {}
    if ids:
        try:
            response = (
                service.client.table(package_state.TABLE)
                .select("id,service_id,tier,name,price_ngwee,delivery_days,status")
                .in_("service_id", ids)
                .execute()
            )
        except Exception:
            response = None
        found = package_state.rows(response)
        for row in found:
            grouped.setdefault(str(row.get("service_id")), []).append(
                {
                    "id": str(row.get("id")),
                    "tier": row.get("tier"),
                    "name": row.get("name"),
                    "price_ngwee": package_state.int_or_none(row.get("price_ngwee")),
                    "delivery_days": package_state.int_or_none(row.get("delivery_days")),
                    "status": row.get("status"),
                }
            )
    return [
        {**item, "packages": package_state.sort_by_tier(grouped.get(str(item.get("id")), []))}
        for item in items
        if isinstance(item, dict)
    ]


def _product_ids_named(service: SupabaseServiceClient, term: str) -> list[str]:
    response = (
        service.client.table("products")
        .select("id")
        .ilike("name", f"%{term}%")
        .limit(200)
        .execute()
    )
    data = response.data if isinstance(response.data, list) else []
    return [str(row["id"]) for row in data if isinstance(row, dict) and row.get("id")]


@router.get("/inventory")
def list_inventory(
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
    q: Annotated[str | None, Query(max_length=MAX_TERM_LEN)] = None,
    status: Annotated[str | None, Query(pattern=_STATUS_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, Any]:
    query = (
        service.client.table("vendor_listings")
        .select(
            "id,vendor_id,product_id,title_override,price_ngwee,stock_mode,stock_qty,status,"
            "vendors(display_name),products(name)",
            count=CountMethod.exact,
        )
        .eq("stock_mode", "tracked")
    )
    term = clean_search_term(q)
    if term is not None:
        product_ids = _product_ids_named(service, term)
        clauses = [f"title_override.ilike.%{term}%"]
        if product_ids:
            clauses.append(f"product_id.in.({','.join(product_ids)})")
        query = query.or_(",".join(clauses))
    if status is not None:
        query = query.eq("status", status)
    response = query.order("stock_qty").range(offset, offset + limit - 1).execute()
    raw = response.data if isinstance(response.data, list) else []
    items = [_inventory_oversight_row(row) for row in raw if isinstance(row, dict)]
    return _page(items, getattr(response, "count", None), offset, limit)


def _inventory_oversight_row(row: dict[str, Any]) -> dict[str, Any]:
    products = row.get("products")
    product_name = None
    if isinstance(products, dict):
        name = products.get("name")
        if isinstance(name, str) and name.strip():
            product_name = name.strip()
    title = row.get("title_override")
    listing_title = title.strip() if isinstance(title, str) and title.strip() else None
    cleaned = {key: value for key, value in row.items() if key not in {"vendors", "products"}}
    cleaned["vendor_display_name"] = _vendor_display_name(row)
    cleaned["product_name"] = product_name
    cleaned["display_title"] = listing_title or product_name
    return cleaned
