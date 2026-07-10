"""Escrow release rules — buyer-confirm, auto timers, dispute hold, idempotent ledger post."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from app.services.commissions.engine import compute_order_commission
from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import SYSTEM_ACTOR_ID

DEFAULT_RELEASE_AFTER_DELIVERED_HOURS = 48
DEFAULT_RELEASE_AFTER_SHIPPED_DAYS = 7

OPEN_DISPUTE_STATUSES = frozenset({"open", "vendor_responded", "under_review"})

RELEASE_ELIGIBLE_STATUSES = frozenset({"shipped", "delivered", "completed"})


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


ReleaseOutcome = Literal["held", "released", "already_released", "not_eligible"]


@dataclass(frozen=True, slots=True)
class ReleaseResult:
    order_id: str
    outcome: ReleaseOutcome
    reason: str
    rule: str | None = None
    transaction_id: str | None = None
    net_ngwee: int | None = None


@dataclass(frozen=True, slots=True)
class ReleaseSweepResult:
    scanned: int
    released: int
    held: int
    already_released: int
    not_eligible: int


@dataclass(frozen=True, slots=True)
class _OrderContext:
    order_id: str
    status: str
    vendor_id: str
    cod: bool
    commission_snapshot: dict[str, Any]
    gross_ngwee: int
    has_open_dispute: bool
    already_released: bool
    buyer_confirmed: bool
    delivered_at: datetime | None
    shipped_at: datetime | None


def release_idempotency_key(order_id: str) -> str:
    return f"release-{order_id}"


def _sql_uuid(value: str, field: str) -> str:
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


def _read_config_int(key: str, default: int) -> int:
    key_sql = sql_literal(key)
    script = f"""
SELECT value::text
FROM public.platform_config
WHERE key = {key_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return default
    raw = result.rows[0].strip()
    if raw.isdigit():
        return int(raw)
    if raw.startswith('"') and raw.endswith('"') and raw[1:-1].isdigit():
        return int(raw[1:-1])
    return default


def _already_released(order_id: str) -> bool:
    key_sql = sql_literal(release_idempotency_key(order_id))
    script = f"""
SELECT id::text
FROM public.ledger_transactions
WHERE idempotency_key = {key_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    return bool(result.ok and result.rows)


def _order_gross_ngwee(order_id: str, delivery_fee_ngwee: int) -> int:
    order_sql = _sql_uuid(order_id, "order_id")
    script = f"""
SELECT coalesce(sum(qty * unit_price_ngwee), 0)::text
FROM public.order_items
WHERE order_id = {order_sql};
"""
    result = run_sql_script(script)
    subtotal = int(result.rows[0]) if result.ok and result.rows else 0
    return subtotal + int(delivery_fee_ngwee)


def _load_order_events(order_id: str) -> list[tuple[str | None, str, str | None, str]]:
    order_sql = _sql_uuid(order_id, "order_id")
    script = f"""
SELECT
  coalesce(from_status, ''),
  coalesce(to_status, ''),
  coalesce(actor::text, ''),
  created_at::text
FROM public.order_events
WHERE order_id = {order_sql}
ORDER BY created_at ASC, id ASC;
"""
    result = run_sql_script(script)
    if not result.ok:
        return []
    events: list[tuple[str | None, str, str | None, str]] = []
    for row in result.rows:
        parts = row.split("|", 3)
        if len(parts) != 4:
            continue
        from_status = parts[0] or None
        to_status = parts[1]
        actor = parts[2] or None
        created_at = parts[3]
        events.append((from_status, to_status, actor, created_at))
    return events


def _event_timestamps(
    events: list[tuple[str | None, str, str | None, str]],
) -> tuple[datetime | None, datetime | None, bool]:
    delivered_at: datetime | None = None
    shipped_at: datetime | None = None
    buyer_confirmed = False

    for from_status, to_status, actor, created_at_raw in events:
        created_at = _parse_timestamp(created_at_raw)

        if to_status == "shipped" and shipped_at is None and created_at is not None:
            shipped_at = created_at
        if to_status == "delivered" and delivered_at is None and created_at is not None:
            delivered_at = created_at
        if (
            from_status == "delivered"
            and to_status == "completed"
            and actor
            and actor != SYSTEM_ACTOR_ID
        ):
            buyer_confirmed = True

    return delivered_at, shipped_at, buyer_confirmed


def _has_open_dispute(order_id: str) -> bool:
    order_sql = _sql_uuid(order_id, "order_id")
    statuses_sql = ", ".join(sql_literal(status) for status in sorted(OPEN_DISPUTE_STATUSES))
    script = f"""
SELECT count(*)::text
FROM public.disputes
WHERE order_id = {order_sql}
  AND status IN ({statuses_sql});
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return False
    return int(result.rows[0]) > 0


def compute_net_ngwee(*, gross_ngwee: int, commission_snapshot: dict[str, Any]) -> int:
    """Order gross minus purchase-time snapshot commission (integer-exact)."""
    commission = compute_order_commission(commission_snapshot)
    net = gross_ngwee - commission.commission_ngwee
    if net < 0:
        msg = "net vendor amount must not be negative"
        raise ValueError(msg)
    return net


def evaluate_release_rules(
    *,
    status: str,
    cod: bool,
    has_open_dispute: bool,
    already_released: bool,
    buyer_confirmed: bool,
    delivered_at: datetime | None,
    shipped_at: datetime | None,
    release_after_delivered_hours: int,
    release_after_shipped_days: int,
    now: datetime,
) -> tuple[ReleaseOutcome, str, str | None]:
    """Pure rule evaluation in priority order; returns (outcome, reason, rule)."""
    if already_released:
        return "already_released", "release_already_posted", None

    if cod:
        return "not_eligible", "cod_order", None

    if status not in RELEASE_ELIGIBLE_STATUSES:
        return "not_eligible", f"status_{status}", None

    if has_open_dispute:
        return "held", "dispute_open", None

    if buyer_confirmed:
        return "released", "buyer_confirm_received", "buyer_confirm"

    if delivered_at is not None:
        auto_deadline = delivered_at + timedelta(hours=release_after_delivered_hours)
        if now >= auto_deadline:
            return "released", "auto_after_delivered", "auto_delivered"

    has_delivered = delivered_at is not None
    if shipped_at is not None and not has_delivered:
        fallback_deadline = shipped_at + timedelta(days=release_after_shipped_days)
        if now >= fallback_deadline:
            return "released", "shipped_fallback", "shipped_fallback"

    return "not_eligible", "timers_not_met", None


def _load_order_context(order_id: str) -> _OrderContext | None:
    order_sql = _sql_uuid(order_id, "order_id")
    script = f"""
SELECT
  status,
  vendor_id::text,
  cod::text,
  delivery_fee_ngwee::text,
  commission_snapshot::text
FROM public.orders
WHERE id = {order_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None

    parts = result.rows[0].split("|", 4)
    if len(parts) != 5:
        return None

    status, vendor_id, cod_raw, delivery_fee_raw, snapshot_raw = parts
    commission_snapshot: dict[str, Any]
    if snapshot_raw.strip():
        try:
            loaded = json.loads(snapshot_raw)
            commission_snapshot = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            commission_snapshot = {}
    else:
        commission_snapshot = {}

    delivery_fee_ngwee = int(delivery_fee_raw)
    events = _load_order_events(order_id)
    delivered_at, shipped_at, buyer_confirmed = _event_timestamps(events)

    return _OrderContext(
        order_id=order_id,
        status=status,
        vendor_id=vendor_id,
        cod=cod_raw == "t",
        commission_snapshot=commission_snapshot,
        gross_ngwee=_order_gross_ngwee(order_id, delivery_fee_ngwee),
        has_open_dispute=_has_open_dispute(order_id),
        already_released=_already_released(order_id),
        buyer_confirmed=buyer_confirmed,
        delivered_at=delivered_at,
        shipped_at=shipped_at,
    )


def _post_release(*, order_id: str, vendor_id: str, net_ngwee: int) -> str:
    posted = post_transaction(
        idempotency_key=release_idempotency_key(order_id),
        template=LedgerTemplate.RELEASE_TO_VENDOR,
        order_id=order_id,
        net_ngwee=net_ngwee,
        vendor_id=vendor_id,
    )
    return posted.id


def evaluate_and_release(
    service_client: ServiceRoleClient,
    order_id: str,
    *,
    now: datetime | None = None,
) -> ReleaseResult:
    """Evaluate escrow release rules for one order and post at most one release transaction."""
    _ = service_client
    context = _load_order_context(order_id)
    if context is None:
        return ReleaseResult(
            order_id=order_id,
            outcome="not_eligible",
            reason="order_not_found",
        )

    effective_now = now or datetime.now(UTC)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=UTC)

    delivered_hours = _read_config_int(
        "release_after_delivered_hours",
        DEFAULT_RELEASE_AFTER_DELIVERED_HOURS,
    )
    shipped_days = _read_config_int(
        "release_after_shipped_days",
        DEFAULT_RELEASE_AFTER_SHIPPED_DAYS,
    )

    outcome, reason, rule = evaluate_release_rules(
        status=context.status,
        cod=context.cod,
        has_open_dispute=context.has_open_dispute,
        already_released=context.already_released,
        buyer_confirmed=context.buyer_confirmed,
        delivered_at=context.delivered_at,
        shipped_at=context.shipped_at,
        release_after_delivered_hours=delivered_hours,
        release_after_shipped_days=shipped_days,
        now=effective_now,
    )

    if outcome != "released":
        return ReleaseResult(
            order_id=order_id,
            outcome=outcome,
            reason=reason,
            rule=rule,
        )

    net_ngwee = compute_net_ngwee(
        gross_ngwee=context.gross_ngwee,
        commission_snapshot=context.commission_snapshot,
    )
    transaction_id = _post_release(
        order_id=order_id,
        vendor_id=context.vendor_id,
        net_ngwee=net_ngwee,
    )
    return ReleaseResult(
        order_id=order_id,
        outcome="released",
        reason=reason,
        rule=rule,
        transaction_id=transaction_id,
        net_ngwee=net_ngwee,
    )


def _list_release_candidate_ids() -> list[str]:
    statuses_sql = ", ".join(sql_literal(status) for status in sorted(RELEASE_ELIGIBLE_STATUSES))
    script = f"""
SELECT id::text
FROM public.orders
WHERE status IN ({statuses_sql})
  AND cod = false
ORDER BY created_at ASC;
"""
    result = run_sql_script(script)
    if not result.ok:
        return []
    return result.rows


def sweep_escrow_releases(
    service_client: ServiceRoleClient,
    *,
    now: datetime | None = None,
) -> ReleaseSweepResult:
    """Sweep release-eligible orders; idempotent under overlap via ledger idempotency keys."""
    _ = service_client
    order_ids = _list_release_candidate_ids()

    released = 0
    held = 0
    already_released = 0
    not_eligible = 0

    for order_id in order_ids:
        result = evaluate_and_release(service_client, order_id, now=now)
        if result.outcome == "released":
            released += 1
        elif result.outcome == "held":
            held += 1
        elif result.outcome == "already_released":
            already_released += 1
        else:
            not_eligible += 1

    return ReleaseSweepResult(
        scanned=len(order_ids),
        released=released,
        held=held,
        already_released=already_released,
        not_eligible=not_eligible,
    )
