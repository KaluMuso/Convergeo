"""Vendor: my businesses & shops (flag ``multi_branch``, default off).

A business (legal entity, ``vendor_businesses``) owns one or more shops
(``vendors`` rows = branches). The owner's KYC is done once; each extra shop has
its own location, contacts, payout MoMo, plan add-on and onboarding status, and
needs admin verification (storefront photo + proof of premises for physical
shops).

Every route: vendor role (authz) + ownership resolved from the DB (another
owner's business/branch -> 404, never 403, so ids are not probeable) + Pydantic
validation; every mutation: an in-router rate limit keyed by the caller. The
database enforces every limit (see migration 20261117000000); refusals map to
stable ``vendor.branches.errors.*`` message keys.
"""

from __future__ import annotations

import re
import time
from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import SENSITIVE_WRITE, STANDARD_WRITE, RateLimitPolicy
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.branches.rules import (
    EVIDENCE_BUCKET,
    REGISTERED_TYPES,
    ShopAllowance,
    geo_distance_m,
    is_zm_mobile,
    min_sibling_distance_m,
    multi_branch_enabled,
    normalize_zm_msisdn,
    raise_mapped,
    shop_allowance,
    slugify_branch,
)
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.vendor_plans.resolver import PLAN_COLUMNS
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator

router = APIRouter(prefix="/vendor/businesses", tags=["vendor-branches"])

MAX_EVIDENCE_BYTES = 10_485_760  # matches the kyc-docs bucket limit (config.toml).
BRANCH_PLAN_COLUMNS = (
    PLAN_COLUMNS + ", included_shops, extra_shop_price_ngwee, staff_seats, "
    "whatsapp_broadcasts_per_month, integrations_level, ad_credit_ngwee, payout_speed, "
    "support_level, official_store_badge, click_and_collect, multi_branch_stock"
)
VENDOR_BRANCH_COLUMNS = (
    "id, business_id, slug, display_name, status, branch_status, branch_kind, "
    "is_primary_branch, contact_phone, contact_email, whatsapp_msisdn, payout_msisdn, "
    "payout_rail, payout_hold_until, created_at"
)
BusinessType = Literal["company", "business_name", "unregistered"]
EvidenceKind = Literal["storefront_photo", "premises_proof"]
ProofType = Literal["lease", "utility_bill", "council_permit"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _limit(client: Any, user_id: str, policy: RateLimitPolicy) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=policy.scope,
        key=f"branches:{user_id}",
        window=policy.window,
        limit=policy.limit,
        client=client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after, message_key="vendor.branches.errors.rateLimited"
        )


def _not_found(what: str = "business") -> AppError:
    key = "businessNotFound" if what == "business" else "branchNotFound"
    return AppError(
        code="not_found",
        message=f"{what} not found",
        http_status=404,
        details={"message_key": f"vendor.branches.errors.{key}"},
    )


def _require_flag(client: Any) -> None:
    if not multi_branch_enabled(client):
        raise AppError(
            code="feature_disabled",
            message="Multi-branch businesses are not enabled",
            http_status=404,
            details={"message_key": "vendor.branches.errors.disabled"},
        )


def _owned_business(client: Any, business_id: UUID, owner_id: str) -> dict[str, Any]:
    rows = _rows(
        client.table("vendor_businesses")
        .select(
            "id, owner_user_id, legal_name, registration_type, pacra_number, pacra_cert_path, "
            "pacra_verified_at, status"
        )
        .eq("id", str(business_id))
        .eq("owner_user_id", owner_id)
        .execute()
    )
    if not rows:
        raise _not_found("business")
    return rows[0]


def _owned_branch(client: Any, business_id: UUID, branch_id: UUID, owner_id: str) -> dict[str, Any]:
    rows = _rows(
        client.table("vendors")
        .select(VENDOR_BRANCH_COLUMNS)
        .eq("id", str(branch_id))
        .eq("business_id", str(business_id))
        .eq("owner_user_id", owner_id)
        .execute()
    )
    if not rows:
        raise _not_found("branch")
    return rows[0]


def _business_plan(client: Any, branches: list[dict[str, Any]]) -> dict[str, Any] | None:
    primary = next((b for b in branches if b.get("is_primary_branch") is True), None)
    plan_key: str | None = None
    if primary is not None:
        assigned = _rows(
            client.table("vendor_plan_assignments")
            .select("plan_key")
            .eq("vendor_id", str(primary["id"]))
            .execute()
        )
        if assigned:
            plan_key = str(assigned[0].get("plan_key"))
    query = client.table("vendor_plans").select(BRANCH_PLAN_COLUMNS)
    query = query.eq("key", plan_key) if plan_key else query.eq("is_default", True)
    rows = _rows(query.execute())
    return rows[0] if rows else None


def _active_count(branches: list[dict[str, Any]]) -> int:
    return sum(1 for b in branches if b.get("branch_status") != "rejected")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class AllowanceOut(BaseModel):
    registered: bool
    plan_key: str | None
    included_shops: int | None
    extra_shop_price_ngwee: int | None
    used: int
    limit: int | None
    can_add: bool
    next_billing_role: str | None
    next_price_ngwee: int | None
    blocked_reason: str | None


class BranchOut(BaseModel):
    id: str
    slug: str
    display_name: str
    status: str
    branch_status: str
    branch_kind: str
    is_primary: bool
    payout_on_hold: bool = False
    review_note: str | None = None


class BusinessOut(BaseModel):
    id: str
    legal_name: str
    registration_type: str
    pacra_number: str | None
    pacra_verified: bool
    status: str
    owner_kyc_approved: bool
    staff_seats: int | None
    staff_used: int
    allowance: AllowanceOut
    branches: list[BranchOut]


class BusinessesResponse(BaseModel):
    enabled: bool
    businesses: list[BusinessOut]


def _allowance_out(allowance: ShopAllowance) -> AllowanceOut:
    return AllowanceOut(
        registered=allowance.registered,
        plan_key=allowance.plan_key,
        included_shops=allowance.included_shops,
        extra_shop_price_ngwee=allowance.extra_shop_price_ngwee,
        used=allowance.used,
        limit=allowance.limit,
        can_add=allowance.can_add,
        next_billing_role=allowance.next_billing_role,
        next_price_ngwee=allowance.next_price_ngwee,
        blocked_reason=allowance.blocked_reason,
    )


def _branch_out(row: dict[str, Any], note: str | None = None) -> BranchOut:
    hold = row.get("payout_hold_until")
    return BranchOut(
        id=str(row["id"]),
        slug=str(row.get("slug") or ""),
        display_name=str(row.get("display_name") or ""),
        status=str(row.get("status") or "draft"),
        branch_status=str(row.get("branch_status") or "approved"),
        branch_kind=str(row.get("branch_kind") or "physical"),
        is_primary=row.get("is_primary_branch") is True,
        payout_on_hold=isinstance(hold, str) and hold > time.strftime("%Y-%m-%d"),
        review_note=note,
    )


def _latest_notes(client: Any, branch_ids: list[str]) -> dict[str, str]:
    if not branch_ids:
        return {}
    rows = _rows(
        client.table("vendor_branch_events")
        .select("vendor_id, to_status, note, created_at")
        .in_("vendor_id", branch_ids)
        .order("created_at", desc=True)
        .execute()
    )
    notes: dict[str, str] = {}
    for row in rows:
        key = str(row.get("vendor_id"))
        if key not in notes and row.get("to_status") in ("info_requested", "rejected"):
            note = row.get("note")
            if isinstance(note, str) and note:
                notes[key] = note
    return notes


def _business_out(client: Any, business: dict[str, Any]) -> BusinessOut:
    branches = _rows(
        client.table("vendors")
        .select(VENDOR_BRANCH_COLUMNS)
        .eq("business_id", str(business["id"]))
        .order("created_at")
        .execute()
    )
    plan = _business_plan(client, branches)
    allowance = shop_allowance(
        pacra_number=business.get("pacra_number"), plan=plan, used=_active_count(branches)
    )
    branch_ids = [str(b["id"]) for b in branches]
    kyc = (
        _rows(
            client.table("kyc_records")
            .select("id")
            .in_("vendor_id", branch_ids)
            .eq("status", "approved")
            .limit(1)
            .execute()
        )
        if branch_ids
        else []
    )
    staff = _rows(
        client.table("vendor_business_staff")
        .select("id, status")
        .eq("business_id", str(business["id"]))
        .execute()
    )
    notes = _latest_notes(
        client, [str(b["id"]) for b in branches if not b.get("is_primary_branch")]
    )
    seats = plan.get("staff_seats") if plan else 0
    return BusinessOut(
        id=str(business["id"]),
        legal_name=str(business.get("legal_name") or ""),
        registration_type=str(business.get("registration_type") or "unspecified"),
        pacra_number=business.get("pacra_number"),
        pacra_verified=bool(business.get("pacra_verified_at")),
        status=str(business.get("status") or "active"),
        owner_kyc_approved=bool(kyc),
        staff_seats=seats if isinstance(seats, int) or seats is None else 0,
        staff_used=sum(1 for s in staff if s.get("status") != "revoked"),
        allowance=_allowance_out(allowance),
        branches=[_branch_out(b, notes.get(str(b["id"]))) for b in branches],
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
@router.get("", response_model=BusinessesResponse)
async def list_my_businesses(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BusinessesResponse:
    """The header switcher's data. Flag off: ``enabled=false`` (switcher hidden)."""
    client: Any = service_client.client
    if not multi_branch_enabled(client):
        return BusinessesResponse(enabled=False, businesses=[])
    rows = _rows(
        client.table("vendor_businesses")
        .select(
            "id, owner_user_id, legal_name, registration_type, pacra_number, "
            "pacra_verified_at, status"
        )
        .eq("owner_user_id", current_user.id)
        .order("created_at")
        .execute()
    )
    return BusinessesResponse(enabled=True, businesses=[_business_out(client, row) for row in rows])


# ---------------------------------------------------------------------------
# Business registration (PACRA)
# ---------------------------------------------------------------------------
class BusinessUpdate(StrictModel):
    legal_name: str | None = Field(default=None, min_length=1, max_length=160)
    registration_type: BusinessType | None = None
    pacra_number: str | None = Field(default=None, min_length=4, max_length=40)
    pacra_cert_path: str | None = Field(default=None, max_length=300)

    @field_validator("pacra_number")
    @classmethod
    def normalise_pacra(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = re.sub(r"\s", "", value).upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9/-]{3,31}", cleaned):
            raise ValueError("invalid PACRA number")
        return cleaned

    @model_validator(mode="after")
    def check_shape(self) -> BusinessUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if self.registration_type == "unregistered" and self.pacra_number:
            raise ValueError("an unregistered trader has no PACRA number")
        if self.legal_name is not None and not self.legal_name.strip():
            raise ValueError("legal_name must not be blank")
        return self


@router.patch("/{business_id}", response_model=BusinessOut)
async def update_business(
    business_id: UUID,
    body: BusinessUpdate,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BusinessOut:
    client: Any = service_client.client
    _limit(client, current_user.id, SENSITIVE_WRITE)
    _require_flag(client)
    business = _owned_business(client, business_id, current_user.id)
    patch: dict[str, Any] = {}
    if body.legal_name is not None:
        patch["legal_name"] = body.legal_name.strip()
    if body.registration_type is not None:
        patch["registration_type"] = body.registration_type
        if body.registration_type == "unregistered":
            patch["pacra_number"] = None
            patch["pacra_cert_path"] = None
    if body.pacra_number is not None:
        patch["pacra_number"] = body.pacra_number
    if body.pacra_cert_path is not None:
        if not body.pacra_cert_path.startswith(f"businesses/{business['id']}/"):
            raise AppError(
                code="validation_error",
                message="certificate path is not in this business folder",
                http_status=422,
                details={"message_key": "vendor.branches.errors.evidencePath"},
            )
        patch["pacra_cert_path"] = body.pacra_cert_path
    reg = patch.get("registration_type", business.get("registration_type"))
    number = patch.get("pacra_number", business.get("pacra_number"))
    cert = patch.get("pacra_cert_path", business.get("pacra_cert_path"))
    if reg in REGISTERED_TYPES and (not number or not cert):
        raise AppError(
            code="validation_error",
            message="registered businesses need a PACRA number and certificate",
            http_status=422,
            details={"message_key": "vendor.branches.errors.pacraRequired"},
        )
    if reg == "unregistered":
        active = _rows(
            client.table("vendors")
            .select("id, branch_status")
            .eq("business_id", str(business["id"]))
            .execute()
        )
        if _active_count(active) > 1:
            raise AppError(
                code="conflict",
                message="unregistered traders are limited to one shop",
                http_status=409,
                details={"message_key": "vendor.branches.errors.unregisteredLimit"},
            )
    try:
        client.table("vendor_businesses").update(patch).eq("id", str(business["id"])).execute()
    except Exception as exc:  # noqa: BLE001 — DB refusal -> stable error
        raise_mapped(exc)
    return _business_out(client, _owned_business(client, business_id, current_user.id))


# ---------------------------------------------------------------------------
# Add a shop / branch
# ---------------------------------------------------------------------------
class BranchLocation(StrictModel):
    lat: float = Field(ge=-18.1, le=-8.2)  # Zambia bounding box
    lng: float = Field(ge=21.9, le=33.8)
    landmark: str = Field(min_length=3, max_length=200)
    address: str | None = Field(default=None, max_length=300)
    map_url: str | None = Field(default=None, max_length=500, pattern=r"^https://")


class DayHours(StrictModel):
    open: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    close: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    closed: bool = False


DayKey = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class BranchCreate(StrictModel):
    display_name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    branch_kind: Literal["physical", "online"] = "physical"
    location: BranchLocation | None = None
    hours: dict[DayKey, DayHours] = Field(default_factory=dict)
    contact_phone: str = Field(min_length=9, max_length=20)
    contact_email: str | None = Field(
        default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )
    whatsapp_msisdn: str | None = Field(default=None, min_length=9, max_length=20)
    payout_msisdn: str = Field(min_length=9, max_length=20)
    payout_rail: Literal["mtn", "airtel", "zamtel"]

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("display_name is too short")
        return stripped

    @field_validator("contact_phone", "payout_msisdn", "whatsapp_msisdn")
    @classmethod
    def zm_mobile(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalised = normalize_zm_msisdn(value)
        if not is_zm_mobile(normalised):
            raise ValueError("must be a Zambian mobile number")
        return normalised

    @model_validator(mode="after")
    def physical_needs_location(self) -> BranchCreate:
        if self.branch_kind == "physical" and self.location is None:
            raise ValueError("a physical shop needs a location")
        return self


class BranchCreated(BaseModel):
    branch: BranchOut
    plan_key: str | None
    branch_billing_role: str
    addon_price_ngwee: int | None
    needs_review_flags: int


def _check_sibling_distance(client: Any, business_id: str, location: BranchLocation) -> None:
    """Friendly pre-check; the vendor_locations trigger is the authority."""
    minimum = min_sibling_distance_m(client)
    siblings = _rows(
        client.table("vendors")
        .select("id, branch_status, vendor_locations(lat, lng)")
        .eq("business_id", business_id)
        .execute()
    )
    nearest: float | None = None
    for sibling in siblings:
        if sibling.get("branch_status") == "rejected":
            continue
        for loc in sibling.get("vendor_locations") or []:
            if not isinstance(loc, dict) or loc.get("lat") is None or loc.get("lng") is None:
                continue
            distance = geo_distance_m(
                location.lat, location.lng, float(loc["lat"]), float(loc["lng"])
            )
            nearest = distance if nearest is None else min(nearest, distance)
    if nearest is not None and nearest < minimum:
        raise AppError(
            code="validation_error",
            message="branch is too close to another branch of this business",
            http_status=422,
            details={
                "message_key": "vendor.branches.errors.tooClose",
                "min_m": minimum,
                "nearest_m": round(nearest),
            },
        )


@router.post("/{business_id}/branches", response_model=BranchCreated, status_code=201)
async def create_branch(
    business_id: UUID,
    body: BranchCreate,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BranchCreated:
    client: Any = service_client.client
    _limit(client, current_user.id, SENSITIVE_WRITE)
    _require_flag(client)
    business = _owned_business(client, business_id, current_user.id)
    if body.location is not None:
        _check_sibling_distance(client, str(business["id"]), body.location)
    payload: dict[str, Any] = {
        "display_name": body.display_name,
        "description": body.description,
        "slug": slugify_branch(body.display_name),
        "branch_kind": body.branch_kind,
        "contact_phone": body.contact_phone,
        "contact_email": body.contact_email.lower() if body.contact_email else None,
        "whatsapp_msisdn": body.whatsapp_msisdn,
        "payout_msisdn": body.payout_msisdn,
        "payout_rail": body.payout_rail,
        "hours": {day: hours.model_dump(exclude_none=True) for day, hours in body.hours.items()},
    }
    if body.location is not None:
        payload.update(body.location.model_dump())
    try:
        result = client.rpc(
            "create_vendor_branch",
            {
                "p_business_id": str(business["id"]),
                "p_owner": current_user.id,
                "p_payload": payload,
            },
        ).execute()
    except Exception as exc:  # noqa: BLE001 — DB refusal -> stable error
        raise_mapped(exc)
    data = getattr(result, "data", None)
    if not isinstance(data, dict) or not data.get("id"):
        raise AppError(code="internal_error", message="branch was not created", http_status=500)
    branch = _owned_branch(client, business_id, UUID(str(data["id"])), current_user.id)
    addon = data.get("addon_price_ngwee")
    return BranchCreated(
        branch=_branch_out(branch),
        plan_key=data.get("plan_key"),
        branch_billing_role=str(data.get("branch_billing_role") or "included"),
        addon_price_ngwee=int(addon) if isinstance(addon, int) else None,
        needs_review_flags=int(data.get("flags_opened") or 0),
    )


# ---------------------------------------------------------------------------
# Evidence (storefront photo + proof of premises) -> private Storage
# ---------------------------------------------------------------------------
class EvidenceSignRequest(StrictModel):
    kind: Literal["storefront_photo", "premises_proof", "pacra_certificate"]
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    file_size_bytes: int = Field(ge=1, le=MAX_EVIDENCE_BYTES)


class EvidenceSignResponse(BaseModel):
    bucket: str
    path: str
    token: str
    signed_url: str


def _signed_upload(client: Any, path: str) -> EvidenceSignResponse:
    try:
        result = client.storage.from_(EVIDENCE_BUCKET).create_signed_upload_url(path)
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            code="storage_error", message="Could not create a signed upload URL", http_status=502
        ) from exc

    def _get(snake: str, camel: str) -> str | None:
        value = (
            result.get(snake, result.get(camel))
            if isinstance(result, dict)
            else getattr(result, snake, None) or getattr(result, camel, None)
        )
        return value if isinstance(value, str) and value else None

    url, token = _get("signed_url", "signedUrl"), _get("token", "token")
    if not url or not token:
        raise AppError(
            code="storage_error", message="Storage returned no upload URL", http_status=502
        )
    return EvidenceSignResponse(bucket=EVIDENCE_BUCKET, path=path, token=token, signed_url=url)


_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


@router.post("/{business_id}/evidence/sign", response_model=EvidenceSignResponse)
async def sign_business_evidence(
    business_id: UUID,
    body: EvidenceSignRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    branch_id: UUID | None = None,
) -> EvidenceSignResponse:
    """Signed upload into the caller's own folder (path pinned server-side)."""
    client: Any = service_client.client
    _limit(client, current_user.id, SENSITIVE_WRITE)
    _require_flag(client)
    business = _owned_business(client, business_id, current_user.id)
    ext = _EXT[body.content_type]
    stamp = int(time.time())
    if body.kind == "pacra_certificate":
        path = f"businesses/{business['id']}/pacra-{stamp}.{ext}"
    else:
        if branch_id is None:
            raise AppError(
                code="validation_error",
                message="branch_id is required for branch evidence",
                http_status=422,
                details={"message_key": "vendor.branches.errors.branchRequired"},
            )
        branch = _owned_branch(client, business_id, branch_id, current_user.id)
        path = f"branches/{business['id']}/{branch['id']}/{body.kind}-{stamp}.{ext}"
    return _signed_upload(client, path)


class EvidenceRecord(StrictModel):
    kind: EvidenceKind
    storage_path: str = Field(max_length=300)
    proof_type: ProofType | None = None
    content_sha256: str | None = Field(default=None, min_length=64, max_length=64)

    @model_validator(mode="after")
    def proof_shape(self) -> EvidenceRecord:
        if (self.kind == "premises_proof") != (self.proof_type is not None):
            raise ValueError("proof_type is required for premises_proof only")
        if self.content_sha256 is not None and not _SHA256.match(self.content_sha256):
            raise ValueError("content_sha256 must be lowercase hex")
        return self


class EvidenceOut(BaseModel):
    kind: str
    proof_type: str | None
    uploaded: bool = True
    duplicate_flags: int = 0


@router.put("/{business_id}/branches/{branch_id}/evidence", response_model=EvidenceOut)
async def record_branch_evidence(
    business_id: UUID,
    branch_id: UUID,
    body: EvidenceRecord,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> EvidenceOut:
    client: Any = service_client.client
    _limit(client, current_user.id, STANDARD_WRITE)
    _require_flag(client)
    branch = _owned_branch(client, business_id, branch_id, current_user.id)
    if branch.get("branch_status") not in ("draft", "info_requested"):
        raise AppError(
            code="conflict",
            message="evidence can only change before review",
            http_status=409,
            details={"message_key": "vendor.branches.errors.evidenceLocked"},
        )
    prefix = f"branches/{business_id}/{branch_id}/{body.kind}-"
    if not body.storage_path.startswith(prefix) or not re.fullmatch(
        r"[A-Za-z0-9._/-]+", body.storage_path
    ):
        raise AppError(
            code="validation_error",
            message="evidence path is not in this branch folder",
            http_status=422,
            details={"message_key": "vendor.branches.errors.evidencePath"},
        )
    try:
        client.table("vendor_branch_evidence").upsert(
            {
                "vendor_id": str(branch_id),
                "kind": body.kind,
                "proof_type": body.proof_type,
                "storage_path": body.storage_path,
                "content_sha256": body.content_sha256,
                "uploaded_by": current_user.id,
            },
            on_conflict="vendor_id,kind",
        ).execute()
        scan = client.rpc("vendor_branch_dedup_scan", {"p_vendor_id": str(branch_id)}).execute()
    except Exception as exc:  # noqa: BLE001
        raise_mapped(exc)
    flags = getattr(scan, "data", 0)
    return EvidenceOut(
        kind=body.kind,
        proof_type=body.proof_type,
        duplicate_flags=flags if isinstance(flags, int) else 0,
    )


@router.post("/{business_id}/branches/{branch_id}/submit", response_model=BranchOut)
async def submit_branch(
    business_id: UUID,
    branch_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BranchOut:
    """draft / info_requested -> pending_review (guarded DB transition)."""
    client: Any = service_client.client
    _limit(client, current_user.id, STANDARD_WRITE)
    _require_flag(client)
    _owned_branch(client, business_id, branch_id, current_user.id)
    try:
        client.rpc("vendor_branch_dedup_scan", {"p_vendor_id": str(branch_id)}).execute()
        client.rpc(
            "transition_vendor_branch",
            {
                "p_vendor_id": str(branch_id),
                "p_to": "pending_review",
                "p_actor": current_user.id,
                "p_note": None,
            },
        ).execute()
    except Exception as exc:  # noqa: BLE001
        raise_mapped(exc)
    return _branch_out(_owned_branch(client, business_id, branch_id, current_user.id))


# ---------------------------------------------------------------------------
# Staff seats (registry + plan cap; staff access wiring comes later)
# ---------------------------------------------------------------------------
class StaffOut(BaseModel):
    id: str
    display_name: str
    invite_msisdn: str | None
    role: str
    status: str
    branch_ids: list[str]


class StaffInvite(StrictModel):
    display_name: str = Field(min_length=1, max_length=80)
    invite_msisdn: str = Field(min_length=9, max_length=20)
    role: Literal["manager", "staff"] = "staff"
    branch_ids: list[Annotated[str, Field(pattern=_UUID_PATTERN)]] = Field(
        default_factory=list, max_length=200
    )

    @field_validator("invite_msisdn")
    @classmethod
    def zm_mobile(cls, value: str) -> str:
        normalised = normalize_zm_msisdn(value)
        if not is_zm_mobile(normalised):
            raise ValueError("must be a Zambian mobile number")
        return str(normalised)


def _staff_out(row: dict[str, Any]) -> StaffOut:
    return StaffOut(
        id=str(row["id"]),
        display_name=str(row.get("display_name") or ""),
        invite_msisdn=row.get("invite_msisdn"),
        role=str(row.get("role") or "staff"),
        status=str(row.get("status") or "invited"),
        branch_ids=[str(b) for b in row.get("branch_ids") or []],
    )


@router.get("/{business_id}/staff", response_model=list[StaffOut])
async def list_staff(
    business_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[StaffOut]:
    client: Any = service_client.client
    _require_flag(client)
    business = _owned_business(client, business_id, current_user.id)
    rows = _rows(
        client.table("vendor_business_staff")
        .select("id, display_name, invite_msisdn, role, status, branch_ids")
        .eq("business_id", str(business["id"]))
        .neq("status", "revoked")
        .order("created_at")
        .execute()
    )
    return [_staff_out(row) for row in rows]


@router.post("/{business_id}/staff", response_model=StaffOut, status_code=201)
async def invite_staff(
    business_id: UUID,
    body: StaffInvite,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> StaffOut:
    client: Any = service_client.client
    _limit(client, current_user.id, SENSITIVE_WRITE)
    _require_flag(client)
    business = _owned_business(client, business_id, current_user.id)
    if body.branch_ids:
        owned = {
            str(row["id"])
            for row in _rows(
                client.table("vendors")
                .select("id")
                .eq("business_id", str(business["id"]))
                .execute()
            )
        }
        if not {b.lower() for b in body.branch_ids} <= owned:
            raise _not_found("branch")
    try:
        rows = _rows(
            client.table("vendor_business_staff")
            .insert(
                {
                    "business_id": str(business["id"]),
                    "display_name": body.display_name.strip(),
                    "invite_msisdn": body.invite_msisdn,
                    "role": body.role,
                    "branch_ids": [b.lower() for b in body.branch_ids],
                    "created_by": current_user.id,
                }
            )
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise_mapped(exc)
    if not rows:
        raise AppError(code="internal_error", message="staff invite failed", http_status=500)
    return _staff_out(rows[0])


@router.delete("/{business_id}/staff/{staff_id}", status_code=204)
async def revoke_staff(
    business_id: UUID,
    staff_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> None:
    client: Any = service_client.client
    _limit(client, current_user.id, STANDARD_WRITE)
    _require_flag(client)
    business = _owned_business(client, business_id, current_user.id)
    rows = _rows(
        client.table("vendor_business_staff")
        .update({"status": "revoked"})
        .eq("id", str(staff_id))
        .eq("business_id", str(business["id"]))
        .execute()
    )
    if not rows:
        raise AppError(
            code="not_found",
            message="staff not found",
            http_status=404,
            details={"message_key": "vendor.branches.errors.staffNotFound"},
        )
