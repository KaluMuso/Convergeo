"""M17-P08 — clip cost and conversion dashboard.

Mounted on ``admin_base``, so ``require_role("admin")`` and the audited route
class apply to every path without this module restating them.

The dashboard answers two questions an operator actually has:

* **"Are we going to get a bill?"** — recorded spend for the month, the cap, the
  headroom left, and whether the upload guard has tripped.
* **"Is any of this working?"** — the funnel, from published clips through views
  and likes to add-to-cart and attributed orders. The attributed numbers count
  only server-validated attribution (M17-P05), so a vendor cannot inflate them.

The reset action is the documented operator reversal from
``docs/ops/clip-cost-runbook.md``. It is audited, because "who turned the guard
off, and when" is exactly the question asked after a surprising invoice.
"""

from __future__ import annotations

from typing import Annotated, Any, Final, Protocol

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.routers.admin_base import router as admin_router
from app.services.clips import spend, state_machine
from fastapi import APIRouter, Depends
from pydantic import BaseModel

analytics_router = APIRouter(prefix="/clip-analytics", tags=["admin-clips"])

CLIPS_TABLE: Final = "video_clips"
ANALYTICS_TABLE: Final = "analytics_events"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class ClipCostSummary(BaseModel):
    month_key: str
    spend_usd_micros: int
    cap_usd_micros: int
    headroom_usd_micros: int
    uploads_paused: bool


class ClipFunnelSummary(BaseModel):
    published_clips: int
    pending_review: int
    rejected: int
    taken_down: int
    views: int
    likes: int
    add_to_carts: int
    attributed_orders: int


class ClipAnalyticsResponse(BaseModel):
    cost: ClipCostSummary
    funnel: ClipFunnelSummary


class KillSwitchResetResponse(BaseModel):
    month_key: str
    uploads_paused: bool
    reset: bool


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _count_by_status(service_client: ServiceRoleClient) -> dict[str, int]:
    rows = _rows(
        service_client.client.table(CLIPS_TABLE)
        .select("id, status, view_count, like_count")
        .execute()
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row.get("status") or "")] = counts.get(str(row.get("status") or ""), 0) + 1
    counts["_views"] = sum(int(row.get("view_count") or 0) for row in rows)
    counts["_likes"] = sum(int(row.get("like_count") or 0) for row in rows)
    return counts


def _count_events(service_client: ServiceRoleClient, event_type: str) -> int:
    try:
        return len(
            _rows(
                service_client.client.table(ANALYTICS_TABLE)
                .select("id")
                .eq("entity_type", "video_clip")
                .eq("event_type", event_type)
                .execute()
            )
        )
    except Exception:
        # An analytics outage must not take the cost dashboard down with it —
        # the cost half is the half that prevents a bill.
        return 0


@analytics_router.get("", response_model=ClipAnalyticsResponse)
async def get_clip_analytics(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ClipAnalyticsResponse:
    counts = _count_by_status(service_client)
    month_key = spend.current_month_key()

    return ClipAnalyticsResponse(
        cost=ClipCostSummary(
            month_key=month_key,
            spend_usd_micros=spend.current_month_total_micros(service_client),
            cap_usd_micros=spend.monthly_cap_usd_micros(service_client),
            headroom_usd_micros=spend.headroom_micros(service_client),
            uploads_paused=spend.is_killed(service_client),
        ),
        funnel=ClipFunnelSummary(
            published_clips=counts.get(state_machine.PUBLISHED, 0),
            pending_review=counts.get(state_machine.PENDING_REVIEW, 0),
            rejected=counts.get(state_machine.REJECTED, 0),
            taken_down=counts.get(state_machine.TAKEN_DOWN, 0),
            views=counts.get("_views", 0),
            likes=counts.get("_likes", 0),
            add_to_carts=_count_events(service_client, "clip_add_to_cart"),
            attributed_orders=_count_events(service_client, "clip_order"),
        ),
    )


@analytics_router.post("/reset-kill-switch", response_model=KillSwitchResetResponse)
async def reset_clip_kill_switch(
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> KillSwitchResetResponse:
    """Re-open uploads for the month. Reversible, recorded, and never silent."""
    month_key = spend.current_month_key()
    was_paused = spend.is_killed(service_client, month_key=month_key)
    did_reset = spend.reset_kill_switch(service_client, month_key=month_key)

    recorder.record(
        action="admin.clips.reset_kill_switch",
        entity_type="clip_spend_monthly",
        entity_id=None,
        before={"month_key": month_key, "uploads_paused": was_paused},
        after={"month_key": month_key, "uploads_paused": False, "reset": did_reset},
    )

    return KillSwitchResetResponse(
        month_key=month_key,
        uploads_paused=spend.is_killed(service_client, month_key=month_key),
        reset=did_reset,
    )


admin_router.include_router(analytics_router)
