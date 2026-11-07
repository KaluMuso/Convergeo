"""Issue the canonical scanner ticket through the real free-RSVP service path."""

from __future__ import annotations

from typing import Any

from app.services.orders.audit import run_sql_script
from app.services.tickets.purchase import rsvp
from app.staging.synthetic_contract import SEED_PREFIX, event_fixture, persona_by_key
from app.staging.ticket_credentials import (
    TicketCredential,
    recover_service_issued_credential,
)

SCANNER_RSVP_IDEMPOTENCY_KEY = f"{SEED_PREFIX}-scanner-certification-rsvp-v1"


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_scanner_rsvp_cleanup_sql() -> str:
    """Delete only the canonical scanner RSVP and its checkout spine.

    The order is intentional: override rows restrict-delete tickets; tickets
    restrict-delete order items; order items cascade-delete order_item_tickets;
    orders then release the checkout group.  No payment row is deleted because a
    legitimate free RSVP never creates one.  If a payment somehow appears on this
    scoped group, its restrictive FK makes cleanup fail closed.  The exact
    synthetic holder/instance/type tuple also catches a real RSVP interrupted
    before its generated ids could be canonicalised.
    """
    event = event_fixture("EVENT_LAUNCH_EXPO")
    ticket = event.tickets[0]
    holder = persona_by_key(ticket.holder_key)
    ticket_id = _sql_text(ticket.ticket_id)
    instance_id = _sql_text(event.instance_id)
    ticket_type_id = _sql_text(ticket.ticket_type_id)
    holder_id = _sql_text(holder.user_id)
    key = _sql_text(SCANNER_RSVP_IDEMPOTENCY_KEY)
    return f"""
CREATE TEMP TABLE scanner_rsvp_cleanup_groups ON COMMIT DROP AS
SELECT DISTINCT cg.id
FROM public.checkout_groups cg
LEFT JOIN public.orders o ON o.checkout_group_id = cg.id
LEFT JOIN public.order_items oi ON oi.order_id = o.id
LEFT JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id
WHERE cg.idempotency_key = {key}
   OR (
     cg.customer_id = {holder_id}
     AND o.customer_id = {holder_id}
     AND oit.instance_id = {instance_id}
     AND oit.ticket_type_id = {ticket_type_id}
   );

CREATE TEMP TABLE scanner_rsvp_cleanup_orders ON COMMIT DROP AS
SELECT id FROM public.orders
WHERE checkout_group_id IN (SELECT id FROM scanner_rsvp_cleanup_groups);

CREATE TEMP TABLE scanner_rsvp_cleanup_items ON COMMIT DROP AS
SELECT id FROM public.order_items
WHERE order_id IN (SELECT id FROM scanner_rsvp_cleanup_orders);

DELETE FROM public.event_checkin_overrides
WHERE ticket_id IN (
  SELECT id FROM public.tickets
  WHERE id = {ticket_id}
     OR (
       instance_id = {instance_id}
       AND ticket_type_id = {ticket_type_id}
       AND holder_user_id = {holder_id}
     )
     OR order_item_id IN (SELECT id FROM scanner_rsvp_cleanup_items)
);

DELETE FROM public.tickets
WHERE id = {ticket_id}
   OR (
     instance_id = {instance_id}
     AND ticket_type_id = {ticket_type_id}
     AND holder_user_id = {holder_id}
   )
   OR order_item_id IN (SELECT id FROM scanner_rsvp_cleanup_items);

DELETE FROM public.order_items
WHERE id IN (SELECT id FROM scanner_rsvp_cleanup_items);

DELETE FROM public.orders
WHERE id IN (SELECT id FROM scanner_rsvp_cleanup_orders);

DELETE FROM public.checkout_groups
WHERE id IN (SELECT id FROM scanner_rsvp_cleanup_groups);
"""


def _cleanup_failed_rsvp(*, checkout_group_id: str, ticket_id: str) -> None:
    """Best-effort cleanup for the narrow gap between RSVP and canonicalisation."""
    result = run_sql_script(
        f"""
BEGIN;
DELETE FROM public.tickets
WHERE id = {_sql_text(ticket_id)}
   OR order_item_id IN (
     SELECT oi.id
     FROM public.order_items oi
     JOIN public.orders o ON o.id = oi.order_id
     WHERE o.checkout_group_id = {_sql_text(checkout_group_id)}
   );
DELETE FROM public.order_items
WHERE order_id IN (
  SELECT id FROM public.orders WHERE checkout_group_id = {_sql_text(checkout_group_id)}
);
DELETE FROM public.orders WHERE checkout_group_id = {_sql_text(checkout_group_id)};
DELETE FROM public.checkout_groups WHERE id = {_sql_text(checkout_group_id)};
COMMIT;
"""
    )
    if not result.ok:
        raise RuntimeError(f"scanner RSVP rollback failed: {result.error}")


def issue_scanner_certification_ticket(service_client: Any) -> TicketCredential:
    """Create one canonical, check-in-able ticket without fabricating payment.

    `rsvp()` performs the real type check, capacity claim, completed free checkout
    creation, order-item linkage and credential issuance.  The staging-only step
    afterwards normalises the generated ticket id and credential so browser
    certification can use a stable identity across cleanup/reseed cycles.
    """
    event = event_fixture("EVENT_LAUNCH_EXPO")
    if len(event.tickets) != 1:
        raise RuntimeError("scanner certification requires exactly one ticket fixture")
    ticket = event.tickets[0]
    ticket_type = next(
        (item for item in event.ticket_types if item.ticket_type_id == ticket.ticket_type_id),
        None,
    )
    if ticket_type is None or ticket_type.kind != "free_rsvp" or ticket_type.price_ngwee != 0:
        raise RuntimeError("scanner certification ticket type must be a zero-price free RSVP")

    cleanup = run_sql_script(f"BEGIN;{build_scanner_rsvp_cleanup_sql()}COMMIT;")
    if not cleanup.ok:
        raise RuntimeError(f"scanner RSVP cleanup failed: {cleanup.error}")

    holder = persona_by_key(ticket.holder_key)
    outcome = rsvp(
        service_client,
        customer_id=holder.user_id,
        instance_id=event.instance_id,
        ticket_type_id=ticket_type.ticket_type_id,
        qty=1,
    )
    if len(outcome.ticket_ids) != 1:
        raise RuntimeError("scanner RSVP did not issue exactly one ticket")

    generated_ticket_id = outcome.ticket_ids[0]
    issued_credential = run_sql_script(
        f"""
SELECT pin_hash
FROM public.tickets
WHERE id = {_sql_text(generated_ticket_id)}
  AND order_item_id = {_sql_text(outcome.order_item_id)}
  AND status = 'issued';
"""
    )
    if not issued_credential.ok or len(issued_credential.rows) != 1:
        _cleanup_failed_rsvp(
            checkout_group_id=outcome.checkout_group_id,
            ticket_id=generated_ticket_id,
        )
        detail = issued_credential.error or "service-issued scanner credential missing"
        raise RuntimeError(f"scanner RSVP credential recovery failed: {detail}")
    try:
        credential = recover_service_issued_credential(
            issued_ticket_id=generated_ticket_id,
            canonical_ticket_id=ticket.ticket_id,
            stored_pin_hash=issued_credential.rows[0],
        )
    except RuntimeError:
        _cleanup_failed_rsvp(
            checkout_group_id=outcome.checkout_group_id,
            ticket_id=generated_ticket_id,
        )
        raise
    finalise = run_sql_script(
        f"""
BEGIN;
UPDATE public.tickets
SET id = {_sql_text(ticket.ticket_id)},
    status = 'issued',
    checked_in_at = NULL,
    pin_hash = {_sql_text(credential.pin_hash)}
WHERE id = {_sql_text(generated_ticket_id)}
  AND order_item_id = {_sql_text(outcome.order_item_id)}
RETURNING id::text;

UPDATE public.orders
SET commission_snapshot = jsonb_set(
  commission_snapshot,
  '{{ticket_claim_ids}}',
  to_jsonb(ARRAY[{_sql_text(ticket.ticket_id)}]::text[]),
  true
)
WHERE id = {_sql_text(outcome.order_id)};

UPDATE public.checkout_groups
SET idempotency_key = {_sql_text(SCANNER_RSVP_IDEMPOTENCY_KEY)}
WHERE id = {_sql_text(outcome.checkout_group_id)};

SELECT count(*)::text
FROM public.tickets t
JOIN public.order_items oi ON oi.id = t.order_item_id
JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id
JOIN public.orders o ON o.id = oi.order_id
JOIN public.checkout_groups cg ON cg.id = o.checkout_group_id
JOIN public.ticket_types tt ON tt.id = t.ticket_type_id
WHERE t.id = {_sql_text(ticket.ticket_id)}
  AND t.instance_id = {_sql_text(event.instance_id)}
  AND t.holder_user_id = {_sql_text(holder.user_id)}
  AND t.status = 'issued'
  AND t.checked_in_at IS NULL
  AND tt.kind = 'free_rsvp'
  AND tt.price_ngwee = 0
  AND cg.status = 'completed'
  AND o.status = 'completed'
  AND cg.idempotency_key = {_sql_text(SCANNER_RSVP_IDEMPOTENCY_KEY)}
  AND NOT EXISTS (
    SELECT 1 FROM public.payments p WHERE p.checkout_group_id = cg.id
  );
COMMIT;
"""
    )
    if not finalise.ok or finalise.rows[-1:] != ["1"]:
        _cleanup_failed_rsvp(
            checkout_group_id=outcome.checkout_group_id,
            ticket_id=generated_ticket_id,
        )
        detail = finalise.error or "canonical free-RSVP verification returned no row"
        raise RuntimeError(f"scanner RSVP canonicalisation failed: {detail}")
    return credential


__all__ = [
    "SCANNER_RSVP_IDEMPOTENCY_KEY",
    "build_scanner_rsvp_cleanup_sql",
    "issue_scanner_certification_ticket",
]
