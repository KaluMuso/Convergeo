"""Event escrow release timing (M10-P08) — a parallel path to services/escrow/release.py.

Ticket orders never reach the shipped/delivered/completed statuses the order-delivery
release engine (``release.py``) keys off of, so the order engine never auto-releases
them. This module is the event-date-anchored release path for ticket orders only.

Timing rules (D5). The <=14d / >14d branch is decided by the lead time from
purchase to ``event_instances.starts_at``; the release *due* times anchor on the
instance's END — ``ends_at``, falling back to ``starts_at`` for legacy rows with
no end time (see ``instance_settlement_end``) — so a multi-day event's funds no
longer release mid-event:
  - Event <= 14 days out at purchase time -> single full release at end + 24h.
  - Event > 14 days out at purchase time -> 50% at starts_at - 7d, 50% at end + 1d.
  - Recurring event (event_type, D29/P14) -> single full release at end + 24h
    regardless of lead time (no >14d phased pre-event advance): a routine series
    holds funds until after each instance. All other event_types use the lead-time
    branch above; per-type rules live in services/events/type_policy.py.
  - Cancelled event -> block all further releases + flag for admin-executed mass refund.
  - Open dispute (same OPEN_DISPUTE_STATUSES as the order engine) -> hold.

MONEY SEAM: idempotency keys here (``event-release-{order_id}-full`` /
``-phase1`` / ``-phase2``) are deliberately distinct from release.py's
``release-{order_id}`` so this path can never collide with or double-post
against the order-delivery release engine. Commission capture uses
``event-release-{order_id}-commission-*`` (once per order, before the first
phase). Reuses ``post_transaction`` + ``LedgerTemplate.RELEASE_TO_VENDOR`` /
``COMMISSION_CAPTURE`` — the sole ledger write path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from app.services.commissions.engine import capture_order_commission
from app.services.escrow.release_accounting import (
    ReleaseAccountingError,
    compute_release_amounts,
    order_has_open_dispute,
    order_is_refund_blocked,
)
from app.services.events.timing import instance_settlement_end
from app.services.events.type_policy import policy_for
from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import SYSTEM_ACTOR_ID

PHASED_THRESHOLD_DAYS = 14
FULL_RELEASE_DELAY_HOURS = 24
PHASE1_LEAD_DAYS = 7
PHASE2_DELAY_DAYS = 1

MASS_REFUND_FLAG_ACTION = "event_release.mass_refund_flagged"

EventReleaseBranch = Literal["full", "phased"]
EventReleaseOutcome = Literal[
    "released", "held", "already_released", "not_eligible", "blocked_cancelled"
]


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class EventReleaseResult:
    order_id: str
    outcome: EventReleaseOutcome
    reason: str
    branch: EventReleaseBranch | None = None
    phases_posted: tuple[str, ...] = ()
    transaction_ids: tuple[str, ...] = ()
    net_ngwee: int = 0


@dataclass(frozen=True, slots=True)
class EventReleaseSweepResult:
    scanned: int
    released: int
    held: int
    already_released: int
    not_eligible: int
    blocked_cancelled: int


@dataclass(frozen=True, slots=True)
class _EventOrderContext:
    order_id: str
    vendor_id: str
    checkout_group_id: str
    gross_ngwee: int
    commission_snapshot: dict[str, Any]
    purchased_at: datetime
    instance_id: str
    event_id: str
    starts_at: datetime
    ends_at: datetime | None
    event_status: str
    event_type: str
    is_paid: bool
    has_open_dispute: bool | None


def full_release_key(order_id: str) -> str:
    return f"event-release-{order_id}-full"


def phase1_release_key(order_id: str) -> str:
    return f"event-release-{order_id}-phase1"


def phase2_release_key(order_id: str) -> str:
    return f"event-release-{order_id}-phase2"


def event_commission_idempotency_prefix(order_id: str) -> str:
    """Exactly-once commission capture key prefix for ticket orders (≠ release keys)."""
    return f"event-release-{order_id}"


def _sql_uuid(value: str, field: str) -> str:
    del field
    return f"'{value}'::uuid"


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_now(now: datetime | None) -> datetime:
    effective_now = now or datetime.now(UTC)
    if effective_now.tzinfo is None:
        return effective_now.replace(tzinfo=UTC)
    return effective_now.astimezone(UTC)


def determine_branch(
    *, purchased_at: datetime, starts_at: datetime, event_type: str | None = None
) -> EventReleaseBranch:
    """Decide the ≤14d / >14d branch from purchase-time lead vs. the event's starts_at.

    There is no snapshot column recording this decision at purchase time (no migration
    for this pebble); it is derived by comparing the order's created_at (purchase
    timestamp) against the ticketed instance's starts_at whenever this is evaluated.
    Both timestamps are immutable once set (orders.created_at never changes; an
    event's starts_at can only change pre-publish per M10-P05's schedule-change
    guard), so this derivation is stable across repeated evaluations of the same order.

    event_type drives this via the ``type_policy`` map (D29/P14): a ``full_only``
    settlement rule (a ``recurring`` series) forces a single full release regardless
    of lead time — no >14d phased pre-event advance, so a routine series holds funds
    until end+24h. All other types use ``timing_default`` (the lead-time branch,
    unchanged). event_type defaults to ``standard``, so existing orders are unaffected.
    """
    if policy_for(event_type).settlement_rule == "full_only":
        return "full"
    lead = starts_at - purchased_at
    if lead <= timedelta(days=PHASED_THRESHOLD_DAYS):
        return "full"
    return "phased"


def _order_ticket_gross_ngwee(order_id: str) -> int:
    order_sql = _sql_uuid(order_id, "order_id")
    script = f"""
SELECT coalesce(sum(qty * unit_price_ngwee), 0)::text
FROM public.order_items
WHERE order_id = {order_sql}
  AND item_kind = 'ticket';
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return 0
    return int(result.rows[0])


def _has_successful_payment(checkout_group_id: str) -> bool:
    group_sql = _sql_uuid(checkout_group_id, "checkout_group_id")
    script = f"""
SELECT count(*)::text
FROM public.payments
WHERE checkout_group_id = {group_sql}
  AND status = 'success';
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return False
    return int(result.rows[0]) > 0


def _has_open_dispute(order_id: str) -> bool | None:
    """Return dispute state, or None when disputes cannot be queried (fail-closed)."""
    try:
        return order_has_open_dispute(order_id)
    except ReleaseAccountingError:
        return None


def _posted_release_keys(keys: tuple[str, ...]) -> set[str]:
    if not keys:
        return set()
    keys_sql = ", ".join(sql_literal(key) for key in keys)
    script = f"""
SELECT idempotency_key
FROM public.ledger_transactions
WHERE idempotency_key IN ({keys_sql});
"""
    result = run_sql_script(script)
    if not result.ok:
        return set()
    return set(result.rows)


def _load_event_order_context(order_id: str) -> _EventOrderContext | None:
    order_sql = _sql_uuid(order_id, "order_id")
    script = f"""
SELECT
  o.vendor_id::text,
  o.commission_snapshot::text,
  o.created_at::text,
  o.checkout_group_id::text,
  ei.id::text,
  ei.starts_at::text,
  coalesce(ei.ends_at::text, ''),
  e.id::text,
  e.status,
  e.event_type
FROM public.orders o
INNER JOIN public.order_items oi
  ON oi.order_id = o.id AND oi.item_kind = 'ticket'
INNER JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id
INNER JOIN public.event_instances ei ON ei.id = oit.instance_id
INNER JOIN public.events e ON e.id = ei.event_id
WHERE o.id = {order_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None

    parts = result.rows[0].split("|", 9)
    if len(parts) != 10:
        return None

    (
        vendor_id,
        snapshot_raw,
        created_at_raw,
        checkout_group_id,
        instance_id,
        starts_at_raw,
        ends_at_raw,
        event_id,
        event_status,
        event_type,
    ) = parts

    purchased_at = _parse_timestamp(created_at_raw)
    starts_at = _parse_timestamp(starts_at_raw)
    ends_at = _parse_timestamp(ends_at_raw)
    if purchased_at is None or starts_at is None:
        return None

    commission_snapshot: dict[str, Any]
    if snapshot_raw.strip():
        try:
            loaded = json.loads(snapshot_raw)
            commission_snapshot = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            commission_snapshot = {}
    else:
        commission_snapshot = {}

    return _EventOrderContext(
        order_id=order_id,
        vendor_id=vendor_id,
        checkout_group_id=checkout_group_id,
        gross_ngwee=_order_ticket_gross_ngwee(order_id),
        commission_snapshot=commission_snapshot,
        purchased_at=purchased_at,
        instance_id=instance_id,
        event_id=event_id,
        starts_at=starts_at,
        ends_at=ends_at,
        event_status=event_status,
        event_type=event_type,
        is_paid=_has_successful_payment(checkout_group_id),
        has_open_dispute=_has_open_dispute(order_id),
    )


def _mass_refund_already_flagged(order_id: str) -> bool:
    order_sql = _sql_uuid(order_id, "order_id")
    action_sql = sql_literal(MASS_REFUND_FLAG_ACTION)
    script = f"""
SELECT id::text
FROM public.audit_log
WHERE entity_type = 'order'
  AND entity_id = {order_sql}
  AND action = {action_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    return bool(result.ok and result.rows)


def _flag_mass_refund(*, order_id: str, event_id: str) -> None:
    """Admin-visible marker for cancelled-event mass refund (audit_log row).

    ``audit_log`` (0007_trust_ops.sql) is the established append-only admin
    mutation trail used throughout the codebase (disputes/KYC/payments state
    machines all write to it) — reused here rather than inventing a new table,
    per the pebble's no-migration constraint. Deduped per-order via a
    check-then-insert so re-running the tick does not spam duplicate flags.
    """
    if _mass_refund_already_flagged(order_id):
        return
    order_sql = _sql_uuid(order_id, "order_id")
    actor_sql = _sql_uuid(SYSTEM_ACTOR_ID, "actor")
    action_sql = sql_literal(MASS_REFUND_FLAG_ACTION)
    after_payload = json.dumps({"event_id": event_id, "order_id": order_id})
    after_sql = sql_literal(after_payload) + "::jsonb"
    script = f"""
INSERT INTO public.audit_log (actor, action, entity_type, entity_id, before, after)
VALUES ({actor_sql}, {action_sql}, 'order', {order_sql}, NULL, {after_sql});
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"flag mass refund failed: {result.error}")


def _post_event_release(
    *, order_id: str, vendor_id: str, net_ngwee: int, idempotency_key: str
) -> str:
    posted = post_transaction(
        idempotency_key=idempotency_key,
        template=LedgerTemplate.RELEASE_TO_VENDOR,
        order_id=order_id,
        net_ngwee=net_ngwee,
        vendor_id=vendor_id,
    )
    return posted.id


def evaluate_event_release(
    service_client: ServiceRoleClient,
    order_id: str,
    *,
    now: datetime | None = None,
) -> EventReleaseResult:
    """Evaluate event-date escrow release for one ticket order.

    Posts at most the phase(s) currently due and not yet posted (so a tick that
    missed a window still catches up correctly on the next run, without ever
    double-posting a given phase — post_transaction's idempotency-key dedup is
    the final backstop).
    """
    _ = service_client
    context = _load_event_order_context(order_id)
    if context is None:
        return EventReleaseResult(
            order_id=order_id, outcome="not_eligible", reason="not_ticket_order"
        )

    if not context.is_paid:
        return EventReleaseResult(order_id=order_id, outcome="not_eligible", reason="unpaid")

    # Ticket cancellation is gated via event.status below; refunds still block release.
    # Lookup failures fail closed — never treat an unreadable refund state as clear.
    try:
        refund_blocked = order_is_refund_blocked(order_id)
    except ReleaseAccountingError as exc:
        return EventReleaseResult(
            order_id=order_id,
            outcome="not_eligible",
            reason=str(exc) if str(exc) else "refund_lookup_failed",
        )
    if refund_blocked:
        return EventReleaseResult(
            order_id=order_id, outcome="not_eligible", reason="order_refunded"
        )

    try:
        amounts = compute_release_amounts(
            order_id=order_id,
            gross_ngwee=context.gross_ngwee,
            commission_snapshot=context.commission_snapshot,
        )
    except ReleaseAccountingError:
        return EventReleaseResult(
            order_id=order_id,
            outcome="not_eligible",
            reason="invalid_commission_snapshot",
        )

    net_ngwee = amounts.net_ngwee
    if net_ngwee <= 0:
        return EventReleaseResult(
            order_id=order_id, outcome="not_eligible", reason="zero_net_amount"
        )

    effective_now = _normalize_now(now)
    branch = determine_branch(
        purchased_at=context.purchased_at,
        starts_at=context.starts_at,
        event_type=context.event_type,
    )

    required_keys: tuple[str, ...] = (
        (full_release_key(order_id),)
        if branch == "full"
        else (phase1_release_key(order_id), phase2_release_key(order_id))
    )
    posted_keys = _posted_release_keys(required_keys)

    if set(required_keys) <= posted_keys:
        return EventReleaseResult(
            order_id=order_id,
            outcome="already_released",
            reason="release_already_posted",
            branch=branch,
        )

    if context.event_status == "cancelled":
        _flag_mass_refund(order_id=order_id, event_id=context.event_id)
        return EventReleaseResult(
            order_id=order_id,
            outcome="blocked_cancelled",
            reason="event_cancelled",
            branch=branch,
        )

    if context.has_open_dispute is None:
        return EventReleaseResult(
            order_id=order_id,
            outcome="held",
            reason="dispute_lookup_failed",
            branch=branch,
        )
    if context.has_open_dispute:
        return EventReleaseResult(
            order_id=order_id, outcome="held", reason="dispute_open", branch=branch
        )

    # Decide which phases are due *before* capturing commission so we never
    # capture on a timers_not_met tick. Capture runs at most once (idempotent
    # prefix) immediately before the first RELEASE_TO_VENDOR for the order.
    phases_due: list[tuple[str, int, str]] = []

    # Post-event releases anchor on the instance's end (ends_at, or starts_at for
    # legacy rows). The pre-event phase-1 partial stays anchored on starts_at.
    settlement_end = instance_settlement_end(context.starts_at, context.ends_at)

    if branch == "full":
        due_at = settlement_end + timedelta(hours=FULL_RELEASE_DELAY_HOURS)
        key = full_release_key(order_id)
        if key not in posted_keys and effective_now >= due_at:
            phases_due.append(("full", net_ngwee, key))
    else:
        # Integer-exact halves: floor(net/2) + remainder == net, no ngwee lost to rounding.
        phase1_amount = net_ngwee // 2
        phase2_amount = net_ngwee - phase1_amount
        phase1_due = context.starts_at - timedelta(days=PHASE1_LEAD_DAYS)
        phase2_due = settlement_end + timedelta(days=PHASE2_DELAY_DAYS)
        phase1_key = phase1_release_key(order_id)
        phase2_key = phase2_release_key(order_id)

        if phase1_key not in posted_keys and effective_now >= phase1_due and phase1_amount > 0:
            phases_due.append(("phase1", phase1_amount, phase1_key))

        if phase2_key not in posted_keys and effective_now >= phase2_due and phase2_amount > 0:
            phases_due.append(("phase2", phase2_amount, phase2_key))

    if not phases_due:
        return EventReleaseResult(
            order_id=order_id, outcome="not_eligible", reason="timers_not_met", branch=branch
        )

    # Capture commission from purchase-time snapshot BEFORE any vendor release.
    # Phased releases still capture once (full commission) before phase1/phase2.
    capture_order_commission(
        order_id=order_id,
        commission_snapshot=context.commission_snapshot,
        idempotency_key_prefix=event_commission_idempotency_prefix(order_id),
    )

    phases_posted: list[str] = []
    transaction_ids: list[str] = []
    total_net = 0
    for phase_name, amount, key in phases_due:
        txn_id = _post_event_release(
            order_id=order_id,
            vendor_id=context.vendor_id,
            net_ngwee=amount,
            idempotency_key=key,
        )
        phases_posted.append(phase_name)
        transaction_ids.append(txn_id)
        total_net += amount

    return EventReleaseResult(
        order_id=order_id,
        outcome="released",
        reason="phase_release_posted" if branch == "phased" else "full_release_posted",
        branch=branch,
        phases_posted=tuple(phases_posted),
        transaction_ids=tuple(transaction_ids),
        net_ngwee=total_net,
    )


def _list_event_release_candidate_ids(
    *, limit: int, cursor: str | None, now: datetime
) -> list[str]:
    cursor_filter = f"AND o.id > {sql_literal(cursor)}::uuid" if cursor else ""
    now_sql = sql_literal(now.isoformat())
    script = f"""
SELECT DISTINCT o.id::text
FROM public.orders o
INNER JOIN public.order_items oi
  ON oi.order_id = o.id AND oi.item_kind = 'ticket'
INNER JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id
INNER JOIN public.event_instances ei ON ei.id = oit.instance_id
INNER JOIN public.events e ON e.id = ei.event_id
WHERE EXISTS (
  SELECT 1 FROM public.payments p
  WHERE p.checkout_group_id = o.checkout_group_id
    AND p.status = 'success'
)
AND NOT EXISTS (
  SELECT 1 FROM public.ledger_transactions lt
  WHERE lt.idempotency_key IN (
    'event-release-' || o.id::text || '-full',
    'event-release-' || o.id::text || '-phase2'
  )
)
AND (
  e.status = 'cancelled'
  OR {now_sql}::timestamptz >= (ei.starts_at - interval '{PHASE1_LEAD_DAYS} days')
)
{cursor_filter}
ORDER BY o.id::text ASC
LIMIT {int(limit)};
"""
    result = run_sql_script(script)
    if not result.ok:
        return []
    return result.rows


def sweep_event_releases(
    service_client: ServiceRoleClient,
    *,
    limit: int = 200,
    cursor: str | None = None,
    now: datetime | None = None,
) -> tuple[EventReleaseSweepResult, str | None]:
    """Batch-evaluate event release candidates; idempotent under overlap via ledger keys."""
    effective_now = _normalize_now(now)
    order_ids = _list_event_release_candidate_ids(
        limit=limit, cursor=cursor, now=effective_now
    )

    released = 0
    held = 0
    already_released = 0
    not_eligible = 0
    blocked_cancelled = 0

    for order_id in order_ids:
        result = evaluate_event_release(service_client, order_id, now=effective_now)
        if result.outcome == "released":
            released += 1
        elif result.outcome == "held":
            held += 1
        elif result.outcome == "already_released":
            already_released += 1
        elif result.outcome == "blocked_cancelled":
            blocked_cancelled += 1
        else:
            not_eligible += 1

    next_cursor = order_ids[-1] if len(order_ids) >= limit and order_ids else None

    return (
        EventReleaseSweepResult(
            scanned=len(order_ids),
            released=released,
            held=held,
            already_released=already_released,
            not_eligible=not_eligible,
            blocked_cancelled=blocked_cancelled,
        ),
        next_cursor,
    )
