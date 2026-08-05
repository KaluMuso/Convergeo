from __future__ import annotations

import importlib
from typing import Any, cast

from supabase import Client


def _service_client_module() -> Any:
    return importlib.import_module("app.supabase_client")


def get_service_client() -> Any:
    return _service_client_module().get_supabase_service_client()


def fetch_active_cart_by_guest(guest_token: str) -> dict[str, Any] | None:
    service = get_service_client()
    response = (
        service.client.table("carts")
        .select("id, user_id, guest_token, status")
        .eq("guest_token", guest_token)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    rows = response.data
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return None


def create_guest_cart(guest_token: str) -> dict[str, Any]:
    import uuid

    service = get_service_client()
    cart_id = str(uuid.uuid4())
    response = (
        service.client.table("carts")
        .insert({"id": cart_id, "guest_token": guest_token, "status": "active"})
        .execute()
    )
    rows = response.data
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return {"id": cart_id, "user_id": None, "guest_token": guest_token, "status": "active"}


def fetch_listing(listing_id: str, *, business_eligible: bool = False) -> dict[str, Any]:
    """Load a listing for a cart mutation, applying D36's wholesale omission rule.

    ``business_eligible`` defaults to False — the safe value — so a caller that
    forgets to pass it gets the *stricter* behaviour rather than the leakier one.
    """
    from app.errors import AppError

    def _not_found() -> AppError:
        return AppError(
            code="cart.listing_not_found",
            message="Listing not found",
            http_status=404,
            details={"listing_id": listing_id},
        )

    service = get_service_client()
    response = (
        service.client.table("vendor_listings")
        .select(
            "id, vendor_id, title_override, price_ngwee, wholesale, moq, price_tiers, status, "
            "product_class, condition, fulfilment_mode, lead_time_days, vendor_capacity_per_week, "
            "stock_mode, stock_qty"
        )
        .eq("id", listing_id)
        .limit(1)
        .execute()
    )
    rows = response.data
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise _not_found()
    listing = rows[0]

    # D36 — a wholesale-only listing is omitted from every consumer surface, and a
    # direct hit is answered as though it never existed.
    #
    # This raises the SAME error object as an unknown id above — same code, same
    # status, same message — and deliberately not `business.wholesale_forbidden`
    # (403), which is what the B2B feed returns and what the B2B audit originally
    # specified here. A 403 would confirm that the id names a real listing, which
    # is all an id enumerator needs to map the B2B catalogue without ever
    # qualifying as a buyer. 403 stays reserved for `?wholesale=true`, where the
    # caller asserted business intent and refusing answers a question they asked.
    #
    # Checked BEFORE the status check below so a wholesale-only listing gets one
    # uniform answer: an inactive wholesale listing must not be distinguishable
    # from an inactive retail one by its error code either.
    if listing.get("wholesale") and not business_eligible:
        raise _not_found()

    if listing.get("status") != "active":
        raise AppError(
            code="cart.listing_inactive",
            message="Listing is not available for purchase",
            http_status=400,
            details={"listing_id": listing_id, "status": listing.get("status")},
        )
    return listing


def fetch_listings_for_items(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    listing_ids = sorted({str(item["listing_id"]) for item in items})
    if not listing_ids:
        return {}
    service = get_service_client()
    response = (
        service.client.table("vendor_listings")
        .select(
            "id, vendor_id, title_override, price_ngwee, wholesale, moq, price_tiers, status, "
            "product_class, condition, fulfilment_mode, lead_time_days, vendor_capacity_per_week, "
            "stock_mode, stock_qty"
        )
        .in_("id", listing_ids)
        .execute()
    )
    rows = response.data
    if not isinstance(rows, list):
        return {}
    return {str(row["id"]): row for row in rows if isinstance(row, dict)}


def mark_guest_cart_converted(guest_cart_id: str) -> None:
    service = get_service_client()
    service.client.table("carts").update({"status": "converted"}).eq("id", guest_cart_id).execute()


def service_db_client() -> Client:
    return cast(Client, get_service_client().client)
