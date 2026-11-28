"""Admin review queue for Made in Zambia claims (docs/plan/vendor-sourcing-hub.md).

Vendors CLAIM a listing (optional PACRA/ZABS reference); an admin APPROVES or
REJECTS. Only ``approved`` is public in the sourcing hub. Mounted under the
audited, admin-guarded ``/admin`` router, ``vendors.manage`` permission. Data only:
no money, order or ledger row is touched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import ADMIN_WRITE
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.routers.vendor_sourcing import rows_of
from app.schemas.base import StrictModel
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

claims_router = APIRouter(prefix="/made-in-zambia-claims", tags=["admin-made-in-zambia"])

ClaimStatus = Literal["claimed", "approved", "rejected"]
#: from-state -> allowed decisions. An approved claim can be revoked (rejected).
DECISIONS: Final[dict[str, dict[str, str]]] = {
    "claimed": {"approve": "approved", "reject": "rejected"},
    "approved": {"reject": "rejected"},
}
COLUMNS: Final = (
    "id, vendor_id, title_override, status, made_in_zambia_status, made_in_zambia_reference, "
    "made_in_zambia_claimed_at, made_in_zambia_reviewed_by, made_in_zambia_reviewed_at, "
    "made_in_zambia_review_note, products(name)"
)


class ClaimOut(BaseModel):
    listing_id: str
    vendor_id: str
    vendor_name: str | None = None
    title: str
    status: ClaimStatus
    reference: str | None = None
    claimed_at: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_note: str | None = None


class DecisionBody(StrictModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=500)


def _limit(client: Any, actor_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=ADMIN_WRITE.scope,
        key=f"made-in-zambia:{actor_id}",
        window=ADMIN_WRITE.window,
        limit=ADMIN_WRITE.limit,
        client=client,
    )
    if not allowed:
        raise_rate_limited(retry_after=retry_after, message_key="admin.common.rateLimited")


def _claim_from_row(row: dict[str, Any], vendor_name: str | None) -> ClaimOut:
    product = row.get("products") if isinstance(row.get("products"), dict) else {}
    return ClaimOut(
        listing_id=str(row["id"]),
        vendor_id=str(row["vendor_id"]),
        vendor_name=vendor_name,
        title=str(row.get("title_override") or (product or {}).get("name") or ""),
        status=row["made_in_zambia_status"],
        reference=row.get("made_in_zambia_reference"),
        claimed_at=str(row["made_in_zambia_claimed_at"])
        if row.get("made_in_zambia_claimed_at")
        else None,
        reviewed_by=str(row["made_in_zambia_reviewed_by"])
        if row.get("made_in_zambia_reviewed_by")
        else None,
        reviewed_at=str(row["made_in_zambia_reviewed_at"])
        if row.get("made_in_zambia_reviewed_at")
        else None,
        review_note=row.get("made_in_zambia_review_note"),
    )


def _vendor_names(client: Any, rows: list[dict[str, Any]]) -> dict[str, str]:
    ids = sorted({str(r["vendor_id"]) for r in rows})
    if not ids:
        return {}
    return {
        str(v["id"]): str(v.get("display_name") or "")
        for v in rows_of(
            client.table("vendors").select("id, display_name").in_("id", ids).execute()
        )
    }


@claims_router.get("", response_model=list[ClaimOut])
def list_claims(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[ClaimStatus, Query()] = "claimed",
) -> list[ClaimOut]:
    client: Any = service_client.client
    rows = rows_of(
        client.table("vendor_listings")
        .select(COLUMNS)
        .eq("made_in_zambia_status", status)
        .order("made_in_zambia_claimed_at", desc=False)
        .limit(200)
        .execute()
    )
    names = _vendor_names(client, rows)
    return [_claim_from_row(r, names.get(str(r["vendor_id"]))) for r in rows]


@claims_router.post("/{listing_id}/decision", response_model=ClaimOut)
def decide_claim(
    listing_id: UUID,
    body: DecisionBody,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ClaimOut:
    client: Any = service_client.client
    _limit(client, user.id)
    rows = rows_of(
        client.table("vendor_listings").select(COLUMNS).eq("id", str(listing_id)).execute()
    )
    if not rows or rows[0].get("made_in_zambia_status") is None:
        raise AppError(code="not_found", message="Claim not found", http_status=404)
    before = rows[0]
    current = str(before["made_in_zambia_status"])
    target = DECISIONS.get(current, {}).get(body.decision)
    if target is None:
        raise AppError(
            code="made_in_zambia.invalid_transition",
            message=f"Cannot {body.decision} a claim that is {current}",
            http_status=409,
            details={"message_key": "admin.madeInZambia.errors.invalidTransition"},
        )
    note = body.note.strip() if body.note and body.note.strip() else None
    patch = {
        "made_in_zambia_status": target,
        "made_in_zambia_reviewed_by": user.id,
        "made_in_zambia_reviewed_at": datetime.now(UTC).isoformat(),
        "made_in_zambia_review_note": note,
    }
    # The from-state is asserted inside the UPDATE so a concurrent change loses.
    updated = rows_of(
        client.table("vendor_listings")
        .update(patch)
        .eq("id", str(listing_id))
        .eq("made_in_zambia_status", current)
        .execute()
    )
    if not updated:
        raise AppError(
            code="made_in_zambia.conflict",
            message="Claim changed, reload and retry",
            http_status=409,
        )
    recorder.record(
        action=f"made_in_zambia.{target}",
        entity_type="vendor_listing",
        entity_id=str(listing_id),
        before={"status": current},
        after={"status": target, "reference": before.get("made_in_zambia_reference"), "note": note},
    )
    after = {**before, **patch}
    names = _vendor_names(client, [after])
    return _claim_from_row(after, names.get(str(after["vendor_id"])))


admin_router.include_router(claims_router)
