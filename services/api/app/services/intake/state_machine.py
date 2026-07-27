"""M18-P01 — guarded state machine for WAHA intake sessions (D35).

Convention #4: session status changes go through the guarded functions here,
never a raw UPDATE. Every transition:

* validates the target against an explicit allow-map (illegal moves raise);
* asserts the from-state **in the UPDATE's WHERE clause**, so two concurrent
  callers cannot both win — the loser gets ``intake_transition_conflict`` (409);
* writes an append-only ``intake_events`` audit row.

Lifecycle::

    collecting ──▶ needs_details ──▶ collecting            (vendor supplies more)
        │                │
        └────────────────┴──▶ ready_for_vendor_review
                                     │
                                     ▼
                                 submitted ──▶ pending_admin_review
                                                     │
                                          ┌──────────┴──────────┐
                                          ▼                     ▼
                                      approved              rejected

``expired`` is reachable from any non-terminal state (the M18-P07 sweep).

This module never touches ``vendor_listings``. Under the corrected D35 only
M18-P05's guarded, vendor-confirmed handoff may do that.
"""

from __future__ import annotations

from typing import Any, Final, Protocol

from app.errors import AppError

SESSIONS_TABLE: Final = "intake_sessions"
EVENTS_TABLE: Final = "intake_events"

# --- States -----------------------------------------------------------------
COLLECTING: Final = "collecting"
NEEDS_DETAILS: Final = "needs_details"
READY_FOR_VENDOR_REVIEW: Final = "ready_for_vendor_review"
SUBMITTED: Final = "submitted"
PENDING_ADMIN_REVIEW: Final = "pending_admin_review"
APPROVED: Final = "approved"
REJECTED: Final = "rejected"
EXPIRED: Final = "expired"

SESSION_STATUSES: Final[frozenset[str]] = frozenset(
    {
        COLLECTING,
        NEEDS_DETAILS,
        READY_FOR_VENDOR_REVIEW,
        SUBMITTED,
        PENDING_ADMIN_REVIEW,
        APPROVED,
        REJECTED,
        EXPIRED,
    }
)

TERMINAL_STATUSES: Final[frozenset[str]] = frozenset({APPROVED, REJECTED, EXPIRED})

# The only moves that exist. Anything absent from this map is impossible.
ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    COLLECTING: frozenset({NEEDS_DETAILS, READY_FOR_VENDOR_REVIEW, EXPIRED}),
    NEEDS_DETAILS: frozenset({COLLECTING, READY_FOR_VENDOR_REVIEW, EXPIRED}),
    READY_FOR_VENDOR_REVIEW: frozenset({NEEDS_DETAILS, SUBMITTED, EXPIRED}),
    SUBMITTED: frozenset({PENDING_ADMIN_REVIEW, EXPIRED}),
    PENDING_ADMIN_REVIEW: frozenset({APPROVED, REJECTED, NEEDS_DETAILS, EXPIRED}),
    APPROVED: frozenset(),
    REJECTED: frozenset(),
    EXPIRED: frozenset(),
}

# --- Audit dispositions (D35 §11) -------------------------------------------
DISPOSITION_DRAFT_CREATED: Final = "draft_created"
DISPOSITION_DROPPED_GROUP: Final = "dropped_group"
DISPOSITION_DROPPED_UNVERIFIED: Final = "dropped_unverified"
DISPOSITION_DROPPED_FLAG_OFF: Final = "dropped_flag_off"
DISPOSITION_REJECTED_AUTH: Final = "rejected_auth"
DISPOSITION_ERROR: Final = "error"

DISPOSITIONS: Final[frozenset[str]] = frozenset(
    {
        DISPOSITION_DRAFT_CREATED,
        DISPOSITION_DROPPED_GROUP,
        DISPOSITION_DROPPED_UNVERIFIED,
        DISPOSITION_DROPPED_FLAG_OFF,
        DISPOSITION_REJECTED_AUTH,
        DISPOSITION_ERROR,
    }
)


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _table(service_client: ServiceRoleClient, name: str) -> Any:
    return service_client.client.table(name)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def record_ingestion(
    service_client: ServiceRoleClient,
    *,
    disposition: str,
    vendor_id: str | None = None,
    session_id: str | None = None,
    provider_event_id: str | None = None,
    message_kind: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one *ingestion* row to the D35 §11 audit trail.

    ``vendor_id`` stays ``None`` for drops we could not resolve — recording a
    guess would defeat the no-account-disclosure rule.
    """
    if disposition not in DISPOSITIONS:
        raise AppError(
            code="invalid_intake_disposition",
            message="Unknown intake disposition",
            http_status=500,
            details={"disposition": disposition},
        )

    payload: dict[str, Any] = {
        "kind": "ingestion",
        "disposition": disposition,
        "vendor_id": vendor_id,
        "session_id": session_id,
        "provider_event_id": provider_event_id,
        "message_kind": message_kind,
        "detail": detail or {},
    }
    response = _table(service_client, EVENTS_TABLE).insert(payload).execute()
    rows = _rows(response)
    return rows[0] if rows else payload


def record_transition(
    service_client: ServiceRoleClient,
    *,
    session_id: str,
    from_status: str,
    to_status: str,
    vendor_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one *transition* row. No disposition applies to a state change."""
    payload: dict[str, Any] = {
        "kind": "transition",
        "session_id": session_id,
        "vendor_id": vendor_id,
        "from_status": from_status,
        "to_status": to_status,
        "detail": detail or {},
    }
    response = _table(service_client, EVENTS_TABLE).insert(payload).execute()
    rows = _rows(response)
    return rows[0] if rows else payload


def load_session(service_client: ServiceRoleClient, session_id: str) -> dict[str, Any]:
    response = (
        _table(service_client, SESSIONS_TABLE)
        .select("*")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    rows = _rows(response)
    if not rows:
        raise AppError(
            code="intake_session_not_found",
            message="Intake session not found",
            http_status=404,
            details={"session_id": session_id},
        )
    return rows[0]


def transition(
    service_client: ServiceRoleClient,
    *,
    session_id: str,
    to_status: str,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Move a session to ``to_status``, guarded and audited.

    Raises ``intake_invalid_transition`` (409) for a move that does not exist,
    and ``intake_transition_conflict`` (409) when another writer changed the row
    first. Never performs an unguarded UPDATE.
    """
    if to_status not in SESSION_STATUSES:
        raise AppError(
            code="intake_invalid_status",
            message="Unknown intake session status",
            http_status=500,
            details={"to_status": to_status},
        )

    current = load_session(service_client, session_id)
    from_status = str(current.get("status", ""))
    if from_status not in SESSION_STATUSES:
        raise AppError(
            code="intake_invalid_status",
            message="Intake session has an invalid status",
            http_status=500,
            details={"session_id": session_id, "status": from_status},
        )

    if to_status not in ALLOWED_TRANSITIONS.get(from_status, frozenset()):
        raise AppError(
            code="intake_invalid_transition",
            message="Intake session transition is not allowed",
            http_status=409,
            details={"from_status": from_status, "to_status": to_status},
        )

    patch: dict[str, Any] = {"status": to_status}
    if extra:
        patch.update(extra)
    if to_status == REJECTED and reason:
        patch["rejection_reason"] = reason

    # The from-state in the WHERE clause is what makes this race-safe: a second
    # concurrent caller matches zero rows and is told so, rather than silently
    # overwriting the first caller's transition.
    response = (
        _table(service_client, SESSIONS_TABLE)
        .update(patch)
        .eq("id", session_id)
        .eq("status", from_status)
        .execute()
    )
    updated = _rows(response)
    if not updated:
        raise AppError(
            code="intake_transition_conflict",
            message="Intake session changed concurrently",
            http_status=409,
            details={"session_id": session_id, "from_status": from_status},
        )

    detail: dict[str, Any] = {}
    if reason:
        detail["reason"] = reason
    record_transition(
        service_client,
        session_id=session_id,
        from_status=from_status,
        to_status=to_status,
        vendor_id=str(current.get("vendor_id")) if current.get("vendor_id") else None,
        detail=detail,
    )
    return updated[0]


def expire(service_client: ServiceRoleClient, *, session_id: str) -> dict[str, Any]:
    """Expire a stale session (M18-P07's sweep). Terminal states are left alone."""
    return transition(service_client, session_id=session_id, to_status=EXPIRED)


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES
