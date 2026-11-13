"""Superadmin-only administrator directory and deactivation (2026-11 governance).

* GET  /admin/accounts                    — every account holding an admin role, with
  display name, email and roles. Assign/revoke stay on /admin/roles/* (manage_admin_role).
* POST /admin/accounts/{user_id}/deactivate — decision D4: deactivating an administrator
  means revoking every admin role in one audited transaction
  (`public.deactivate_admin_account`). The next API call with the same token is refused,
  because roles are re-read from user_roles on every request. The Supabase login itself is
  not banned; the person keeps any customer/vendor access they had.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from fastapi import APIRouter, Depends, Request
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-accounts"])

_MAX_ACCOUNTS = 200


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def is_admin_role(role: str) -> bool:
    return role in {"superadmin", "admin", "moderator"} or role.startswith("rbac_")


class AdminAccountOut(BaseModel):
    user_id: str
    display_name: str | None
    email: str | None
    roles: list[str]


def _email_for(service: ServiceRoleClient, user_id: str) -> str | None:
    try:
        response = service.client.auth.admin.get_user_by_id(user_id)
    except Exception:  # noqa: BLE001 - directory still renders without the email
        logger.warning("admin directory: email lookup failed", exc_info=True)
        return None
    user = getattr(response, "user", None)
    email = getattr(user, "email", None)
    return email if isinstance(email, str) and email else None


@router.get("/accounts")
def list_admin_accounts(
    _actor: Annotated[CurrentUser, Depends(require_role("superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    data = getattr(
        service.client.table("user_roles").select("user_id,role").execute(), "data", None
    )
    roles_by_user: dict[str, set[str]] = {}
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict):
            continue
        user_id, role = row.get("user_id"), row.get("role")
        if isinstance(user_id, str) and isinstance(role, str) and is_admin_role(role):
            roles_by_user.setdefault(user_id, set()).add(role)
    user_ids = sorted(roles_by_user)[:_MAX_ACCOUNTS]
    names: dict[str, str | None] = {}
    if user_ids:
        profiles = getattr(
            service.client.table("profiles")
            .select("id,display_name")
            .in_("id", user_ids)
            .execute(),
            "data",
            None,
        )
        for row in profiles if isinstance(profiles, list) else []:
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                name = row.get("display_name")
                names[row["id"]] = name if isinstance(name, str) else None
    accounts = [
        AdminAccountOut(
            user_id=user_id,
            display_name=names.get(user_id),
            email=_email_for(service, user_id),
            roles=sorted(roles_by_user[user_id]),
        )
        for user_id in user_ids
    ]
    return {"accounts": [account.model_dump() for account in accounts]}


class DeactivateBody(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    confirmation: Literal["DEACTIVATE"]


@router.post("/accounts/{user_id}/deactivate")
def deactivate_admin_account(
    user_id: UUID,
    body: DeactivateBody,
    request: Request,
    actor: Annotated[CurrentUser, Depends(require_role("superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    if str(user_id) == actor.id:
        raise AppError(
            code="self_deactivation",
            message="A superadmin cannot deactivate their own account",
            http_status=422,
        )
    request_id = getattr(request.state, "request_id", None)
    try:
        response = service.client.rpc(
            "deactivate_admin_account",
            {
                "p_actor": actor.id,
                "p_target": str(user_id),
                "p_reason": body.reason.strip(),
                "p_request_id": request_id if isinstance(request_id, str) else None,
            },
        ).execute()
    except APIError as exc:
        code = exc.code
        if code == "42501":
            raise AppError(
                code="forbidden", message="Superadmin role required", http_status=403
            ) from exc
        if code == "P0002":
            raise AppError(
                code="not_found", message="Account holds no admin role", http_status=404
            ) from exc
        if code == "23514":
            # protect_last_superadmin(): the installation must keep one superadmin.
            raise AppError(
                code="last_superadmin", message=str(exc.message), http_status=409
            ) from exc
        if code == "22023":
            raise AppError(
                code="invalid_deactivation", message=str(exc.message), http_status=422
            ) from exc
        raise
    data = response.data
    if not isinstance(data, dict):
        raise AppError(
            code="deactivation_failed", message="Deactivation was not confirmed", http_status=500
        )
    return data
