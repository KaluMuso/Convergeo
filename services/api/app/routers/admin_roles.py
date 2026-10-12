"""Superadmin-only role definitions and assignments over public.user_roles."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from app.core.auth import (
    ADMIN_PERMISSIONS,
    CurrentUser,
    get_current_user,
    load_admin_permissions,
    require_role,
)
from app.deps import SupabaseServiceClient, get_supabase_client
from app.errors import AppError
from fastapi import APIRouter, Depends
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field

router = APIRouter(prefix="/admin", tags=["admin-roles"])


class RoleInput(BaseModel):
    key: str = Field(pattern=r"^rbac_[a-z][a-z0-9_]{2,39}$")
    name: str = Field(min_length=3, max_length=80)
    permissions: list[str] = Field(min_length=1)


class RoleUpdate(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    permissions: list[str] = Field(min_length=1)


def _validate_permissions(permissions: list[str]) -> list[str]:
    if len(permissions) != len(set(permissions)) or not set(permissions) <= ADMIN_PERMISSIONS:
        raise AppError(
            code="invalid_permissions", message="Unknown or duplicate permission", http_status=422
        )
    return sorted(permissions)


def _mutate(
    service: SupabaseServiceClient,
    actor: CurrentUser,
    action: str,
    key: str,
    *,
    name: str | None = None,
    permissions: list[str] | None = None,
    target: UUID | None = None,
) -> dict[str, Any]:
    try:
        response = service.client.rpc(
            "manage_admin_role",
            {
                "p_actor": actor.id,
                "p_action": action,
                "p_key": key,
                "p_name": name,
                "p_permissions": permissions,
                "p_target": str(target) if target else None,
            },
        ).execute()
    except APIError as exc:
        code = exc.code
        if code == "42501":
            raise AppError(
                code="forbidden", message="Superadmin role required", http_status=403
            ) from exc
        if code in {"23503", "23505", "23514", "P0002"}:
            raise AppError(code="role_conflict", message=str(exc.message), http_status=409) from exc
        if code == "22023":
            raise AppError(
                code="invalid_role", message="Invalid role or assignment", http_status=422
            ) from exc
        raise
    data = response.data
    if not isinstance(data, dict):
        raise AppError(
            code="role_write_failed", message="Role mutation was not confirmed", http_status=500
        )
    return data


@router.get("/me/permissions")
def my_permissions(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    permissions = load_admin_permissions(user, service)
    if not permissions and not user.roles.intersection({"moderator", "admin", "superadmin"}):
        raise AppError(code="forbidden", message="Admin role required", http_status=403)
    return {
        "permissions": sorted(permissions),
        "can_manage_roles": "superadmin" in user.roles,
        "unrestricted": bool(user.roles.intersection({"admin", "superadmin"})),
    }


@router.get("/roles")
def list_roles(
    _actor: Annotated[CurrentUser, Depends(require_role("superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    definitions = (
        service.client.table("admin_roles")
        .select("key,name,permissions")
        .order("key")
        .execute()
        .data
    )
    role_keys = ["superadmin", "admin"]
    if isinstance(definitions, list):
        role_keys += [
            row["key"]
            for row in definitions
            if isinstance(row, dict) and isinstance(row.get("key"), str)
        ]
    assignments = (
        service.client.table("user_roles")
        .select("user_id,role")
        .in_("role", role_keys)
        .execute()
        .data
    )
    return {
        "roles": definitions if isinstance(definitions, list) else [],
        "assignments": [
            row
            for row in assignments
            if isinstance(row, dict)
            and (
                str(row.get("role", "")).startswith("rbac_")
                or row.get("role") in {"superadmin", "admin"}
            )
        ]
        if isinstance(assignments, list)
        else [],
    }


@router.post("/roles", status_code=201)
def create_role(
    body: RoleInput,
    actor: Annotated[CurrentUser, Depends(require_role("superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _mutate(
        service,
        actor,
        "create",
        body.key,
        name=body.name.strip(),
        permissions=_validate_permissions(body.permissions),
    )


@router.patch("/roles/{key}")
def update_role(
    key: str,
    body: RoleUpdate,
    actor: Annotated[CurrentUser, Depends(require_role("superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _mutate(
        service,
        actor,
        "update",
        key,
        name=body.name.strip(),
        permissions=_validate_permissions(body.permissions),
    )


@router.delete("/roles/{key}")
def delete_role(
    key: str,
    actor: Annotated[CurrentUser, Depends(require_role("superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _mutate(service, actor, "delete", key)


@router.put("/roles/{key}/users/{user_id}")
def assign_role(
    key: str,
    user_id: UUID,
    actor: Annotated[CurrentUser, Depends(require_role("superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _mutate(service, actor, "assign", key, target=user_id)


@router.delete("/roles/{key}/users/{user_id}")
def revoke_role(
    key: str,
    user_id: UUID,
    actor: Annotated[CurrentUser, Depends(require_role("superadmin"))],
    service: Annotated[SupabaseServiceClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _mutate(service, actor, "revoke", key, target=user_id)
