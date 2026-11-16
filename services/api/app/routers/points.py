"""Convergeo Points — the customer's own balance and history (flag ``loyalty_points``).

Read-only. Every query filters on ``user_id = current_user.id`` (service client
round-trip; the table also has FORCE RLS limiting direct reads to own rows).
Points are earned/reversed only by the database (migration 20261116020000);
redemption into a coupon waits for PR #792 (see app/services/points/redeem.py).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, Final, Literal, Protocol, cast

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import RateLimitPolicy
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends, Query

router = APIRouter(tags=["points"])

FLAG: Final = "loyalty_points"
TABLE: Final = "points_ledger"
READ_POLICY: Final = RateLimitPolicy(scope="points_read", limit=300, window=timedelta(hours=1))
DEFAULT_THRESHOLD: Final = 500
MAX_HISTORY: Final = 50

Reason = Literal["order_completed", "review", "reversal", "redeem", "expire", "admin_adjust"]


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class PointsEntry(StrictModel):
    id: str
    points: int
    reason: Reason
    order_id: str | None = None
    created_at: str


class PointsOut(StrictModel):
    enabled: bool
    balance: int
    lifetime_earned: int
    next_coupon_threshold: int
    points_to_next: int
    redeem_available: bool
    history: list[PointsEntry]


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], r) for r in data if isinstance(r, dict)]
    return []


def points_enabled(service_client: ServiceRoleClient) -> bool:
    """Fresh read, fails closed."""
    try:
        rows = _rows(
            service_client.client.table("feature_flags")
            .select("enabled")
            .eq("flag", FLAG)
            .limit(1)
            .execute()
        )
    except Exception:
        return False
    return bool(rows and rows[0].get("enabled") is True)


def _threshold(service_client: ServiceRoleClient) -> int:
    try:
        rows = _rows(
            service_client.client.table("platform_config")
            .select("value")
            .eq("key", "points_coupon_threshold")
            .limit(1)
            .execute()
        )
    except Exception:
        return DEFAULT_THRESHOLD
    raw = rows[0].get("value") if rows else None
    if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
        return raw
    return DEFAULT_THRESHOLD


@router.get("/me/points", response_model=PointsOut)
async def my_points(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=MAX_HISTORY)] = 20,
) -> PointsOut:
    if not points_enabled(service_client):
        raise AppError(code="not_found", message="Not found", http_status=404)
    allowed, retry_after = bump_rate_counter(
        scope=READ_POLICY.scope,
        key=current_user.id,
        window=READ_POLICY.window,
        limit=READ_POLICY.limit,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="account.rewards.errors.rateLimited",
            message="Too many requests",
        )
    summary_resp = service_client.client.rpc(
        "points_summary", {"p_user": current_user.id}
    ).execute()
    summary = summary_resp.data if isinstance(summary_resp.data, dict) else {}
    history = _rows(
        service_client.client.table(TABLE)
        .select("id, points, reason, order_id, created_at")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    balance = int(summary.get("balance") or 0)
    threshold = _threshold(service_client)
    return PointsOut(
        enabled=True,
        balance=balance,
        lifetime_earned=int(summary.get("lifetime_earned") or 0),
        next_coupon_threshold=threshold,
        points_to_next=max(threshold - balance, 0),
        # TODO-after-#792: true once redeem-as-coupon is wired.
        redeem_available=False,
        history=[
            PointsEntry.model_validate(row) for row in history if int(row.get("points", 0)) != 0
        ],
    )
