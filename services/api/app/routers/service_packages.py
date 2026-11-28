"""Vendor management of service packages (open, ordered list; cap 10 active).

* ``GET    /vendor/services/{service_id}/packages``                       — all, incl. archived
* ``POST   /vendor/services/{service_id}/packages``                       — create one (cap 10)
* ``PUT    /vendor/services/{service_id}/packages/{package_id}``          — update one
* ``DELETE /vendor/services/{service_id}/packages/{package_id}``          — remove one (audited)
* ``POST   /vendor/services/{service_id}/packages/reorder``               — set display order
* ``POST   /vendor/services/{service_id}/packages/{package_id}/archive``  — hide one (audited)

Ownership is the existing service ownership check (a non-owner gets the same 404 as
a missing service). Package copy runs through the same prohibited-content screen
as service listings (SP-9). Status only moves through the guarded, audited
``state.transition_status``; saving an archived package re-activates it that way
(and counts against the cap of 10 active packages: ``package_limit_reached``).

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
from app.schemas.service_archetypes import (
    attribute_text,
    effective_archetype,
    validate_offer_attributes,
)
from app.schemas.service_packages import (
    PackageReorderRequest,
    PackageUpsertRequest,
    VendorPackageListResponse,
    VendorPackageOut,
    to_vendor,
)
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.moderation.prohibited import screen_listing
from app.services.service_packages import state
from fastapi import APIRouter, Depends, Response

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
    text = " ".join(
        part
        for part in [body.description or "", *body.includes, attribute_text(body.attributes)]
        if part
    )
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


def _package_not_found() -> AppError:
    return AppError(
        code="not_found",
        message="Package not found",
        http_status=404,
        details={"message_key": "services.vendor.packages.errors.notFound"},
    )


def _load_owned_package(
    service_client: ServiceRoleClient, *, service_id: str, package_id: str
) -> dict[str, Any]:
    if not UUID_RE.match(package_id):
        raise _package_not_found()
    existing = state.load_package(service_client, service_id=service_id, package_id=package_id)
    if existing is None:
        raise _package_not_found()
    return existing


def _fields(body: PackageUpsertRequest, service: dict[str, Any]) -> dict[str, Any]:
    """Row fields; attributes are validated against the service's effective archetype."""
    return {
        "attributes": validate_offer_attributes(effective_archetype(service), body.attributes),
        "name": body.name,
        "description": body.description,
        "price_ngwee": body.price_ngwee,
        "delivery_days": body.delivery_days,
        "revisions": body.revisions,
        "includes": body.includes,
    }


def _audit(
    service_client: ServiceRoleClient,
    *,
    action: str,
    package_id: str,
    actor_id: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    written = state.rows(
        service_client.client.table("audit_log")
        .insert(
            {
                "actor": actor_id,
                "action": action,
                "entity_type": "service_package",
                "entity_id": package_id,
                "before": before,
                "after": after,
            }
        )
        .execute()
    )
    if not written:
        raise AppError(
            code="audit_write_failed",
            message="Failed to persist service package audit_log row",
            http_status=500,
        )


@router.get("/vendor/services/{service_id}/packages", response_model=VendorPackageListResponse)
def list_service_packages(
    service_id: str,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorPackageListResponse:
    _vendor, service = _assert_vendor_owns_service(service_client, user.id, service_id)
    found = state.list_for_service(service_client, str(service["id"]))
    return VendorPackageListResponse(
        service_id=str(service["id"]), items=[to_vendor(row) for row in found]
    )


@router.post("/vendor/services/{service_id}/packages", response_model=VendorPackageOut)
def create_service_package(
    service_id: str,
    body: PackageUpsertRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorPackageOut:
    _rate_limit(service_client, user.id)
    vendor, service = _assert_vendor_owns_service(service_client, user.id, service_id)
    _screen(body, service.get("category"))

    siblings = state.list_for_service(service_client, str(service["id"]))
    state.assert_below_cap(state.count_active(siblings))
    next_order = min(
        state.SORT_ORDER_MAX,
        max((int(r.get("sort_order") or 0) for r in siblings), default=-1) + 1,
    )
    created = state.rows(
        service_client.client.table(state.TABLE)
        .insert(
            {
                "service_id": str(service["id"]),
                "vendor_id": str(vendor["id"]),
                "status": state.ACTIVE,
                "sort_order": next_order,
                **_fields(body, service),
            }
        )
        .execute()
    )
    if not created:
        raise AppError(code="internal_error", message="Failed to create package", http_status=500)
    return to_vendor(created[0])


@router.put("/vendor/services/{service_id}/packages/{package_id}", response_model=VendorPackageOut)
def update_service_package(
    service_id: str,
    package_id: str,
    body: PackageUpsertRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorPackageOut:
    _rate_limit(service_client, user.id)
    _vendor, service = _assert_vendor_owns_service(service_client, user.id, service_id)
    _screen(body, service.get("category"))
    existing = _load_owned_package(
        service_client, service_id=str(service["id"]), package_id=package_id
    )
    if str(existing.get("status")) == state.ARCHIVED:
        # Saving an archived package re-activates it, which must respect the cap.
        siblings = state.list_for_service(service_client, str(service["id"]))
        state.assert_below_cap(state.count_active(siblings))

    fields = _fields(body, service)
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
    "/vendor/services/{service_id}/packages/reorder", response_model=VendorPackageListResponse
)
def reorder_service_packages(
    service_id: str,
    body: PackageReorderRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorPackageListResponse:
    _rate_limit(service_client, user.id)
    _vendor, service = _assert_vendor_owns_service(service_client, user.id, service_id)
    found = state.list_for_service(service_client, str(service["id"]))
    active_ids = {str(r["id"]) for r in found if str(r.get("status")) == state.ACTIVE}
    if set(body.ids) != active_ids:
        raise AppError(
            code="package_order_mismatch",
            message="The order must list every active package of the service exactly once",
            http_status=409,
            details={"message_key": "services.vendor.packages.errors.orderMismatch"},
        )
    for index, package_id in enumerate(body.ids):
        state.rows(
            service_client.client.table(state.TABLE)
            .update({"sort_order": index})
            .eq("id", package_id)
            .eq("service_id", str(service["id"]))
            .execute()
        )
    return VendorPackageListResponse(
        service_id=str(service["id"]),
        items=[
            to_vendor(row) for row in state.list_for_service(service_client, str(service["id"]))
        ],
    )


@router.delete("/vendor/services/{service_id}/packages/{package_id}", status_code=204)
def delete_service_package(
    service_id: str,
    package_id: str,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> Response:
    """Remove a package. RFQ threads keep their immutable snapshot (FK is SET NULL)."""
    _rate_limit(service_client, user.id)
    _vendor, service = _assert_vendor_owns_service(service_client, user.id, service_id)
    existing = _load_owned_package(
        service_client, service_id=str(service["id"]), package_id=package_id
    )
    service_client.client.table(state.TABLE).delete().eq("id", str(existing["id"])).execute()
    _audit(
        service_client,
        action="service_package.deleted",
        package_id=str(existing["id"]),
        actor_id=user.id,
        before={"status": existing.get("status"), "name": existing.get("name")},
        after={"deleted": True},
    )
    return Response(status_code=204)


@router.post(
    "/vendor/services/{service_id}/packages/{package_id}/archive",
    response_model=VendorPackageOut,
)
def archive_service_package(
    service_id: str,
    package_id: str,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorPackageOut:
    _rate_limit(service_client, user.id)
    _vendor, service = _assert_vendor_owns_service(service_client, user.id, service_id)
    existing = _load_owned_package(
        service_client, service_id=str(service["id"]), package_id=package_id
    )
    row = state.transition_status(
        service_client,
        package=existing,
        to_status=state.ARCHIVED,
        actor_id=user.id,
        reason="vendor_archived",
    )
    return to_vendor(row)
