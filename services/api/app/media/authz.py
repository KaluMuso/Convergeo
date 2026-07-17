from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from fastapi import Depends

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError


@dataclass(frozen=True, slots=True)
class VendorScope:
    vendor_id: str


class _ServiceRoleClient(Protocol):
    """Structural type for the service-role client's postgrest surface.

    Declared locally (not imported from ``app.supabase_client``) so this module
    stays outside the service-role import allowlist — the client is provided by
    the ``get_supabase_client`` dependency, which owns that import.
    """

    @property
    def client(self) -> Any: ...


def _resolve_owned_vendor_id(
    service_client: _ServiceRoleClient,
    owner_user_id: str,
) -> str | None:
    """Return the id of the vendor owned by ``owner_user_id``, or None if none.

    Ownership is the ``vendors.owner_user_id`` column — the single source of
    truth used across the vendor surface (kyc, profile, listings, returns).
    """
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    data = getattr(response, "data", None)
    row: dict[str, Any] | None = None
    if isinstance(data, dict):
        row = data
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        row = data[0]

    if row is None:
        return None
    vendor_id = row.get("id")
    if isinstance(vendor_id, str) and vendor_id.strip():
        return vendor_id.strip()
    return None


async def require_vendor_scope(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorScope:
    """Resolve the caller's vendor scope from DB ownership — never from JWT claims.

    The vendor is the row whose ``owner_user_id`` is the authenticated user id,
    matching the rest of the vendor surface (``require_vendor_owner`` in kyc /
    vendor_profile / listings) and CLAUDE.md #3 ("roles / ownership are
    DB-sourced, never claim-trusted").

    Resolves the M04-P02 TODO: the prior implementation derived ``vendor_id`` from
    JWT metadata (client-writable ``user_metadata``) and fell back to ``sub`` — a
    caller could set ``user_metadata.vendor_id`` to another vendor's id and obtain
    upload signatures scoped to that vendor's listings/KYC folder. Both
    ``/media/sign`` and ``/media/kyc-doc/sign`` pin the upload path to
    ``scope.vendor_id``, so this is the authorization boundary for those uploads.
    """
    vendor_id = _resolve_owned_vendor_id(service_client, current_user.id)
    if vendor_id is None:
        raise AppError(
            code="forbidden",
            message="Authenticated caller does not own a vendor profile",
            http_status=403,
        )
    return VendorScope(vendor_id=vendor_id)
