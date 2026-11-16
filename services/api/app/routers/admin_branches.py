"""Admin: branch verification queue + duplicate flags (flag ``multi_branch``).

Mounted on the shared ``/admin`` router, so ``require_admin_scope`` and the
audited route class apply: every decision writes exactly one ``audit_log`` row
(the DB transition also appends ``vendor_branch_events`` history). RBAC: mapped
to ``vendors.manage`` (same as KYC review). Every mutation: admin authz +
Pydantic validation + in-router ``ADMIN_WRITE`` rate limit keyed by the admin.

Status changes go through ``transition_vendor_branch`` (guarded state machine):
approval is refused while duplicate flags are open, physical evidence is
missing, or the business owner has no approved KYC.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import ADMIN_WRITE
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.schemas.base import StrictModel
from app.services.branches.rules import EVIDENCE_BUCKET, raise_mapped
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator

# require_role("admin"): admins, plus rbac roles holding vendors.manage; never the
# fixed moderator role (consistent with the other vendors.manage decision routes).
branches_router = APIRouter(
    prefix="/branches",
    tags=["admin-branches"],
    dependencies=[Depends(require_role("admin"))],
)

SIGNED_URL_TTL_S = 300
QueueStatus = Literal["pending_review", "info_requested", "draft", "approved", "rejected"]
FlagStatus = Literal["open", "cleared", "confirmed"]
FLAG_COLUMNS = (
    "id, vendor_id, kind, matched_vendor_id, score, details, status, resolution_note, created_at"
)
BRANCH_COLUMNS = (
    "id, business_id, owner_user_id, slug, display_name, status, branch_status, branch_kind, "
    "is_primary_branch, contact_phone, contact_email, whatsapp_msisdn, payout_msisdn, "
    "payout_rail, payout_hold_until, created_at, updated_at"
)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _limit(client: Any, actor_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=ADMIN_WRITE.scope,
        key=actor_id,
        window=ADMIN_WRITE.window,
        limit=ADMIN_WRITE.limit,
        client=client,
    )
    if not allowed:
        raise_rate_limited(retry_after=retry_after, message_key="admin.common.rateLimited")


def _not_found(entity: str) -> AppError:
    return AppError(code="not_found", message=f"{entity} not found", http_status=404)


def _load_branch(client: Any, branch_id: UUID) -> dict[str, Any]:
    rows = _rows(client.table("vendors").select(BRANCH_COLUMNS).eq("id", str(branch_id)).execute())
    if not rows:
        raise _not_found("Branch")
    return rows[0]


def _mask(msisdn: Any) -> str | None:
    if not isinstance(msisdn, str) or len(msisdn) < 6:
        return None
    return f"{msisdn[:5]}***{msisdn[-3:]}"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class QueueItem(BaseModel):
    id: str
    business_id: str | None
    business_name: str | None
    slug: str
    display_name: str
    branch_kind: str
    branch_status: str
    open_flags: int
    evidence_count: int
    submitted_at: str | None


class FlagOut(BaseModel):
    id: str
    vendor_id: str
    vendor_name: str | None = None
    kind: str
    matched_vendor_id: str | None
    matched_vendor_name: str | None = None
    score: float
    details: dict[str, Any]
    status: str
    resolution_note: str | None = None
    created_at: str | None = None


class EvidenceView(BaseModel):
    kind: str
    proof_type: str | None
    signed_url: str | None
    content_sha256: str | None


class SiblingOut(BaseModel):
    id: str
    slug: str
    display_name: str
    branch_status: str
    is_primary: bool


class EventOut(BaseModel):
    from_status: str | None
    to_status: str
    note: str | None
    created_at: str | None


class LocationOut(BaseModel):
    lat: float
    lng: float
    landmark: str
    address: str | None = None
    map_url: str | None = None


class BranchDetail(BaseModel):
    id: str
    slug: str
    display_name: str
    status: str
    branch_status: str
    branch_kind: str
    business: dict[str, Any] | None
    owner_kyc_approved: bool
    contact_phone: str | None
    contact_email: str | None
    payout_msisdn_masked: str | None
    payout_rail: str | None
    payout_on_hold: bool
    location: LocationOut | None
    plan: dict[str, Any] | None
    evidence: list[EvidenceView]
    flags: list[FlagOut]
    siblings: list[SiblingOut]
    history: list[EventOut]


def _flag_out(row: dict[str, Any], names: dict[str, str]) -> FlagOut:
    matched = row.get("matched_vendor_id")
    vendor_id = str(row.get("vendor_id"))
    raw_details = row.get("details")
    details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
    return FlagOut(
        id=str(row["id"]),
        vendor_id=vendor_id,
        vendor_name=names.get(vendor_id),
        kind=str(row.get("kind")),
        matched_vendor_id=str(matched) if matched else None,
        matched_vendor_name=names.get(str(matched)) if matched else None,
        score=float(row.get("score") or 0),
        details=details,
        status=str(row.get("status") or "open"),
        resolution_note=row.get("resolution_note"),
        created_at=str(row["created_at"]) if row.get("created_at") else None,
    )


def _vendor_names(client: Any, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = _rows(
        client.table("vendors").select("id, display_name").in_("id", sorted(ids)).execute()
    )
    return {str(r["id"]): str(r.get("display_name") or "") for r in rows}


# ---------------------------------------------------------------------------
# Queue + detail
# ---------------------------------------------------------------------------
@branches_router.get("", response_model=list[QueueItem])
async def list_branch_queue(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[QueueStatus, Query()] = "pending_review",
) -> list[QueueItem]:
    client: Any = service_client.client
    branches = _rows(
        client.table("vendors")
        .select("id, business_id, slug, display_name, branch_kind, branch_status, updated_at")
        .eq("branch_status", status)
        .eq("is_primary_branch", False)
        .order("updated_at")
        .limit(200)
        .execute()
    )
    ids = [str(b["id"]) for b in branches]
    flags: dict[str, int] = {}
    evidence: dict[str, int] = {}
    businesses: dict[str, str] = {}
    if ids:
        for row in _rows(
            client.table("vendor_branch_flags")
            .select("vendor_id")
            .in_("vendor_id", ids)
            .eq("status", "open")
            .execute()
        ):
            key = str(row.get("vendor_id"))
            flags[key] = flags.get(key, 0) + 1
        for row in _rows(
            client.table("vendor_branch_evidence")
            .select("vendor_id")
            .in_("vendor_id", ids)
            .execute()
        ):
            key = str(row.get("vendor_id"))
            evidence[key] = evidence.get(key, 0) + 1
        business_ids = sorted({str(b["business_id"]) for b in branches if b.get("business_id")})
        if business_ids:
            for row in _rows(
                client.table("vendor_businesses")
                .select("id, legal_name")
                .in_("id", business_ids)
                .execute()
            ):
                businesses[str(row["id"])] = str(row.get("legal_name") or "")
    return [
        QueueItem(
            id=str(b["id"]),
            business_id=str(b["business_id"]) if b.get("business_id") else None,
            business_name=businesses.get(str(b.get("business_id"))),
            slug=str(b.get("slug") or ""),
            display_name=str(b.get("display_name") or ""),
            branch_kind=str(b.get("branch_kind") or "physical"),
            branch_status=str(b.get("branch_status") or ""),
            open_flags=flags.get(str(b["id"]), 0),
            evidence_count=evidence.get(str(b["id"]), 0),
            submitted_at=str(b["updated_at"]) if b.get("updated_at") else None,
        )
        for b in branches
    ]


@branches_router.get("/flags", response_model=list[FlagOut])
async def list_duplicate_flags(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[FlagStatus, Query()] = "open",
) -> list[FlagOut]:
    client: Any = service_client.client
    rows = _rows(
        client.table("vendor_branch_flags")
        .select(FLAG_COLUMNS)
        .eq("status", status)
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    ids = {str(r.get("vendor_id")) for r in rows} | {
        str(r["matched_vendor_id"]) for r in rows if r.get("matched_vendor_id")
    }
    names = _vendor_names(client, ids)
    return [_flag_out(row, names) for row in rows]


def _signed_download(client: Any, path: str) -> str | None:
    try:
        result = client.storage.from_(EVIDENCE_BUCKET).create_signed_url(path, SIGNED_URL_TTL_S)
    except Exception:  # noqa: BLE001 — evidence view degrades to "unavailable"
        return None
    if isinstance(result, dict):
        value = result.get("signedURL") or result.get("signed_url") or result.get("signedUrl")
        return value if isinstance(value, str) else None
    return None


@branches_router.get("/{branch_id}", response_model=BranchDetail)
async def get_branch_detail(
    branch_id: UUID,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BranchDetail:
    client: Any = service_client.client
    branch = _load_branch(client, branch_id)
    business_id = str(branch.get("business_id") or "")
    business_rows = _rows(
        client.table("vendor_businesses")
        .select(
            "id, legal_name, registration_type, pacra_number, pacra_cert_path, "
            "pacra_verified_at, status"
        )
        .eq("id", business_id)
        .execute()
    )
    business = business_rows[0] if business_rows else None
    if business and business.get("pacra_cert_path"):
        business = {
            **business,
            "pacra_cert_url": _signed_download(client, str(business["pacra_cert_path"])),
        }
        business.pop("pacra_cert_path", None)
    siblings = _rows(
        client.table("vendors")
        .select("id, slug, display_name, branch_status, is_primary_branch")
        .eq("business_id", business_id)
        .neq("id", str(branch_id))
        .execute()
    )
    sibling_ids = [str(s["id"]) for s in siblings] + [str(branch_id)]
    kyc = _rows(
        client.table("kyc_records")
        .select("id")
        .in_("vendor_id", sibling_ids)
        .eq("status", "approved")
        .limit(1)
        .execute()
    )
    locations = _rows(
        client.table("vendor_locations")
        .select("lat, lng, landmark, address, map_url")
        .eq("vendor_id", str(branch_id))
        .limit(1)
        .execute()
    )
    plan = _rows(
        client.table("vendor_plan_assignments")
        .select("plan_key, branch_billing_role, addon_price_ngwee, billing_status")
        .eq("vendor_id", str(branch_id))
        .execute()
    )
    evidence = _rows(
        client.table("vendor_branch_evidence")
        .select("kind, proof_type, storage_path, content_sha256")
        .eq("vendor_id", str(branch_id))
        .execute()
    )
    flag_rows = _rows(
        client.table("vendor_branch_flags")
        .select(FLAG_COLUMNS)
        .eq("vendor_id", str(branch_id))
        .order("created_at", desc=True)
        .execute()
    )
    names = _vendor_names(
        client,
        {str(branch_id)}
        | {str(f["matched_vendor_id"]) for f in flag_rows if f.get("matched_vendor_id")},
    )
    history = _rows(
        client.table("vendor_branch_events")
        .select("from_status, to_status, note, created_at")
        .eq("vendor_id", str(branch_id))
        .order("created_at", desc=True)
        .execute()
    )
    hold = branch.get("payout_hold_until")
    loc = locations[0] if locations else None
    return BranchDetail(
        id=str(branch["id"]),
        slug=str(branch.get("slug") or ""),
        display_name=str(branch.get("display_name") or ""),
        status=str(branch.get("status") or ""),
        branch_status=str(branch.get("branch_status") or ""),
        branch_kind=str(branch.get("branch_kind") or "physical"),
        business=business,
        owner_kyc_approved=bool(kyc),
        contact_phone=branch.get("contact_phone"),
        contact_email=branch.get("contact_email"),
        payout_msisdn_masked=_mask(branch.get("payout_msisdn")),
        payout_rail=branch.get("payout_rail"),
        payout_on_hold=isinstance(hold, str) and bool(hold),
        location=LocationOut(
            lat=float(loc["lat"]),
            lng=float(loc["lng"]),
            landmark=str(loc.get("landmark") or ""),
            address=loc.get("address"),
            map_url=loc.get("map_url"),
        )
        if loc
        else None,
        plan=plan[0] if plan else None,
        evidence=[
            EvidenceView(
                kind=str(e.get("kind")),
                proof_type=e.get("proof_type"),
                signed_url=_signed_download(client, str(e.get("storage_path"))),
                content_sha256=e.get("content_sha256"),
            )
            for e in evidence
        ],
        flags=[_flag_out(row, names) for row in flag_rows],
        siblings=[
            SiblingOut(
                id=str(s["id"]),
                slug=str(s.get("slug") or ""),
                display_name=str(s.get("display_name") or ""),
                branch_status=str(s.get("branch_status") or ""),
                is_primary=s.get("is_primary_branch") is True,
            )
            for s in siblings
        ],
        history=[
            EventOut(
                from_status=h.get("from_status"),
                to_status=str(h.get("to_status")),
                note=h.get("note"),
                created_at=str(h["created_at"]) if h.get("created_at") else None,
            )
            for h in history
        ],
    )


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
class DecisionRequest(StrictModel):
    note: str | None = Field(default=None, max_length=1000)


class RequiredNoteRequest(StrictModel):
    note: str = Field(min_length=3, max_length=1000)

    @field_validator("note")
    @classmethod
    def not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("note is required")
        return stripped


class DecisionOut(BaseModel):
    id: str
    branch_status: str
    status: str


def _decide(
    client: Any,
    recorder: AdminAuditRecorder,
    actor: str,
    branch_id: UUID,
    to_status: str,
    note: str | None,
) -> DecisionOut:
    _limit(client, actor)
    before = _load_branch(client, branch_id)
    try:
        result = client.rpc(
            "transition_vendor_branch",
            {"p_vendor_id": str(branch_id), "p_to": to_status, "p_actor": actor, "p_note": note},
        ).execute()
    except Exception as exc:  # noqa: BLE001 — DB refusal -> stable error
        raise_mapped(exc)
    after = _load_branch(client, branch_id)
    data = getattr(result, "data", None)
    recorder.record(
        action=f"branches.{to_status}",
        entity_type="vendor_branch",
        entity_id=str(branch_id),
        before={"branch_status": before.get("branch_status"), "status": before.get("status")},
        after={
            "branch_status": after.get("branch_status"),
            "status": after.get("status"),
            "note": note,
            "transition": data if isinstance(data, dict) else None,
        },
    )
    return DecisionOut(
        id=str(branch_id),
        branch_status=str(after.get("branch_status")),
        status=str(after.get("status")),
    )


@branches_router.post("/{branch_id}/approve", response_model=DecisionOut)
async def approve_branch(
    branch_id: UUID,
    body: DecisionRequest,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> DecisionOut:
    note = body.note.strip() if body.note else None
    return _decide(service_client.client, recorder, user.id, branch_id, "approved", note)


@branches_router.post("/{branch_id}/request-info", response_model=DecisionOut)
async def request_branch_info(
    branch_id: UUID,
    body: RequiredNoteRequest,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> DecisionOut:
    return _decide(service_client.client, recorder, user.id, branch_id, "info_requested", body.note)


@branches_router.post("/{branch_id}/reject", response_model=DecisionOut)
async def reject_branch(
    branch_id: UUID,
    body: RequiredNoteRequest,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> DecisionOut:
    return _decide(service_client.client, recorder, user.id, branch_id, "rejected", body.note)


class FlagResolveRequest(StrictModel):
    resolution: Literal["cleared", "confirmed"]
    note: str = Field(min_length=3, max_length=1000)


@branches_router.post("/flags/{flag_id}/resolve", response_model=FlagOut)
async def resolve_duplicate_flag(
    flag_id: UUID,
    body: FlagResolveRequest,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> FlagOut:
    """Clear (not a duplicate / shared number approved) or confirm a flag.

    Clearing a same-owner shared payout number lifts the payout hold the DB put on
    the branch. A cross-owner payout flag can never be cleared.
    """
    client: Any = service_client.client
    _limit(client, user.id)
    rows = _rows(
        client.table("vendor_branch_flags").select(FLAG_COLUMNS).eq("id", str(flag_id)).execute()
    )
    if not rows:
        raise _not_found("Flag")
    before = rows[0]
    if before.get("status") != "open":
        raise AppError(
            code="conflict",
            message="flag already resolved",
            http_status=409,
            details={"message_key": "admin.branches.errors.flagResolved"},
        )
    if before.get("kind") == "payout_other_owner" and body.resolution == "cleared":
        raise AppError(
            code="conflict",
            message="a payout number can never be shared across owners",
            http_status=409,
            details={"message_key": "admin.branches.errors.payoutOtherOwner"},
        )
    updated = _rows(
        client.table("vendor_branch_flags")
        .update(
            {
                "status": body.resolution,
                "resolved_by": user.id,
                "resolved_at": datetime.now(UTC).isoformat(),
                "resolution_note": body.note.strip(),
            }
        )
        .eq("id", str(flag_id))
        .eq("status", "open")
        .execute()
    )
    if not updated:
        raise AppError(code="conflict", message="flag already resolved", http_status=409)
    hold_lifted = False
    if before.get("kind") == "payout_shared_same_owner" and body.resolution == "cleared":
        remaining = _rows(
            client.table("vendor_branch_flags")
            .select("id")
            .eq("vendor_id", str(before["vendor_id"]))
            .eq("kind", "payout_shared_same_owner")
            .eq("status", "open")
            .execute()
        )
        if not remaining:
            client.table("vendors").update({"payout_hold_until": None}).eq(
                "id", str(before["vendor_id"])
            ).execute()
            hold_lifted = True
    names = _vendor_names(
        client,
        {str(before["vendor_id"])}
        | ({str(before["matched_vendor_id"])} if before.get("matched_vendor_id") else set()),
    )
    out = _flag_out(updated[0], names)
    recorder.record(
        action=f"branches.flag.{body.resolution}",
        entity_type="vendor_branch_flag",
        entity_id=str(flag_id),
        before={
            "status": "open",
            "kind": before.get("kind"),
            "vendor_id": str(before["vendor_id"]),
        },
        after={
            "status": body.resolution,
            "note": body.note.strip(),
            "payout_hold_lifted": hold_lifted,
        },
    )
    return out


class PacraVerifyRequest(StrictModel):
    verified: bool
    note: str | None = Field(default=None, max_length=500)


@branches_router.post("/businesses/{business_id}/pacra", response_model=dict[str, Any])
async def verify_business_pacra(
    business_id: UUID,
    body: PacraVerifyRequest,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Mark the PACRA number/certificate checked (or un-check it)."""
    client: Any = service_client.client
    _limit(client, user.id)
    rows = _rows(
        client.table("vendor_businesses")
        .select("id, pacra_number, pacra_verified_at")
        .eq("id", str(business_id))
        .execute()
    )
    if not rows:
        raise _not_found("Business")
    if body.verified and not rows[0].get("pacra_number"):
        raise AppError(
            code="conflict",
            message="business has no PACRA number",
            http_status=409,
            details={"message_key": "admin.branches.errors.noPacra"},
        )
    patch = (
        {"pacra_verified_at": datetime.now(UTC).isoformat(), "pacra_verified_by": user.id}
        if body.verified
        else {"pacra_verified_at": None, "pacra_verified_by": None}
    )
    client.table("vendor_businesses").update(patch).eq("id", str(business_id)).execute()
    recorder.record(
        action="branches.business.pacra_verify"
        if body.verified
        else "branches.business.pacra_unverify",
        entity_type="vendor_business",
        entity_id=str(business_id),
        before={"pacra_verified_at": rows[0].get("pacra_verified_at")},
        after={**patch, "note": body.note},
    )
    return {"id": str(business_id), "pacra_verified": body.verified}


admin_router.include_router(branches_router)
