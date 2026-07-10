"""Dispute state machine — guarded transitions with audit_log rows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, cast

from app.errors import AppError

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

TERMINAL_STATUSES = frozenset(
    {
        "resolved_refund",
        "resolved_release",
        "resolved_partial",
        "rejected",
    }
)


class DisputeStatus(StrEnum):
    OPEN = "open"
    VENDOR_RESPONDED = "vendor_responded"
    UNDER_REVIEW = "under_review"
    RESOLVED_REFUND = "resolved_refund"
    RESOLVED_RELEASE = "resolved_release"
    RESOLVED_PARTIAL = "resolved_partial"
    REJECTED = "rejected"


class DisputeEvent(StrEnum):
    VENDOR_RESPOND = "vendor_respond"
    ESCALATE = "escalate"
    RESOLVE_REFUND = "resolve_refund"
    RESOLVE_RELEASE = "resolve_release"
    RESOLVE_PARTIAL = "resolve_partial"
    REJECT = "reject"


class ActorRole(StrEnum):
    CUSTOMER = "customer"
    VENDOR = "vendor"
    ADMIN = "admin"


class ServiceRoleClient(Protocol):
    client: Any


@dataclass(frozen=True, slots=True)
class TransitionSpec:
    from_status: DisputeStatus
    event: DisputeEvent
    to_status: DisputeStatus
    actors: frozenset[ActorRole]


@dataclass(frozen=True, slots=True)
class DisputeSnapshot:
    id: str
    order_id: str
    status: DisputeStatus
    opener_user_id: str


@dataclass(frozen=True, slots=True)
class TransitionOutcome:
    dispute_id: str
    from_status: DisputeStatus
    to_status: DisputeStatus
    event: DisputeEvent
    actor_id: str
    note: str


class DisputeTransitionError(AppError):
    def __init__(
        self,
        message: str,
        *,
        from_status: str,
        event: str,
        actor_role: str,
    ) -> None:
        super().__init__(
            code="dispute_invalid_transition",
            message=message,
            http_status=409,
            details={"from_status": from_status, "event": event, "actor_role": actor_role},
        )


TRANSITION_TABLE: tuple[TransitionSpec, ...] = (
    TransitionSpec(
        DisputeStatus.OPEN,
        DisputeEvent.VENDOR_RESPOND,
        DisputeStatus.VENDOR_RESPONDED,
        frozenset({ActorRole.VENDOR}),
    ),
    TransitionSpec(
        DisputeStatus.OPEN,
        DisputeEvent.ESCALATE,
        DisputeStatus.UNDER_REVIEW,
        frozenset({ActorRole.ADMIN}),
    ),
    TransitionSpec(
        DisputeStatus.OPEN,
        DisputeEvent.REJECT,
        DisputeStatus.REJECTED,
        frozenset({ActorRole.ADMIN}),
    ),
    TransitionSpec(
        DisputeStatus.VENDOR_RESPONDED,
        DisputeEvent.ESCALATE,
        DisputeStatus.UNDER_REVIEW,
        frozenset({ActorRole.ADMIN}),
    ),
    TransitionSpec(
        DisputeStatus.VENDOR_RESPONDED,
        DisputeEvent.REJECT,
        DisputeStatus.REJECTED,
        frozenset({ActorRole.ADMIN}),
    ),
    TransitionSpec(
        DisputeStatus.UNDER_REVIEW,
        DisputeEvent.RESOLVE_REFUND,
        DisputeStatus.RESOLVED_REFUND,
        frozenset({ActorRole.ADMIN}),
    ),
    TransitionSpec(
        DisputeStatus.UNDER_REVIEW,
        DisputeEvent.RESOLVE_RELEASE,
        DisputeStatus.RESOLVED_RELEASE,
        frozenset({ActorRole.ADMIN}),
    ),
    TransitionSpec(
        DisputeStatus.UNDER_REVIEW,
        DisputeEvent.RESOLVE_PARTIAL,
        DisputeStatus.RESOLVED_PARTIAL,
        frozenset({ActorRole.ADMIN}),
    ),
    TransitionSpec(
        DisputeStatus.UNDER_REVIEW,
        DisputeEvent.REJECT,
        DisputeStatus.REJECTED,
        frozenset({ActorRole.ADMIN}),
    ),
)

_TRANSITION_LOOKUP: dict[tuple[DisputeStatus, DisputeEvent], TransitionSpec] = {
    (spec.from_status, spec.event): spec for spec in TRANSITION_TABLE
}


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return cast(dict[str, Any], first)
    return None


def resolve_transition(
    *,
    from_status: DisputeStatus,
    event: DisputeEvent,
    actor_role: ActorRole,
) -> DisputeStatus | None:
    spec = _TRANSITION_LOOKUP.get((from_status, event))
    if spec is None or actor_role not in spec.actors:
        return None
    return spec.to_status


def write_dispute_audit_log(
    service_client: ServiceRoleClient,
    *,
    actor_id: str,
    dispute_id: str,
    from_status: str,
    to_status: str,
    note: str,
) -> dict[str, Any]:
    row = {
        "actor": actor_id,
        "action": "dispute.transition",
        "entity_type": "dispute",
        "entity_id": dispute_id,
        "before": {"status": from_status},
        "after": {"status": to_status, "note": note},
    }
    response = service_client.client.table("audit_log").insert(row).execute()
    data = response.data
    if not isinstance(data, list) or not data:
        raise AppError(
            code="audit_write_failed",
            message="Failed to persist dispute audit_log row",
            http_status=500,
        )
    return cast(dict[str, Any], data[0])


def _validate_actor_id(actor_role: ActorRole, actor_id: str) -> None:
    if not _UUID_RE.match(actor_id):
        raise ValueError("actor_id must be a valid UUID")


def load_dispute_snapshot(
    service_client: ServiceRoleClient,
    dispute_id: str,
) -> DisputeSnapshot | None:
    response = (
        service_client.client.table("disputes")
        .select("id, order_id, status, opener_user_id")
        .eq("id", dispute_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None
    return DisputeSnapshot(
        id=str(row["id"]),
        order_id=str(row["order_id"]),
        status=DisputeStatus(str(row["status"])),
        opener_user_id=str(row["opener_user_id"]),
    )


def load_dispute_by_order(
    service_client: ServiceRoleClient,
    order_id: str,
) -> DisputeSnapshot | None:
    response = (
        service_client.client.table("disputes")
        .select("id, order_id, status, opener_user_id")
        .eq("order_id", order_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return None
    row = rows[0]
    return DisputeSnapshot(
        id=str(row["id"]),
        order_id=str(row["order_id"]),
        status=DisputeStatus(str(row["status"])),
        opener_user_id=str(row["opener_user_id"]),
    )


def transition_dispute(
    service_client: ServiceRoleClient,
    *,
    dispute_id: str,
    event: DisputeEvent,
    actor_role: ActorRole,
    actor_id: str,
    note: str,
    extra_updates: dict[str, Any] | None = None,
) -> TransitionOutcome:
    """Execute a guarded dispute transition; raw status UPDATEs are forbidden elsewhere."""
    _validate_actor_id(actor_role, actor_id)
    if not note.strip():
        raise AppError(
            code="validation_error",
            message="Transition note is required",
            http_status=422,
        )

    snapshot = load_dispute_snapshot(service_client, dispute_id)
    if snapshot is None:
        raise AppError(code="not_found", message="Dispute not found", http_status=404)

    to_status = resolve_transition(
        from_status=snapshot.status,
        event=event,
        actor_role=actor_role,
    )
    if to_status is None:
        raise DisputeTransitionError(
            f"Transition not permitted for {snapshot.status.value} + {event.value}",
            from_status=snapshot.status.value,
            event=event.value,
            actor_role=actor_role.value,
        )

    payload: dict[str, Any] = {"status": to_status.value}
    if extra_updates:
        payload.update(extra_updates)

    response = (
        service_client.client.table("disputes")
        .update(payload)
        .eq("id", dispute_id)
        .eq("status", snapshot.status.value)
        .execute()
    )
    row = _single_row(response)
    if row is None:
        rows = _rows(response)
        if not rows:
            raise DisputeTransitionError(
                "Concurrent transition changed dispute state",
                from_status=snapshot.status.value,
                event=event.value,
                actor_role=actor_role.value,
            )
        row = rows[0]

    write_dispute_audit_log(
        service_client,
        actor_id=actor_id,
        dispute_id=dispute_id,
        from_status=snapshot.status.value,
        to_status=to_status.value,
        note=note,
    )

    return TransitionOutcome(
        dispute_id=dispute_id,
        from_status=snapshot.status,
        to_status=to_status,
        event=event,
        actor_id=actor_id,
        note=note,
    )


def count_dispute_audit_events(service_client: ServiceRoleClient, dispute_id: str) -> int:
    response = (
        service_client.client.table("audit_log")
        .select("id", count="exact")
        .eq("entity_type", "dispute")
        .eq("entity_id", dispute_id)
        .execute()
    )
    count = getattr(response, "count", None)
    if isinstance(count, int):
        return count
    return len(_rows(response))
