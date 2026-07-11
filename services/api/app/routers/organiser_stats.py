"""Organiser dashboard-lite stats (M10-P08) — sales, check-in, ledger-derived escrow split.

Read-only, organiser-scoped. All money and check-in figures are derived from the
authoritative tables (tickets/order_items/ledger_*) rather than a cached counter,
mirroring how vendor_payouts.py derives pending/released balances from the ledger.
"""

from __future__ import annotations

from typing import Annotated, Protocol

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.orders.audit import run_sql_script, sql_literal
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/organiser", tags=["organiser-stats"])

MASS_REFUND_FLAG_ACTION = "event_release.mass_refund_flagged"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> object: ...


class TicketTypeSales(StrictModel):
    ticket_type_id: str
    kind: str
    name: str
    price_ngwee: int
    sold: int
    checked_in: int
    revenue_ngwee: int


class CheckInProgress(StrictModel):
    issued: int
    checked_in: int


class EscrowSplit(StrictModel):
    pending_ngwee: int
    released_ngwee: int


class OrganiserEventStatsResponse(StrictModel):
    event_id: str
    event_status: str
    sales_by_type: list[TicketTypeSales]
    revenue_ngwee: int
    check_in: CheckInProgress
    escrow: EscrowSplit
    mass_refund_flagged: bool


def _sql_uuid(value: str) -> str:
    return f"'{value}'::uuid"


def _load_vendor_id_for_owner(owner_user_id: str) -> str | None:
    owner_sql = _sql_uuid(owner_user_id)
    script = f"""
SELECT id::text
FROM public.vendors
WHERE owner_user_id = {owner_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None
    return result.rows[0]


def _load_event(event_id: str) -> tuple[str, str] | None:
    """Returns (organiser_vendor_id, status) or None if the event does not exist."""
    event_sql = _sql_uuid(event_id)
    script = f"""
SELECT organiser_vendor_id::text, status
FROM public.events
WHERE id = {event_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None
    parts = result.rows[0].split("|", 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def _load_sales_by_type(event_id: str) -> list[TicketTypeSales]:
    event_sql = _sql_uuid(event_id)
    script = f"""
SELECT
  tt.id::text,
  tt.kind,
  tt.name,
  tt.price_ngwee::text,
  count(t.id) FILTER (
    WHERE t.status IN ('issued', 'checked_in') AND t.order_item_id IS NOT NULL
  )::text AS sold,
  count(t.id) FILTER (
    WHERE t.status = 'checked_in' AND t.order_item_id IS NOT NULL
  )::text AS checked_in,
  coalesce(sum(oi.unit_price_ngwee) FILTER (
    WHERE t.status IN ('issued', 'checked_in') AND t.order_item_id IS NOT NULL
  ), 0)::text AS revenue
FROM public.ticket_types tt
LEFT JOIN public.tickets t ON t.ticket_type_id = tt.id
LEFT JOIN public.order_items oi ON oi.id = t.order_item_id
WHERE tt.event_id = {event_sql}
GROUP BY tt.id, tt.kind, tt.name, tt.price_ngwee, tt.created_at
ORDER BY tt.created_at ASC;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise AppError(
            code="stats_query_failed",
            message="Failed to load ticket type sales",
            http_status=500,
            details={"error": result.error},
        )

    rows: list[TicketTypeSales] = []
    for raw in result.rows:
        parts = raw.split("|", 6)
        if len(parts) != 7:
            continue
        ticket_type_id, kind, name, price_raw, sold_raw, checked_in_raw, revenue_raw = parts
        # order_items.unit_price_ngwee is forced to a nominal 1 ngwee for free_rsvp
        # (schema requires unit_price_ngwee > 0) — that is a storage workaround, not
        # real money, so free_rsvp revenue is always reported as 0.
        revenue = 0 if kind == "free_rsvp" else int(revenue_raw)
        rows.append(
            TicketTypeSales(
                ticket_type_id=ticket_type_id,
                kind=kind,
                name=name,
                price_ngwee=int(price_raw),
                sold=int(sold_raw),
                checked_in=int(checked_in_raw),
                revenue_ngwee=revenue,
            )
        )
    return rows


def _load_escrow_split(event_id: str) -> EscrowSplit:
    event_sql = _sql_uuid(event_id)
    script = f"""
WITH event_orders AS (
  SELECT DISTINCT oi.order_id
  FROM public.order_item_tickets oit
  JOIN public.order_items oi ON oi.id = oit.order_item_id
  JOIN public.event_instances ei ON ei.id = oit.instance_id
  WHERE ei.event_id = {event_sql}
),
paid_orders AS (
  SELECT eo.order_id
  FROM event_orders eo
  JOIN public.orders o ON o.id = eo.order_id
  WHERE EXISTS (
    SELECT 1 FROM public.payments p
    WHERE p.checkout_group_id = o.checkout_group_id AND p.status = 'success'
  )
),
per_order AS (
  SELECT
    po.order_id,
    coalesce((
      SELECT sum(lp.amount_ngwee)
      FROM public.ledger_transactions lt
      JOIN public.ledger_postings lp ON lp.transaction_id = lt.id
      JOIN public.ledger_accounts la ON la.id = lp.account_id AND la.kind = 'escrow'
      WHERE lt.order_id = po.order_id
    ), 0) AS escrow_net,
    coalesce((
      SELECT sum(-lp.amount_ngwee)
      FROM public.ledger_transactions lt
      JOIN public.ledger_postings lp ON lp.transaction_id = lt.id
      JOIN public.ledger_accounts la ON la.id = lp.account_id AND la.kind = 'vendor_payable'
      WHERE lt.order_id = po.order_id AND lt.kind = 'release_to_vendor'
    ), 0) AS released_net
  FROM paid_orders po
)
SELECT
  coalesce(sum(greatest(0, -escrow_net)), 0)::text,
  coalesce(sum(released_net), 0)::text
FROM per_order;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise AppError(
            code="stats_query_failed",
            message="Failed to derive escrow split",
            http_status=500,
            details={"error": result.error},
        )
    parts = result.rows[0].split("|", 1)
    if len(parts) != 2:
        return EscrowSplit(pending_ngwee=0, released_ngwee=0)
    return EscrowSplit(pending_ngwee=int(parts[0]), released_ngwee=int(parts[1]))


def _mass_refund_flagged(event_id: str) -> bool:
    event_sql = _sql_uuid(event_id)
    action_sql = sql_literal(MASS_REFUND_FLAG_ACTION)
    script = f"""
SELECT count(*)::text
FROM public.audit_log al
WHERE al.entity_type = 'order'
  AND al.action = {action_sql}
  AND al.entity_id IN (
    SELECT DISTINCT oi.order_id
    FROM public.order_item_tickets oit
    JOIN public.order_items oi ON oi.id = oit.order_item_id
    JOIN public.event_instances ei ON ei.id = oit.instance_id
    WHERE ei.event_id = {event_sql}
  );
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return False
    return int(result.rows[0]) > 0


@router.get("/events/{event_id}/stats", response_model=OrganiserEventStatsResponse)
async def get_organiser_event_stats(
    event_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> OrganiserEventStatsResponse:
    del service_client  # data access is raw-SQL (run_sql_script), like escrow/event_release.py

    vendor_id = _load_vendor_id_for_owner(current_user.id)
    if vendor_id is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )

    event = _load_event(event_id)
    if event is None:
        raise AppError(
            code="not_found",
            message="Event not found",
            http_status=404,
            details={"message_key": "vendor.eventDashboard.errors.notFound"},
        )
    organiser_vendor_id, event_status = event
    if organiser_vendor_id != vendor_id:
        raise AppError(
            code="forbidden",
            message="Organiser may only view stats for their own events",
            http_status=403,
            details={"message_key": "vendor.eventDashboard.errors.forbidden"},
        )

    sales = _load_sales_by_type(event_id)
    total_revenue = sum(row.revenue_ngwee for row in sales)
    total_issued = sum(row.sold for row in sales)
    total_checked_in = sum(row.checked_in for row in sales)
    escrow = _load_escrow_split(event_id)
    flagged = _mass_refund_flagged(event_id)

    return OrganiserEventStatsResponse(
        event_id=event_id,
        event_status=event_status,
        sales_by_type=sales,
        revenue_ngwee=total_revenue,
        check_in=CheckInProgress(issued=total_issued, checked_in=total_checked_in),
        escrow=escrow,
        mass_refund_flagged=flagged,
    )


__all__ = [
    "get_organiser_event_stats",
]
