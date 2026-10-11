"""Intake-only canonical validation and insert in one PostgREST transaction."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.errors import AppError
from app.services.intake.handoff import DraftNotSubmittable
from app.services.kyc.state_machine import ServiceRoleClient
from postgrest.exceptions import APIError

RPC_NAME = "insert_intake_class_a_listing"
_REASONS = {
    "intake_canonical_unavailable": "canonicalUnavailable",
    "intake_canonical_class": "unsupportedClass",
    "intake_canonical_units": "unsupported_mapping",
    "intake_canonical_category": "canonicalCategory",
}


def insert_intake_class_a_listing(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    product_id: str,
    expected_category_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Use the caller's client; failures must never use another insert/DSN."""
    try:
        response = service_client.client.rpc(
            RPC_NAME,
            {
                "p_vendor_id": vendor_id,
                "p_product_id": product_id,
                "p_expected_category_id": expected_category_id,
                "p_listing_payload": payload,
            },
        ).execute()
    except APIError as exc:
        reason = _REASONS.get(str(getattr(exc, "message", "")))
        if getattr(exc, "code", None) == "23514" and reason:
            raise DraftNotSubmittable(reason) from exc
        raise AppError(
            code="internal_error", message="Atomic intake listing insert failed", http_status=500
        ) from exc

    rows = getattr(response, "data", None)
    if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict):
        row = rows[0]
        try:
            listing_id = str(UUID(row["id"]))
        except (KeyError, TypeError, ValueError, AttributeError):
            listing_id = None
        if listing_id and row.get("status") == "draft" and row.get("product_id") == product_id:
            return {"id": listing_id, "status": "draft", "product_id": product_id}
    raise AppError(
        code="internal_error",
        message="Atomic intake listing insert returned invalid data",
        http_status=500,
    )
