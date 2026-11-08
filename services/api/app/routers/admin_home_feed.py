"""Admin CRUD for home feed sections and ad placements (``ads.manage``).

Mounted on the shared ``/admin`` router, so ``require_admin_scope`` + the audited
route class apply: every mutation records exactly one ``audit_log`` row. Ad
status changes go through the ``transition_ad_placement`` SQL function (guarded
state machine + ``ad_placement_transitions`` history) — never a raw UPDATE.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.home_feed.models import (
    PlacementCreate,
    PlacementOut,
    PlacementStats,
    PlacementUpdate,
    ReorderRequest,
    SectionConfig,
    SectionCreate,
    SectionOut,
    SectionUpdate,
    TransitionRequest,
    validate_cta_href,
    validate_section_shape,
)
from app.services.home_feed.resolver import (
    PLACEMENT_COLUMNS,
    SECTION_COLUMNS,
    build_feed_page,
    parse_ts,
    placement_effective_state,
    section_is_live,
)
from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError

feed_admin_router = APIRouter(tags=["admin-home-feed"])

# Dummy public router export is intentionally absent: everything here is admin.
STATS_WINDOW_DAYS = 30


def allowed_external_hosts() -> frozenset[str]:
    """Comma-separated ``AD_EXTERNAL_HOST_ALLOWLIST``; empty = internal links only."""
    raw = os.environ.get("AD_EXTERNAL_HOST_ALLOWLIST", "")
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _one(response: Any, *, message: str) -> dict[str, Any]:
    rows = _rows(response)
    if not rows:
        raise AppError(code="internal_error", message=message, http_status=500)
    return rows[0]


def _not_found(kind: str, entity_id: UUID) -> AppError:
    return AppError(
        code="not_found",
        message=f"{kind} not found",
        http_status=404,
        details={"id": str(entity_id)},
    )


def _section_out(row: dict[str, Any], *, now: datetime) -> SectionOut:
    return SectionOut(
        id=str(row["id"]),
        key=str(row["key"]),
        section_type=row["section_type"],
        layout=row.get("layout") or "rail",
        title_key=row.get("title_key"),
        title_i18n=dict(row.get("title_i18n") or {}),
        config=dict(row.get("config") or {}),
        position=int(row.get("position") or 0),
        enabled=bool(row.get("enabled", True)),
        starts_at=parse_ts(row.get("starts_at")),
        ends_at=parse_ts(row.get("ends_at")),
        audience=row.get("audience") or "all",
        live=section_is_live(row, now=now, signed_in=False)
        or section_is_live(row, now=now, signed_in=True),
        updated_at=parse_ts(row.get("updated_at")),
    )


def _load_section(client: Any, section_id: UUID) -> dict[str, Any]:
    rows = _rows(
        client.table("home_feed_sections")
        .select(SECTION_COLUMNS)
        .eq("id", str(section_id))
        .execute()
    )
    if not rows:
        raise _not_found("Feed section", section_id)
    return rows[0]


def _validation(message: str) -> AppError:
    return AppError(code="validation_error", message=message, http_status=422)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


@feed_admin_router.get("/home-feed/sections", response_model=list[SectionOut])
async def list_feed_sections(
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> list[SectionOut]:
    rows = _rows(
        service_client.client.table("home_feed_sections")
        .select(SECTION_COLUMNS)
        .order("position", desc=False)
        .execute()
    )
    now = datetime.now(UTC)
    return [_section_out(row, now=now) for row in rows]


@feed_admin_router.post("/home-feed/sections", response_model=SectionOut, status_code=201)
async def create_feed_section(
    body: SectionCreate,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> SectionOut:
    existing = _rows(
        service_client.client.table("home_feed_sections").select("id").eq("key", body.key).execute()
    )
    if existing:
        raise AppError(code="conflict", message="Section key already exists", http_status=409)
    row = {
        "key": body.key,
        "section_type": body.section_type,
        "layout": body.layout,
        "title_key": body.title_key,
        "title_i18n": body.title_i18n,
        "config": body.config.model_dump(mode="json", exclude_none=True),
        "position": body.position,
        "enabled": body.enabled,
        "starts_at": body.starts_at.isoformat() if body.starts_at else None,
        "ends_at": body.ends_at.isoformat() if body.ends_at else None,
        "audience": body.audience,
        "created_by": user.id,
        "updated_by": user.id,
    }
    created = _one(
        service_client.client.table("home_feed_sections").insert(row).execute(),
        message="Failed to create feed section",
    )
    out = _section_out(created, now=datetime.now(UTC))
    recorder.record(
        action="home_feed.section.create",
        entity_type="home_feed_section",
        entity_id=out.id,
        before=None,
        after=out.model_dump(mode="json"),
    )
    return out


@feed_admin_router.patch("/home-feed/sections/{section_id}", response_model=SectionOut)
async def update_feed_section(
    section_id: UUID,
    body: SectionUpdate,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> SectionOut:
    before = _load_section(service_client.client, section_id)
    fields: dict[str, Any] = {}
    for name in ("title_key", "title_i18n", "layout", "position", "enabled", "audience"):
        value = getattr(body, name)
        if value is not None:
            fields[name] = value
    if body.config is not None:
        fields["config"] = body.config.model_dump(mode="json", exclude_none=True)
    if body.clear_schedule:
        fields["starts_at"] = None
        fields["ends_at"] = None
    if body.starts_at is not None:
        fields["starts_at"] = body.starts_at.isoformat()
    if body.ends_at is not None:
        fields["ends_at"] = body.ends_at.isoformat()

    merged = {**before, **fields}
    try:
        config = SectionConfig.model_validate(merged.get("config") or {})
        validate_section_shape(
            str(merged["section_type"]),
            str(merged.get("layout") or "rail"),
            config,
            merged.get("title_key"),
            dict(merged.get("title_i18n") or {}),
        )
    except (ValueError, ValidationError) as exc:
        raise _validation(str(exc)) from exc
    starts_at = parse_ts(merged.get("starts_at"))
    ends_at = parse_ts(merged.get("ends_at"))
    if starts_at and ends_at and ends_at <= starts_at:
        raise _validation("ends_at must be after starts_at")
    if not fields:
        return _section_out(before, now=datetime.now(UTC))
    fields["updated_by"] = user.id
    updated = _one(
        service_client.client.table("home_feed_sections")
        .update(fields)
        .eq("id", str(section_id))
        .execute(),
        message="Failed to update feed section",
    )
    now = datetime.now(UTC)
    out = _section_out(updated, now=now)
    recorder.record(
        action="home_feed.section.update",
        entity_type="home_feed_section",
        entity_id=str(section_id),
        before=_section_out(before, now=now).model_dump(mode="json"),
        after=out.model_dump(mode="json"),
    )
    return out


@feed_admin_router.delete("/home-feed/sections/{section_id}", status_code=204)
async def delete_feed_section(
    section_id: UUID,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> None:
    before = _load_section(service_client.client, section_id)
    service_client.client.table("home_feed_sections").delete().eq("id", str(section_id)).execute()
    recorder.record(
        action="home_feed.section.delete",
        entity_type="home_feed_section",
        entity_id=str(section_id),
        before=_section_out(before, now=datetime.now(UTC)).model_dump(mode="json"),
        after=None,
    )


@feed_admin_router.post("/home-feed/sections/reorder", response_model=list[SectionOut])
async def reorder_feed_sections(
    body: ReorderRequest,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[SectionOut]:
    table = service_client.client.table
    rows = _rows(table("home_feed_sections").select(SECTION_COLUMNS).execute())
    known = {str(row["id"]) for row in rows}
    if set(body.ordered_ids) != known:
        raise _validation("ordered_ids must list every section exactly once")
    before = [str(row["id"]) for row in sorted(rows, key=lambda r: int(r.get("position") or 0))]
    for index, section_id in enumerate(body.ordered_ids):
        table("home_feed_sections").update(
            {"position": (index + 1) * 10, "updated_by": user.id}
        ).eq("id", section_id).execute()
    recorder.record(
        action="home_feed.section.reorder",
        entity_type="home_feed_section",
        entity_id=None,
        before={"order": before},
        after={"order": body.ordered_ids},
    )
    now = datetime.now(UTC)
    fresh = _rows(
        table("home_feed_sections").select(SECTION_COLUMNS).order("position", desc=False).execute()
    )
    return [_section_out(row, now=now) for row in fresh]


@feed_admin_router.get("/home-feed/preview")
async def preview_feed(
    service_client: Annotated[Any, Depends(get_supabase_client)],
    cursor: Annotated[str | None, Query(max_length=16)] = None,
    locale: Annotated[str, Query(max_length=8)] = "en",
    at: Annotated[datetime | None, Query()] = None,
) -> dict[str, Any]:
    """Resolve the feed as a guest would see it (optionally at a future instant)."""
    try:
        page = build_feed_page(
            service_client.client,
            cursor=cursor,
            page_size=8,
            locale=locale,
            user_id=None,
            now=(at or datetime.now(UTC)),
        )
    except ValueError as exc:
        raise _validation("Invalid feed cursor") from exc
    return page.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Ad placements
# ---------------------------------------------------------------------------


def _load_placement(client: Any, placement_id: UUID) -> dict[str, Any]:
    rows = _rows(
        client.table("ad_placements")
        .select(PLACEMENT_COLUMNS)
        .eq("id", str(placement_id))
        .execute()
    )
    if not rows:
        raise _not_found("Ad placement", placement_id)
    return rows[0]


def _stats_by_placement(client: Any, ids: list[str]) -> dict[str, PlacementStats]:
    if not ids:
        return {}
    since = (date.today() - timedelta(days=STATS_WINDOW_DAYS)).isoformat()
    try:
        rows = _rows(
            client.table("ad_placement_daily_stats")
            .select("placement_id, impressions, clicks")
            .in_("placement_id", ids)
            .gte("day", since)
            .execute()
        )
    except Exception:
        return {}
    totals: dict[str, list[int]] = {}
    for row in rows:
        bucket = totals.setdefault(str(row["placement_id"]), [0, 0])
        bucket[0] += int(row.get("impressions") or 0)
        bucket[1] += int(row.get("clicks") or 0)
    return {
        key: PlacementStats(impressions=imp, clicks=clk, ctr_bp=(clk * 10_000 // imp) if imp else 0)
        for key, (imp, clk) in totals.items()
    }


def _placement_out(
    row: dict[str, Any], *, now: datetime, stats: PlacementStats | None = None
) -> PlacementOut:
    return PlacementOut(
        id=str(row["id"]),
        advertiser_kind=row["advertiser_kind"],
        advertiser_vendor_id=(
            str(row["advertiser_vendor_id"]) if row.get("advertiser_vendor_id") else None
        ),
        advertiser_name=str(row["advertiser_name"]),
        placement_type=row["placement_type"],
        image_public_id=str(row["image_public_id"]),
        headline=str(row["headline"]),
        body=row.get("body"),
        cta_label=row.get("cta_label"),
        cta_href=str(row["cta_href"]),
        starts_at=parse_ts(row["starts_at"]) or now,
        ends_at=parse_ts(row["ends_at"]) or now,
        priority=int(row.get("priority") or 0),
        paid_amount_ngwee=int(row.get("paid_amount_ngwee") or 0),
        payment_reference=row.get("payment_reference"),
        status=row["status"],
        enabled=bool(row.get("enabled", True)),
        effective_state=placement_effective_state(row, now=now),  # type: ignore[arg-type]
        stats=stats or PlacementStats(),
        updated_at=parse_ts(row.get("updated_at")),
    )


@feed_admin_router.get("/ads/placements", response_model=list[PlacementOut])
async def list_ad_placements(
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> list[PlacementOut]:
    rows = _rows(
        service_client.client.table("ad_placements")
        .select(PLACEMENT_COLUMNS)
        .order("starts_at", desc=True)
        .execute()
    )
    stats = _stats_by_placement(service_client.client, [str(row["id"]) for row in rows])
    now = datetime.now(UTC)
    return [_placement_out(row, now=now, stats=stats.get(str(row["id"]))) for row in rows]


@feed_admin_router.post("/ads/placements", response_model=PlacementOut, status_code=201)
async def create_ad_placement(
    body: PlacementCreate,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PlacementOut:
    try:
        cta_href = validate_cta_href(body.cta_href, allowed_external_hosts())
    except ValueError as exc:
        raise _validation(str(exc)) from exc
    row = body.model_dump(mode="json")
    row.update(
        {"cta_href": cta_href, "status": "draft", "created_by": user.id, "updated_by": user.id}
    )
    created = _one(
        service_client.client.table("ad_placements").insert(row).execute(),
        message="Failed to create ad placement",
    )
    out = _placement_out(created, now=datetime.now(UTC))
    recorder.record(
        action="ads.placement.create",
        entity_type="ad_placement",
        entity_id=out.id,
        before=None,
        after=out.model_dump(mode="json"),
    )
    return out


@feed_admin_router.patch("/ads/placements/{placement_id}", response_model=PlacementOut)
async def update_ad_placement(
    placement_id: UUID,
    body: PlacementUpdate,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PlacementOut:
    before = _load_placement(service_client.client, placement_id)
    if before.get("status") == "ended":
        raise _validation("Ended placements are read-only")
    fields = body.model_dump(mode="json", exclude_none=True)
    if "cta_href" in fields:
        try:
            fields["cta_href"] = validate_cta_href(fields["cta_href"], allowed_external_hosts())
        except ValueError as exc:
            raise _validation(str(exc)) from exc
    starts_at = parse_ts(fields.get("starts_at", before.get("starts_at")))
    ends_at = parse_ts(fields.get("ends_at", before.get("ends_at")))
    if starts_at is None or ends_at is None or ends_at <= starts_at:
        raise _validation("ends_at must be after starts_at")
    now = datetime.now(UTC)
    if not fields:
        return _placement_out(before, now=now)
    fields["updated_by"] = user.id
    updated = _one(
        service_client.client.table("ad_placements")
        .update(fields)
        .eq("id", str(placement_id))
        .execute(),
        message="Failed to update ad placement",
    )
    out = _placement_out(updated, now=now)
    recorder.record(
        action="ads.placement.update",
        entity_type="ad_placement",
        entity_id=str(placement_id),
        before=_placement_out(before, now=now).model_dump(mode="json"),
        after=out.model_dump(mode="json"),
    )
    return out


@feed_admin_router.post("/ads/placements/{placement_id}/transition", response_model=PlacementOut)
async def transition_ad_placement(
    placement_id: UUID,
    body: TransitionRequest,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PlacementOut:
    before = _load_placement(service_client.client, placement_id)
    try:
        result = service_client.client.rpc(
            "transition_ad_placement",
            {
                "p_placement_id": str(placement_id),
                "p_to_status": body.to_status,
                "p_actor": user.id,
                "p_reason": body.reason,
            },
        ).execute()
    except Exception as exc:
        raise AppError(
            code="invalid_transition",
            message="Ad placement transition rejected",
            http_status=409,
            details={"from": before.get("status"), "to": body.to_status},
        ) from exc
    data = getattr(result, "data", None)
    row = data[0] if isinstance(data, list) and data else data
    if not isinstance(row, dict):
        row = _load_placement(service_client.client, placement_id)
    now = datetime.now(UTC)
    out = _placement_out(row, now=now)
    recorder.record(
        action="ads.placement.transition",
        entity_type="ad_placement",
        entity_id=str(placement_id),
        before={"status": before.get("status")},
        after={"status": out.status, "reason": body.reason},
    )
    return out


admin_router.include_router(feed_admin_router)
