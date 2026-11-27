"""Admin category manager: one tree per umbrella (product | service | event | wholesale).

Mounted on the shared ``/admin`` router (``require_admin_scope`` + audited route class: every
mutation writes exactly one ``audit_log`` row; ``reorder`` is a single request so it is a single
row). Storage and rules live in :mod:`app.services.categories.taxonomy`; tables, slugs and ids
are unchanged so existing listings keep resolving. Blocking never touches listings.

Permissions: the route map grants ``products.manage`` (products + wholesale). Event umbrella
additionally requires ``events.manage`` and the service umbrella the unrestricted admin role
(services mutations have no rbac grant today, mirroring ``admin_catalog_control``).
"""

from __future__ import annotations

import time
from typing import Annotated, Any

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user, load_admin_permissions
from app.deps import get_supabase_client
from app.errors import AppError
from app.media.cloudinary_signing import (
    DEFAULT_ALLOWED_FORMATS,
    build_signed_params,
)
from app.routers.admin_base import router as admin_router
from app.schemas.base import StrictModel
from app.services.categories import taxonomy as tx
from app.services.categories.public import invalidate_public_categories_cache
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends, Query
from pydantic import Field, field_validator, model_validator

taxonomy_router = APIRouter(prefix="/catalog/taxonomy", tags=["admin-taxonomy"])

MAX_IMAGE_BYTES = 5_242_880
Umbrella = tx.Umbrella


def _require_umbrella(umbrella: str, user: CurrentUser, service_client: Any) -> None:
    if umbrella not in tx.UMBRELLAS:
        raise AppError(code="not_found", message="Unknown umbrella", http_status=404)
    if user.roles & {"superadmin", "admin"}:
        return
    if umbrella in ("product", "wholesale"):
        return
    if umbrella == "event" and "events.manage" in load_admin_permissions(user, service_client):
        return
    raise AppError(code="forbidden", message="Insufficient admin permissions", http_status=403)


class NodeFields(StrictModel):
    status: tx.Status | None = None
    show_in_customer: bool | None = None
    show_in_vendor: bool | None = None
    icon: str | None = Field(default=None, max_length=40)
    image_public_id: str | None = Field(default=None, max_length=500)
    image_alt: str | None = Field(default=None, max_length=200)

    @field_validator("icon")
    @classmethod
    def _icon(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not tx.ICON_RE.fullmatch(value):
            raise ValueError("icon must be a lowercase token")
        return value

    @field_validator("image_public_id")
    @classmethod
    def _public_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if ".." in trimmed or trimmed.startswith("/"):
            raise ValueError("image_public_id is invalid")
        return trimmed

    def to_columns(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in self.model_fields_set:
            out[key] = getattr(self, key)
        return out


class CreateNodeRequest(NodeFields):
    umbrella: Umbrella
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=80)
    parent_id: str | None = None
    commission_key: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _image_needs_alt(self) -> CreateNodeRequest:
        if self.image_public_id and not (self.image_alt or "").strip():
            raise ValueError("image_alt is required with an image")
        return self


class UpdateNodeRequest(NodeFields):
    name: str | None = Field(default=None, min_length=2, max_length=120)

    @model_validator(mode="after")
    def _image_needs_alt(self) -> UpdateNodeRequest:
        if self.image_public_id and "image_alt" in self.model_fields_set:
            if not (self.image_alt or "").strip():
                raise ValueError("image_alt is required with an image")
        return self


class StatusRequest(StrictModel):
    status: tx.Status
    reason: str | None = Field(default=None, max_length=500)


class MoveRequest(StrictModel):
    parent_id: str | None = None


class ReorderRequest(StrictModel):
    parent_id: str | None = None
    ordered_ids: list[str] = Field(min_length=1, max_length=500)

    @field_validator("ordered_ids")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("ordered_ids must be unique")
        return value


class SignImageRequest(StrictModel):
    umbrella: Umbrella
    file_size_bytes: int | None = Field(default=None, ge=1)


class SignImageResponse(StrictModel):
    cloud_name: str
    api_key: str
    timestamp: int
    signature: str
    folder: str
    allowed_formats: str
    max_file_size: int


def _audit_state(node: tx.TaxonomyNode) -> dict[str, Any]:
    return {
        "umbrella": node.umbrella,
        "slug": node.slug,
        "name": node.name,
        "status": node.status,
        "parent_id": node.parent_id,
        "sort_order": node.sort_order,
        "show_in_customer": node.show_in_customer,
        "show_in_vendor": node.show_in_vendor,
        "image_public_id": node.image_public_id,
    }


def _bust() -> None:
    invalidate_public_categories_cache()


@taxonomy_router.get("", response_model=list[tx.TaxonomyNode])
async def list_taxonomy(
    umbrella: Annotated[Umbrella, Query()],
    service_client: Annotated[Any, Depends(get_supabase_client)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    q: Annotated[str, Query(max_length=80)] = "",
) -> list[tx.TaxonomyNode]:
    _require_umbrella(umbrella, user, service_client)
    return tx.list_admin_nodes(service_client.client, umbrella, q=q)


@taxonomy_router.post("/image/sign", response_model=SignImageResponse)
async def sign_taxonomy_image(
    body: SignImageRequest,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> SignImageResponse:
    """Signed Cloudinary upload slot into ``taxonomy/<umbrella>`` (same signer as listings)."""
    _require_umbrella(body.umbrella, user, service_client)
    if body.file_size_bytes is not None and body.file_size_bytes > MAX_IMAGE_BYTES:
        raise AppError(
            code="file_too_large",
            message="Image exceeds the maximum allowed size",
            http_status=400,
            details={"max_bytes": MAX_IMAGE_BYTES},
        )
    try:
        cloud_name = settings.cloudinary_cloud_name
        api_key = settings.cloudinary_api_key
        api_secret = settings.cloudinary_api_secret
    except ValueError as exc:
        raise AppError(
            code="configuration_error", message="Cloudinary is not configured", http_status=503
        ) from exc
    signed = build_signed_params(
        folder=f"taxonomy/{body.umbrella}",
        public_id=None,
        timestamp=int(time.time()),
        api_secret=api_secret,
        allowed_formats=DEFAULT_ALLOWED_FORMATS,
        max_bytes=MAX_IMAGE_BYTES,
    )
    recorder.record(
        action="catalog.taxonomy.image_sign",
        entity_type="taxonomy",
        entity_id=None,
        before=None,
        after={"umbrella": body.umbrella, "folder": str(signed["folder"])},
    )
    return SignImageResponse(
        cloud_name=cloud_name,
        api_key=api_key,
        timestamp=int(signed["timestamp"]),
        signature=str(signed["signature"]),
        folder=str(signed["folder"]),
        allowed_formats=str(signed["allowed_formats"]),
        max_file_size=int(signed["max_file_size"]),
    )


@taxonomy_router.post("", response_model=tx.TaxonomyNode, status_code=201)
async def create_taxonomy_node(
    body: CreateNodeRequest,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> tx.TaxonomyNode:
    _require_umbrella(body.umbrella, user, service_client)
    fields = {
        key: value
        for key, value in body.to_columns().items()
        if key not in {"umbrella", "name", "slug", "parent_id", "commission_key"}
        and value is not None
    }
    fields.setdefault("status", "draft")
    if body.umbrella == "wholesale":
        # Bulk/supplies categories are vendor-facing until an admin opts them into the customer app.
        fields.setdefault("show_in_customer", False)
    node = tx.create_node(
        service_client.client,
        body.umbrella,
        name=body.name,
        slug=body.slug,
        parent_id=body.parent_id,
        fields=fields,
        actor=user.id,
        commission_key=body.commission_key,
    )
    _bust()
    recorder.record(
        action="catalog.taxonomy.create",
        entity_type="taxonomy",
        entity_id=node.id,
        before=None,
        after=_audit_state(node),
    )
    return node


@taxonomy_router.post("/{umbrella}/reorder", response_model=list[tx.TaxonomyNode])
async def reorder_taxonomy(
    umbrella: Umbrella,
    body: ReorderRequest,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> list[tx.TaxonomyNode]:
    _require_umbrella(umbrella, user, service_client)
    nodes = tx.reorder_nodes(
        service_client.client, umbrella, body.parent_id, body.ordered_ids, actor=user.id
    )
    _bust()
    recorder.record(
        action="catalog.taxonomy.reorder",
        entity_type="taxonomy",
        entity_id=body.parent_id,
        before=None,
        after={"umbrella": umbrella, "parent_id": body.parent_id, "ordered_ids": body.ordered_ids},
    )
    return nodes


@taxonomy_router.patch("/{umbrella}/{node_id}", response_model=tx.TaxonomyNode)
async def update_taxonomy_node(
    umbrella: Umbrella,
    node_id: str,
    body: UpdateNodeRequest,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> tx.TaxonomyNode:
    _require_umbrella(umbrella, user, service_client)
    changes = body.to_columns()
    if not changes:
        raise AppError(code="validation_error", message="Nothing to change", http_status=422)
    if "name" in changes and changes["name"] is not None:
        changes["name"] = str(changes["name"]).strip()
    before = tx.get_node(service_client.client, umbrella, node_id)
    node = tx.update_node(service_client.client, umbrella, node_id, changes, actor=user.id)
    _bust()
    recorder.record(
        action="catalog.taxonomy.update",
        entity_type="taxonomy",
        entity_id=node.id,
        before=_audit_state(before),
        after=_audit_state(node),
    )
    return node


@taxonomy_router.post("/{umbrella}/{node_id}/status", response_model=tx.TaxonomyNode)
async def set_taxonomy_status(
    umbrella: Umbrella,
    node_id: str,
    body: StatusRequest,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> tx.TaxonomyNode:
    """Publish / unpublish (draft) / block. Listings are never modified."""
    _require_umbrella(umbrella, user, service_client)
    before = tx.get_node(service_client.client, umbrella, node_id)
    node = tx.update_node(
        service_client.client, umbrella, node_id, {"status": body.status}, actor=user.id
    )
    _bust()
    recorder.record(
        action=f"catalog.taxonomy.{body.status}",
        entity_type="taxonomy",
        entity_id=node.id,
        before=_audit_state(before),
        after={**_audit_state(node), "reason": body.reason},
        reason=body.reason,
    )
    return node


@taxonomy_router.post("/{umbrella}/{node_id}/move", response_model=tx.TaxonomyNode)
async def move_taxonomy_node(
    umbrella: Umbrella,
    node_id: str,
    body: MoveRequest,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> tx.TaxonomyNode:
    _require_umbrella(umbrella, user, service_client)
    before = tx.get_node(service_client.client, umbrella, node_id)
    node = tx.move_node(service_client.client, umbrella, node_id, body.parent_id, actor=user.id)
    _bust()
    recorder.record(
        action="catalog.taxonomy.move",
        entity_type="taxonomy",
        entity_id=node.id,
        before=_audit_state(before),
        after=_audit_state(node),
    )
    return node


@taxonomy_router.delete("/{umbrella}/{node_id}", response_model=tx.TaxonomyNode)
async def delete_taxonomy_node(
    umbrella: Umbrella,
    node_id: str,
    service_client: Annotated[Any, Depends(get_supabase_client)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> tx.TaxonomyNode:
    """Delete an unused leaf. Anything with listings or children must be blocked instead."""
    _require_umbrella(umbrella, user, service_client)
    node = tx.delete_node(service_client.client, umbrella, node_id)
    _bust()
    recorder.record(
        action="catalog.taxonomy.delete",
        entity_type="taxonomy",
        entity_id=node.id,
        before=_audit_state(node),
        after=None,
    )
    return node


admin_router.include_router(taxonomy_router)
