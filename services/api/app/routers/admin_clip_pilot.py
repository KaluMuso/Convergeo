"""Admin control for the Clips pilot allowlist.

Mounted on ``admin_base`` (``require_role("admin")`` + the audited route class),
under ``/admin/clip-pilot``. A separate prefix rather than ``/admin/clips/pilot``
because ``/admin/clips/{clip_id}`` would otherwise swallow the path.

* ``GET``    ``/admin/clip-pilot``                     — gate state + allowlist
* ``POST``   ``/admin/clip-pilot/vendors``             — add a vendor (idempotent)
* ``DELETE`` ``/admin/clip-pilot/vendors/{vendor_id}`` — remove a vendor

Every effective change writes one ``audit_log`` row with before/after. A replay
(adding a vendor who is already in, removing one who is not) changes nothing and
writes nothing.

The enforcement switch itself (``platform_config.clip_pilot_allowlist_enforced``)
is deliberately **not** editable here: it is read-only on this page and changed in
the existing admin config screen, whose own audit trigger records the actor.
Ending a pilot is a founder decision, not a button next to the vendor list.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Final, Protocol

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.schemas.base import StrictModel
from app.services.clips import flags, pilot
from fastapi import APIRouter, Depends
from pydantic import Field

pilot_router = APIRouter(prefix="/clip-pilot", tags=["admin-clips"])

VENDORS_TABLE: Final = "vendors"
MAX_NOTE_LEN: Final = 280


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class PilotVendorOut(StrictModel):
    vendor_id: str
    vendor_name: str | None
    vendor_status: str | None
    kyc_tier: int | None
    note: str | None
    added_by: str | None
    created_at: str | None


class PilotStateResponse(StrictModel):
    clips_enabled: bool
    comments_flag_enabled: bool
    allowlist_enforced: bool
    max_vendors: int
    vendors: list[PilotVendorOut]


class PilotAddRequest(StrictModel):
    vendor_id: str = Field(min_length=36, max_length=36)
    note: str | None = Field(default=None, max_length=MAX_NOTE_LEN)


class PilotChangeResponse(StrictModel):
    vendor_id: str
    allowlisted: bool
    changed: bool


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _valid_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="validation_error",
            message="vendor_id must be a UUID",
            http_status=422,
            details={"field": "vendor_id"},
        ) from exc


def _pilot_rows(service_client: ServiceRoleClient) -> list[dict[str, Any]]:
    # Read directly (not via pilot.allowlisted_vendor_ids) so an admin sees a read
    # failure as an error, not as a silently empty list.
    return _rows(
        service_client.client.table(pilot.PILOT_TABLE)
        .select("vendor_id, note, added_by, created_at")
        .order("created_at")
        .limit(pilot.MAX_PILOT_VENDORS)
        .execute()
    )


def _pilot_row(service_client: ServiceRoleClient, vendor_id: str) -> dict[str, Any] | None:
    rows = _rows(
        service_client.client.table(pilot.PILOT_TABLE)
        .select("vendor_id, note, added_by, created_at")
        .eq("vendor_id", vendor_id)
        .maybe_single()
        .execute()
    )
    return rows[0] if rows else None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@pilot_router.get("", response_model=PilotStateResponse)
async def get_clip_pilot(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PilotStateResponse:
    rows = _pilot_rows(service_client)
    vendor_ids = [str(row["vendor_id"]) for row in rows if row.get("vendor_id")]
    vendors: dict[str, dict[str, Any]] = {}
    if vendor_ids:
        vendors = {
            str(v.get("id")): v
            for v in _rows(
                service_client.client.table(VENDORS_TABLE)
                .select("id, display_name, status, kyc_tier")
                .in_("id", vendor_ids)
                .execute()
            )
        }
    items = []
    for row in rows:
        vid = str(row.get("vendor_id") or "")
        vendor = vendors.get(vid, {})
        items.append(
            PilotVendorOut(
                vendor_id=vid,
                vendor_name=(str(vendor["display_name"]) if vendor.get("display_name") else None),
                vendor_status=(str(vendor["status"]) if vendor.get("status") else None),
                kyc_tier=_int_or_none(vendor.get("kyc_tier")),
                note=(str(row["note"]) if row.get("note") else None),
                added_by=(str(row["added_by"]) if row.get("added_by") else None),
                created_at=(str(row["created_at"]) if row.get("created_at") else None),
            )
        )
    return PilotStateResponse(
        clips_enabled=flags.clips_enabled(service_client),
        comments_flag_enabled=flags.comments_enabled(service_client),
        allowlist_enforced=pilot.allowlist_enforced(service_client),
        max_vendors=pilot.MAX_PILOT_VENDORS,
        vendors=items,
    )


@pilot_router.post("/vendors", response_model=PilotChangeResponse)
async def add_clip_pilot_vendor(
    body: PilotAddRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> PilotChangeResponse:
    """Allowlist a vendor. The vendor must exist and be active."""
    vendor_id = _valid_uuid(body.vendor_id)
    vendor_rows = _rows(
        service_client.client.table(VENDORS_TABLE)
        .select("id, status")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    if not vendor_rows:
        raise AppError(
            code="not_found",
            message="Vendor not found",
            http_status=404,
            details={"vendor_id": vendor_id},
        )
    if str(vendor_rows[0].get("status")) != "active":
        raise AppError(
            code="vendor_not_active",
            message="Only an active vendor can join the Clips pilot",
            http_status=422,
            details={"vendor_id": vendor_id, "message_key": "admin.clips.pilot.errors.notActive"},
        )

    if _pilot_row(service_client, vendor_id) is not None:
        return PilotChangeResponse(vendor_id=vendor_id, allowlisted=True, changed=False)

    if len(_pilot_rows(service_client)) >= pilot.MAX_PILOT_VENDORS:
        raise AppError(
            code="clip_pilot_full",
            message="The Clips pilot allowlist is full",
            http_status=422,
            details={
                "max_vendors": pilot.MAX_PILOT_VENDORS,
                "message_key": "admin.clips.pilot.errors.full",
            },
        )

    note = body.note.strip() if body.note else None
    service_client.client.table(pilot.PILOT_TABLE).insert(
        {"vendor_id": vendor_id, "note": note or None, "added_by": current_user.id}
    ).execute()
    recorder.record(
        action="admin.clips.pilot_add",
        entity_type="vendor",
        entity_id=vendor_id,
        before={"clip_pilot": False},
        after={"clip_pilot": True, "note": note or None},
    )
    return PilotChangeResponse(vendor_id=vendor_id, allowlisted=True, changed=True)


@pilot_router.delete("/vendors/{vendor_id}", response_model=PilotChangeResponse)
async def remove_clip_pilot_vendor(
    vendor_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> PilotChangeResponse:
    """Remove a vendor. Their published clips stop being served immediately;
    nothing is deleted, so re-adding them restores the clips as they were."""
    vendor_id = _valid_uuid(vendor_id)
    existing = _pilot_row(service_client, vendor_id)
    if existing is None:
        return PilotChangeResponse(vendor_id=vendor_id, allowlisted=False, changed=False)

    service_client.client.table(pilot.PILOT_TABLE).delete().eq("vendor_id", vendor_id).execute()
    recorder.record(
        action="admin.clips.pilot_remove",
        entity_type="vendor",
        entity_id=vendor_id,
        before={"clip_pilot": True, "note": existing.get("note")},
        after={"clip_pilot": False},
    )
    return PilotChangeResponse(vendor_id=vendor_id, allowlisted=False, changed=True)


admin_router.include_router(pilot_router)
