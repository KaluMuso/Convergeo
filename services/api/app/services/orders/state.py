"""Order state machine — single authority for (status × event × actor) transitions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from app.errors import AppError
from app.services.orders.audit import run_sql_script, sql_literal

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Well-known UUID for automated jobs (auto-confirm, auto-release).
SYSTEM_ACTOR_ID = "00000000-0000-0000-0000-000000000001"


class OrderStatus(StrEnum):
    PLACED = "placed"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    READY = "ready"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderEvent(StrEnum):
    CONFIRM = "confirm"
    REJECT = "reject"
    CANCEL = "cancel"
    START_PROCESSING = "start_processing"
    READY_FOR_PICKUP = "ready_for_pickup"
    SHIP = "ship"
    VERIFY_PICKUP = "verify_pickup"
    MARK_DELIVERED = "mark_delivered"
    CONFIRM_RECEIVED = "confirm_received"
    AUTO_CONFIRM = "auto_confirm"
    AUTO_RELEASE = "auto_release"


class ActorRole(StrEnum):
    CUSTOMER = "customer"
    VENDOR = "vendor"
    ADMIN = "admin"
    SYSTEM = "system"


Fulfilment = Literal["delivery", "pickup"]

CANCELLATION_EVENTS = frozenset({OrderEvent.REJECT, OrderEvent.CANCEL})

# Fulfilment-progress events require a successful prepaid payment (COD exempt).
# Sellers must never pack/ship/confirm an unpaid prepaid order (PAY-01).
PREPAID_PAYMENT_REQUIRED_EVENTS = frozenset(
    {
        OrderEvent.CONFIRM,
        OrderEvent.START_PROCESSING,
        OrderEvent.READY_FOR_PICKUP,
        OrderEvent.SHIP,
        OrderEvent.VERIFY_PICKUP,
        OrderEvent.MARK_DELIVERED,
        OrderEvent.CONFIRM_RECEIVED,
        OrderEvent.AUTO_CONFIRM,
        OrderEvent.AUTO_RELEASE,
    }
)


@dataclass(frozen=True, slots=True)
class TransitionSpec:
    from_status: OrderStatus
    event: OrderEvent
    to_status: OrderStatus
    actors: frozenset[ActorRole]
    fulfilment: Fulfilment | None = None


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    id: str
    status: OrderStatus
    fulfilment: Fulfilment
    checkout_group_id: str
    cod: bool
    paid: bool
    has_collected_money: bool = False


@dataclass(frozen=True, slots=True)
class TransitionResult:
    permitted: bool
    to_status: OrderStatus | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class TransitionOutcome:
    order_id: str
    from_status: OrderStatus
    to_status: OrderStatus
    event: OrderEvent
    actor_id: str
    note: str


class OrderTransitionError(AppError):
    def __init__(
        self,
        message: str,
        *,
        from_status: str,
        event: str,
        actor_role: str,
        code: str = "order_invalid_transition",
        http_status: int = 409,
        extra_details: dict[str, Any] | None = None,
    ) -> None:
        details: dict[str, Any] = {
            "from_status": from_status,
            "event": event,
            "actor_role": actor_role,
            "message_key": "vendor.orders.errors.invalidTransition",
        }
        if extra_details:
            details.update(extra_details)
        super().__init__(
            code=code,
            message=message,
            http_status=http_status,
            details=details,
        )


class PrepaidPaymentRequiredError(OrderTransitionError):
    """Raised when fulfilment is attempted on an unpaid prepaid order."""

    def __init__(self, *, from_status: str, event: str, actor_role: str) -> None:
        super().__init__(
            "Prepaid order requires successful payment before fulfilment",
            from_status=from_status,
            event=event,
            actor_role=actor_role,
            code="order_payment_required",
            http_status=409,
            extra_details={"message_key": "vendor.orders.errors.paymentRequired"},
        )


class RefundPathRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="order_refund_path_required",
            message=("Collected money requires an authorized financial-resolution path"),
            http_status=409,
            details={"refund_path_required": True},
        )


TRANSITION_TABLE: tuple[TransitionSpec, ...] = (
    TransitionSpec(
        OrderStatus.PLACED,
        OrderEvent.CONFIRM,
        OrderStatus.CONFIRMED,
        frozenset({ActorRole.VENDOR, ActorRole.ADMIN}),
    ),
    TransitionSpec(
        OrderStatus.PLACED,
        OrderEvent.REJECT,
        OrderStatus.CANCELLED,
        frozenset({ActorRole.VENDOR, ActorRole.ADMIN}),
    ),
    TransitionSpec(
        OrderStatus.PLACED,
        OrderEvent.CANCEL,
        OrderStatus.CANCELLED,
        frozenset({ActorRole.CUSTOMER, ActorRole.ADMIN}),
    ),
    TransitionSpec(
        OrderStatus.CONFIRMED,
        OrderEvent.START_PROCESSING,
        OrderStatus.PROCESSING,
        frozenset({ActorRole.VENDOR, ActorRole.ADMIN}),
    ),
    TransitionSpec(
        OrderStatus.CONFIRMED,
        OrderEvent.REJECT,
        OrderStatus.CANCELLED,
        frozenset({ActorRole.VENDOR, ActorRole.ADMIN}),
    ),
    TransitionSpec(
        OrderStatus.CONFIRMED,
        OrderEvent.CANCEL,
        OrderStatus.CANCELLED,
        frozenset({ActorRole.CUSTOMER, ActorRole.ADMIN}),
    ),
    TransitionSpec(
        OrderStatus.PROCESSING,
        OrderEvent.READY_FOR_PICKUP,
        OrderStatus.READY,
        frozenset({ActorRole.VENDOR, ActorRole.ADMIN}),
        fulfilment="pickup",
    ),
    TransitionSpec(
        OrderStatus.PROCESSING,
        OrderEvent.SHIP,
        OrderStatus.SHIPPED,
        frozenset({ActorRole.VENDOR, ActorRole.ADMIN}),
        fulfilment="delivery",
    ),
    TransitionSpec(
        OrderStatus.PROCESSING,
        OrderEvent.CANCEL,
        OrderStatus.CANCELLED,
        frozenset({ActorRole.VENDOR, ActorRole.ADMIN}),
    ),
    TransitionSpec(
        OrderStatus.READY,
        OrderEvent.VERIFY_PICKUP,
        OrderStatus.DELIVERED,
        frozenset({ActorRole.VENDOR, ActorRole.ADMIN}),
    ),
    TransitionSpec(
        OrderStatus.READY,
        OrderEvent.CANCEL,
        OrderStatus.CANCELLED,
        frozenset({ActorRole.ADMIN}),
    ),
    TransitionSpec(
        OrderStatus.SHIPPED,
        OrderEvent.MARK_DELIVERED,
        OrderStatus.DELIVERED,
        frozenset({ActorRole.VENDOR, ActorRole.ADMIN, ActorRole.SYSTEM}),
    ),
    TransitionSpec(
        OrderStatus.SHIPPED,
        OrderEvent.AUTO_RELEASE,
        OrderStatus.COMPLETED,
        frozenset({ActorRole.SYSTEM}),
    ),
    TransitionSpec(
        OrderStatus.SHIPPED,
        OrderEvent.CANCEL,
        OrderStatus.CANCELLED,
        frozenset({ActorRole.ADMIN}),
    ),
    TransitionSpec(
        OrderStatus.DELIVERED,
        OrderEvent.CONFIRM_RECEIVED,
        OrderStatus.COMPLETED,
        frozenset({ActorRole.CUSTOMER, ActorRole.ADMIN}),
    ),
    TransitionSpec(
        OrderStatus.DELIVERED,
        OrderEvent.AUTO_CONFIRM,
        OrderStatus.COMPLETED,
        frozenset({ActorRole.SYSTEM}),
    ),
)

_TRANSITION_LOOKUP: dict[tuple[OrderStatus, OrderEvent], TransitionSpec] = {
    (spec.from_status, spec.event): spec for spec in TRANSITION_TABLE
}

_ALL_STATUSES = tuple(OrderStatus)
_ALL_EVENTS = tuple(OrderEvent)
_ALL_ACTORS = tuple(ActorRole)


def sql_uuid(value: str, field: str) -> str:
    if not _UUID_RE.match(value):
        raise ValueError(f"Invalid UUID for {field}")
    UUID(value)
    return f"'{value}'::uuid"


def _fetch_order_snapshot(order_id: str, *, for_update: bool = False) -> OrderSnapshot | None:
    order_sql = sql_uuid(order_id, "order_id")
    lock_clause = "FOR UPDATE" if for_update else ""
    script = f"""
SELECT
  o.id::text,
  o.status,
  o.fulfilment,
  o.checkout_group_id::text,
  o.cod::text,
  CASE
    WHEN o.cod THEN 'false'
    WHEN EXISTS (
      SELECT 1
      FROM public.payments p
      JOIN public.checkout_groups c ON c.id=p.checkout_group_id AND c.customer_id=o.customer_id
      WHERE p.checkout_group_id = o.checkout_group_id
        AND p.status = 'success'
    ) THEN 'true'
    ELSE 'false'
  END,
  public.order_has_collected_money(o.id)::text
FROM public.orders o
WHERE o.id = {order_sql}
{lock_clause};
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None
    parts = result.rows[0].split("|")
    if len(parts) != 7:
        return None
    return OrderSnapshot(
        id=parts[0],
        status=OrderStatus(parts[1]),
        fulfilment=parts[2],  # type: ignore[arg-type]
        checkout_group_id=parts[3],
        # psql -At / ::text may render boolean as t/f or true/false.
        cod=parts[4].lower() in {"t", "true", "1"},
        paid=parts[5].lower() in {"t", "true", "1"},
        has_collected_money=parts[6].lower() in {"t", "true", "1"},
    )


def is_order_paid(order: OrderSnapshot) -> bool:
    """Any collected money requires resolution; this is not full service funding."""
    return order.has_collected_money and not order.cod


def resolve_transition(
    *,
    from_status: OrderStatus,
    event: OrderEvent,
    actor_role: ActorRole,
    fulfilment: Fulfilment,
) -> TransitionResult:
    spec = _TRANSITION_LOOKUP.get((from_status, event))
    if spec is None:
        return TransitionResult(
            permitted=False,
            reason=f"No transition for {from_status.value} + {event.value}",
        )
    if actor_role not in spec.actors:
        return TransitionResult(
            permitted=False,
            reason=(
                f"Actor {actor_role.value} not permitted for {from_status.value} + {event.value}"
            ),
        )
    if spec.fulfilment is not None and spec.fulfilment != fulfilment:
        return TransitionResult(
            permitted=False,
            reason=(
                f"Event {event.value} requires fulfilment={spec.fulfilment}, order has {fulfilment}"
            ),
        )
    return TransitionResult(permitted=True, to_status=spec.to_status)


def all_matrix_cases() -> list[tuple[OrderStatus, OrderEvent, ActorRole, Fulfilment, bool]]:
    """Every (status, event, actor, fulfilment) with expected permit/reject."""
    cases: list[tuple[OrderStatus, OrderEvent, ActorRole, Fulfilment, bool]] = []
    for status in _ALL_STATUSES:
        for event in _ALL_EVENTS:
            for actor in _ALL_ACTORS:
                for fulfilment in ("delivery", "pickup"):
                    if status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
                        expected = False
                    else:
                        result = resolve_transition(
                            from_status=status,
                            event=event,
                            actor_role=actor,
                            fulfilment=fulfilment,
                        )
                        expected = result.permitted
                    cases.append((status, event, actor, fulfilment, expected))
    return cases


def _validate_actor_id(actor_role: ActorRole, actor_id: str) -> None:
    if actor_role == ActorRole.SYSTEM:
        if actor_id != SYSTEM_ACTOR_ID:
            raise ValueError("system transitions must use SYSTEM_ACTOR_ID")
        return
    if not _UUID_RE.match(actor_id):
        raise ValueError("actor_id must be a valid UUID for non-system actors")


def transition_order(
    *,
    order_id: str,
    event: OrderEvent,
    actor_role: ActorRole,
    actor_id: str,
    note: str,
    refund_path: bool = False,
) -> TransitionOutcome:
    """Execute a guarded order transition via service-role row-locked update."""
    _validate_actor_id(actor_role, actor_id)
    if not note.strip():
        raise AppError(
            code="validation_error",
            message="Transition note is required",
            http_status=422,
        )

    snapshot = _fetch_order_snapshot(order_id)
    if snapshot is None:
        raise AppError(code="not_found", message="Order not found", http_status=404)

    resolved = resolve_transition(
        from_status=snapshot.status,
        event=event,
        actor_role=actor_role,
        fulfilment=snapshot.fulfilment,
    )
    if not resolved.permitted or resolved.to_status is None:
        raise OrderTransitionError(
            resolved.reason or "Transition not permitted",
            from_status=snapshot.status.value,
            event=event.value,
            actor_role=actor_role.value,
        )

    order_sql = sql_uuid(order_id, "order_id")
    to_status = resolved.to_status.value
    from_status = snapshot.status.value
    actor_sql = sql_uuid(actor_id, "actor_id")
    # Roles alone and a caller-supplied refund_path flag are not order authority.
    authority_sql = {
        ActorRole.CUSTOMER: f"o.customer_id = {actor_sql}",
        ActorRole.VENDOR: (
            "EXISTS (SELECT 1 FROM public.vendors v "
            f"WHERE v.id=o.vendor_id AND v.owner_user_id={actor_sql})"
        ),
        ActorRole.ADMIN: (
            "EXISTS (SELECT 1 FROM public.user_roles ur "
            f"WHERE ur.user_id={actor_sql} AND ur.role IN ('admin','superadmin'))"
        ),
        ActorRole.SYSTEM: "true",  # identity checked above; internal trusted caller only
    }[actor_role]
    cancellation = event in CANCELLATION_EVENTS
    refund_authority = refund_path and actor_role in {ActorRole.ADMIN, ActorRole.VENDOR}
    update_script = f"""
BEGIN;
SELECT set_config('app.order_actor', {sql_literal(actor_id)}, true);
SELECT set_config('app.order_note', {sql_literal(note)}, true);
SELECT public.lock_payment_checkout_scope(
  (SELECT checkout_group_id FROM public.orders WHERE id={order_sql}));
SELECT id FROM public.orders WHERE id={order_sql} FOR UPDATE;
SELECT pg_advisory_xact_lock(hashtext('order_escrow:' || {order_sql}::text));
DO $order_authority$
DECLARE o public.orders%rowtype; has_money boolean; has_uncertain_attempt boolean;
BEGIN
  SELECT * INTO STRICT o FROM public.orders WHERE id={order_sql};
  IF NOT ({authority_sql}) THEN
    RAISE EXCEPTION 'ORDER_ACTOR_FORBIDDEN';
  END IF;
  IF o.status <> '{from_status}' THEN
    RAISE EXCEPTION 'ORDER_TRANSITION_CONFLICT';
  END IF;
  has_money := public.order_has_collected_money(o.id);
  has_uncertain_attempt := EXISTS (
    SELECT 1 FROM public.order_payment_checkouts(o.id) scope
    JOIN public.payments p ON p.checkout_group_id=scope.checkout_group_id
    WHERE p.status NOT IN ('success','cancelled')
      AND (p.status<>'failed' OR coalesce(p.raw->>'terminal_provider_failure','false')<>'true')
  );
  IF {str(cancellation).lower()} AND has_money AND NOT o.cod THEN
    IF NOT {str(refund_authority).lower()} THEN
      RAISE EXCEPTION 'ORDER_REFUND_AUTHORITY_REQUIRED';
    END IF;
    -- An authorized cancellation reserves financial resolution, not a refund
    -- entitlement or provider payout. Existing release ownership is preserved.
    INSERT INTO public.order_money_gates(order_id,gate)
    SELECT o.id,'refund' WHERE NOT EXISTS (
      SELECT 1 FROM public.ledger_transactions
      WHERE order_id=o.id AND kind='release_to_vendor')
    ON CONFLICT(order_id) DO NOTHING;
  END IF;
  IF {str(cancellation).lower()} AND (has_money OR has_uncertain_attempt) AND NOT o.cod THEN
    INSERT INTO public.audit_log(actor,action,entity_type,entity_id,after)
    VALUES ({actor_sql},'order.financial_resolution_required','order',o.id,
      jsonb_build_object('event','{event.value}','reason',{sql_literal(note)},
        'collected_money',has_money,'uncertain_attempt',has_uncertain_attempt,
        'checkout_groups',(SELECT jsonb_agg(checkout_group_id)
                          FROM public.order_payment_checkouts(o.id))));
  END IF;
END $order_authority$;
UPDATE public.orders o
SET status = '{to_status}'
WHERE o.id = {order_sql} AND o.status = '{from_status}'
  AND (
    '{event.value}' NOT IN ('confirm', 'start_processing', 'mark_ready', 'ship')
    OR o.cod
    OR EXISTS (SELECT 1 FROM public.payments p
               JOIN public.checkout_groups c ON c.id=p.checkout_group_id
                 AND c.customer_id=o.customer_id
               WHERE p.checkout_group_id=o.checkout_group_id AND p.status='success')
  )
RETURNING o.status;
COMMIT;
"""
    update_result = run_sql_script(update_script)
    if not update_result.ok:
        error = update_result.error or ""
        if "ORDER_ACTOR_FORBIDDEN" in error:
            raise AppError(
                code="forbidden", message="Order actor is not authorized", http_status=403
            )
        if "ORDER_REFUND_AUTHORITY_REQUIRED" in error:
            raise RefundPathRequiredError()
        if "ORDER_TRANSITION_CONFLICT" in error:
            current = _fetch_order_snapshot(order_id)
            if (
                cancellation
                and current is not None
                and is_order_paid(current)
                and not refund_authority
            ):
                raise RefundPathRequiredError()
            raise OrderTransitionError(
                "Concurrent transition changed order state",
                from_status=from_status,
                event=event.value,
                actor_role=actor_role.value,
            )
        raise RuntimeError(f"order transition failed: {update_result.error}")
    if not update_result.rows or update_result.rows[-1] != to_status:
        current = _fetch_order_snapshot(order_id)
        if (
            event in CANCELLATION_EVENTS
            and current is not None
            and is_order_paid(current)
            and not refund_authority
        ):
            raise RefundPathRequiredError()
        if (
            event in PREPAID_PAYMENT_REQUIRED_EVENTS
            and current is not None
            and not current.cod
            and not current.paid
        ):
            raise PrepaidPaymentRequiredError(
                from_status=current.status.value,
                event=event.value,
                actor_role=actor_role.value,
            )
        raise OrderTransitionError(
            "Concurrent transition changed order state",
            from_status=from_status,
            event=event.value,
            actor_role=actor_role.value,
        )

    return TransitionOutcome(
        order_id=order_id,
        from_status=snapshot.status,
        to_status=resolved.to_status,
        event=event,
        actor_id=actor_id,
        note=note,
    )


def fetch_latest_audit_event(order_id: str) -> dict[str, Any] | None:
    """Read the most recent order_events row for assertions."""
    order_sql = sql_uuid(order_id, "order_id")
    script = f"""
SELECT
  actor::text,
  from_status,
  to_status,
  coalesce(note, ''),
  id::text
FROM public.order_events
WHERE order_id = {order_sql}
ORDER BY created_at DESC, id DESC
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None
    parts = result.rows[0].split("|")
    if len(parts) != 5:
        return None
    return {
        "actor": parts[0] if parts[0] else None,
        "from_status": parts[1],
        "to_status": parts[2],
        "note": parts[3],
        "id": parts[4],
    }


def count_audit_events(order_id: str) -> int:
    order_sql = sql_uuid(order_id, "order_id")
    result = run_sql_script(
        f"SELECT count(*)::text FROM public.order_events WHERE order_id = {order_sql};"
    )
    if not result.ok or not result.rows:
        return 0
    return int(result.rows[0])
