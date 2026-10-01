"""Admin dashboard aggregates — cached 5 minutes, ledger-derived liabilities."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Protocol, cast

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.ask.spend import (
    MICROS_PER_USD,
    current_month_total_usd_micros,
    is_killed,
    reset_kill_switch,
)
from app.services.ledger.engine import account_balance_ngwee, resolve_account_id
from app.services.ledger.templates import AccountRef
from app.services.orders.audit import run_sql_script
from app.services.payments.reconcile import _has_discrepancies
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DASHBOARD_CACHE_TTL_SECONDS = 300.0
DEFAULT_AI_MONTHLY_CAP_USD = 15

_cache_lock = threading.Lock()
_cache_payload: DashboardOut | None = None
_cache_expires_at: float = 0.0

dashboard_router = APIRouter(prefix="/dashboard", tags=["admin-dashboard"])


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class OrdersByStatusOut(BaseModel):
    placed: int = 0
    confirmed: int = 0
    processing: int = 0
    ready: int = 0
    shipped: int = 0
    delivered: int = 0
    completed: int = 0
    cancelled: int = 0


class PayoutLiabilitiesOut(BaseModel):
    escrow_held_ngwee: int
    released_unpaid_ngwee: int
    total_ngwee: int


class ReconciliationTileOut(BaseModel):
    status: str = Field(
        description="green for certified current evidence; red for discrepancies; otherwise unknown"
    )
    report_id: str | None = None
    report_date: date | None = None
    has_mismatch: bool = False
    provenance: str = "MISSING"
    evidence_state: str = "missing"
    expected_report_date: date | None = None
    provider_account_id: str | None = None
    currency: str | None = None
    version_number: int | None = None
    input_fingerprint: str | None = None
    source_version: str | None = None
    certifiable: bool = False
    discrepancies: dict[str, Any] = Field(default_factory=dict)


class CatalogCountsOut(BaseModel):
    vendors: int
    listings: int
    products: int


class AiUsageTileOut(BaseModel):
    data_available: bool
    flagged: bool
    killed: bool = False
    spend_usd: float | None = None
    cap_usd: int


class KillSwitchResetOut(BaseModel):
    reset: bool
    killed: bool


class FunnelSnapshotOut(BaseModel):
    checkout_started: int
    checkout_completed: int
    orders_placed: int
    orders_completed: int


class DashboardOut(BaseModel):
    gmv_ngwee: int
    orders_by_status: OrdersByStatusOut
    payout_liabilities: PayoutLiabilitiesOut
    reconciliation: ReconciliationTileOut
    counts: CatalogCountsOut
    ai_usage: AiUsageTileOut
    funnel: FunnelSnapshotOut
    cached_at: datetime


def clear_dashboard_cache() -> None:
    global _cache_payload, _cache_expires_at
    with _cache_lock:
        _cache_payload = None
        _cache_expires_at = 0.0


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return cast(dict[str, Any], first)
    return None


def platform_escrow_held_ngwee() -> int:
    """Ledger-derived escrow still held platform-wide (M12-P08 seam)."""
    account_id = resolve_account_id(AccountRef("escrow"))
    balance = account_balance_ngwee(account_id)
    return max(0, -balance)


def platform_released_unpaid_ngwee() -> int:
    """Sum of vendor_payable credits not yet paid out (negative balances)."""
    script = """
SELECT coalesce(sum(greatest(0, -vendor_bal)), 0)::text
FROM (
  SELECT la.id, coalesce(sum(lp.amount_ngwee), 0) AS vendor_bal
  FROM public.ledger_accounts la
  LEFT JOIN public.ledger_postings lp ON lp.account_id = la.id
  WHERE la.kind = 'vendor_payable'
  GROUP BY la.id
) per_vendor;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise AppError(
            code="ledger_query_failed",
            message="Failed to derive released-unpaid liabilities",
            http_status=500,
            details={"error": result.error},
        )
    return int(result.rows[0])


def compute_payout_liabilities() -> PayoutLiabilitiesOut:
    escrow_held = platform_escrow_held_ngwee()
    released_unpaid = platform_released_unpaid_ngwee()
    return PayoutLiabilitiesOut(
        escrow_held_ngwee=escrow_held,
        released_unpaid_ngwee=released_unpaid,
        total_ngwee=escrow_held + released_unpaid,
    )


def compute_gmv_ngwee() -> int:
    script = """
SELECT coalesce(sum(item_totals.item_total + o.delivery_fee_ngwee), 0)::text
FROM public.orders o
JOIN (
  SELECT order_id, coalesce(sum(qty * unit_price_ngwee), 0) AS item_total
  FROM public.order_items
  GROUP BY order_id
) item_totals ON item_totals.order_id = o.id
WHERE o.status <> 'cancelled';
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise AppError(
            code="dashboard_query_failed",
            message="Failed to compute GMV",
            http_status=500,
            details={"error": result.error},
        )
    return int(result.rows[0])


def _count_table(service_client: ServiceRoleClient, table: str) -> int:
    response = service_client.client.table(table).select("id", count="exact").limit(0).execute()
    count = getattr(response, "count", None)
    if isinstance(count, int):
        return count
    return len(_rows(response))


def _orders_by_status(service_client: ServiceRoleClient) -> OrdersByStatusOut:
    response = service_client.client.table("orders").select("status").execute()
    counts = OrdersByStatusOut()
    for row in _rows(response):
        status = str(row.get("status", ""))
        if hasattr(counts, status):
            setattr(counts, status, getattr(counts, status) + 1)
    return counts


def _latest_reconciliation(service_client: ServiceRoleClient) -> ReconciliationTileOut:
    # Writer's daily default is the most recent completed UTC day. Read only
    # this configured account and supported currency, not a globally newest row.
    expected = datetime.now(UTC).date() - timedelta(days=1)
    account = os.environ.get("LENCO_ACCOUNT_ID", "").strip()
    if not account:
        return ReconciliationTileOut(
            status="unknown", evidence_state="account_unconfigured", expected_report_date=expected
        )
    row = _single_row(
        service_client.client.table("reconciliation_report_versions")
        .select("*")
        .eq("provider_account_id", account)
        .eq("currency", "ZMW")
        .lte("report_date", expected.isoformat())
        .order("report_date", desc=True)
        .order("version_number", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    provenance = "VERSIONED_ACCOUNT_BOUND"
    if row is None:
        row = _single_row(
            service_client.client.table("reconciliation_reports")
            .select("id, report_date, summary, discrepancies")
            .lte("report_date", expected.isoformat())
            .order("report_date", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        provenance = "LEGACY_UNVERSIONED_ACCOUNT_UNBOUND"
    if row is None:
        return ReconciliationTileOut(
            status="unknown",
            expected_report_date=expected,
            provider_account_id=account,
            currency="ZMW",
        )
    raw_date = row.get("report_date")
    try:
        observed = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
    except ValueError:
        observed = None
    summary = row.get("summary")
    discrepancies = row.get("discrepancies")
    valid_payload = isinstance(summary, dict) and isinstance(discrepancies, dict)
    discrepancies = discrepancies if isinstance(discrepancies, dict) else {}
    try:
        mismatch = _has_discrepancies(discrepancies)
    except (TypeError, ValueError):
        mismatch = False
        valid_payload = False
    certifiable = isinstance(summary, dict) and summary.get("certifiable") is True
    if provenance.startswith("LEGACY"):
        state = "legacy_unbound"
    elif not valid_payload or not isinstance(observed, date):
        state = "invalid"
    elif observed != expected:
        state = "stale"
    elif mismatch:
        state = "unresolved"
    elif not certifiable:
        state = "noncertifying"
    else:
        state = "current_clean"
    return ReconciliationTileOut(
        status="red" if mismatch else "green" if state == "current_clean" else "unknown",
        report_id=str(row["id"]),
        report_date=observed,
        has_mismatch=mismatch,
        provenance=provenance,
        evidence_state=state,
        expected_report_date=expected,
        provider_account_id=row.get("provider_account_id"),
        currency=row.get("currency"),
        version_number=row.get("version_number"),
        input_fingerprint=row.get("input_fingerprint"),
        source_version=row.get("source_version"),
        certifiable=certifiable,
        discrepancies=discrepancies,
    )


def _ai_monthly_cap_usd(service_client: ServiceRoleClient) -> int:
    response = (
        service_client.client.table("platform_config")
        .select("value")
        .eq("key", "ai_monthly_cap_usd")
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return DEFAULT_AI_MONTHLY_CAP_USD
    value = row.get("value")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return DEFAULT_AI_MONTHLY_CAP_USD


def _funnel_snapshot(service_client: ServiceRoleClient) -> FunnelSnapshotOut:
    checkout_response = service_client.client.table("checkout_groups").select("status").execute()
    checkout_started = 0
    checkout_completed = 0
    for row in _rows(checkout_response):
        status = str(row.get("status", ""))
        if status in {"pending", "completed", "abandoned", "expired"}:
            checkout_started += 1
        if status == "completed":
            checkout_completed += 1

    orders_response = service_client.client.table("orders").select("status").execute()
    orders_placed = 0
    orders_completed = 0
    for row in _rows(orders_response):
        status = str(row.get("status", ""))
        if status != "cancelled":
            orders_placed += 1
        if status == "completed":
            orders_completed += 1

    return FunnelSnapshotOut(
        checkout_started=checkout_started,
        checkout_completed=checkout_completed,
        orders_placed=orders_placed,
        orders_completed=orders_completed,
    )


def _build_ai_usage_tile(service_client: ServiceRoleClient) -> AiUsageTileOut:
    """Real Ask-spend tile from ``ask_spend_monthly`` + the kill-switch state.

    Aggregate money only — never per-user question content. Falls back to a
    'no data' placeholder if the spend row can't be read, so one flaky tile never
    breaks the whole dashboard.
    """
    cap_usd = _ai_monthly_cap_usd(service_client)
    client = service_client.client
    try:
        spent_micros = current_month_total_usd_micros(client=client)
        killed = is_killed(client=client)
    except Exception:  # noqa: BLE001 — a spend-read hiccup must not break the dashboard.
        logger.warning("AI-spend tile read failed; showing no-data placeholder", exc_info=True)
        return AiUsageTileOut(data_available=False, flagged=False, killed=False, cap_usd=cap_usd)
    return AiUsageTileOut(
        data_available=True,
        flagged=killed,
        killed=killed,
        spend_usd=round(spent_micros / MICROS_PER_USD, 2),
        cap_usd=cap_usd,
    )


def build_dashboard(service_client: ServiceRoleClient) -> DashboardOut:
    liabilities = compute_payout_liabilities()
    return DashboardOut(
        gmv_ngwee=compute_gmv_ngwee(),
        orders_by_status=_orders_by_status(service_client),
        payout_liabilities=liabilities,
        reconciliation=_latest_reconciliation(service_client),
        counts=CatalogCountsOut(
            vendors=_count_table(service_client, "vendors"),
            listings=_count_table(service_client, "vendor_listings"),
            products=_count_table(service_client, "products"),
        ),
        ai_usage=_build_ai_usage_tile(service_client),
        funnel=_funnel_snapshot(service_client),
        cached_at=datetime.now(UTC),
    )


def _get_cached_dashboard(service_client: ServiceRoleClient) -> DashboardOut:
    global _cache_payload, _cache_expires_at
    now = time.monotonic()
    with _cache_lock:
        if _cache_payload is not None and now < _cache_expires_at:
            return _cache_payload

    payload = build_dashboard(service_client)
    with _cache_lock:
        _cache_payload = payload
        _cache_expires_at = now + DASHBOARD_CACHE_TTL_SECONDS
    return payload


@dashboard_router.get("", response_model=DashboardOut)
async def get_admin_dashboard(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> DashboardOut:
    return _get_cached_dashboard(service_client)


admin_router.include_router(dashboard_router)


def _invalidate_dashboard_cache() -> None:
    """Drop the cached dashboard so the next read reflects a just-changed state."""
    global _cache_payload, _cache_expires_at
    with _cache_lock:
        _cache_payload = None
        _cache_expires_at = 0.0


# Defined directly on the admin router (prefix /admin, route_class=AdminAuditedRoute,
# require_role("admin")) so it audits + gates like /admin/echo and enumerates cleanly.
@admin_router.post("/ai-spend/reset-kill-switch", response_model=KillSwitchResetOut)
async def reset_ai_kill_switch(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> KillSwitchResetOut:
    """Admin-only: clear the Ask $/mo kill-switch latch (audited).

    Aggregate control only — touches no per-user data. The clear is recorded to
    `audit_log` (who + when) and the dashboard cache is invalidated so the AI tile
    reflects the change immediately.
    """
    client = service_client.client
    reset = reset_kill_switch(client=client)
    killed = is_killed(client=client)
    recorder.record(
        action="ai.kill_switch.reset",
        entity_type="ask_spend_monthly",
        entity_id=None,
        before={"killed": True},
        after={"reset": reset, "killed": killed},
    )
    _invalidate_dashboard_cache()
    return KillSwitchResetOut(reset=reset, killed=killed)
