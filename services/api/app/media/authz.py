from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request

from app.core.auth import CurrentUser, get_current_user, get_request_jwt_claims
from app.errors import AppError


@dataclass(frozen=True, slots=True)
class VendorScope:
    vendor_id: str


def _extract_vendor_id(claims: dict[str, Any]) -> str | None:
    for key in ("vendor_id",):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for metadata_key in ("app_metadata", "user_metadata"):
        metadata = claims.get(metadata_key)
        if isinstance(metadata, dict):
            vendor_id = metadata.get("vendor_id")
            if isinstance(vendor_id, str) and vendor_id.strip():
                return vendor_id.strip()

    subject = claims.get("sub")
    if isinstance(subject, str) and subject.strip():
        return subject.strip()

    return None


async def require_vendor_scope(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> VendorScope:
    """Resolve the authenticated vendor scope for media signing.

    TODO(M04-P02): verify vendor role + ownership against the vendors table before
    issuing upload signatures. JWT verification is centralized in app.core.auth;
    vendor_id is still derived from JWT claims (vendor_id metadata when present,
    otherwise sub).
    """
    _ = current_user
    claims = get_request_jwt_claims(request)
    vendor_id = _extract_vendor_id(claims)
    if not vendor_id:
        raise AppError(
            code="forbidden",
            message="Authenticated caller is missing vendor scope",
            http_status=403,
        )

    return VendorScope(vendor_id=vendor_id)
