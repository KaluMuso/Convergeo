"""Vendor management of service packages (Basic / Standard / Premium).

* ``GET  /vendor/services/{service_id}/packages``                — all tiers, incl. archived
* ``PUT  /vendor/services/{service_id}/packages/{tier}``         — create or update one tier
* ``POST /vendor/services/{service_id}/packages/{tier}/archive`` — hide a tier (audited)

Ownership is the existing service ownership check (a non-owner gets the same 404 as
a missing service). Package copy runs through the same prohibited-content screen
as service listings (SP-9). Status only moves through the guarded, audited
``state.transition_status``; saving an archived tier re-activates it that way.

Design and product decisions: ``docs/plan/service-packages.md``.
"""

from __future__ import annotations

from typing import Annotated, Any

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import STANDARD_WRITE
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.services_listings import UUID_RE
from app.routers.services_listings import _assert_vendor_owns_service as _owns_service
from app.schemas.service_packages import (
    PackageUpsertRequest,
    Tier,
    VendorPackageListResponse,
    VendorPackageOut,
    to_vendor,
)
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.moderation.prohibited import screen_listing
from app.services.service_packages import state
from fastapi import APIRouter, Depends

router = APIRouter(tags=["service-packages"])


def _assert_vendor_owns_service(
    service_client: ServiceRoleClient, user_id: str, service_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Same 404 for a malformed id, a missing service and someone else's service."""
    if not UUID_RE.match(service_id):
        raise AppError(
            code="not_found",
            message="Service not found",
            http_status=404,
            details={"message_key": "services.errors.not_found"},
        )
    return _owns_service(service_client, user_id, service_id)


def _rate_limit(service_client: ServiceRoleClient, user_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=STANDARD_WRITE.scope,
        key=f"service_packages:{user_id}",
        window=STANDARD_WRITE.window,
        limit=STANDARD_WRITE.limit,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="services.vendor.packages.errors.rateLimited",
            message="Too many package changes",
        )


def _screen(body: PackageUpsertRequest, category: Any) -> None:
    text = " ".join(part for part in [body.description or "", *body.includes] if part)
    verdict = screen_listing(title=body.name, description=text or None, category=category)
    if not verdict.allowed:
        raise AppError(
            code="prohibited_listing",
            message="Package contains a prohibited category or keyword",
            http_status=422,
            details={
                "message_key": "services.vendor.packages.errors.prohibited",
                "reason": verdict.reason,
                "matched": verdict.matched,
            },
        )


@router.get("/vendor/services/{service_id}/packages", response_model=VendorPackageListResponse)
def list_service_packages(
    service_id: str,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorPackageListResponse:
    _vendor, service = _assert_vendor_owns_service(service_client, user.id, service_id)
    found = state.rows(
        service_client.client.table(state.TABLE)
        .select(state.PACKAGE_COLUMNS)
        .eq("service_id", str(service["id"]))
        .execute()
    )
    return VendorPackageListResponse(
        service_id=str(service["id"]),
        items=[to_vendor(row) for row in state.sort_by_tier(found)],
    )


@router.put("/vendor/services/{service_id}/packages/{tier}", response_model=VendorPackageOut)
def upsert_service_package(
    service_id: str,
    tier: Tier,
    body: PackageUpsertRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorPackageOut:
    _rate_limit(service_client, user.id)
    vendor, service = _assert_vendor_owns_service(service_client, user.id, service_id)
    _screen(body, service.get("category"))

    fields = {
        "name": body.name,
        "description": body.description,
        "price_ngwee": body.price_ngwee,
        "delivery_days": body.delivery_days,
        "revisions": body.revisions,
        "includes": body.includes,
    }
    existing = state.load_package(service_client, service_id=str(service["id"]), tier=tier)

    if existing is None:
        created = state.rows(
            service_client.client.table(state.TABLE)
            .insert(
                {
                    "service_id": str(service["id"]),
                    "vendor_id": str(vendor["id"]),
                    "tier": tier,
                    "status": state.ACTIVE,
                    **fields,
                }
            )
            .execute()
        )
        if not created:
            raise AppError(
                code="internal_error", message="Failed to create package", http_status=500
            )
        return to_vendor(created[0])

    updated = state.rows(
        service_client.client.table(state.TABLE)
        .update(fields)
        .eq("id", str(existing["id"]))
        .execute()
    )
    row = updated[0] if updated else {**existing, **fields}
    if str(row.get("status")) == state.ARCHIVED:
        row = state.transition_status(
            service_client,
            package=row,
            to_status=state.ACTIVE,
            actor_id=user.id,
            reason="vendor_saved",
        )
    return to_vendor(row)


@router.post(
    "/vendor/services/{service_id}/packages/{tier}/archive",
    response_model=VendorPackageOut,
)
def archive_service_package(
    service_id: str,
    tier: Tier,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorPackageOut:
    _rate_limit(service_client, user.id)
    _vendor, service = _assert_vendor_owns_service(service_client, user.id, service_id)
    existing = state.load_package(service_client, service_id=str(service["id"]), tier=tier)
    if existing is None:
        raise AppError(
            code="not_found",
            message="Package not found",
            http_status=404,
            details={"message_key": "services.vendor.packages.errors.notFound"},
        )
    row = state.transition_status(
        service_client,
        package=existing,
        to_status=state.ARCHIVED,
        actor_id=user.id,
        reason="vendor_archived",
    )
    return to_vendor(row)
