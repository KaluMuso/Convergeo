"""Create / list / pause coupons for admins (platform-funded) and vendors (own shop)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal

from app.errors import AppError
from app.services.coupons.rules import CouponError, lusaka_day_start
from app.services.coupons.store import COUPON_COLUMNS, ServiceRoleClient, normalize_code
from postgrest.exceptions import APIError
from pydantic import BaseModel, ConfigDict, Field

CouponStatus = Literal["active", "paused", "archived"]
DEFAULT_VENDOR_MAX_PERCENT_BPS = 5_000
_UNIQUE_VIOLATION = "23505"


class CouponCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=3, max_length=32)
    title: str | None = Field(default=None, max_length=80)
    kind: Literal["percent", "fixed"]
    percent_bps: int | None = Field(default=None, ge=1, le=10_000)
    amount_ngwee: int | None = Field(default=None, gt=0, le=100_000_000)
    max_discount_ngwee: int | None = Field(default=None, gt=0, le=100_000_000)
    scope: Literal["all", "vendor", "category", "listing"] = "all"
    scope_id: str | None = Field(default=None, min_length=36, max_length=36)
    min_spend_ngwee: int = Field(default=0, ge=0, le=100_000_000)
    #: Local Lusaka calendar dates; ``ends_on`` is inclusive (the code works all day).
    starts_on: date
    ends_on: date | None = None
    total_limit: int | None = Field(default=None, gt=0, le=1_000_000)
    per_user_limit: int = Field(default=1, ge=1, le=100)


class CouponStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CouponStatus


class CouponOut(BaseModel):
    id: str
    code: str
    title: str | None = None
    kind: str
    percent_bps: int | None = None
    amount_ngwee: int | None = None
    max_discount_ngwee: int | None = None
    funder: str
    vendor_id: str | None = None
    scope: str
    scope_id: str | None = None
    min_spend_ngwee: int
    starts_at: str
    ends_at: str | None = None
    total_limit: int | None = None
    per_user_limit: int
    uses_count: int
    source: str
    status: str


class CouponListResponse(BaseModel):
    coupons: list[CouponOut]


def coupon_out(row: dict[str, Any]) -> CouponOut:
    scope = str(row.get("scope") or "all")
    scope_id = {
        "vendor": row.get("scope_vendor_id"),
        "category": row.get("scope_category_id"),
        "listing": row.get("scope_listing_id"),
    }.get(scope)
    return CouponOut(
        id=str(row["id"]),
        code=str(row["code"]),
        title=row.get("title"),
        kind=str(row["kind"]),
        percent_bps=row.get("percent_bps"),
        amount_ngwee=row.get("amount_ngwee"),
        max_discount_ngwee=row.get("max_discount_ngwee"),
        funder=str(row["funder"]),
        vendor_id=row.get("vendor_id"),
        scope=scope,
        scope_id=str(scope_id) if scope_id else None,
        min_spend_ngwee=int(row.get("min_spend_ngwee") or 0),
        starts_at=str(row["starts_at"]),
        ends_at=str(row["ends_at"]) if row.get("ends_at") else None,
        total_limit=row.get("total_limit"),
        per_user_limit=int(row.get("per_user_limit") or 1),
        uses_count=int(row.get("uses_count") or 0),
        source=str(row.get("source") or "admin"),
        status=str(row.get("status") or "active"),
    )


def _invalid(field: str, key: str) -> AppError:
    return AppError(
        code="validation_error",
        message="Coupon details are not valid",
        http_status=422,
        details={"field": field, "message_key": f"coupons.form.errors.{key}"},
    )


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def vendor_max_percent_bps(service: ServiceRoleClient) -> int:
    try:
        rows = _rows(
            service.client.table("platform_config")
            .select("value")
            .eq("key", "vendor_coupon_max_percent_bps")
            .execute()
        )
    except Exception:
        return DEFAULT_VENDOR_MAX_PERCENT_BPS
    value = rows[0].get("value") if rows else None
    return (
        value if isinstance(value, int) and 0 < value <= 10_000 else DEFAULT_VENDOR_MAX_PERCENT_BPS
    )


def build_coupon_row(
    body: CouponCreateRequest,
    *,
    funder: Literal["platform", "vendor"],
    vendor_id: str | None,
    actor_id: str,
    max_percent_bps: int = 10_000,
    today: date | None = None,
) -> dict[str, Any]:
    """Validate a create request into an insertable row (pure; no I/O)."""
    try:
        code = normalize_code(body.code)
    except CouponError as exc:
        raise _invalid("code", "code") from exc
    if body.kind == "percent":
        if body.percent_bps is None or body.amount_ngwee is not None:
            raise _invalid("percent_bps", "percent")
        if body.percent_bps > max_percent_bps:
            raise _invalid("percent_bps", "percentTooHigh")
    elif body.amount_ngwee is None or body.percent_bps is not None:
        raise _invalid("amount_ngwee", "amount")
    if body.ends_on is not None and body.ends_on < body.starts_on:
        raise _invalid("ends_on", "dates")
    if today is not None and body.ends_on is not None and body.ends_on < today:
        raise _invalid("ends_on", "dates")

    scope = body.scope
    scope_vendor_id: str | None = None
    scope_category_id: str | None = None
    scope_listing_id: str | None = None
    if funder == "vendor":
        if scope in {"all", "vendor"}:
            scope, scope_vendor_id = "vendor", vendor_id
        elif scope == "listing" and body.scope_id:
            scope_listing_id = body.scope_id
        else:
            raise _invalid("scope", "scope")
    elif scope == "vendor" and body.scope_id:
        scope_vendor_id = body.scope_id
    elif scope == "category" and body.scope_id:
        scope_category_id = body.scope_id
    elif scope == "listing" and body.scope_id:
        scope_listing_id = body.scope_id
    elif scope != "all":
        raise _invalid("scope_id", "scope")

    starts_at = lusaka_day_start(body.starts_on.isoformat())
    ends_at: datetime | None = (
        lusaka_day_start(body.ends_on.isoformat()) + timedelta(days=1) if body.ends_on else None
    )
    return {
        "code": code,
        "title": body.title.strip() if body.title else None,
        "kind": body.kind,
        "percent_bps": body.percent_bps if body.kind == "percent" else None,
        "amount_ngwee": body.amount_ngwee if body.kind == "fixed" else None,
        "max_discount_ngwee": body.max_discount_ngwee,
        "funder": funder,
        "vendor_id": vendor_id if funder == "vendor" else None,
        "scope": scope,
        "scope_vendor_id": scope_vendor_id,
        "scope_category_id": scope_category_id,
        "scope_listing_id": scope_listing_id,
        "min_spend_ngwee": body.min_spend_ngwee,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat() if ends_at else None,
        "total_limit": body.total_limit,
        "per_user_limit": body.per_user_limit,
        "source": "vendor" if funder == "vendor" else "admin",
        "status": "active",
        "created_by": actor_id,
    }


def insert_coupon(service: ServiceRoleClient, row: dict[str, Any], *, actor_id: str) -> CouponOut:
    try:
        response = service.client.table("coupons").insert(row).execute()
    except APIError as exc:
        if getattr(exc, "code", None) == _UNIQUE_VIOLATION:
            raise AppError(
                code="coupon.code_taken",
                message="That code is already in use",
                http_status=409,
                details={"field": "code", "message_key": "coupons.form.errors.codeTaken"},
            ) from exc
        raise
    rows = _rows(response)
    if not rows:
        raise AppError(code="coupon.create_failed", message="Coupon not saved", http_status=500)
    created = rows[0]
    _audit(service, actor_id, "coupon.created", str(created["id"]), None, {"code": row["code"]})
    return coupon_out(created)


def _audit(
    service: ServiceRoleClient,
    actor_id: str,
    action: str,
    coupon_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> None:
    service.client.table("audit_log").insert(
        {
            "actor": actor_id,
            "action": action,
            "entity_type": "coupon",
            "entity_id": coupon_id,
            "before": before,
            "after": after,
        }
    ).execute()


def list_coupons(service: ServiceRoleClient, *, vendor_id: str | None) -> CouponListResponse:
    query = service.client.table("coupons").select(COUPON_COLUMNS)
    query = query.eq("vendor_id", vendor_id) if vendor_id else query.eq("funder", "platform")
    rows = _rows(
        query.neq("source", "birthday").order("created_at", desc=True).limit(200).execute()
    )
    return CouponListResponse(coupons=[coupon_out(row) for row in rows])


def set_coupon_status(
    service: ServiceRoleClient,
    *,
    coupon_id: str,
    status: CouponStatus,
    actor_id: str,
    vendor_id: str | None,
) -> CouponOut:
    query = service.client.table("coupons").select(COUPON_COLUMNS).eq("id", coupon_id)
    query = query.eq("vendor_id", vendor_id) if vendor_id else query.eq("funder", "platform")
    rows = _rows(query.limit(1).execute())
    if not rows:
        raise AppError(code="not_found", message="Coupon not found", http_status=404)
    current = rows[0]
    if current.get("status") == "archived" and status != "archived":
        raise AppError(
            code="coupon.archived",
            message="Archived coupons cannot be reopened",
            http_status=409,
            details={"message_key": "coupons.form.errors.archived"},
        )
    updated = _rows(
        service.client.table("coupons").update({"status": status}).eq("id", coupon_id).execute()
    )
    _audit(
        service,
        actor_id,
        "coupon.status_changed",
        coupon_id,
        {"status": current.get("status")},
        {"status": status},
    )
    return coupon_out(updated[0] if updated else {**current, "status": status})


def assert_vendor_owns_listing(
    service: ServiceRoleClient, *, vendor_id: str, listing_id: str
) -> None:
    rows = _rows(
        service.client.table("vendor_listings")
        .select("id")
        .eq("id", listing_id)
        .eq("vendor_id", vendor_id)
        .limit(1)
        .execute()
    )
    if not rows:
        raise _invalid("scope_id", "listing")
