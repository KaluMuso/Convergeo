"""M17-P01 — guarded lifecycle for video clips (spec: docs/plan/m17-video-feed.md).

Convention #4: a clip's status changes through the guarded functions here, never a
raw UPDATE. Every transition:

* validates the move against an explicit allow-map — anything absent is impossible;
* asserts the from-state **inside the UPDATE's WHERE clause**, so two concurrent
  callers cannot both win and the loser is told (``clip_transition_conflict``, 409)
  rather than silently overwriting;
* writes an append-only ``audit_log`` row.

Lifecycle::

    draft ──▶ screening ──▶ pending_review ──▶ published ──▶ taken_down
                  │                │
                  └────────────────┴──▶ rejected

``rejected`` and ``taken_down`` are **terminal**. The spec's §3 diagram shows no
return path, and inventing one here would be scope the pebble does not own — a
vendor whose clip was rejected uploads a new one. If a resubmit flow is wanted
later it should be a deliberate decision, not an accident of this map.

``taken_down`` is reachable only from ``published`` because it means "was public,
now is not". A clip that never published is refused with ``rejected`` instead, and
neither is publicly selectable in the first place.

**Instant-hide** is not implemented here; it is a property of the RLS policy in
migration ``0076``, which matches only ``status = 'published'``. The moment this
module moves a row out of that status the public SELECT stops returning it, in the
same statement. That is why takedown needs no cache invalidation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final, Protocol

from app.errors import AppError

CLIPS_TABLE: Final = "video_clips"
AUDIT_TABLE: Final = "audit_log"

# --- States -----------------------------------------------------------------
DRAFT: Final = "draft"
SCREENING: Final = "screening"
PENDING_REVIEW: Final = "pending_review"
PUBLISHED: Final = "published"
REJECTED: Final = "rejected"
TAKEN_DOWN: Final = "taken_down"

CLIP_STATUSES: Final[frozenset[str]] = frozenset(
    {DRAFT, SCREENING, PENDING_REVIEW, PUBLISHED, REJECTED, TAKEN_DOWN}
)

TERMINAL_STATUSES: Final[frozenset[str]] = frozenset({REJECTED, TAKEN_DOWN})

#: The only moves that exist. Anything not listed cannot happen.
ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    DRAFT: frozenset({SCREENING}),
    SCREENING: frozenset({PENDING_REVIEW, REJECTED}),
    PENDING_REVIEW: frozenset({PUBLISHED, REJECTED}),
    PUBLISHED: frozenset({TAKEN_DOWN}),
    REJECTED: frozenset(),
    TAKEN_DOWN: frozenset(),
}

#: The single status the public RLS policy matches. Named so callers can assert
#: against it instead of hard-coding the string.
PUBLIC_STATUS: Final = PUBLISHED

# --- Counters ---------------------------------------------------------------
LIKE_COUNT: Final = "like_count"
COMMENT_COUNT: Final = "comment_count"
VIEW_COUNT: Final = "view_count"

COUNTER_COLUMNS: Final[frozenset[str]] = frozenset({LIKE_COUNT, COMMENT_COUNT, VIEW_COUNT})


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


def _now() -> str:
    return datetime.now(UTC).isoformat()


def load_clip(service_client: ServiceRoleClient, clip_id: str) -> dict[str, Any]:
    rows = _rows(
        _table(service_client, CLIPS_TABLE)
        .select("*")
        .eq("id", clip_id)
        .maybe_single()
        .execute()
    )
    if not rows:
        raise AppError(
            code="clip_not_found",
            message="Clip not found",
            http_status=404,
            details={"clip_id": clip_id},
        )
    return rows[0]


def _record_audit(
    service_client: ServiceRoleClient,
    *,
    clip_id: str,
    actor_id: str | None,
    from_status: str,
    to_status: str,
    reason: str | None = None,
) -> None:
    """Append the transition to the shared admin audit trail.

    Uses the existing ``audit_log`` table rather than a clip-specific events table:
    the trail is meant to be one place a reviewer can look, and M17 has no audit
    need that ``audit_log``'s (actor, action, entity, before, after) shape misses.
    """
    after: dict[str, Any] = {"status": to_status}
    if reason:
        after["reason"] = reason
    _table(service_client, AUDIT_TABLE).insert(
        {
            "actor": actor_id,
            "action": "clip.transition",
            "entity_type": "video_clip",
            "entity_id": clip_id,
            "before": {"status": from_status},
            "after": after,
        }
    ).execute()


def transition(
    service_client: ServiceRoleClient,
    *,
    clip_id: str,
    to_status: str,
    actor_id: str | None = None,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Move a clip to ``to_status``, guarded and audited.

    Raises ``clip_invalid_transition`` (409) for a move that does not exist, and
    ``clip_transition_conflict`` (409) when another writer changed the row first.
    Never performs an unguarded UPDATE.
    """
    if to_status not in CLIP_STATUSES:
        raise AppError(
            code="clip_invalid_status",
            message="Unknown clip status",
            http_status=500,
            details={"to_status": to_status},
        )

    current = load_clip(service_client, clip_id)
    from_status = str(current.get("status", ""))
    if from_status not in CLIP_STATUSES:
        raise AppError(
            code="clip_invalid_status",
            message="Clip has an invalid status",
            http_status=500,
            details={"clip_id": clip_id, "status": from_status},
        )

    if to_status not in ALLOWED_TRANSITIONS.get(from_status, frozenset()):
        raise AppError(
            code="clip_invalid_transition",
            message="Clip status transition is not allowed",
            http_status=409,
            details={"from_status": from_status, "to_status": to_status},
        )

    patch: dict[str, Any] = {"status": to_status}
    if to_status == PUBLISHED:
        patch["published_at"] = _now()
    if to_status == TAKEN_DOWN:
        patch["taken_down_at"] = _now()
    if to_status == REJECTED and reason:
        patch["rejection_reason"] = reason
    if extra:
        patch.update(extra)

    # The from-state in the WHERE clause is what makes this race-safe: a second
    # concurrent caller matches zero rows and is told so, rather than silently
    # overwriting the first caller's transition.
    updated = _rows(
        _table(service_client, CLIPS_TABLE)
        .update(patch)
        .eq("id", clip_id)
        .eq("status", from_status)
        .execute()
    )
    if not updated:
        raise AppError(
            code="clip_transition_conflict",
            message="Clip status changed concurrently",
            http_status=409,
            details={"clip_id": clip_id, "from_status": from_status},
        )

    _record_audit(
        service_client,
        clip_id=clip_id,
        actor_id=actor_id,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
    )
    return updated[0]


# --- Named transitions ------------------------------------------------------
def start_screening(
    service_client: ServiceRoleClient, *, clip_id: str, actor_id: str | None = None
) -> dict[str, Any]:
    """Upload finished — hand the clip to the automated screen (M17-P02)."""
    return transition(
        service_client, clip_id=clip_id, to_status=SCREENING, actor_id=actor_id
    )


def pass_screening(
    service_client: ServiceRoleClient, *, clip_id: str, actor_id: str | None = None
) -> dict[str, Any]:
    """Automated screen passed — queue for the human reviewer (D-V8)."""
    return transition(
        service_client, clip_id=clip_id, to_status=PENDING_REVIEW, actor_id=actor_id
    )


def reject(
    service_client: ServiceRoleClient,
    *,
    clip_id: str,
    reason: str,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Refuse a clip, from either the automated screen or the human queue."""
    return transition(
        service_client, clip_id=clip_id, to_status=REJECTED, actor_id=actor_id, reason=reason
    )


def publish(
    service_client: ServiceRoleClient, *, clip_id: str, actor_id: str | None = None
) -> dict[str, Any]:
    """Approve — the only path that makes a clip publicly visible (D-V8)."""
    return transition(
        service_client, clip_id=clip_id, to_status=PUBLISHED, actor_id=actor_id
    )


def take_down(
    service_client: ServiceRoleClient,
    *,
    clip_id: str,
    reason: str | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Pull a published clip. Instant-hide — see the module docstring."""
    return transition(
        service_client,
        clip_id=clip_id,
        to_status=TAKEN_DOWN,
        actor_id=actor_id,
        reason=reason,
    )


def take_down_vendor_clips(
    service_client: ServiceRoleClient, *, vendor_id: str, actor_id: str | None = None
) -> list[str]:
    """Cascade: pull every published clip belonging to a suspended vendor.

    Each clip goes through the guarded transition individually so every takedown
    is audited. A clip that another writer already moved is skipped rather than
    forced — the desired end state (not public) was reached either way.
    """
    published = _rows(
        _table(service_client, CLIPS_TABLE)
        .select("id")
        .eq("vendor_id", vendor_id)
        .eq("status", PUBLISHED)
        .execute()
    )

    taken: list[str] = []
    for row in published:
        clip_id = str(row["id"])
        try:
            take_down(
                service_client,
                clip_id=clip_id,
                reason="vendor_suspended",
                actor_id=actor_id,
            )
            taken.append(clip_id)
        except AppError:
            continue
    return taken


# --- Counters ---------------------------------------------------------------
def bump_counter(
    service_client: ServiceRoleClient, *, clip_id: str, column: str, delta: int
) -> int:
    """Move a denormalised counter through the ``SECURITY DEFINER`` function.

    The function is the only path with the privilege to touch these columns — no
    client role holds ``UPDATE`` on them (migration ``0076`` grants column-level
    UPDATE for metadata only). Calling it with a relative delta rather than a
    read-then-write is what makes concurrent likes safe.
    """
    if column not in COUNTER_COLUMNS:
        raise AppError(
            code="clip_invalid_counter",
            message="Unknown clip counter",
            http_status=500,
            details={"column": column},
        )

    response = service_client.client.rpc(
        "clip_bump_counter",
        {"p_clip_id": clip_id, "p_column": column, "p_delta": delta},
    ).execute()

    data = getattr(response, "data", None)
    if isinstance(data, int):
        return data
    if isinstance(data, list) and data and isinstance(data[0], int):
        return data[0]
    raise AppError(
        code="clip_counter_failed",
        message="Counter update did not return a value",
        http_status=500,
        details={"clip_id": clip_id, "column": column},
    )


def is_public(status: str) -> bool:
    """Whether this status is the one the public RLS policy matches."""
    return status == PUBLIC_STATUS


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES
