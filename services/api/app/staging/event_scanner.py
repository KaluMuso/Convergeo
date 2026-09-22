"""Staging scanner-ticket driver — a check-in-able ticket from the real service path.

The static seed (``app.staging.seed_sql``) writes ticket rows directly, so those
rows carry no ``order_item_id``. ``POST /tickets/verify`` refuses exactly that
shape with ``ticket_unpaid_hold``
(``app.routers.ticket_verify::_assert_paid_ticket``), and that refusal is a
production safety rule, not a staging inconvenience: it is what stops an
unclaimed hold from walking into a venue. It is proven by
``services/api/tests/test_ticket_verify.py`` and is never weakened, bypassed or
special-cased here.

So the organiser scanner journey needs a ticket that is legitimately
check-in-able, and this module produces one the only honest way available
without a payment provider: it drives ``services/tickets/purchase.py::rsvp()``,
the same function ``POST /events/{id}/rsvp`` calls. For a ``free_rsvp`` ticket
type that path claims inventory under the oversell lock, writes a completed
checkout group / order / order item spine, links the claimed ticket to
``order_item_id`` and seals its PIN and QR secret — with no provider charge and
no ``payments`` row anywhere in it. Nothing here inserts a fake successful
payment, and nothing here hand-assigns ``order_item_id`` to a paid ticket.

Two consequences follow from using the real path, and both are deliberate:

* **The ticket id is minted per run**, by ``claim_ticket``'s INSERT, exactly
  like the PIN. It is therefore run state and not canonical fixture identity, so
  it is handed to the test runner through the private runtime file rather than
  compiled into ``fixture_version()`` or the generated TypeScript.
* **The PIN is the one the service itself issued.** ``_link_claimed_tickets``
  seals a fresh PIN into ``pin_hash``; this module reads it back through
  ``extract_pin_for_holder()`` — the same function the wallet endpoint
  (``app.routers.ticket_wallet``) serves to the holder. No credential is
  rewritten, so the scanner is driven with a PIN a real holder would see.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.env_guards import StagingIsolationError
from app.services.db import run_sql_script
from app.services.stock.claim import sql_uuid
from app.services.tickets.qr import extract_pin_for_holder
from app.staging.synthetic_contract import (
    EventFixture,
    TicketTypeFixture,
    event_fixture,
    persona_by_key,
    scanner_ticket_type,
)

# One ticket is all the scanner journey verifies; the lane's allocation exists
# to absorb repeated --apply runs, not to mint a batch.
SCANNER_RSVP_QTY = 1

SCANNER_EVENT_KEY = "EVENT_LAUNCH_EXPO"
SCANNER_HOLDER_KEY = "CUSTOMER_A"


@dataclass(frozen=True, slots=True)
class ScannerTicketFixture:
    """Where the scanner ticket comes from, resolved from the contract only."""

    event: EventFixture
    ticket_type: TicketTypeFixture
    instance_id: str
    holder_user_id: str


@dataclass(frozen=True, slots=True)
class ScannerTicket:
    """One run's check-in-able scanner ticket, as the seeder produced it."""

    ticket_id: str
    order_item_id: str
    order_id: str
    checkout_group_id: str
    pin: str
    replayed: bool

    def __repr__(self) -> str:  # pragma: no cover - defensive
        # A stray repr() in a traceback must not print the PIN.
        return (
            f"ScannerTicket(ticket_id={self.ticket_id!r}, "
            f"order_item_id={self.order_item_id!r}, "
            f"replayed={self.replayed!r}, pin=<redacted>)"
        )


def scanner_ticket_fixture() -> ScannerTicketFixture:
    """Resolve the scanner lane from the canonical contract (no DB access)."""
    event = event_fixture(SCANNER_EVENT_KEY)
    if event.status != "published":
        raise StagingIsolationError(
            "the scanner event must be published — rsvp() and /tickets/verify "
            "both refuse an unpublished event"
        )
    holder = persona_by_key(SCANNER_HOLDER_KEY)
    return ScannerTicketFixture(
        event=event,
        ticket_type=scanner_ticket_type(event),
        instance_id=event.instance_id,
        holder_user_id=holder.user_id,
    )


def _find_existing_scanner_ticket(
    fixture: ScannerTicketFixture,
) -> tuple[str, str, str, str] | None:
    """The scanner ticket a previous run already issued, if one survives.

    Only a ticket that is genuinely linked to an order item counts: the JOIN on
    ``order_items`` is an inner join, so an unpaid hold can never be mistaken
    for a replayable scanner ticket.
    """
    script = f"""
SELECT
  t.id::text,
  oi.id::text,
  oi.order_id::text,
  o.checkout_group_id::text
FROM public.tickets t
INNER JOIN public.order_items oi ON oi.id = t.order_item_id
INNER JOIN public.orders o ON o.id = oi.order_id
WHERE t.instance_id = {sql_uuid(fixture.instance_id, "instance_id")}
  AND t.ticket_type_id = {sql_uuid(fixture.ticket_type.ticket_type_id, "ticket_type_id")}
  AND t.holder_user_id = {sql_uuid(fixture.holder_user_id, "holder_user_id")}
  AND t.status <> 'void'
ORDER BY t.created_at ASC, t.id ASC
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"scanner ticket lookup failed: {result.error}")
    if not result.rows:
        return None
    parts = result.rows[0].split("|")
    if len(parts) != 4:
        raise RuntimeError("unexpected scanner ticket lookup shape")
    return parts[0], parts[1], parts[2], parts[3]


def _restore_unscanned(ticket_id: str) -> None:
    """Return a replayed scanner ticket to its un-scanned state.

    This clears a SCAN, not a payment: ``order_item_id`` is never touched, so the
    ticket stays exactly as paid-for as ``rsvp()`` made it. The static seed does
    the same thing for its own rows (``checked_in_at = NULL`` on conflict) for
    the same reason — verify-then-duplicate-reject is only reproducible from a
    fresh ticket.
    """
    script = f"""
UPDATE public.tickets
SET status = 'issued', checked_in_at = NULL
WHERE id = {sql_uuid(ticket_id, "ticket_id")}
  AND status IN ('issued', 'checked_in')
RETURNING id::text;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"scanner ticket reset failed: {result.error}")
    if not result.rows:
        raise RuntimeError(
            "scanner ticket could not be restored to an un-scanned state "
            f"({ticket_id})"
        )


def _load_scanner_pin(ticket_id: str) -> str:
    """Read the ticket's PIN back through the holder-retrieval path.

    ``extract_pin_for_holder`` is the wallet's own function
    (``app.routers.ticket_wallet::_pin_fields``), so the value handed to the E2E
    run is literally the PIN the holder would be shown — not a second credential
    written over the top of the service's.
    """
    result = run_sql_script(
        f"SELECT coalesce(pin_hash, '') FROM public.tickets "
        f"WHERE id = {sql_uuid(ticket_id, 'ticket_id')};"
    )
    if not result.ok:
        raise RuntimeError(f"scanner ticket credential lookup failed: {result.error}")
    if not result.rows:
        raise RuntimeError(f"scanner ticket disappeared before credential read ({ticket_id})")
    pin = extract_pin_for_holder(result.rows[0], ticket_id=ticket_id)
    if not pin:
        raise RuntimeError(
            "scanner ticket PIN could not be read back through the holder path — "
            "SUPABASE_SERVICE_ROLE_KEY must be the same key the seal was written "
            f"with ({ticket_id})"
        )
    return pin


def _assert_check_in_ready(ticket_id: str) -> None:
    """Fail closed unless the seeded ticket would actually pass /tickets/verify.

    Mirrors the router's own gates (`_assert_event_published`,
    `_assert_paid_ticket`, `_assert_checkinable_status`) so a broken fixture is a
    seed failure rather than a red scanner assertion an hour later.
    """
    script = f"""
SELECT
  (t.order_item_id IS NOT NULL)::text,
  t.status,
  (t.checked_in_at IS NULL)::text,
  (t.pin_hash IS NOT NULL)::text,
  (t.qr_secret IS NOT NULL)::text,
  e.status,
  tt.kind
FROM public.tickets t
INNER JOIN public.event_instances ei ON ei.id = t.instance_id
INNER JOIN public.events e ON e.id = ei.event_id
INNER JOIN public.ticket_types tt ON tt.id = t.ticket_type_id
WHERE t.id = {sql_uuid(ticket_id, "ticket_id")};
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"scanner ticket verification failed: {result.error}")
    if not result.rows:
        raise RuntimeError(f"scanner ticket not found after setup ({ticket_id})")
    parts = result.rows[0].split("|")
    if len(parts) != 7:
        raise RuntimeError("unexpected scanner ticket verification shape")
    linked, status, unscanned, has_pin, has_qr, event_status, kind = parts
    if linked != "true":
        raise RuntimeError(
            "scanner ticket has no order_item_id — it is an unpaid hold and "
            f"/tickets/verify would reject it with ticket_unpaid_hold ({ticket_id})"
        )
    if status != "issued" or unscanned != "true":
        raise RuntimeError(
            f"scanner ticket is not un-scanned and issued (status={status}, {ticket_id})"
        )
    if has_pin != "true" or has_qr != "true":
        raise RuntimeError(f"scanner ticket is missing its credentials ({ticket_id})")
    if event_status != "published":
        raise RuntimeError(f"scanner ticket's event is not published ({ticket_id})")
    if kind != "free_rsvp":
        raise RuntimeError(
            "scanner ticket is not on the free_rsvp lane — a paid ticket must "
            f"never be linked by hand ({ticket_id})"
        )


def apply_rsvp_scanner_ticket(client: Any) -> ScannerTicket:
    """Produce (or replay) the run's check-in-able scanner ticket.

    Idempotent by design. A scanner ticket already linked to an order item is
    replayed — restored to un-scanned and its existing PIN read back — rather
    than claimed again, so repeated ``--apply`` runs without a ``--cleanup``
    neither drain the lane's allocation nor leave a second ticket behind for the
    spec to pick the wrong one of.
    """
    # Imported lazily for the same reason apply_cod_placed() does it: this module
    # is reachable from the plan-only CLI and from the E2E fixture generator,
    # which must stay importable without the ticket-service dependency graph.
    from app.services.tickets.purchase import rsvp

    fixture = scanner_ticket_fixture()

    existing = _find_existing_scanner_ticket(fixture)
    if existing is not None:
        ticket_id, order_item_id, order_id, checkout_group_id = existing
        _restore_unscanned(ticket_id)
        replayed = True
    else:
        result = rsvp(
            client,
            customer_id=fixture.holder_user_id,
            instance_id=fixture.instance_id,
            ticket_type_id=fixture.ticket_type.ticket_type_id,
            qty=SCANNER_RSVP_QTY,
        )
        if len(result.ticket_ids) != SCANNER_RSVP_QTY:
            raise RuntimeError(
                "rsvp() did not claim exactly one scanner ticket "
                f"(got {len(result.ticket_ids)})"
            )
        ticket_id = result.ticket_ids[0]
        order_item_id = result.order_item_id
        order_id = result.order_id
        checkout_group_id = result.checkout_group_id
        replayed = False

    _assert_check_in_ready(ticket_id)
    return ScannerTicket(
        ticket_id=ticket_id,
        order_item_id=order_item_id,
        order_id=order_id,
        checkout_group_id=checkout_group_id,
        pin=_load_scanner_pin(ticket_id),
        replayed=replayed,
    )


__all__ = [
    "SCANNER_EVENT_KEY",
    "SCANNER_HOLDER_KEY",
    "SCANNER_RSVP_QTY",
    "ScannerTicket",
    "ScannerTicketFixture",
    "apply_rsvp_scanner_ticket",
    "scanner_ticket_fixture",
]
