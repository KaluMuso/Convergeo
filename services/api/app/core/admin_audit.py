from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import Depends, Request, Response
from fastapi.routing import APIRoute

from app.core.auth import CurrentUser, require_role
from app.errors import AppError
from app.supabase_client import SupabaseServiceClient, get_supabase_service_client

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_AUDIT_RECORDER_STATE_KEY = "admin_audit_recorder"


class AdminAuditRecorder:
    """Records a single admin mutation into `public.audit_log` via the service-role client."""

    def __init__(self, actor_id: str, service_client: SupabaseServiceClient) -> None:
        self._actor_id = actor_id
        self._service_client = service_client
        self._recorded = False

    @property
    def is_recorded(self) -> bool:
        return self._recorded

    def record(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | UUID | None,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if self._recorded:
            raise AppError(
                code="audit_duplicate",
                message="Admin mutation already recorded for this request",
                http_status=500,
            )

        normalized_entity_id = _normalize_entity_id(entity_id)
        row = {
            "actor": self._actor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": normalized_entity_id,
            "before": dict(before) if before is not None else None,
            "after": dict(after) if after is not None else None,
        }

        response = self._service_client.client.table("audit_log").insert(row).execute()
        data = response.data
        if not isinstance(data, list) or not data:
            raise AppError(
                code="audit_write_failed",
                message="Failed to persist admin audit_log row",
                http_status=500,
            )

        self._recorded = True
        return cast(dict[str, Any], data[0])


def _normalize_entity_id(entity_id: str | UUID | None) -> str | None:
    if entity_id is None:
        return None
    if isinstance(entity_id, UUID):
        return str(entity_id)
    value = entity_id.strip()
    return value or None


async def get_admin_audit_recorder(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> AdminAuditRecorder:
    existing = getattr(request.state, _AUDIT_RECORDER_STATE_KEY, None)
    if isinstance(existing, AdminAuditRecorder):
        return existing

    recorder = AdminAuditRecorder(current_user.id, get_supabase_service_client())
    setattr(request.state, _AUDIT_RECORDER_STATE_KEY, recorder)
    return recorder


def enforce_admin_audit_or_raise(request: Request, recorder: AdminAuditRecorder) -> None:
    if request.method in MUTATING_METHODS and not recorder.is_recorded:
        raise AppError(
            code="audit_incomplete",
            message="Admin mutation must write an audit_log row",
            http_status=500,
            details={"method": request.method, "path": request.url.path},
        )


class AdminAuditedRoute(APIRoute):
    """Transparent admin audit guard — mutating routes must call `AdminAuditRecorder.record`."""

    def get_route_handler(self) -> Callable[[Request], Any]:
        original_route_handler = super().get_route_handler()

        async def audited_route_handler(request: Request) -> Response:
            response = await original_route_handler(request)

            recorder = getattr(request.state, _AUDIT_RECORDER_STATE_KEY, None)
            if isinstance(recorder, AdminAuditRecorder):
                enforce_admin_audit_or_raise(request, recorder)
            elif request.method in MUTATING_METHODS:
                raise AppError(
                    code="audit_incomplete",
                    message="Admin mutation must write an audit_log row",
                    http_status=500,
                    details={"method": request.method, "path": request.url.path},
                )

            return response

        return audited_route_handler


def mutation_requires_audit(request: Request) -> bool:
    return request.method in MUTATING_METHODS
