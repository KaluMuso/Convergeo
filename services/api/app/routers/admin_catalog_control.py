"""Admin catalog control: view, edit display fields, hide / block and restore
listings, services, events and vendors.

Mounted on the shared ``/admin`` router (``require_admin_scope`` + audited route
class: every mutation writes exactly one ``audit_log`` row). Status changes go
through the guarded SQL functions ``moderate_catalog_entity`` /
``release_catalog_moderation`` (20261123100000) — never a raw status UPDATE. An
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
from app.routers.admin_products import _cloudinary_delivery_url
from app.services.catalog.listing_price_review import (
    REVIEW_FLAG_PRICE_BELOW_CATEGORY_FLOOR,
    listing_price_review_flags,
)
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
    vendor_label: str | None = None
    product_label: str | None = None
    price_ngwee: int | None = None
    thumbnail_url: str | None = None
    visible: bool
    href: str
    hold: HoldOut | None = None
    review_flags: list[str] = Field(default_factory=list)


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


def _embed_display_name(row: dict[str, Any]) -> str | None:
    vendors = row.get("vendors")
    if isinstance(vendors, dict):
        name = vendors.get("display_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _embed_product_name(row: dict[str, Any]) -> str | None:
    products = row.get("products")
    if isinstance(products, dict):
        name = products.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _embed_category_path(row: dict[str, Any]) -> str | None:
    products = row.get("products")
    if not isinstance(products, dict):
        return None
    categories = products.get("categories")
    if not isinstance(categories, dict):
        return None
    path = categories.get("path")
    if isinstance(path, str) and path.strip():
        return path.strip()
    return None


def _listing_title(row: dict[str, Any], *, product_label: str | None) -> str:
    title = row.get("title_override")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return product_label or ""


def _listing_review_flags(row: dict[str, Any]) -> list[str]:
    price = row.get("price_ngwee")
    price_ngwee = int(price) if isinstance(price, int) else None
    return listing_price_review_flags(
        price_ngwee=price_ngwee,
        category_path=_embed_category_path(row),
        title=_listing_title(row, product_label=_embed_product_name(row)),
    )


def _search_listings_below_price_floor(
    client: Any, q: str, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Scan active-ish listings for below-floor prices (admin filter; not a launch gate)."""
    request = client.table("vendor_listings").select(
        "id, title_override, price_ngwee, status, vendor_id"
    )
    term = q.strip()
    if term:
        request = request.ilike("title_override", f"%{term}%")
    rows = _rows(request.limit(400).execute())
    if not rows:
        return []
    ids = [str(row["id"]) for row in rows if row.get("id")]
    detail = _rows(
        client.table("vendor_listings")
        .select("id, title_override, price_ngwee, products(name, categories(path))")
        .in_("id", ids)
        .execute()
    )
    by_id = {str(row["id"]): row for row in detail if row.get("id")}
    matched: list[dict[str, Any]] = []
    for row in rows:
        detail_row = by_id.get(str(row["id"]), row)
        if REVIEW_FLAG_PRICE_BELOW_CATEGORY_FLOOR in _listing_review_flags(detail_row):
            matched.append(row)
    return matched[:limit]


def _listing_thumbnails(client: Any, listing_ids: list[str]) -> dict[str, str]:
    if not listing_ids:
        return {}
    rows = _rows(
        client.table("listing_images")
        .select("listing_id, cloudinary_public_id, position")
        .in_("listing_id", listing_ids)
        .order("position")
        .execute()
    )
    out: dict[str, str] = {}
    for row in rows:
        listing_id = str(row.get("listing_id") or "")
        if listing_id in out:
            continue
        public_id = row.get("cloudinary_public_id")
        if not isinstance(public_id, str) or not public_id.strip():
            continue
        url = _cloudinary_delivery_url(public_id)
        if url:
            out[listing_id] = url
    return out


def _enrich_catalog_entities(
    client: Any, kind: CatalogKind, entities: list[CatalogEntityOut]
) -> None:
    if not entities:
        return
    if kind == "listing":
        ids = [entity.id for entity in entities]
        rows = _rows(
            client.table("vendor_listings")
            .select(
                "id, title_override, price_ngwee, vendors(display_name), "
                "products(name, categories(path))"
            )
            .in_("id", ids)
            .execute()
        )
        by_id = {str(row["id"]): row for row in rows if row.get("id")}
        thumbs = _listing_thumbnails(client, ids)
        for entity in entities:
            row = by_id.get(entity.id)
            if not row:
                continue
            entity.vendor_label = _embed_display_name(row)
            entity.product_label = _embed_product_name(row)
            title = row.get("title_override")
            if isinstance(title, str) and title.strip():
                entity.label = title.strip()
            elif entity.product_label:
                entity.label = entity.product_label
            price = row.get("price_ngwee")
            entity.price_ngwee = int(price) if isinstance(price, int) else None
            entity.thumbnail_url = thumbs.get(entity.id)
            entity.review_flags = _listing_review_flags(row)
        return
    if kind == "vendor":
        for entity in entities:
            entity.vendor_label = entity.label
        return
    if kind in {"service", "event"}:
        vendor_column = "vendor_id" if kind == "service" else "organiser_vendor_id"
        table = "services" if kind == "service" else "events"
        ids = [entity.id for entity in entities]
        service_price_col = ", from_price_ngwee" if kind == "service" else ""
        rows = _rows(
            client.table(table)
            .select(f"id, {vendor_column}{service_price_col}")
            .in_("id", ids)
            .execute()
        )
        vendor_ids = sorted(
            {str(row[vendor_column]) for row in rows if row.get(vendor_column) is not None}
        )
        vendor_labels: dict[str, str] = {}
        if vendor_ids:
            for vendor in _rows(
                client.table("vendors").select("id, display_name").in_("id", vendor_ids).execute()
            ):
                name = vendor.get("display_name")
                if isinstance(name, str) and name.strip():
                    vendor_labels[str(vendor["id"])] = name.strip()
        by_id = {str(row["id"]): row for row in rows if row.get("id")}
        for entity in entities:
            row = by_id.get(entity.id)
            if row and row.get(vendor_column):
                entity.vendor_label = vendor_labels.get(str(row[vendor_column]))
        if kind == "service":
            for entity in entities:
                row = by_id.get(entity.id)
                if row and isinstance(row.get("from_price_ngwee"), int):
                    entity.price_ngwee = row["from_price_ngwee"]


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
        below_price_floor_only: bool = False,
    ) -> list[CatalogEntityOut]:
        client = service_client.client
        if kind == "listing" and below_price_floor_only:
            raw = _search_listings_below_price_floor(client, q)
            rows = load_targets(client, kind, [str(row["id"]) for row in raw])
        elif held_only:
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
        entities = [CatalogEntityOut(**row, hold=holds.get(row["id"])) for row in rows]
        _enrich_catalog_entities(client, kind, entities)
        return entities

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
