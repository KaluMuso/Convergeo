"""Admin translation overrides — the write side of the admin translator.

Overrides layer a locale's value for a namespaced message key over the committed
message files. Admins edit here; the admin app merges overrides with the bundled
files and exports the result back into packages/i18n/messages for the apps to
ship. Data access is service-role (RLS-bypassing); admin authz is enforced here.
"""

from __future__ import annotations

from typing import Annotated, Any

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.schemas.base import StrictModel
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field

router = APIRouter(prefix="/admin/translations", tags=["admin-translations"])

_LOCALE = Field(min_length=2, max_length=16)
_NAMESPACE = Field(min_length=1, max_length=64)
_MESSAGE_KEY = Field(min_length=1, max_length=200)


class OverrideRow(StrictModel):
    locale: str
    namespace: str
    message_key: str
    value: str
    updated_at: str | None = None


class OverridesResponse(StrictModel):
    overrides: list[OverrideRow]


class OverridePutRequest(StrictModel):
    locale: str = _LOCALE
    namespace: str = _NAMESPACE
    message_key: str = _MESSAGE_KEY
    value: str = Field(min_length=1, max_length=4000)


def _to_override(row: dict[str, Any]) -> OverrideRow:
    updated_at = row.get("updated_at")
    return OverrideRow(
        locale=str(row["locale"]),
        namespace=str(row["namespace"]),
        message_key=str(row["message_key"]),
        value=str(row["value"]),
        updated_at=str(updated_at) if updated_at is not None else None,
    )


@router.get("/overrides", response_model=OverridesResponse)
def list_overrides(
    user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> OverridesResponse:
    del user
    response = (
        service_client.client.table("translation_overrides")
        .select("locale, namespace, message_key, value, updated_at")
        .order("namespace")
        .order("message_key")
        .execute()
    )
    rows = [row for row in (response.data or []) if isinstance(row, dict)]
    return OverridesResponse(overrides=[_to_override(row) for row in rows])


@router.put("/overrides", response_model=OverrideRow)
def upsert_override(
    body: OverridePutRequest,
    user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> OverrideRow:
    payload = {
        "locale": body.locale,
        "namespace": body.namespace,
        "message_key": body.message_key,
        "value": body.value,
        "updated_by": user.id,
    }
    response = (
        service_client.client.table("translation_overrides")
        .upsert(payload, on_conflict="locale,namespace,message_key")
        .execute()
    )
    rows = [row for row in (response.data or []) if isinstance(row, dict)]
    if rows:
        return _to_override(rows[0])
    # Fake clients may not echo the row; reflect the request.
    return OverrideRow(
        locale=body.locale,
        namespace=body.namespace,
        message_key=body.message_key,
        value=body.value,
    )


@router.delete("/overrides", status_code=204)
def delete_override(
    user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    locale: Annotated[str, Query(min_length=2, max_length=16)],
    namespace: Annotated[str, Query(min_length=1, max_length=64)],
    message_key: Annotated[str, Query(min_length=1, max_length=200)],
) -> Response:
    del user
    (
        service_client.client.table("translation_overrides")
        .delete()
        .eq("locale", locale)
        .eq("namespace", namespace)
        .eq("message_key", message_key)
        .execute()
    )
    return Response(status_code=204)


__all__ = ["delete_override", "list_overrides", "upsert_override"]
