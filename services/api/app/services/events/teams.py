"""Event-scoped Owner / Manager / Door team access."""

from __future__ import annotations

from typing import Any, Literal

from app.errors import AppError

TeamRole = Literal["owner", "manager", "door"]

EDIT_ROLES = frozenset({"owner", "manager"})
SCAN_ROLES = frozenset({"owner", "manager", "door"})
FINANCE_ROLES = frozenset({"owner"})
OVERRIDE_ROLES = frozenset({"owner", "manager"})


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def load_event_role(
    client: Any,
    *,
    event_id: str,
    user_id: str,
    organiser_owner_user_id: str | None,
) -> TeamRole | None:
    if organiser_owner_user_id and organiser_owner_user_id == user_id:
        return "owner"
    response = (
        client.table("event_team_members")
        .select("role, revoked_at")
        .eq("event_id", event_id)
        .eq("user_id", user_id)
        .is_("revoked_at", "null")
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None
    role = row.get("role")
    if role in {"owner", "manager", "door"}:
        return role  # type: ignore[return-value]
    return None


def require_event_role(
    client: Any,
    *,
    event_id: str,
    user_id: str,
    organiser_owner_user_id: str | None,
    allowed: frozenset[str],
) -> TeamRole:
    role = load_event_role(
        client,
        event_id=event_id,
        user_id=user_id,
        organiser_owner_user_id=organiser_owner_user_id,
    )
    if role is None or role not in allowed:
        raise AppError(
            code="forbidden",
            message="You do not have access to this event",
            http_status=403,
            details={"message_key": "vendor.events.errors.forbidden"},
        )
    return role


def list_team_members(client: Any, *, event_id: str) -> list[dict[str, Any]]:
    response = (
        client.table("event_team_members")
        .select("id, user_id, role, accepted_at, revoked_at, created_at")
        .eq("event_id", event_id)
        .is_("revoked_at", "null")
        .execute()
    )
    return _rows(response)
