from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from app.core.admin_audit import (
    AdminAuditedRoute,
    AdminAuditRecorder,
    get_admin_audit_recorder,
)
from app.core.auth import CurrentUser, require_role
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    route_class=AdminAuditedRoute,
    dependencies=[Depends(require_role("admin"))],
)


class AdminEchoRequest(BaseModel):
    entity_type: str = Field(min_length=1)
    entity_id: UUID | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


@router.get("/health")
async def admin_health(
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> dict[str, str]:
    return {"status": "ok", "actor": current_user.id}


@router.post("/echo")
async def admin_echo(
    body: AdminEchoRequest,
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> dict[str, str]:
    recorder.record(
        action="admin.echo",
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        before=body.before,
        after=body.after,
    )
    return {"status": "ok"}
