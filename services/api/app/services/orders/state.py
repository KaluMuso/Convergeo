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
    ) -> None:
        super().__init__(
            code="order_invalid_transition",
            message=message,
            http_status=409,
            details={"from_status": from_status, "event": event, "actor_role": actor_role},
        )


class RefundPathRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="order_refund_path_required",
            message=(
                "Paid order cancellation requires refund_path=True "
                "(M08 refund execution pending)"
            ),
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
      WHERE p.checkout_group_id = o.checkout_group_id
        AND p.status = 'success'
    ) THEN 'true'
    ELSE 'false'
  END
FROM public.orders o
WHERE o.id = {order_sql}
{lock_clause};
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None
    parts = result.rows[0].split("|")
    if len(parts) != 6:
        return None
    return OrderSnapshot(
        id=parts[0],
        status=OrderStatus(parts[1]),
        fulfilment=parts[2],  # type: ignore[arg-type]
        checkout_group_id=parts[3],
        cod=parts[4] == "t",
        paid=parts[5] == "true",
    )


def is_order_paid(order: OrderSnapshot) -> bool:
    """Paid = successful checkout payment and not COD (collection-at-delivery)."""
    return order.paid and not order.cod


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
                f"Actor {actor_role.value} not permitted for "
                f"{from_status.value} + {event.value}"
            ),
        )
    if spec.fulfilment is not None and spec.fulfilment != fulfilment:
        return TransitionResult(
            permitted=False,
            reason=(
                f"Event {event.value} requires fulfilment={spec.fulfilment}, "
                f"order has {fulfilment}"
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

    if event in CANCELLATION_EVENTS and is_order_paid(snapshot) and not refund_path:
        raise RefundPathRequiredError()

    order_sql = sql_uuid(order_id, "order_id")
    to_status = resolved.to_status.value
    from_status = snapshot.status.value
    update_script = f"""
BEGIN;
SELECT set_config('app.order_actor', {sql_literal(actor_id)}, true);
SELECT set_config('app.order_note', {sql_literal(note)}, true);
WITH locked AS (
  SELECT id, status
  FROM public.orders
  WHERE id = {order_sql}
  FOR UPDATE
)
UPDATE public.orders o
SET status = '{to_status}'
FROM locked l
WHERE o.id = l.id
  AND l.status = '{from_status}'
RETURNING o.status;
COMMIT;
"""
    update_result = run_sql_script(update_script)
    if not update_result.ok:
        raise RuntimeError(f"order transition failed: {update_result.error}")
    if not update_result.rows or update_result.rows[-1] != to_status:
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
