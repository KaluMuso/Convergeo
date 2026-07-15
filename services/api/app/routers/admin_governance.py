"""Admin vendor-governance surface (F11) — read-only cancel-rate watchlist.

Surfaces the cancel-rate governance signal (``services.moderation.vendor_governance``)
to admins so a rising cancel-rate is visible *before* it silently costs the D9
preferred badge. Read-only: the admin acts via the existing manual moderation
controls (``/flags/{id}/warn-vendor``, ``/flags/{id}/escalate-suspend``). No vendor
state is mutated here — consistent with the v1 "manual admin moderation" stance.

Mounted under ``admin_router`` (``/admin`` prefix, ``require_role("admin")``), so the
GET is admin-gated automatically and classified ROLE/admin by the authz matrix.
Being non-mutating it needs no rate-limit policy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from app.deps import get_supabase_client
from app.routers.admin_base import router as admin_router
from app.services.moderation.vendor_governance import (
    CRITICAL_CANCEL_RATE,
    MIN_ORDERS_FOR_SIGNAL,
    WARN_CANCEL_RATE,
    Severity,
    VendorGovernanceSignal,
    scan_vendor_governance,
)
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

governance_router = APIRouter(prefix="/governance", tags=["admin-governance"])

# The query filter is the *minimum* severity to include; "all" also surfaces
# healthy vendors (severity ok) for a full overview.
SeverityFilter = Literal["all", "warn", "critical"]
_FILTER_TO_MIN_SEVERITY: dict[SeverityFilter, Severity] = {
    "all": "ok",
    "warn": "warn",
    "critical": "critical",
}


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class VendorGovernanceItem(BaseModel):
    vendor_id: UUID
    display_name: str | None = None
    slug: str | None = None
    status: str
    total_orders: int
    cancelled_orders: int
    cancel_rate: float
    severity: Severity


class VendorGovernanceResponse(BaseModel):
    severity_filter: SeverityFilter
    warn_threshold: float
    critical_threshold: float
    min_orders: int
    generated_at: datetime
    vendors: list[VendorGovernanceItem]


def _to_item(signal: VendorGovernanceSignal) -> VendorGovernanceItem:
    return VendorGovernanceItem(
        vendor_id=UUID(signal.vendor_id),
        display_name=signal.display_name,
        slug=signal.slug,
        status=signal.status,
        total_orders=signal.total_orders,
        cancelled_orders=signal.cancelled_orders,
        cancel_rate=signal.cancel_rate,
        severity=signal.severity,
    )


@governance_router.get("/vendors", response_model=VendorGovernanceResponse)
async def list_vendor_governance(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    severity: Annotated[SeverityFilter, Query()] = "warn",
) -> VendorGovernanceResponse:
    signals = scan_vendor_governance(
        service_client,
        min_severity=_FILTER_TO_MIN_SEVERITY[severity],
    )
    return VendorGovernanceResponse(
        severity_filter=severity,
        warn_threshold=WARN_CANCEL_RATE,
        critical_threshold=CRITICAL_CANCEL_RATE,
        min_orders=MIN_ORDERS_FOR_SIGNAL,
        generated_at=datetime.now(UTC),
        vendors=[_to_item(signal) for signal in signals],
    )


admin_router.include_router(governance_router)
