"""Admin catalog control: view, edit display fields, hide / block and restore
listings, services, events and vendors.

Mounted on the shared ``/admin`` router (``require_admin_scope`` + audited route
class: every mutation writes exactly one ``audit_log`` row). Status changes go
through the guarded SQL functions ``moderate_catalog_entity`` /
``release_catalog_moderation`` (20261113020000) — never a raw status UPDATE. An
active hold pins the entity off its customer-visible status for every other
writer, so a vendor cannot undo an admin block.

Routes are literal per kind (``/catalog/listings``, ``/catalog/services`` …) so
the explicit RBAC inventory in ``app.core.auth`` can grant each kind to the
existing permission that owns it.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.catalog_visibility import load_targets, search_targets
from fastapi import APIRouter, Depends, Query
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field, field_validator

CatalogKind = Literal["listing", "service", "event", "vendor"]

# URL segment -> entity kind
KIND_SEGMENTS: dict[str, CatalogKind] = {
    "listings": "listing",
    "services": "service",
    "events": "event",
    "vendors": "vendor",
}
_TABLES: dict[str, str] = {
    "listing": "vendor_listings",
    "service": "services",
    "event": "events",
    "vendor": "vendors",
}
# Admin-editable display fields: request field -> column.
_EDITABLE: dict[str, dict[str, str]] = {
    "listing": {"title": "title_override", "description": "description"},
    "service": {"title": "title", "description": "description"},
    "event": {"title": "title", "description": "description"},
    "vendor": {"title": "display_name", "description": "description"},
}
_ALLOWED_ACTIONS: dict[str, frozenset[str]] = {
    "listing": frozenset({"hide", "block"}),
    "service": frozenset({"hide", "block"}),
    "event": frozenset({"hide", "block"}),
    "vendor": frozenset({"block"}),
}
HOLD_COLUMNS = (
    "id, entity_kind, entity_id, action, from_status, reason, actor, created_at, "
    "released_at, released_by, release_reason"
)

catalog_router = APIRouter(prefix="/catalog", tags=["admin-catalog-control"])


class ModerateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    action: Literal["hide", "block"]
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("reason is required")
        return value.strip()


class RestoreRequest(BaseModel):
    model_config = {"extra": "forbid"}

    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("reason is required")
        return value.strip()


class DisplayEdit(BaseModel):
    model_config = {"extra": "forbid"}

    title: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    reason: str = Field(min_length=3, max_length=500)


class HoldOut(BaseModel):
    id: str
    action: str
    from_status: str
    reason: str
    actor: str | None = None
    created_at: str | None = None
    released_at: str | None = None
    release_reason: str | None = None


class CatalogEntityOut(BaseModel):
    kind: CatalogKind
    id: str
    label: str
    status: str
    vendor_id: str | None = None
    visible: bool
    href: str
    hold: HoldOut | None = None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _active_holds(client: Any, kind: str, ids: list[str]) -> dict[str, HoldOut]:
    if not ids:
        return {}
    rows = _rows(
        client.table("catalog_moderation_holds")
        .select(HOLD_COLUMNS)
        .eq("entity_kind", kind)
        .in_("entity_id", ids)
        .is_("released_at", "null")
        .execute()
    )
    return {
        str(row["entity_id"]): HoldOut(
            id=str(row["id"]),
            action=str(row["action"]),
            from_status=str(row["from_status"]),
            reason=str(row["reason"]),
            actor=str(row["actor"]) if row.get("actor") else None,
            created_at=str(row["created_at"]) if row.get("created_at") else None,
        )
        for row in rows
    }


def _entity_out(client: Any, kind: str, row: dict[str, Any]) -> CatalogEntityOut:
    holds = _active_holds(client, kind, [row["id"]])
    return CatalogEntityOut(**row, hold=holds.get(row["id"]))


def _load_one(client: Any, kind: str, entity_id: UUID) -> dict[str, Any]:
    rows = load_targets(client, kind, [str(entity_id)])
    if not rows:
        raise AppError(
            code="not_found",
            message="Catalog entity not found",
            http_status=404,
            details={"kind": kind, "id": str(entity_id)},
        )
    return rows[0]


def _rpc_error(exc: APIError, *, kind: str, entity_id: UUID) -> AppError:
    code = str(getattr(exc, "code", "") or "")
    details = {"kind": kind, "id": str(entity_id)}
    if code == "P0002":
        return AppError(
            code="not_found", message="Nothing to restore", http_status=404, details=details
        )
    if code == "23505":
        return AppError(
            code="already_moderated",
            message="Entity is already moderated; restore it first",
            http_status=409,
            details=details,
        )
    if code == "22023":
        return AppError(
            code="validation_error", message=str(exc.message), http_status=422, details=details
        )
    return AppError(
        code="invalid_transition",
        message=str(getattr(exc, "message", "") or "Moderation transition rejected"),
        http_status=409,
        details=details,
    )


def _kind_for(segment: str) -> CatalogKind:
    kind = KIND_SEGMENTS.get(segment)
    if kind is None:
        raise AppError(code="not_found", message="Unknown catalog kind", http_status=404)
    return kind


def _register(segment: str) -> None:
    kind = _kind_for(segment)

    @catalog_router.get(
        f"/{segment}",
        response_model=list[CatalogEntityOut],
        name=f"list_catalog_{segment}",
    )
    async def list_entities(
        service_client: Annotated[Any, Depends(get_supabase_client)],
        q: Annotated[str, Query(max_length=80)] = "",
        held_only: bool = False,
    ) -> list[CatalogEntityOut]:
        client = service_client.client
        if held_only:
            held = _rows(
                client.table("catalog_moderation_holds")
                .select("entity_id")
                .eq("entity_kind", kind)
                .is_("released_at", "null")
                .limit(100)
                .execute()
            )
            rows = load_targets(client, kind, [str(row["entity_id"]) for row in held])
        else:
            rows = search_targets(client, kind, q, limit=50)
        holds = _active_holds(client, kind, [row["id"] for row in rows])
        return [CatalogEntityOut(**row, hold=holds.get(row["id"])) for row in rows]

    @catalog_router.post(
        f"/{segment}/{{entity_id}}/moderate",
        response_model=CatalogEntityOut,
        name=f"moderate_catalog_{segment}",
    )
    async def moderate_entity(
        entity_id: UUID,
        body: ModerateRequest,
        service_client: Annotated[Any, Depends(get_supabase_client)],
        recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CatalogEntityOut:
        if body.action not in _ALLOWED_ACTIONS[kind]:
            raise AppError(
                code="validation_error",
                message=f"{kind} does not support {body.action}",
                http_status=422,
            )
        client = service_client.client
        before = _load_one(client, kind, entity_id)
        try:
            client.rpc(
                "moderate_catalog_entity",
                {
                    "p_kind": kind,
                    "p_entity_id": str(entity_id),
                    "p_action": body.action,
                    "p_actor": user.id,
                    "p_reason": body.reason,
                },
            ).execute()
        except APIError as exc:
            raise _rpc_error(exc, kind=kind, entity_id=entity_id) from exc
        after = _entity_out(client, kind, _load_one(client, kind, entity_id))
        recorder.record(
            action=f"catalog.{kind}.{body.action}",
            entity_type=kind,
            entity_id=str(entity_id),
            before={"status": before["status"], "visible": before["visible"]},
            after={"status": after.status, "visible": after.visible, "reason": body.reason},
        )
        return after

    @catalog_router.post(
        f"/{segment}/{{entity_id}}/restore",
        response_model=CatalogEntityOut,
        name=f"restore_catalog_{segment}",
    )
    async def restore_entity(
        entity_id: UUID,
        body: RestoreRequest,
        service_client: Annotated[Any, Depends(get_supabase_client)],
        recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CatalogEntityOut:
        client = service_client.client
        before = _load_one(client, kind, entity_id)
        try:
            client.rpc(
                "release_catalog_moderation",
                {
                    "p_kind": kind,
                    "p_entity_id": str(entity_id),
                    "p_actor": user.id,
                    "p_reason": body.reason,
                },
            ).execute()
        except APIError as exc:
            raise _rpc_error(exc, kind=kind, entity_id=entity_id) from exc
        after = _entity_out(client, kind, _load_one(client, kind, entity_id))
        recorder.record(
            action=f"catalog.{kind}.restore",
            entity_type=kind,
            entity_id=str(entity_id),
            before={"status": before["status"], "visible": before["visible"]},
            after={"status": after.status, "visible": after.visible, "reason": body.reason},
        )
        return after

    @catalog_router.patch(
        f"/{segment}/{{entity_id}}",
        response_model=CatalogEntityOut,
        name=f"edit_catalog_{segment}",
    )
    async def edit_entity(
        entity_id: UUID,
        body: DisplayEdit,
        service_client: Annotated[Any, Depends(get_supabase_client)],
        recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    ) -> CatalogEntityOut:
        """Correct customer-facing display text (never status, price or ownership)."""
        client = service_client.client
        columns = _EDITABLE[kind]
        fields: dict[str, Any] = {}
        if body.title is not None:
            fields[columns["title"]] = body.title.strip()
        if body.description is not None:
            fields[columns["description"]] = body.description.strip() or None
        if not fields:
            raise AppError(code="validation_error", message="Nothing to change", http_status=422)
        table = _TABLES[kind]
        snapshot_columns = ", ".join(["id", *fields.keys()])
        previous = _rows(
            client.table(table).select(snapshot_columns).eq("id", str(entity_id)).execute()
        )
        if not previous:
            raise AppError(code="not_found", message="Catalog entity not found", http_status=404)
        client.table(table).update(fields).eq("id", str(entity_id)).execute()
        after = _entity_out(client, kind, _load_one(client, kind, entity_id))
        recorder.record(
            action=f"catalog.{kind}.edit",
            entity_type=kind,
            entity_id=str(entity_id),
            before={key: previous[0].get(key) for key in fields},
            after={**fields, "reason": body.reason},
        )
        return after


for _segment in KIND_SEGMENTS:
    _register(_segment)


admin_router.include_router(catalog_router)
