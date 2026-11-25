"""Bounded read-only service and inventory oversight for restricted operators."""

from __future__ import annotations

from typing import Annotated, Any

from app.core.auth import CurrentUser, require_role
from app.deps import SupabaseServiceClient, get_supabase_client
from app.services.service_packages import state as package_state
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/admin", tags=["admin-catalog-oversight"])


@router.get("/services")
def list_services(
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    response = (
        service.client.table("services")
        .select(
            "id,vendor_id,title,category,status,created_at,from_price_ngwee,vendors(display_name)"
        )
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )
    items = [_service_oversight_row(row) for row in package_state.rows(response)]
    return {"items": _with_packages(service, items)}


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


@router.get("/inventory")
def list_inventory(
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    response = (
        service.client.table("vendor_listings")
        .select(
            "id,vendor_id,product_id,title_override,price_ngwee,stock_mode,stock_qty,status,"
            "vendors(display_name),products(name)"
        )
        .eq("stock_mode", "tracked")
        .order("stock_qty")
        .limit(100)
        .execute()
    )
    raw = response.data if isinstance(response.data, list) else []
    items = [_inventory_oversight_row(row) for row in raw if isinstance(row, dict)]
    return {"items": items}


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
    cleaned["display_title"] = listing_title or product_name or cleaned["id"]
    return cleaned
