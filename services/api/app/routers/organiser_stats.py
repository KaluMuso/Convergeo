"""Organiser dashboard-lite stats (M10-P08) — sales, check-in, ledger-derived escrow split.

Read-only, organiser-scoped. All money and check-in figures are derived from the
authoritative tables (tickets/order_items/ledger_*) rather than a cached counter,
mirroring how vendor_payouts.py derives pending/released balances from the ledger.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Annotated, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.orders.audit import run_sql_script, sql_literal
from fastapi import APIRouter, Depends, Response

router = APIRouter(prefix="/organiser", tags=["organiser-stats"])

MASS_REFUND_FLAG_ACTION = "event_release.mass_refund_flagged"

LUSAKA_TZ = ZoneInfo("Africa/Lusaka")

# Upper bound on roster rows returned in one response — realistic Zambia events are
# far smaller; this caps a pathological payload. `truncated` flags when the true
# count exceeds it so the UI can say so.
ROSTER_CAP = 2000


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


class RosterAttendee(StrictModel):
    ticket_id: str
    holder_name: str | None
    ticket_type_id: str
    ticket_type_name: str
    kind: str
    instance_id: str
    starts_at: str
    status: str
    checked_in_at: str | None


class OrganiserEventRosterResponse(StrictModel):
    event_id: str
    event_status: str
    total: int
    checked_in: int
    truncated: bool
    attendees: list[RosterAttendee]


def _sql_uuid(value: str) -> str:
    return f"'{value}'::uuid"


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


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


def _roster_instance_clause(instance_id: str | None) -> str:
    # instance_id is UUID-validated before this is called, so it cannot inject.
    return f"  AND t.instance_id = {_sql_uuid(instance_id)}\n" if instance_id else ""


def _load_roster_counts(event_id: str, instance_id: str | None) -> tuple[int, int]:
    """(total live tickets, checked-in) for the event, optionally one instance."""
    event_sql = _sql_uuid(event_id)
    instance_clause = _roster_instance_clause(instance_id)
    # order_item_id IS NOT NULL excludes transient, unpaid checkout claims (which
    # carry a null link and are voided by release_stale_ticket_claims) — mirrors
    # the "sold" definition in the organiser stats endpoint.
    script = f"""
SELECT
  count(*) FILTER (WHERE t.status IN ('issued', 'checked_in'))::text,
  count(*) FILTER (WHERE t.status = 'checked_in')::text
FROM public.tickets t
JOIN public.event_instances ei ON ei.id = t.instance_id
WHERE ei.event_id = {event_sql}
  AND t.order_item_id IS NOT NULL
{instance_clause};
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise AppError(
            code="roster_query_failed",
            message="Failed to load roster counts",
            http_status=500,
            details={"error": result.error},
        )
    parts = result.rows[0].split("|", 1)
    if len(parts) != 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


def _load_roster_attendees(event_id: str, instance_id: str | None) -> list[RosterAttendee]:
    """Live (issued/checked-in) tickets with their captured attendee name, if any.

    Each row is emitted as a single ``json_build_object`` so an attendee name (free
    text) can never break field parsing the way a ``|``-delimited row would.
    """
    event_sql = _sql_uuid(event_id)
    instance_clause = _roster_instance_clause(instance_id)
    script = f"""
SELECT json_build_object(
  'ticket_id', t.id,
  'holder_name', t.holder_name,
  'ticket_type_id', tt.id,
  'ticket_type_name', tt.name,
  'kind', tt.kind,
  'instance_id', ei.id,
  'starts_at', ei.starts_at,
  'status', t.status,
  'checked_in_at', t.checked_in_at
)::text
FROM public.tickets t
JOIN public.ticket_types tt ON tt.id = t.ticket_type_id
JOIN public.event_instances ei ON ei.id = t.instance_id
WHERE ei.event_id = {event_sql}
  AND t.status IN ('issued', 'checked_in')
  AND t.order_item_id IS NOT NULL
{instance_clause}
ORDER BY ei.starts_at ASC, tt.created_at ASC, lower(coalesce(t.holder_name, '~')) ASC, t.id ASC
LIMIT {ROSTER_CAP};
"""
    result = run_sql_script(script)
    if not result.ok:
        raise AppError(
            code="roster_query_failed",
            message="Failed to load roster",
            http_status=500,
            details={"error": result.error},
        )
    attendees: list[RosterAttendee] = []
    for raw in result.rows:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        holder = obj.get("holder_name")
        checked_in_at = obj.get("checked_in_at")
        attendees.append(
            RosterAttendee(
                ticket_id=str(obj["ticket_id"]),
                holder_name=str(holder) if holder is not None else None,
                ticket_type_id=str(obj["ticket_type_id"]),
                ticket_type_name=str(obj.get("ticket_type_name") or ""),
                kind=str(obj.get("kind") or ""),
                instance_id=str(obj["instance_id"]),
                starts_at=str(obj["starts_at"]),
                status=str(obj["status"]),
                checked_in_at=str(checked_in_at) if checked_in_at is not None else None,
            )
        )
    return attendees


def _resolve_owned_event(owner_user_id: str, event_id: str) -> str:
    """Vendor → event → owner check for organiser-scoped event reads.

    Returns the event status; raises AppError (404 / 403) when the event id is
    malformed, the event is missing, or it is not owned by the authenticated
    organiser.
    """
    if not _is_uuid(event_id):
        raise AppError(
            code="not_found",
            message="Event not found",
            http_status=404,
            details={"message_key": "vendor.eventDashboard.errors.notFound"},
        )
    vendor_id = _load_vendor_id_for_owner(owner_user_id)
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
            message="Organiser may only view their own events",
            http_status=403,
            details={"message_key": "vendor.eventDashboard.errors.forbidden"},
        )
    return event_status


def _validate_instance_filter(instance_id: str | None) -> None:
    if instance_id is not None and not _is_uuid(instance_id):
        raise AppError(
            code="validation_error",
            message="instance_id must be a valid UUID",
            http_status=422,
            details={"field": "instance_id"},
        )


@router.get("/events/{event_id}/roster", response_model=OrganiserEventRosterResponse)
async def get_organiser_event_roster(
    event_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    instance_id: str | None = None,
) -> OrganiserEventRosterResponse:
    del service_client  # data access is raw-SQL (run_sql_script), like get_..._stats

    _validate_instance_filter(instance_id)
    event_status = _resolve_owned_event(current_user.id, event_id)

    total, checked_in = _load_roster_counts(event_id, instance_id)
    attendees = _load_roster_attendees(event_id, instance_id)

    return OrganiserEventRosterResponse(
        event_id=event_id,
        event_status=event_status,
        total=total,
        checked_in=checked_in,
        truncated=total > ROSTER_CAP,
        attendees=attendees,
    )


def _format_lusaka(iso: str) -> str:
    """Render an ISO timestamp as local Lusaka wall-clock for a printable list."""
    try:
        return datetime.fromisoformat(iso).astimezone(LUSAKA_TZ).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def _roster_csv(attendees: list[RosterAttendee]) -> str:
    """Roster as CSV for offline / printed door check-in. csv.writer quotes any
    name containing a comma or quote, so free-text names stay intact."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "name", "ticket_type", "status"])
    for attendee in attendees:
        writer.writerow(
            [
                _format_lusaka(attendee.starts_at),
                attendee.holder_name or "",
                attendee.ticket_type_name,
                "Checked in" if attendee.status == "checked_in" else "Not checked in",
            ]
        )
    return buffer.getvalue()


@router.get("/events/{event_id}/roster.csv")
async def download_organiser_event_roster_csv(
    event_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    instance_id: str | None = None,
) -> Response:
    del service_client

    _validate_instance_filter(instance_id)
    _resolve_owned_event(current_user.id, event_id)

    attendees = _load_roster_attendees(event_id, instance_id)
    filename = f"roster-{event_id}.csv"
    return Response(
        content=_roster_csv(attendees),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = [
    "download_organiser_event_roster_csv",
    "get_organiser_event_roster",
    "get_organiser_event_stats",
]
