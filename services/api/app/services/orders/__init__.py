"""Order state machine — guarded transitions with audit."""

from app.services.orders.state import (
    SYSTEM_ACTOR_ID,
    TRANSITION_TABLE,
    ActorRole,
    OrderEvent,
    OrderSnapshot,
    OrderStatus,
    OrderTransitionError,
    RefundPathRequiredError,
    all_matrix_cases,
    is_order_paid,
    resolve_transition,
    transition_order,
)

__all__ = [
    "SYSTEM_ACTOR_ID",
    "ActorRole",
    "OrderEvent",
    "OrderSnapshot",
    "OrderStatus",
    "OrderTransitionError",
    "RefundPathRequiredError",
    "TRANSITION_TABLE",
    "all_matrix_cases",
    "is_order_paid",
    "resolve_transition",
    "transition_order",
]
