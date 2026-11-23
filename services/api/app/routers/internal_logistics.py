"""n8n tick for logistics SLA alerts and customer delivered/cancelled messages."""

from __future__ import annotations

from typing import Annotated, Any

from app.deps import get_supabase_client
from app.routers.internal_n8n import require_internal_n8n_token
from app.services.logistics.alerts import run_sla_watch
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/internal/logistics", tags=["internal-logistics"])


@router.post("/sla-watch/tick", dependencies=[Depends(require_internal_n8n_token)])
def sla_watch_tick(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    """Repeat-safe: stale courier jobs, silent vendors, customer messages (outbox)."""
    return {"ok": True, **run_sla_watch(supabase.client)}
