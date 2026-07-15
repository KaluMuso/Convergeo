"""Shared B2B business-buyer access resolver.

Single source of truth for "is this request allowed to see/buy wholesale?" so the
same rule is enforced identically at every wholesale entry point — discovery
(``/catalog/listings?wholesale=true``), cart mutation, and checkout. Guests and
consumers are never eligible; only a user with a ``verified`` ``business_buyers``
row is (see migration 0038 / ``public.is_verified_business``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.settings import get_settings
from fastapi import Depends, Request

VALID_STATUSES = ("pending", "verified", "rejected", "suspended")


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class BusinessAccess:
    """Resolved wholesale eligibility for the current request."""

    user_id: str | None
    status: str | None  # None = no application on file; else one of VALID_STATUSES
    eligible: bool  # True only for a verified business buyer


ANON_ACCESS = BusinessAccess(user_id=None, status=None, eligible=False)


def _row_from_response(response: object | None) -> dict[str, Any] | None:
    if response is None:
        return None
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def fetch_business_buyer(client: Any, user_id: str) -> dict[str, Any] | None:
    """Return the user's business_buyers row (any status), or None."""
    response = (
        client.table("business_buyers")
        .select(
            "id, user_id, legal_name, registration_no, tpin, status, "
            "reviewer_notes, verified_at, created_at, updated_at"
        )
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return _row_from_response(response)


def resolve_business_eligibility(user_id: str, service: ServiceRoleClient) -> BusinessAccess:
    """Resolve eligibility for a known user id using the service-role client."""
    row = fetch_business_buyer(service.client, user_id)
    if row is None:
        return BusinessAccess(user_id=user_id, status=None, eligible=False)
    status = str(row.get("status") or "") or None
    return BusinessAccess(
        user_id=user_id,
        status=status,
        eligible=status == "verified",
    )


async def _optional_current_user(request: Request) -> CurrentUser | None:
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(request, get_settings())
    except AppError:
        return None


async def get_business_access(
    request: Request,
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BusinessAccess:
    """FastAPI dependency: eligibility for the current request (guests → not eligible)."""
    user = await _optional_current_user(request)
    if user is None:
        return ANON_ACCESS
    return resolve_business_eligibility(user.id, service)


def require_wholesale_access(access: BusinessAccess) -> None:
    """Raise 403 unless the caller is a verified business buyer."""
    if access.eligible:
        return
    raise AppError(
        code="business.wholesale_forbidden",
        message="Wholesale is available to verified businesses only",
        http_status=403,
        details={
            "status": access.status,
            "message_key": "supplies.gate.forbidden",
        },
    )
