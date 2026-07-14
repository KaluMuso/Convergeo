"""Persistence helpers for the business_buyers verification lifecycle.

Writes go through the service-role client (the ``business_buyers`` guard trigger
reserves status/verified_at for service_role + admins). The router enforces which
transitions a given actor may request.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.errors import AppError
from app.services.business.access import _row_from_response, fetch_business_buyer


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# Statuses from which a buyer may (re)submit an application.
REAPPLY_STATUSES = frozenset({"pending", "rejected"})


def upsert_application(
    service: ServiceRoleClient,
    *,
    user_id: str,
    legal_name: str,
    registration_no: str,
    tpin: str | None,
) -> dict[str, Any]:
    """Create or refresh a buyer's application, pinning it back to ``pending``.

    Rejected applications may be resubmitted. Verified/suspended buyers cannot
    self-mutate their standing and get a 409.
    """
    existing = fetch_business_buyer(service.client, user_id)
    payload: dict[str, Any] = {
        "legal_name": legal_name,
        "registration_no": registration_no,
        "tpin": tpin,
    }

    if existing is None:
        insert_row = {**payload, "user_id": user_id, "status": "pending"}
        response = service.client.table("business_buyers").insert(insert_row).execute()
        row = _row_from_response(response)
        return row if row is not None else {**insert_row}

    status = str(existing.get("status") or "")
    if status not in REAPPLY_STATUSES:
        raise AppError(
            code="business.already_decided",
            message="This business account cannot be resubmitted",
            http_status=409,
            details={"status": status, "message_key": "account.business.errors.alreadyDecided"},
        )

    update_row = {
        **payload,
        "status": "pending",
        "reviewer_notes": None,
        "verified_at": None,
    }
    response = (
        service.client.table("business_buyers")
        .update(update_row)
        .eq("user_id", user_id)
        .execute()
    )
    row = _row_from_response(response)
    return row if row is not None else {**existing, **update_row}


def load_by_id(service: ServiceRoleClient, buyer_id: str) -> dict[str, Any]:
    response = (
        service.client.table("business_buyers")
        .select(
            "id, user_id, legal_name, registration_no, tpin, status, "
            "reviewer_notes, verified_at, created_at, updated_at"
        )
        .eq("id", buyer_id)
        .maybe_single()
        .execute()
    )
    row = _row_from_response(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Business buyer not found",
            http_status=404,
            details={"buyer_id": buyer_id},
        )
    return row


def set_decision(
    service: ServiceRoleClient,
    *,
    buyer_id: str,
    status: str,
    verified_at: str | None,
    reviewer_notes: str | None,
) -> dict[str, Any]:
    """Admin decision write (verify / reject / suspend)."""
    update_row: dict[str, Any] = {
        "status": status,
        "verified_at": verified_at,
        "reviewer_notes": reviewer_notes,
    }
    response = (
        service.client.table("business_buyers")
        .update(update_row)
        .eq("id", buyer_id)
        .execute()
    )
    row = _row_from_response(response)
    if row is None:
        return {**load_by_id(service, buyer_id), **update_row}
    return row
