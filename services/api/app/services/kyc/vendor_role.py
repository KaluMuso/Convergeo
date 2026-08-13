"""Grant ``user_roles.vendor`` at the approved-vendor boundary.

Portal identity (``user_roles.vendor``) is distinct from commercial capability
(``vendors.status`` + KYC eligibility). This module grants the identity role
only after a Vendor is already ``active``. It never inserts from a browser
client, never special-cases an email, and never grants on signup, draft,
onboarding, KYC submit, or pending KYC.

Suspend / reject / revoke must not strip the role: a suspended Vendor still
needs portal access for remediation, while listing/payout/wholesale caps
continue to enforce ``vendors.status``.
"""

from __future__ import annotations

from typing import Any, Protocol, cast

from app.errors import AppError


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return cast(dict[str, Any], first)
    return None


def _load_active_owner(
    service_client: ServiceRoleClient,
    vendor_id: str,
) -> tuple[str, str]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Vendor not found", http_status=404)
    owner = str(row.get("owner_user_id") or "")
    status = str(row.get("status") or "")
    if not owner:
        raise AppError(
            code="vendor_role_missing_owner",
            message="Vendor has no owner_user_id",
            http_status=500,
        )
    return owner, status


def _existing_vendor_role(
    service_client: ServiceRoleClient,
    user_id: str,
) -> dict[str, Any] | None:
    response = (
        service_client.client.table("user_roles")
        .select("user_id, role")
        .eq("user_id", user_id)
        .eq("role", "vendor")
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def ensure_vendor_owner_role(
    service_client: ServiceRoleClient,
    *,
    owner_user_id: str,
    vendor_id: str,
) -> dict[str, Any]:
    """Idempotently grant ``vendor`` to the owner of an already-active Vendor.

    The owner id must match ``vendors.owner_user_id``. Callers must not pass a
    different user (wrong owner / unrelated account). The Vendor must already
    be ``active`` so draft/pending/rejected paths cannot obtain the role.
    """
    claimed_owner = owner_user_id.strip()
    if not claimed_owner:
        raise AppError(
            code="vendor_role_missing_owner",
            message="owner_user_id is required",
            http_status=500,
        )

    db_owner, status = _load_active_owner(service_client, vendor_id)
    if db_owner != claimed_owner:
        raise AppError(
            code="vendor_role_owner_mismatch",
            message="Vendor role can only be granted to vendors.owner_user_id",
            http_status=409,
            details={"vendor_id": vendor_id},
        )
    if status != "active":
        raise AppError(
            code="vendor_role_vendor_not_active",
            message="Vendor role is granted only after the vendor is active",
            http_status=409,
            details={"vendor_id": vendor_id, "vendor_status": status},
        )

    existing = _existing_vendor_role(service_client, db_owner)
    if existing is not None:
        return {
            "user_id": db_owner,
            "role": "vendor",
            "outcome": "already_present",
            "vendor_id": vendor_id,
        }

    try:
        response = (
            service_client.client.table("user_roles")
            .upsert(
                {"user_id": db_owner, "role": "vendor"},
                on_conflict="user_id,role",
            )
            .execute()
        )
    except Exception as exc:
        raise AppError(
            code="vendor_role_grant_failed",
            message="Failed to grant vendor role to the approved vendor owner",
            http_status=500,
            details={"vendor_id": vendor_id, "owner_user_id": db_owner},
        ) from exc

    row = _single_row(response)
    if row is None:
        rows = _rows(response)
        row = rows[0] if rows else None
    if row is None:
        raced = _existing_vendor_role(service_client, db_owner)
        if raced is not None:
            return {
                "user_id": db_owner,
                "role": "vendor",
                "outcome": "already_present",
                "vendor_id": vendor_id,
            }
        raise AppError(
            code="vendor_role_grant_failed",
            message="Vendor role upsert returned no row",
            http_status=500,
            details={"vendor_id": vendor_id, "owner_user_id": db_owner},
        )

    return {
        "user_id": str(row.get("user_id") or db_owner),
        "role": "vendor",
        "outcome": "granted",
        "vendor_id": vendor_id,
    }
