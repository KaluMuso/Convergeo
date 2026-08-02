"""Vendor regulator licences (R02-P12b) on top of migration 0084.

Three surfaces over ``public.vendor_licences``:

- Vendor-side: apply for a licence and list your own. ``status`` is pinned to
  ``pending`` server-side regardless of anything in the request body (the DB
  guard trigger ``guard_vendor_licence_status_update`` is the second lock).
- Admin-side: review queue, verify/reject/revoke decisions and the expiry
  chase queue. Decisions follow the audited-admin pattern (``AdminAuditRecorder``
  writes one ``audit_log`` row per mutation). Decisions are HUMAN admin actions
  only — there is deliberately no AI/LLM seam anywhere in this router.
- Public: a derived boolean badge via the ``vendor_licence_is_valid`` RPC.
  Validity is DERIVED (verified AND unexpired), never stored and never
  recomputed here, so the badge cannot drift from the SQL truth. The badge
  discloses a boolean and nothing else.

Sensitive-data posture (mirrors KYC):
- ``licence_number`` is commercially sensitive (see the column comment in
  0084): it is NEVER logged, never interpolated into error messages, and never
  placed in audit payloads. It is only returned to the owning vendor and to
  admins.
- Licence documents live in PRIVATE storage; this router stores only the
  storage path. Upload/signing mirrors the KYC media lane (``kyc_media``) and
  is a separate seam — no signing endpoints are exposed here.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import ADMIN_WRITE, POLICIES, RateLimitPolicy
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regulated classes — THE allowlist. One place, easy to extend. Both the vendor
# apply endpoint and the public badge endpoint validate against this set.
# ---------------------------------------------------------------------------
REGULATED_CLASSES: frozenset[str] = frozenset(
    {
        "pharmacy",
        "agrochemicals",
        "alcohol",
        "food",
        "financial_services",
    }
)

LICENCE_STATUSES = ("pending", "verified", "rejected", "revoked")
# Statuses covered by the partial unique index vendor_licences_one_live_per_class.
LIVE_STATUSES = ("pending", "verified")

LicenceStatus = Literal["pending", "verified", "rejected", "revoked"]

VENDOR_LICENCE_APPLY_LIMIT_PER_DAY = 10
VENDOR_LICENCE_APPLY_POLICY = RateLimitPolicy(
    scope="vendor_licence_apply",
    limit=VENDOR_LICENCE_APPLY_LIMIT_PER_DAY,
    window=timedelta(days=1),
)

# The startup sweep (assert_all_mutating_routes_covered) requires every mutating
# route to carry a declared policy. This pebble owns only this module, so the
# declarations live here; ``setdefault`` keeps the central registry in
# app/core/ratelimit_policies.py authoritative if it later declares these ids.
# Admin decision routes are keyed un-prefixed like the other /admin sub-routers
# (see the /kyc and /intake entries): the coverage walker sees a mounted
# sub-router's own paths.
POLICIES.setdefault("POST /vendor/licences", VENDOR_LICENCE_APPLY_POLICY)
POLICIES.setdefault("POST /licences/{licence_id}/verify", ADMIN_WRITE)
POLICIES.setdefault("POST /licences/{licence_id}/reject", ADMIN_WRITE)
POLICIES.setdefault("POST /licences/{licence_id}/revoke", ADMIN_WRITE)

router = APIRouter(tags=["vendor-licences"])
licences_admin_router = APIRouter(prefix="/licences", tags=["admin-licences"])


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def _parse_iso_date(value: object) -> object:
    """Accept ISO ``YYYY-MM-DD`` strings for date fields under strict parsing."""
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("must be an ISO date (YYYY-MM-DD)") from exc
    return value


IsoDate = Annotated[date, BeforeValidator(_parse_iso_date)]


class LicenceApplyRequest(BaseModel):
    """Vendor application body.

    Strict types, but UNKNOWN fields are DISCARDED rather than rejected: a body
    that smuggles ``status: "verified"`` (or ``verified_by`` / ``verified_at``)
    must never influence the stored row. Status is pinned to ``pending``
    server-side — proven in tests — and the DB guard trigger backs this up.
    """

    model_config = ConfigDict(strict=True, extra="ignore")

    regulated_class: str = Field(min_length=1, max_length=64)
    regulator: str = Field(min_length=2, max_length=200)
    licence_number: str = Field(min_length=3, max_length=120)
    issued_on: IsoDate | None = None
    expires_on: IsoDate
    document_path: str | None = Field(default=None, max_length=500)

    @field_validator("document_path")
    @classmethod
    def validate_document_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned.startswith("/") or ".." in cleaned:
            raise ValueError("document_path must be a relative private-storage path")
        return cleaned

    @model_validator(mode="after")
    def validate_dates_ordered(self) -> LicenceApplyRequest:
        # Mirrors the DB constraint vendor_licences_dates_ordered: fail fast
        # with a 422 instead of a DB error.
        if self.issued_on is not None and self.expires_on < self.issued_on:
            raise ValueError("expires_on must be on or after issued_on")
        return self


class VerifyLicenceRequest(StrictModel):
    reviewer_notes: str | None = Field(default=None, max_length=2000)


class LicenceDecisionRequest(StrictModel):
    """Reject/revoke body — notes are mandatory and must be substantive."""

    reviewer_notes: str = Field(min_length=10, max_length=2000)

    @field_validator("reviewer_notes")
    @classmethod
    def validate_notes_substantive(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 10:
            raise ValueError("reviewer_notes must be at least 10 characters")
        return cleaned


class LicenceOut(StrictModel):
    id: str
    vendor_id: str
    regulated_class: str
    regulator: str
    licence_number: str
    issued_on: str | None
    expires_on: str
    document_path: str | None
    status: str
    reviewer_notes: str | None
    verified_by: str | None
    verified_at: str | None
    created_at: str | None
    updated_at: str | None


class LicenceListResponse(StrictModel):
    items: list[LicenceOut]


class AdminLicenceQueueItem(LicenceOut):
    vendor_display_name: str | None
    vendor_slug: str | None


class AdminLicenceQueueResponse(StrictModel):
    items: list[AdminLicenceQueueItem]
    limit: int
    offset: int


class ExpiringLicenceItem(LicenceOut):
    vendor_display_name: str | None
    vendor_slug: str | None
    days_left: int


class ExpiringLicencesResponse(StrictModel):
    items: list[ExpiringLicenceItem]
    days: int


class LicenceDecisionResponse(StrictModel):
    licence_id: str
    vendor_id: str
    regulated_class: str
    status: str
    verified_by: str | None
    verified_at: str | None


class LicenceBadgeResponse(StrictModel):
    """Public derived badge — a boolean and NOTHING else."""

    valid: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _require_known_class(value: str) -> str:
    if value not in REGULATED_CLASSES:
        raise AppError(
            code="licence.unknown_class",
            message="Unknown regulated class",
            http_status=422,
            details={"allowed": sorted(REGULATED_CLASSES)},
        )
    return value


def _load_vendor_for_owner(
    service_client: _ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def _load_licence_row(
    service_client: _ServiceRoleClient,
    licence_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendor_licences")
        .select(
            "id, vendor_id, regulated_class, regulator, licence_number, issued_on, "
            "expires_on, document_path, status, reviewer_notes, verified_by, "
            "verified_at, created_at, updated_at"
        )
        .eq("id", licence_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Licence not found", http_status=404)
    return row


def _vendor_summary(
    service_client: _ServiceRoleClient,
    vendor_id: str,
) -> tuple[str | None, str | None]:
    response = (
        service_client.client.table("vendors")
        .select("id, display_name, slug")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None, None
    return _opt_str(row.get("display_name")), _opt_str(row.get("slug"))


def _licence_out(row: dict[str, Any]) -> LicenceOut:
    return LicenceOut(
        id=str(row["id"]),
        vendor_id=str(row["vendor_id"]),
        regulated_class=str(row["regulated_class"]),
        regulator=str(row["regulator"]),
        licence_number=str(row["licence_number"]),
        issued_on=_opt_str(row.get("issued_on")),
        expires_on=str(row["expires_on"]),
        document_path=_opt_str(row.get("document_path")),
        status=str(row["status"]),
        reviewer_notes=_opt_str(row.get("reviewer_notes")),
        verified_by=_opt_str(row.get("verified_by")),
        verified_at=_opt_str(row.get("verified_at")),
        created_at=_opt_str(row.get("created_at")),
        updated_at=_opt_str(row.get("updated_at")),
    )


def _rate_limit_apply(service_client: _ServiceRoleClient, vendor_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=VENDOR_LICENCE_APPLY_POLICY.scope,
        key=vendor_id,
        window=VENDOR_LICENCE_APPLY_POLICY.window,
        limit=VENDOR_LICENCE_APPLY_POLICY.limit,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="vendor.licences.errors.rateLimited",
            message="Too many licence applications",
        )


# ---------------------------------------------------------------------------
# Vendor-side endpoints
# ---------------------------------------------------------------------------


@router.post("/vendor/licences", response_model=LicenceOut, status_code=201)
def apply_for_licence(
    body: LicenceApplyRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> LicenceOut:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    _require_known_class(body.regulated_class)
    _rate_limit_apply(service_client, vendor_id)

    existing = (
        service_client.client.table("vendor_licences")
        .select("id, status")
        .eq("vendor_id", vendor_id)
        .eq("regulated_class", body.regulated_class)
        .in_("status", list(LIVE_STATUSES))
        .execute()
    )
    if _rows(existing):
        raise AppError(
            code="licence.already_applied",
            message="A live licence application already exists for this class",
            http_status=409,
            details={"regulated_class": body.regulated_class},
        )

    insert_payload: dict[str, Any] = {
        "vendor_id": vendor_id,
        "regulated_class": body.regulated_class,
        "regulator": body.regulator.strip(),
        "licence_number": body.licence_number.strip(),
        "issued_on": body.issued_on.isoformat() if body.issued_on else None,
        "expires_on": body.expires_on.isoformat(),
        "document_path": body.document_path,
        # Pinned server-side. The request model discards any client-sent status
        # and the DB guard trigger rejects non-service-role status writes.
        "status": "pending",
    }
    try:
        response = service_client.client.table("vendor_licences").insert(insert_payload).execute()
    except Exception as exc:
        # Insert race on vendor_licences_one_live_per_class: the pre-check above
        # passed but a concurrent application landed first. Never include the
        # DB error text in the response — it can echo row values.
        if "vendor_licences_one_live_per_class" in str(exc) or "duplicate" in str(exc).lower():
            raise AppError(
                code="licence.already_applied",
                message="A live licence application already exists for this class",
                http_status=409,
                details={"regulated_class": body.regulated_class},
            ) from exc
        raise

    row = _single_row(response)
    if row is None:
        raise AppError(
            code="licence.apply_failed",
            message="Failed to store licence application",
            http_status=500,
        )
    return _licence_out(row)


@router.get("/vendor/licences", response_model=LicenceListResponse)
def list_own_licences(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> LicenceListResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    response = (
        service_client.client.table("vendor_licences")
        .select(
            "id, vendor_id, regulated_class, regulator, licence_number, issued_on, "
            "expires_on, document_path, status, reviewer_notes, verified_by, "
            "verified_at, created_at, updated_at"
        )
        .eq("vendor_id", str(vendor["id"]))
        .order("created_at", desc=True)
        .execute()
    )
    return LicenceListResponse(items=[_licence_out(row) for row in _rows(response)])


# ---------------------------------------------------------------------------
# Public derived badge — boolean only, no auth
# ---------------------------------------------------------------------------


@router.get("/vendors/{vendor_id}/licence-badge", response_model=LicenceBadgeResponse)
def licence_badge(
    vendor_id: UUID,
    regulated_class: Annotated[str, Query(alias="class", min_length=1, max_length=64)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> LicenceBadgeResponse:
    """Derived validity via the vendor_licence_is_valid RPC.

    Returns the same ``{"valid": false}`` for an unknown vendor as for a known
    vendor without a valid licence — no existence oracle. Never discloses the
    licence number, dates, or notes. Fails CLOSED: if the lookup fails the
    platform does not vouch for the licence.
    """
    _require_known_class(regulated_class)
    try:
        response = service_client.client.rpc(
            "vendor_licence_is_valid",
            {"p_vendor_id": str(vendor_id), "p_class": regulated_class},
        ).execute()
    except Exception:
        logger.warning("licence badge validity lookup failed; failing closed", exc_info=True)
        return LicenceBadgeResponse(valid=False)

    data = getattr(response, "data", None)
    valid = data is True or (isinstance(data, list) and len(data) == 1 and data[0] is True)
    return LicenceBadgeResponse(valid=valid)


# ---------------------------------------------------------------------------
# Admin endpoints — audited human decisions only. No AI/LLM is ever consulted
# or permitted to decide here (repo-wide rule).
# ---------------------------------------------------------------------------


@licences_admin_router.get("", response_model=AdminLicenceQueueResponse)
def list_licence_queue(
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[LicenceStatus, Query()] = "pending",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminLicenceQueueResponse:
    response = (
        service_client.client.table("vendor_licences")
        .select(
            "id, vendor_id, regulated_class, regulator, licence_number, issued_on, "
            "expires_on, document_path, status, reviewer_notes, verified_by, "
            "verified_at, created_at, updated_at"
        )
        .eq("status", status)
        .order("created_at", desc=False)
        .limit(limit)
        .offset(offset)
        .execute()
    )
    items: list[AdminLicenceQueueItem] = []
    for row in _rows(response):
        display_name, slug = _vendor_summary(service_client, str(row["vendor_id"]))
        items.append(
            AdminLicenceQueueItem(
                **_licence_out(row).model_dump(),
                vendor_display_name=display_name,
                vendor_slug=slug,
            )
        )
    return AdminLicenceQueueResponse(items=items, limit=limit, offset=offset)


@licences_admin_router.get("/expiring", response_model=ExpiringLicencesResponse)
def list_expiring_licences(
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> ExpiringLicencesResponse:
    """Operational chase-renewals queue: verified licences expiring within N days.

    Validity itself stays derived (a lapsed badge disappears on its own); this
    queue exists so an admin can nudge the vendor BEFORE that happens.
    """
    today = datetime.now(UTC).date()
    horizon = today + timedelta(days=days)
    response = (
        service_client.client.table("vendor_licences")
        .select(
            "id, vendor_id, regulated_class, regulator, licence_number, issued_on, "
            "expires_on, document_path, status, reviewer_notes, verified_by, "
            "verified_at, created_at, updated_at"
        )
        .eq("status", "verified")
        .gte("expires_on", today.isoformat())
        .lte("expires_on", horizon.isoformat())
        .order("expires_on", desc=False)
        .execute()
    )
    items: list[ExpiringLicenceItem] = []
    for row in _rows(response):
        display_name, slug = _vendor_summary(service_client, str(row["vendor_id"]))
        expires_on = date.fromisoformat(str(row["expires_on"]))
        items.append(
            ExpiringLicenceItem(
                **_licence_out(row).model_dump(),
                vendor_display_name=display_name,
                vendor_slug=slug,
                days_left=(expires_on - today).days,
            )
        )
    return ExpiringLicencesResponse(items=items, days=days)


def _decide_licence(
    *,
    action: str,
    licence_id: str,
    allowed_from: tuple[str, ...],
    target_status: str,
    extra_updates: dict[str, Any],
    reviewer_notes: str | None,
    service_client: _ServiceRoleClient,
    recorder: AdminAuditRecorder,
) -> LicenceDecisionResponse:
    row = _load_licence_row(service_client, licence_id)
    current_status = str(row["status"])
    if current_status not in allowed_from:
        # Covers e.g. verifying an already-revoked licence → 409. Details never
        # include the licence number.
        raise AppError(
            code="licence.invalid_transition",
            message=f"Cannot {action} a licence in status {current_status}",
            http_status=409,
            details={"from": current_status, "action": action},
        )

    update_payload: dict[str, Any] = {"status": target_status, **extra_updates}
    if reviewer_notes is not None:
        update_payload["reviewer_notes"] = reviewer_notes

    response = (
        service_client.client.table("vendor_licences")
        .update(update_payload)
        .eq("id", licence_id)
        .eq("status", current_status)
        .execute()
    )
    updated = _rows(response)
    if not updated:
        # Optimistic concurrency: another admin decided between load and update.
        raise AppError(
            code="licence.conflict",
            message="Licence was decided concurrently; reload and retry",
            http_status=409,
        )
    updated_row = updated[0]

    # Audit payloads deliberately EXCLUDE licence_number (commercially
    # sensitive — never logged, and audit rows are log-adjacent).
    recorder.record(
        action=f"admin.licence.{action}",
        entity_type="vendor_licence",
        entity_id=licence_id,
        before={
            "vendor_id": str(row["vendor_id"]),
            "regulated_class": str(row["regulated_class"]),
            "status": current_status,
            "reviewer_notes": _opt_str(row.get("reviewer_notes")),
        },
        after={
            "vendor_id": str(row["vendor_id"]),
            "regulated_class": str(row["regulated_class"]),
            "status": target_status,
            "reviewer_notes": _opt_str(updated_row.get("reviewer_notes")),
        },
    )

    return LicenceDecisionResponse(
        licence_id=str(updated_row["id"]),
        vendor_id=str(updated_row["vendor_id"]),
        regulated_class=str(updated_row["regulated_class"]),
        status=str(updated_row["status"]),
        verified_by=_opt_str(updated_row.get("verified_by")),
        verified_at=_opt_str(updated_row.get("verified_at")),
    )


@licences_admin_router.post("/{licence_id}/verify", response_model=LicenceDecisionResponse)
def verify_licence(
    licence_id: UUID,
    body: VerifyLicenceRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> LicenceDecisionResponse:
    return _decide_licence(
        action="verify",
        licence_id=str(licence_id),
        allowed_from=("pending",),
        target_status="verified",
        extra_updates={
            "verified_by": current_user.id,
            "verified_at": datetime.now(UTC).isoformat(),
        },
        reviewer_notes=body.reviewer_notes,
        service_client=service_client,
        recorder=recorder,
    )


@licences_admin_router.post("/{licence_id}/reject", response_model=LicenceDecisionResponse)
def reject_licence(
    licence_id: UUID,
    body: LicenceDecisionRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> LicenceDecisionResponse:
    _ = current_user  # decision attribution lives in the audit row (recorder actor)
    return _decide_licence(
        action="reject",
        licence_id=str(licence_id),
        allowed_from=("pending",),
        target_status="rejected",
        extra_updates={},
        reviewer_notes=body.reviewer_notes,
        service_client=service_client,
        recorder=recorder,
    )


@licences_admin_router.post("/{licence_id}/revoke", response_model=LicenceDecisionResponse)
def revoke_licence(
    licence_id: UUID,
    body: LicenceDecisionRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> LicenceDecisionResponse:
    _ = current_user  # decision attribution lives in the audit row (recorder actor)
    return _decide_licence(
        action="revoke",
        licence_id=str(licence_id),
        allowed_from=("verified",),
        target_status="revoked",
        extra_updates={},
        reviewer_notes=body.reviewer_notes,
        service_client=service_client,
        recorder=recorder,
    )


admin_router.include_router(licences_admin_router)
