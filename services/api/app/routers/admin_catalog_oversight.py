"""Bounded read-only service and inventory oversight for restricted operators."""

from __future__ import annotations

from typing import Annotated, Any

from app.core.auth import CurrentUser, require_role
from app.supabase_client import SupabaseServiceClient, get_supabase_service_client
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/admin", tags=["admin-catalog-oversight"])


@router.get("/services")
def list_services(
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
) -> dict[str, Any]:
    response = (
        service.client.table("services")
        .select("id,vendor_id,title,category,status,created_at")
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )
    return {"items": response.data if isinstance(response.data, list) else []}


@router.get("/inventory")
def list_inventory(
    _actor: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_service_client)],
) -> dict[str, Any]:
    response = (
        service.client.table("vendor_listings")
        .select("id,vendor_id,product_id,title_override,stock_mode,stock_qty,status")
        .eq("stock_mode", "tracked")
        .order("stock_qty")
        .limit(100)
        .execute()
    )
    return {"items": response.data if isinstance(response.data, list) else []}
