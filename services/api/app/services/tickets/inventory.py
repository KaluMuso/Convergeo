"""Oversell-safe ticket inventory claims per event instance + ticket type."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.errors import AppError
from app.services.stock.claim import run_sql_script, sql_int, sql_uuid

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ClaimResult:
    claimed: bool
    ticket_ids: tuple[str, ...]
    instance_id: str
    ticket_type_id: str
    holder_user_id: str
    qty: int


def _validate_uuid(value: str, field: str) -> None:
    if not _UUID_RE.match(value):
        msg = f"{field} must be a valid UUID"
        raise ValueError(msg)
    UUID(value)


def claim_ticket(
    service_client: Any,
    *,
    instance_id: str,
    ticket_type_id: str,
    holder_user_id: str,
    qty: int = 1,
) -> ClaimResult:
    """Atomically claim ticket inventory under row lock (mirrors M07-P02 stock claim).

    Enforces per-instance capacity, per-type qty_cap, and per_customer_cap under
    concurrency via ``SELECT … FOR UPDATE`` on the instance row plus conditional insert.
  """
    del service_client  # reserved for future metadata lookups; claim is SQL-atomic
    _validate_uuid(instance_id, "instance_id")
    _validate_uuid(ticket_type_id, "ticket_type_id")
    _validate_uuid(holder_user_id, "holder_user_id")
    if qty <= 0:
        raise ValueError("qty must be positive")

    instance_sql = sql_uuid(instance_id, "instance_id")
    type_sql = sql_uuid(ticket_type_id, "ticket_type_id")
    holder_sql = sql_uuid(holder_user_id, "holder_user_id")
    qty_sql = sql_int(qty, "qty")

    script = f"""
BEGIN;
SELECT pg_advisory_xact_lock(hashtext('{instance_id}'));
WITH locked_instance AS (
  SELECT ei.id, ei.capacity, ei.event_id
  FROM public.event_instances ei
  WHERE ei.id = {instance_sql}
  FOR UPDATE
),
type_row AS (
  SELECT tt.id, tt.event_id, tt.qty_cap, tt.per_customer_cap
  FROM public.ticket_types tt
  WHERE tt.id = {type_sql}
),
joined AS (
  SELECT li.id AS instance_id, li.capacity, tr.id AS type_id, tr.qty_cap, tr.per_customer_cap
  FROM locked_instance li
  INNER JOIN type_row tr ON tr.event_id = li.event_id
),
counts AS (
  SELECT
    j.instance_id,
    j.type_id,
    j.capacity,
    j.qty_cap,
    j.per_customer_cap,
    (SELECT count(*)::int FROM public.tickets t
     WHERE t.instance_id = j.instance_id AND t.status <> 'void') AS instance_issued,
    (SELECT count(*)::int FROM public.tickets t
     WHERE t.instance_id = j.instance_id AND t.ticket_type_id = j.type_id
       AND t.status <> 'void') AS type_issued,
    (SELECT count(*)::int FROM public.tickets t
     WHERE t.instance_id = j.instance_id AND t.ticket_type_id = j.type_id
       AND t.holder_user_id = {holder_sql} AND t.status <> 'void') AS holder_issued
  FROM joined j
),
eligible AS (
  SELECT c.instance_id, c.type_id
  FROM counts c
  WHERE c.instance_issued + {qty_sql} <= c.capacity
    AND (c.qty_cap IS NULL OR c.type_issued + {qty_sql} <= c.qty_cap)
    AND (c.per_customer_cap IS NULL OR c.holder_issued + {qty_sql} <= c.per_customer_cap)
),
inserted AS (
  INSERT INTO public.tickets (instance_id, ticket_type_id, holder_user_id, status)
  SELECT e.instance_id, e.type_id, {holder_sql}, 'issued'
  FROM eligible e
  CROSS JOIN generate_series(1, {qty_sql})
  RETURNING id
)
SELECT id::text FROM inserted;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"claim_ticket failed: {result.error}")

    ticket_ids = tuple(result.rows)
    if not ticket_ids:
        return ClaimResult(
            claimed=False,
            ticket_ids=(),
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            holder_user_id=holder_user_id,
            qty=qty,
        )

    return ClaimResult(
        claimed=True,
        ticket_ids=ticket_ids,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        holder_user_id=holder_user_id,
        qty=qty,
    )


def claim_ticket_or_raise(
    service_client: Any,
    *,
    instance_id: str,
    ticket_type_id: str,
    holder_user_id: str,
    qty: int = 1,
) -> ClaimResult:
    """Claim tickets or raise a uniform oversell/cap ``AppError``."""
    result = claim_ticket(
        service_client,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        holder_user_id=holder_user_id,
        qty=qty,
    )
    if result.claimed:
        return result

    raise AppError(
        code="tickets.oversell",
        message="Ticket inventory is no longer available",
        http_status=409,
        details={
            "instance_id": instance_id,
            "ticket_type_id": ticket_type_id,
            "qty": qty,
            "message_key": "vendor.tickets.errors.oversell",
        },
    )
