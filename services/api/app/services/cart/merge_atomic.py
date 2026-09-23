"""Database-atomic application of a trusted login cart-merge proposal."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, cast

from app.errors import AppError
from app.services.cart.merge import MergedCartItem
from postgrest.exceptions import APIError

_RPC_NAME = "apply_login_cart_merge"


class AtomicMergeOutcome(StrEnum):
    APPLIED = "applied"
    ALREADY_CONVERTED = "already_converted"
    STALE_SNAPSHOT = "stale_snapshot"
    STALE_AUTHORITY = "stale_authority"


def cart_items_snapshot(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the exact stable shape the SQL RPC compares under its cart locks."""
    snapshot = [
        {
            "id": str(item["id"]),
            "listing_id": str(item["listing_id"]),
            "qty": int(item["qty"]),
            "unit_price_ngwee": int(item["unit_price_ngwee"]),
            "wholesale": bool(item["wholesale"]),
            "pickup_location_id": (
                str(item["pickup_location_id"])
                if item.get("pickup_location_id") is not None
                else None
            ),
            "rfq_thread_id": (
                str(item["rfq_thread_id"]) if item.get("rfq_thread_id") is not None else None
            ),
        }
        for item in items
    ]
    return sorted(snapshot, key=lambda item: cast(str, item["id"]))


def _proposal_payload(items: list[MergedCartItem]) -> list[dict[str, Any]]:
    return [
        {
            "listing_id": item.listing_id,
            "qty": item.qty,
            "unit_price_ngwee": item.unit_price_ngwee,
            "wholesale": item.wholesale,
            "pickup_location_id": item.pickup_location_id,
            "rfq_thread_id": item.rfq_thread_id,
        }
        for item in items
    ]


def fetch_cart_merge_authority(
    service_client: Any,
    *,
    user_id: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Read the exact authority snapshot the commit RPC locks and rechecks."""
    listing_ids = sorted({str(item["listing_id"]) for item in items})
    rfq_thread_ids = sorted(
        {str(item["rfq_thread_id"]) for item in items if item.get("rfq_thread_id") is not None}
    )
    try:
        response = service_client.rpc(
            "cart_merge_authority",
            {
                "p_user_id": user_id,
                "p_listing_ids": listing_ids,
                "p_rfq_thread_ids": rfq_thread_ids,
            },
        ).execute()
    except APIError as exc:
        raise AppError(
            code="cart.merge_failed",
            message="Could not load authoritative cart state",
            http_status=503,
            details={"retry": True},
        ) from exc
    data = getattr(response, "data", None)
    if not isinstance(data, dict):
        raise AppError(
            code="cart.merge_failed",
            message="Authoritative cart state is unavailable",
            http_status=503,
            details={"retry": True},
        )
    return data


def apply_login_cart_merge_atomic(
    service_client: Any,
    *,
    user_id: str,
    user_cart_id: str,
    guest_cart_id: str,
    guest_token: str,
    expected_user_items: list[dict[str, Any]],
    expected_guest_items: list[dict[str, Any]],
    expected_authority: dict[str, Any],
    merged_items: list[MergedCartItem],
    removed_items: list[dict[str, Any]],
    resolution: dict[str, Any],
) -> AtomicMergeOutcome:
    """Apply one optimistic proposal; stale callers must re-read and recompute."""
    params = {
        "p_user_id": user_id,
        "p_user_cart_id": user_cart_id,
        "p_guest_cart_id": guest_cart_id,
        "p_guest_token": guest_token,
        "p_expected_user_items": cart_items_snapshot(expected_user_items),
        "p_expected_guest_items": cart_items_snapshot(expected_guest_items),
        "p_expected_authority": expected_authority,
        "p_merged_items": _proposal_payload(merged_items),
        "p_removed_items": removed_items,
        "p_resolution": resolution,
    }
    try:
        response = service_client.rpc(_RPC_NAME, params).execute()
    except APIError as exc:
        hint = str(getattr(exc, "message", "") or exc)
        code = getattr(exc, "code", None)
        if code == "42501":
            raise AppError(
                code="forbidden",
                message="Cart merge ownership verification failed",
                http_status=403,
            ) from exc
        if code in {"40001", "40P01", "55P03"}:
            return AtomicMergeOutcome.STALE_SNAPSHOT
        if code == "PT409":
            raise AppError(
                code="cart.merge_conflict",
                message=hint or "Cart merge conflict",
                http_status=409,
                details={"retry": False},
            ) from exc
        raise AppError(
            code="cart.merge_failed",
            message=hint or "Cart merge failed",
            http_status=500,
            details={"retry": True},
        ) from exc

    data = getattr(response, "data", None)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]
    if not isinstance(data, dict):
        raise AppError(
            code="cart.merge_failed",
            message="Cart merge returned no outcome",
            http_status=500,
            details={"retry": True},
        )

    try:
        return AtomicMergeOutcome(str(data.get("outcome")))
    except ValueError as exc:
        raise AppError(
            code="cart.merge_failed",
            message="Cart merge returned an invalid outcome",
            http_status=500,
            details={"retry": True},
        ) from exc
