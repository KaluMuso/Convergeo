"""Admin merchandising slots + public read with preview token.

TODO(home): Customer home (`merch-data.ts`) reads `merch_slots` directly from Supabase.
Wire `loadHomeMerchData()` to `GET /merch/slots?merch_preview=<token>` when
`?merch_preview=draft` is present so draft overlays render without publishing.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

LUSAKA_TZ = ZoneInfo("Africa/Lusaka")
DRAFT_PAYLOAD_KEY = "_merch_draft"
DEFAULT_PREVIEW_TOKEN = "draft"

HERO_VARIANT_KEYS = frozenset({"editorial-light", "gradient-dark", "carousel", "default"})
SLOT_KEYS = frozenset(
    {"hero", "banner_row", "flash_deal", "events_row", "featured_collections", "category_grid"}
)
MERCH_SLOT_COLUMNS = (
    "id, slot_key, variant_key, payload, schedule_from, schedule_to, "
    "position, active, created_at, updated_at"
)

merch_admin_router = APIRouter(prefix="/merch", tags=["admin-merch"])
router = APIRouter(prefix="/merch", tags=["merch"])


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class MerchDraftState(BaseModel):
    variant_key: str | None = None
    payload: dict[str, Any] | None = None
    schedule_from: datetime | None = None
    schedule_to: datetime | None = None
    position: int | None = None
    active: bool | None = None


class MerchSlotOut(BaseModel):
    id: UUID
    slot_key: str
    variant_key: str
    payload: dict[str, Any]
    schedule_from: datetime | None
    schedule_to: datetime | None
    position: int
    active: bool
    created_at: datetime
    updated_at: datetime
    has_draft: bool
    draft: MerchDraftState | None = None


class MerchSlotCreate(BaseModel):
    slot_key: str = Field(min_length=1, max_length=64)
    variant_key: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    schedule_from: datetime | None = None
    schedule_to: datetime | None = None
    position: int = 0
    active: bool = True
    is_default: bool = False


class MerchSlotUpdate(BaseModel):
    variant_key: str | None = Field(default=None, min_length=1, max_length=64)
    payload: dict[str, Any] | None = None
    schedule_from: datetime | None = None
    schedule_to: datetime | None = None
    position: int | None = None
    active: bool | None = None
    is_default: bool | None = None


class MerchDraftSave(BaseModel):
    variant_key: str | None = Field(default=None, min_length=1, max_length=64)
    payload: dict[str, Any] | None = None
    schedule_from: datetime | None = None
    schedule_to: datetime | None = None
    position: int | None = None
    active: bool | None = None


class ResolvedMerchSlotOut(BaseModel):
    id: UUID
    slot_key: str
    variant_key: str
    payload: dict[str, Any]
    schedule_from: datetime | None
    schedule_to: datetime | None
    position: int
    active: bool
    is_preview: bool = False
    is_fallback: bool = False


class HeroVariantOut(BaseModel):
    variant_key: str
    label: str


def _preview_token() -> str:
    return os.environ.get("MERCH_PREVIEW_TOKEN", DEFAULT_PREVIEW_TOKEN)


def _table(client: ServiceRoleClient, name: str) -> Any:
    return client.client.table(name)


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise AppError(
        code="internal_error",
        message="Invalid timestamp in merch slot",
        http_status=500,
    )


def _normalize_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _strip_internal_payload_keys(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != DRAFT_PAYLOAD_KEY}


def _extract_draft(payload: dict[str, Any]) -> MerchDraftState | None:
    raw = payload.get(DRAFT_PAYLOAD_KEY)
    if not isinstance(raw, dict):
        return None
    return MerchDraftState.model_validate(raw)


def _slot_row_to_out(row: dict[str, Any]) -> MerchSlotOut:
    payload = _normalize_payload(row.get("payload"))
    draft = _extract_draft(payload)
    return MerchSlotOut(
        id=UUID(str(row["id"])),
        slot_key=str(row["slot_key"]),
        variant_key=str(row["variant_key"]),
        payload=_strip_internal_payload_keys(payload),
        schedule_from=_parse_timestamp(row.get("schedule_from")),
        schedule_to=_parse_timestamp(row.get("schedule_to")),
        position=int(row.get("position", 0)),
        active=bool(row.get("active", True)),
        created_at=_parse_timestamp(row["created_at"]) or datetime.now(UTC),
        updated_at=_parse_timestamp(row["updated_at"]) or datetime.now(UTC),
        has_draft=draft is not None,
        draft=draft,
    )


def now_in_lusaka(reference: datetime | None = None) -> datetime:
    if reference is None:
        return datetime.now(LUSAKA_TZ)
    if reference.tzinfo is None:
        return reference.replace(tzinfo=UTC).astimezone(LUSAKA_TZ)
    return reference.astimezone(LUSAKA_TZ)


def is_slot_in_schedule(
    slot: dict[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether a slot is active and within its schedule window (Africa/Lusaka)."""
    if not bool(slot.get("active", True)):
        return False

    reference = now_in_lusaka(now)

    schedule_from = _parse_timestamp(slot.get("schedule_from"))
    if schedule_from is not None:
        if reference < schedule_from.astimezone(LUSAKA_TZ):
            return False

    schedule_to = _parse_timestamp(slot.get("schedule_to"))
    if schedule_to is not None:
        if reference > schedule_to.astimezone(LUSAKA_TZ):
            return False

    return True


def _is_default_slot(slot: dict[str, Any]) -> bool:
    payload = _normalize_payload(slot.get("payload"))
    return bool(payload.get("is_default"))


def _merge_preview_overlay(row: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_payload(row.get("payload"))
    draft = payload.get(DRAFT_PAYLOAD_KEY)
    if not isinstance(draft, dict):
        return dict(row)

    merged = dict(row)
    for field in ("variant_key", "schedule_from", "schedule_to", "position", "active"):
        if draft.get(field) is not None:
            merged[field] = draft[field]

    published_payload = _strip_internal_payload_keys(payload)
    draft_payload = draft.get("payload")
    if isinstance(draft_payload, dict):
        merged_payload = {**published_payload, **draft_payload}
    else:
        merged_payload = published_payload
    merged["payload"] = merged_payload
    merged["is_preview"] = True
    return merged


def resolve_slots_for_display(
    rows: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    include_drafts: bool = False,
) -> list[ResolvedMerchSlotOut]:
    """Pick in-window slots per slot_key; fall back to default when none match."""
    reference = now_in_lusaka(now)
    working_rows = [_merge_preview_overlay(row) if include_drafts else dict(row) for row in rows]

    by_key: dict[str, list[dict[str, Any]]] = {}
    for row in working_rows:
        key = str(row["slot_key"])
        by_key.setdefault(key, []).append(row)

    resolved: list[ResolvedMerchSlotOut] = []
    for slot_key, candidates in by_key.items():
        in_window = [
            row
            for row in candidates
            if is_slot_in_schedule(row, now=reference)
        ]
        in_window.sort(key=lambda row: int(row.get("position", 0)))

        non_default_in_window = [row for row in in_window if not _is_default_slot(row)]
        defaults = [row for row in candidates if _is_default_slot(row)]

        chosen: dict[str, Any] | None = None
        is_fallback = False

        if non_default_in_window:
            chosen = non_default_in_window[0]
        elif defaults:
            active_defaults = [row for row in defaults if bool(row.get("active", True))]
            pool = active_defaults or defaults
            pool.sort(key=lambda row: int(row.get("position", 0)))
            chosen = pool[0]
            is_fallback = not bool(non_default_in_window) and (
                not in_window or all(_is_default_slot(row) for row in in_window)
            )
        elif in_window:
            chosen = in_window[0]
        else:
            evergreen = [
                row
                for row in candidates
                if row.get("schedule_from") is None and row.get("schedule_to") is None
            ]
            pool = evergreen or candidates
            pool.sort(key=lambda row: int(row.get("position", 0)))
            if pool:
                chosen = pool[0]
                is_fallback = True

        if chosen is None:
            continue

        payload = _strip_internal_payload_keys(_normalize_payload(chosen.get("payload")))
        resolved.append(
            ResolvedMerchSlotOut(
                id=UUID(str(chosen["id"])),
                slot_key=slot_key,
                variant_key=str(chosen.get("variant_key", "default")),
                payload=payload,
                schedule_from=_parse_timestamp(chosen.get("schedule_from")),
                schedule_to=_parse_timestamp(chosen.get("schedule_to")),
                position=int(chosen.get("position", 0)),
                active=bool(chosen.get("active", True)),
                is_preview=bool(chosen.get("is_preview")),
                is_fallback=is_fallback,
            )
        )

    resolved.sort(key=lambda slot: slot.position)
    return resolved


def _load_all_slots(client: ServiceRoleClient) -> list[dict[str, Any]]:
    response = (
        _table(client, "merch_slots")
        .select(MERCH_SLOT_COLUMNS)
        .order("position", desc=False)
        .execute()
    )
    data = response.data
    if not isinstance(data, list):
        return []
    return [dict(row) for row in data]


def _load_slot(client: ServiceRoleClient, slot_id: UUID) -> dict[str, Any]:
    response = (
        _table(client, "merch_slots")
        .select(MERCH_SLOT_COLUMNS)
        .eq("id", str(slot_id))
        .maybe_single()
        .execute()
    )
    row = response.data
    if not isinstance(row, dict):
        raise AppError(
            code="not_found",
            message="Merch slot not found",
            http_status=404,
            details={"id": str(slot_id)},
        )
    return dict(row)


def _apply_default_flag(payload: dict[str, Any], is_default: bool | None) -> dict[str, Any]:
    next_payload = dict(payload)
    if is_default is True:
        next_payload["is_default"] = True
    elif is_default is False and "is_default" in next_payload:
        del next_payload["is_default"]
    return next_payload


def _audit_mutation(
    recorder: AdminAuditRecorder,
    *,
    action: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    recorder.record(
        action=action,
        entity_type="merch_slot",
        entity_id=entity_id,
        before=before,
        after=after,
    )


def _validate_slot_key(slot_key: str) -> None:
    if slot_key not in SLOT_KEYS:
        raise AppError(
            code="validation_error",
            message="Unsupported slot_key",
            http_status=422,
            details={"slot_key": slot_key, "allowed": sorted(SLOT_KEYS)},
        )


def _validate_variant_key(variant_key: str) -> None:
    if variant_key not in HERO_VARIANT_KEYS and not variant_key.startswith("custom-"):
        raise AppError(
            code="validation_error",
            message="Unsupported variant_key",
            http_status=422,
            details={"variant_key": variant_key, "allowed": sorted(HERO_VARIANT_KEYS)},
        )


@merch_admin_router.get("/hero-variants", response_model=list[HeroVariantOut])
async def list_hero_variants() -> list[HeroVariantOut]:
    return [
        HeroVariantOut(variant_key="editorial-light", label="Editorial light"),
        HeroVariantOut(variant_key="gradient-dark", label="Gradient dark"),
        HeroVariantOut(variant_key="carousel", label="Carousel"),
        HeroVariantOut(variant_key="default", label="Default fallback"),
    ]


@merch_admin_router.get("/slots", response_model=list[MerchSlotOut])
async def list_merch_slots(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[MerchSlotOut]:
    rows = _load_all_slots(service_client)
    return [_slot_row_to_out(row) for row in rows]


@merch_admin_router.post("/slots", response_model=MerchSlotOut, status_code=201)
async def create_merch_slot(
    body: MerchSlotCreate,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> MerchSlotOut:
    _validate_slot_key(body.slot_key)
    _validate_variant_key(body.variant_key)

    payload = _apply_default_flag(body.payload, body.is_default)
    insert_row = {
        "slot_key": body.slot_key,
        "variant_key": body.variant_key,
        "payload": payload,
        "schedule_from": body.schedule_from.isoformat() if body.schedule_from else None,
        "schedule_to": body.schedule_to.isoformat() if body.schedule_to else None,
        "position": body.position,
        "active": body.active,
    }
    response = _table(service_client, "merch_slots").insert(insert_row).execute()
    data = response.data
    if not isinstance(data, list) or not data:
        raise AppError(
            code="internal_error",
            message="Failed to create merch slot",
            http_status=500,
        )
    row = dict(data[0])
    out = _slot_row_to_out(row)
    _audit_mutation(
        recorder,
        action="merch.slot.create",
        entity_id=str(out.id),
        before=None,
        after=out.model_dump(mode="json"),
    )
    return out


@merch_admin_router.patch("/slots/{slot_id}", response_model=MerchSlotOut)
async def update_merch_slot(
    slot_id: UUID,
    body: MerchSlotUpdate,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> MerchSlotOut:
    before_row = _load_slot(service_client, slot_id)
    before_out = _slot_row_to_out(before_row)

    if body.variant_key is not None:
        _validate_variant_key(body.variant_key)

    update_fields: dict[str, Any] = {}
    if body.variant_key is not None:
        update_fields["variant_key"] = body.variant_key
    if body.schedule_from is not None:
        update_fields["schedule_from"] = body.schedule_from.isoformat()
    if body.schedule_to is not None:
        update_fields["schedule_to"] = body.schedule_to.isoformat()
    if body.position is not None:
        update_fields["position"] = body.position
    if body.active is not None:
        update_fields["active"] = body.active

    payload = _normalize_payload(before_row.get("payload"))
    if body.payload is not None:
        draft_key = payload.get(DRAFT_PAYLOAD_KEY)
        payload = {**_strip_internal_payload_keys(body.payload)}
        if draft_key is not None:
            payload[DRAFT_PAYLOAD_KEY] = draft_key
    if body.is_default is not None:
        payload = _apply_default_flag(payload, body.is_default)
    if body.payload is not None or body.is_default is not None:
        update_fields["payload"] = payload

    if not update_fields:
        return before_out

    response = (
        _table(service_client, "merch_slots")
        .update(update_fields)
        .eq("id", str(slot_id))
        .execute()
    )
    data = response.data
    if not isinstance(data, list) or not data:
        raise AppError(
            code="internal_error",
            message="Failed to update merch slot",
            http_status=500,
        )
    after_out = _slot_row_to_out(dict(data[0]))
    _audit_mutation(
        recorder,
        action="merch.slot.update",
        entity_id=str(slot_id),
        before=before_out.model_dump(mode="json"),
        after=after_out.model_dump(mode="json"),
    )
    return after_out


@merch_admin_router.post("/slots/{slot_id}/draft", response_model=MerchSlotOut)
async def save_merch_draft(
    slot_id: UUID,
    body: MerchDraftSave,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> MerchSlotOut:
    before_row = _load_slot(service_client, slot_id)
    before_out = _slot_row_to_out(before_row)

    if body.variant_key is not None:
        _validate_variant_key(body.variant_key)

    payload = _normalize_payload(before_row.get("payload"))
    existing_draft = payload.get(DRAFT_PAYLOAD_KEY)
    draft_state: dict[str, Any] = dict(existing_draft) if isinstance(existing_draft, dict) else {}

    for field in ("variant_key", "schedule_from", "schedule_to", "position", "active"):
        value = getattr(body, field)
        if value is not None:
            if isinstance(value, datetime):
                draft_state[field] = value.isoformat()
            else:
                draft_state[field] = value

    if body.payload is not None:
        draft_state["payload"] = body.payload

    payload[DRAFT_PAYLOAD_KEY] = draft_state

    response = (
        _table(service_client, "merch_slots")
        .update({"payload": payload})
        .eq("id", str(slot_id))
        .execute()
    )
    data = response.data
    if not isinstance(data, list) or not data:
        raise AppError(
            code="internal_error",
            message="Failed to save merch draft",
            http_status=500,
        )
    after_out = _slot_row_to_out(dict(data[0]))
    _audit_mutation(
        recorder,
        action="merch.slot.draft.save",
        entity_id=str(slot_id),
        before=before_out.model_dump(mode="json"),
        after=after_out.model_dump(mode="json"),
    )
    return after_out


@merch_admin_router.post("/slots/{slot_id}/publish", response_model=MerchSlotOut)
async def publish_merch_draft(
    slot_id: UUID,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> MerchSlotOut:
    before_row = _load_slot(service_client, slot_id)
    before_out = _slot_row_to_out(before_row)

    payload = _normalize_payload(before_row.get("payload"))
    draft_raw = payload.get(DRAFT_PAYLOAD_KEY)
    if not isinstance(draft_raw, dict):
        raise AppError(
            code="validation_error",
            message="No draft to publish",
            http_status=422,
            details={"id": str(slot_id)},
        )

    update_fields: dict[str, Any] = {}
    for field in ("variant_key", "schedule_from", "schedule_to", "position", "active"):
        if draft_raw.get(field) is not None:
            update_fields[field] = draft_raw[field]

    published_payload = _strip_internal_payload_keys(payload)
    draft_payload = draft_raw.get("payload")
    if isinstance(draft_payload, dict):
        published_payload = {**published_payload, **draft_payload}

    update_fields["payload"] = published_payload

    response = (
        _table(service_client, "merch_slots")
        .update(update_fields)
        .eq("id", str(slot_id))
        .execute()
    )
    data = response.data
    if not isinstance(data, list) or not data:
        raise AppError(
            code="internal_error",
            message="Failed to publish merch draft",
            http_status=500,
        )
    after_out = _slot_row_to_out(dict(data[0]))
    _audit_mutation(
        recorder,
        action="merch.slot.publish",
        entity_id=str(slot_id),
        before=before_out.model_dump(mode="json"),
        after=after_out.model_dump(mode="json"),
    )
    return after_out


@merch_admin_router.delete("/slots/{slot_id}", status_code=204)
async def delete_merch_slot(
    slot_id: UUID,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> None:
    before_row = _load_slot(service_client, slot_id)
    before_out = _slot_row_to_out(before_row)
    _table(service_client, "merch_slots").delete().eq("id", str(slot_id)).execute()
    _audit_mutation(
        recorder,
        action="merch.slot.delete",
        entity_id=str(slot_id),
        before=before_out.model_dump(mode="json"),
        after=None,
    )


@merch_admin_router.get("/preview-url")
async def get_preview_url() -> dict[str, str]:
    token = _preview_token()
    return {
        "token": token,
        "customer_path": f"/en?merch_preview={token}",
        "api_path": f"/merch/slots?merch_preview={token}",
    }


@router.get("/slots", response_model=list[ResolvedMerchSlotOut])
async def get_public_merch_slots(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    merch_preview: str | None = Query(default=None),
) -> list[ResolvedMerchSlotOut]:
    include_drafts = merch_preview is not None and merch_preview == _preview_token()
    rows = _load_all_slots(service_client)
    return resolve_slots_for_display(rows, include_drafts=include_drafts)


admin_router.include_router(merch_admin_router)
