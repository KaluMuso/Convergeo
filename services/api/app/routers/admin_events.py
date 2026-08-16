"""Admin event high-value verification gate."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Protocol
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router
from fastapi import Depends
from pydantic import BaseModel


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class HighValueVerifyResponse(BaseModel):
    event_id: UUID
    high_value_verified_at: datetime
    high_value_verified_by: UUID


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


@router.post("/events/{event_id}/high-value-verify", response_model=HighValueVerifyResponse)
def verify_high_value_event(
    event_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> HighValueVerifyResponse:
    now = datetime.now(UTC)
    response = (
        service_client.client.table("events")
        .update(
            {
                "high_value_verified_at": now.isoformat(),
                "high_value_verified_by": current_user.id,
            }
        )
        .eq("id", str(event_id))
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Event not found", http_status=404)
    recorder.record(
        action="admin.events.high_value_verify",
        entity_type="event",
        entity_id=event_id,
        before=None,
        after={"high_value_verified_by": current_user.id},
    )
    return HighValueVerifyResponse(
        event_id=event_id,
        high_value_verified_at=now,
        high_value_verified_by=UUID(current_user.id),
    )
