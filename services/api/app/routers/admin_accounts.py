"""Superadmin-only administrator directory and deactivation (2026-11 governance).

* GET  /admin/accounts                    — every account holding an admin role, with
  display name, email and roles; `q` filters by name, email or role, `limit`/`offset`
  page. Assign/revoke stay on /admin/roles/* (manage_admin_role).
* GET  /admin/accounts/lookup?q=           — any account by name, email or id, so the
  role picker never needs a pasted UUID.
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
from app.services.admin_people import (
    MAX_TERM_LEN,
    _emails_for_user_ids,
    clean_search_term,
    search_people,
)
from fastapi import APIRouter, Depends, Query, Request
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


def _names_for(service: ServiceRoleClient, user_ids: list[str]) -> dict[str, str | None]:
    names: dict[str, str | None] = {}
    if not user_ids:
        return names
    profiles = getattr(
        service.client.table("profiles").select("id,display_name").in_("id", user_ids).execute(),
        "data",
        None,
    )
    for row in profiles if isinstance(profiles, list) else []:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            name = row.get("display_name")
            names[row["id"]] = name if isinstance(name, str) else None
    return names


def _sort_key(name: str | None, user_id: str) -> tuple[int, str, str]:
    return (0 if name else 1, (name or "").casefold(), user_id)


@router.get("/accounts")
def list_admin_accounts(
    _actor: Annotated[CurrentUser, Depends(require_role("superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    q: Annotated[str | None, Query(max_length=MAX_TERM_LEN)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=_MAX_ACCOUNTS)] = 0,
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
    names = _names_for(service, user_ids)
    user_ids.sort(key=lambda uid: _sort_key(names.get(uid), uid))
    term = clean_search_term(q)
    emails: dict[str, str | None] = {}
    if term is not None:
        needle = term.casefold()
        matched: list[str] = []
        emails = _emails_for_user_ids(service, user_ids)
        for uid in user_ids:
            haystack = [names.get(uid) or "", *roles_by_user[uid], emails.get(uid) or ""]
            if any(needle in value.casefold() for value in haystack):
                matched.append(uid)
        user_ids = matched
    total = len(user_ids)
    page = user_ids[offset : offset + limit]
    page_emails = emails if emails else _emails_for_user_ids(service, page)
    accounts = [
        AdminAccountOut(
            user_id=user_id,
            display_name=names.get(user_id),
            email=page_emails.get(user_id),
            roles=sorted(roles_by_user[user_id]),
        )
        for user_id in page
    ]
    next_offset = offset + limit if offset + limit < total else None
    return {
        "accounts": [account.model_dump() for account in accounts],
        "total": total,
        "next_offset": next_offset,
    }


class AccountLookupOut(BaseModel):
    user_id: str
    display_name: str | None
    email: str | None
    roles: list[str]


@router.get("/accounts/lookup")
def lookup_accounts(
    _actor: Annotated[CurrentUser, Depends(require_role("superadmin"))],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    q: Annotated[str, Query(min_length=2, max_length=MAX_TERM_LEN)],
) -> dict[str, Any]:
    """Any account (not only admins) by name, email or id, for the role-assignment picker."""
    people = search_people(service, q, limit=10)
    roles_by_user: dict[str, list[str]] = {}
    ids = [person["user_id"] for person in people]
    if ids:
        rows = getattr(
            service.client.table("user_roles").select("user_id,role").in_("user_id", ids).execute(),
            "data",
            None,
        )
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and isinstance(row.get("role"), str):
                roles_by_user.setdefault(str(row.get("user_id")), []).append(row["role"])
    return {
        "accounts": [
            AccountLookupOut(
                user_id=person["user_id"],
                display_name=person["display_name"],
                email=person["email"],
                roles=sorted(roles_by_user.get(person["user_id"], [])),
            ).model_dump()
            for person in people
        ]
    }


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
