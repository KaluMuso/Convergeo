"""Event-scoped Owner / Manager / Door team access."""

from __future__ import annotations

import hashlib
import re
import secrets
from typing import Any, Literal, cast

from app.errors import AppError

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")

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
        return cast(TeamRole, role)
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


def digest_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_invite_token() -> str:
    return secrets.token_urlsafe(32)


def normalize_invite_phone(value: str) -> str:
    digits = "".join(ch for ch in value.strip() if ch.isdigit() or ch == "+")
    if digits.startswith("+"):
        normalized = digits
    elif digits.startswith("260"):
        normalized = f"+{digits}"
    elif digits.startswith("0"):
        normalized = f"+260{digits[1:]}"
    else:
        normalized = f"+{digits}"
    if not _E164_RE.match(normalized):
        raise AppError(
            code="invalid_phone",
            message="Invite phone must be a valid number",
            http_status=422,
        )
    return normalized


def list_team_members(client: Any, *, event_id: str) -> list[dict[str, Any]]:
    response = (
        client.table("event_team_members")
        .select("id, user_id, role, accepted_at, revoked_at, created_at")
        .eq("event_id", event_id)
        .is_("revoked_at", "null")
        .execute()
    )
    return _rows(response)
