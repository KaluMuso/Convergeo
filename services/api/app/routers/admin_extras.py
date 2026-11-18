"""Admin: paid extras catalogue + request queue, and seller free trials.

Mounted on the shared ``/admin`` router (``require_admin_scope`` + audited route
class): every mutation writes exactly one ``audit_log`` row. Catalogue prices and
trials are money-adjacent, so those routes are NOT in the RBAC permission map
(only ``admin``/``superadmin``); the request queue maps to ``vendors.manage``.

Every mutation: admin authz (router dependency) + strict Pydantic + an in-router
``ADMIN_WRITE`` rate limit keyed by the acting admin. No money is collected.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import ADMIN_WRITE
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.routers.vendor_extras import (
    EXTRA_COLUMNS,
    REQUEST_COLUMNS,
    ExtraOut,
    extra_from_row,
    map_transition_error,
)
from app.schemas.base import NgweeInt, StrictModel
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.vendor_plans.billing import in_trial, parse_ts
from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

extras_router = APIRouter(prefix="/extras", tags=["admin-extras"])
trials_router = APIRouter(prefix="/trials", tags=["admin-trials"])

MAX_PRICE_NGWEE = 100_000_000
MAX_TRIAL_DAYS_AHEAD = 366
Pricing = Literal["fixed", "range", "pay_as_you_go"]
Unit = Literal["one_off", "per_month", "per_item"]
RequestStatus = Literal["requested", "quoted", "approved", "fulfilled", "cancelled"]


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


def validate_price_shape(
    pricing: str, price_ngwee: int | None, price_max_ngwee: int | None
) -> None:
    """Mirror of the vendor_extras_price_shape constraint (friendly 422)."""
    ok = (
        (pricing == "fixed" and price_ngwee is not None and price_max_ngwee is None)
        or (
            pricing == "range"
            and price_ngwee is not None
            and price_max_ngwee is not None
            and price_max_ngwee > price_ngwee
        )
        or (pricing == "pay_as_you_go" and price_max_ngwee is None)
    )
    if not ok:
        raise AppError(
            code="validation_error",
            message="price does not match the pricing type",
            http_status=422,
            details={"message_key": "admin.extras.errors.priceShape"},
        )


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
class AdminExtraOut(ExtraOut):
    active: bool = True
    position: int = 0


class ExtraCreate(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,47}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    pricing: Pricing = "fixed"
    price_ngwee: NgweeInt | None = Field(default=None, le=MAX_PRICE_NGWEE)
    price_max_ngwee: NgweeInt | None = Field(default=None, le=MAX_PRICE_NGWEE)
    unit: Unit = "one_off"
    active: bool = True
    position: int = Field(default=0, ge=0, le=1000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class ExtraUpdate(StrictModel):
    """Partial update; send ``price_max_ngwee: null`` to clear a range."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    pricing: Pricing | None = None
    price_ngwee: NgweeInt | None = Field(default=None, le=MAX_PRICE_NGWEE)
    price_max_ngwee: NgweeInt | None = Field(default=None, le=MAX_PRICE_NGWEE)
    unit: Unit | None = None
    active: bool | None = None
    position: int | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def at_least_one(self) -> ExtraUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        nullable = {"price_ngwee", "price_max_ngwee"}
        for field in self.model_fields_set - nullable:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.name is not None and not self.name.strip():
            raise ValueError("name must not be blank")
        return self


def _admin_extra(row: dict[str, Any]) -> AdminExtraOut:
    base = extra_from_row(row)
    return AdminExtraOut(
        **base.model_dump(),
        active=row.get("active") is not False,
        position=int(row.get("position") or 0),
    )


def _load_extra(client: Any, key: str) -> dict[str, Any]:
    rows = _rows(client.table("vendor_extras").select(EXTRA_COLUMNS).eq("key", key).execute())
    if not rows:
        raise _not_found("Extra")
    return rows[0]


@extras_router.get("", response_model=list[AdminExtraOut])
async def list_extras_admin(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[AdminExtraOut]:
    rows = _rows(
        service_client.client.table("vendor_extras")
        .select(EXTRA_COLUMNS)
        .order("position")
        .execute()
    )
    return [_admin_extra(row) for row in rows]


@extras_router.post("", response_model=AdminExtraOut, status_code=201)
async def create_extra(
    body: ExtraCreate,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AdminExtraOut:
    client: Any = service_client.client
    _limit(client, user.id)
    validate_price_shape(body.pricing, body.price_ngwee, body.price_max_ngwee)
    if _rows(client.table("vendor_extras").select("key").eq("key", body.key).execute()):
        raise AppError(
            code="conflict",
            message="extra key already exists",
            http_status=409,
            details={"message_key": "admin.extras.errors.duplicateKey"},
        )
    row = body.model_dump()
    created = _rows(client.table("vendor_extras").insert(row).execute())
    after = created[0] if created else row
    recorder.record(
        action="extras.create",
        entity_type="vendor_extra",
        entity_id=None,
        before=None,
        after={**after},
    )
    return _admin_extra(after)


@extras_router.patch("/{extra_key}", response_model=AdminExtraOut)
async def update_extra(
    extra_key: Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]{1,47}$")],
    body: ExtraUpdate,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AdminExtraOut:
    client: Any = service_client.client
    _limit(client, user.id)
    before = _load_extra(client, extra_key)
    patch = {field: getattr(body, field) for field in body.model_fields_set}
    if "name" in patch:
        patch["name"] = str(patch["name"]).strip()
    merged = {**before, **patch}
    validate_price_shape(
        str(merged.get("pricing")), merged.get("price_ngwee"), merged.get("price_max_ngwee")
    )
    if {"price_ngwee", "price_max_ngwee", "pricing"} & set(patch):
        patch["price_is_placeholder"] = False  # an admin has now set the price
    client.table("vendor_extras").update(patch).eq("key", extra_key).execute()
    after = _load_extra(client, extra_key)
    recorder.record(
        action="extras.update",
        entity_type="vendor_extra",
        entity_id=None,
        before={"key": extra_key, **{k: before.get(k) for k in patch}},
        after={"key": extra_key, **patch},
    )
    return _admin_extra(after)


# ---------------------------------------------------------------------------
# Request queue
# ---------------------------------------------------------------------------
class AdminRequestOut(BaseModel):
    id: str
    vendor_id: str
    vendor_name: str | None = None
    vendor_slug: str | None = None
    extra_key: str
    extra_name: str | None = None
    quantity: int
    note: str | None = None
    status: str
    quoted_price_ngwee: int | None = None
    admin_note: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TransitionRequest(StrictModel):
    to: Literal["quoted", "approved", "fulfilled", "cancelled"]
    note: str | None = Field(default=None, max_length=1000)
    quoted_price_ngwee: NgweeInt | None = Field(default=None, le=MAX_PRICE_NGWEE)

    @model_validator(mode="after")
    def quote_shape(self) -> TransitionRequest:
        if self.to == "quoted" and self.quoted_price_ngwee is None:
            raise ValueError("quoted_price_ngwee is required to quote")
        if self.to != "quoted" and self.quoted_price_ngwee is not None:
            raise ValueError("quoted_price_ngwee is only allowed when quoting")
        return self


def _admin_request(
    row: dict[str, Any], vendors: dict[str, dict[str, Any]], names: dict[str, str]
) -> AdminRequestOut:
    vendor = vendors.get(str(row.get("vendor_id")), {})
    quoted = row.get("quoted_price_ngwee")
    return AdminRequestOut(
        id=str(row["id"]),
        vendor_id=str(row["vendor_id"]),
        vendor_name=vendor.get("display_name"),
        vendor_slug=vendor.get("slug"),
        extra_key=str(row["extra_key"]),
        extra_name=names.get(str(row["extra_key"])),
        quantity=int(row.get("quantity") or 1),
        note=row.get("note"),
        status=str(row["status"]),
        quoted_price_ngwee=int(quoted) if isinstance(quoted, int) else None,
        admin_note=row.get("admin_note"),
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
    )


def _enrich(client: Any, rows: list[dict[str, Any]]) -> list[AdminRequestOut]:
    vendor_ids = sorted({str(row["vendor_id"]) for row in rows})
    vendors: dict[str, dict[str, Any]] = {}
    if vendor_ids:
        vendors = {
            str(v["id"]): v
            for v in _rows(
                client.table("vendors")
                .select("id, display_name, slug")
                .in_("id", vendor_ids)
                .execute()
            )
        }
    names = {
        str(e["key"]): str(e.get("name") or e["key"])
        for e in _rows(client.table("vendor_extras").select("key, name").execute())
    }
    return [_admin_request(row, vendors, names) for row in rows]


@extras_router.get("/requests", response_model=list[AdminRequestOut])
async def list_extra_requests(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    status: Annotated[RequestStatus | None, Query()] = None,
) -> list[AdminRequestOut]:
    client: Any = service_client.client
    query = client.table("vendor_extras_requests").select(REQUEST_COLUMNS)
    if status is not None:
        query = query.eq("status", status)
    rows = _rows(query.order("created_at", desc=True).limit(200).execute())
    return _enrich(client, rows)


@extras_router.post("/requests/{request_id}/transition", response_model=AdminRequestOut)
async def transition_extra_request(
    request_id: UUID,
    body: TransitionRequest,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AdminRequestOut:
    client: Any = service_client.client
    _limit(client, user.id)
    before = _rows(
        client.table("vendor_extras_requests")
        .select(REQUEST_COLUMNS)
        .eq("id", str(request_id))
        .execute()
    )
    if not before:
        raise _not_found("Extras request")
    note = body.note.strip() if body.note and body.note.strip() else None
    try:
        client.rpc(
            "transition_vendor_extras_request",
            {
                "p_request_id": str(request_id),
                "p_to": body.to,
                "p_actor": user.id,
                "p_actor_role": "admin",
                "p_note": note,
                "p_quoted_price_ngwee": body.quoted_price_ngwee,
            },
        ).execute()
    except Exception as exc:  # noqa: BLE001 — DB refusal -> stable error
        raise map_transition_error(exc) from exc
    after = _rows(
        client.table("vendor_extras_requests")
        .select(REQUEST_COLUMNS)
        .eq("id", str(request_id))
        .execute()
    )
    after_row = after[0] if after else before[0]
    recorder.record(
        action=f"extras.request.{body.to}",
        entity_type="vendor_extras_request",
        entity_id=str(request_id),
        before={
            "status": before[0].get("status"),
            "quoted_price_ngwee": before[0].get("quoted_price_ngwee"),
        },
        after={
            "status": after_row.get("status"),
            "quoted_price_ngwee": after_row.get("quoted_price_ngwee"),
            "note": note,
        },
    )
    return _enrich(client, [after_row])[0]


# ---------------------------------------------------------------------------
# Free trials (on the business = billing owner of every shop)
# ---------------------------------------------------------------------------
class TrialOut(BaseModel):
    business_id: str
    legal_name: str
    trial_ends_at: str | None = None
    in_trial: bool = False


class TrialChange(BaseModel):
    # Not strict: ends_at arrives as an ISO string (same as plan overrides).
    model_config = ConfigDict(extra="forbid")

    action: Literal["extend", "end"]
    #: Required for ``extend``: the new end, later than the current one.
    ends_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def shape(self) -> TrialChange:
        if not self.reason.strip():
            raise ValueError("reason is required")
        if self.action == "extend":
            if self.ends_at is None:
                raise ValueError("ends_at is required to extend")
            if self.ends_at.tzinfo is None:
                raise ValueError("ends_at must include a timezone")
            if self.ends_at > datetime.now(UTC) + timedelta(days=MAX_TRIAL_DAYS_AHEAD):
                raise ValueError("ends_at is too far ahead")
        elif self.ends_at is not None:
            raise ValueError("ends_at is only used to extend")
        return self


def _trial_out(row: dict[str, Any]) -> TrialOut:
    ends = parse_ts(row.get("trial_ends_at"))
    return TrialOut(
        business_id=str(row["id"]),
        legal_name=str(row.get("legal_name") or ""),
        trial_ends_at=ends.isoformat() if ends else None,
        in_trial=in_trial(ends),
    )


@trials_router.get("", response_model=list[TrialOut])
async def list_trials(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    q: Annotated[str | None, Query(max_length=80)] = None,
    active_only: Annotated[bool, Query()] = False,
) -> list[TrialOut]:
    client: Any = service_client.client
    query = client.table("vendor_businesses").select("id, legal_name, trial_ends_at")
    if q and q.strip():
        safe = "".join(ch for ch in q.strip() if ch.isalnum() or ch in " -'&.")
        if safe:
            query = query.ilike("legal_name", f"%{safe}%")
    if active_only:
        query = query.gt("trial_ends_at", datetime.now(UTC).isoformat())
    rows = _rows(query.order("trial_ends_at").limit(200).execute())
    return [_trial_out(row) for row in rows]


@trials_router.post("/{business_id}", response_model=TrialOut)
async def change_trial(
    business_id: UUID,
    body: TrialChange,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> TrialOut:
    client: Any = service_client.client
    _limit(client, user.id)
    rows = _rows(
        client.table("vendor_businesses")
        .select("id, legal_name, trial_ends_at")
        .eq("id", str(business_id))
        .execute()
    )
    if not rows:
        raise _not_found("Business")
    current = parse_ts(rows[0].get("trial_ends_at"))
    now = datetime.now(UTC)
    if body.action == "extend":
        assert body.ends_at is not None
        floor = max(current or now, now)
        if body.ends_at <= floor:
            raise AppError(
                code="validation_error",
                message="ends_at must be later than the current trial end",
                http_status=422,
                details={"message_key": "admin.trials.errors.notLater"},
            )
        new_end = body.ends_at
    else:
        if current is None or current <= now:
            raise AppError(
                code="conflict",
                message="trial already ended",
                http_status=409,
                details={"message_key": "admin.trials.errors.alreadyEnded"},
            )
        new_end = now
    client.table("vendor_businesses").update({"trial_ends_at": new_end.isoformat()}).eq(
        "id", str(business_id)
    ).execute()
    recorder.record(
        action=f"trials.{body.action}",
        entity_type="vendor_business",
        entity_id=str(business_id),
        before={"trial_ends_at": current.isoformat() if current else None},
        after={"trial_ends_at": new_end.isoformat(), "reason": body.reason.strip()},
    )
    return _trial_out({**rows[0], "trial_ends_at": new_end.isoformat()})


admin_router.include_router(extras_router)
admin_router.include_router(trials_router)
