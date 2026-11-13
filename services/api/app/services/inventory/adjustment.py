"""Vendor-only adapter to the existing stock tables' atomic adjustment RPC."""

from typing import Any

from app.errors import AppError
from app.services.kyc.state_machine import ServiceRoleClient


def adjust_stock(service: ServiceRoleClient, **parameters: Any) -> dict[str, Any]:
    try:
        response = service.client.rpc("adjust_vendor_stock", parameters).execute()
    except Exception as exc:
        # An unknown transport outcome must be retried with the SAME operation ID.
        raise AppError(
            "stock.unavailable",
            "Stock adjustment outcome is unavailable",
            503,
            {"message_key": "vendor.listings.manage.stock.retrySame", "retry_same_operation": True},
        ) from exc
    outcome = response.data
    if not isinstance(outcome, dict) or not isinstance(outcome.get("ok"), bool):
        raise AppError("stock.unavailable", "Stock adjustment outcome is unavailable", 503)
    if not outcome["ok"]:
        code = str(outcome.get("code", "stock.conflict"))
        raise AppError(
            code,
            "Stock adjustment was rejected",
            int(outcome.get("status", 409)),
            {
                "message_key": "vendor.listings.manage.stock.conflict",
                "operation_id": parameters["p_operation_id"],
            },
        )
    return outcome


def stock_context(
    service: ServiceRoleClient, listing: dict[str, Any], vendor_id: str
) -> dict[str, Any]:
    response = (
        service.client.table("listing_location_stock")
        .select("location_id, stock_qty, vendor_locations(id, vendor_id, label, status)")
        .eq("listing_id", str(listing["id"]))
        .execute()
    )
    rows = response.data or []
    branches = []
    for row in rows:
        location = row.get("vendor_locations") or {}
        if location.get("vendor_id") != vendor_id:
            continue
        branches.append(
            {
                "location_id": row["location_id"],
                "label": location.get("label"),
                "stock_qty": row["stock_qty"],
                "active": location.get("status") == "active",
            }
        )
    return {
        "listing_id": listing["id"],
        "branch_tracked": bool(rows),
        "branches": branches,
        "stock_qty": None if rows else listing.get("stock_qty"),
        "stock_mode": listing["stock_mode"],
        "sale_unit": listing.get("sale_unit", "each"),
        "unit_step_milli": listing.get("unit_step_milli", 1000),
    }
