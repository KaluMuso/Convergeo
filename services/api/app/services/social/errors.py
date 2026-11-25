"""Map Postgres ``social:*`` failures to HTTP + i18n keys."""

from __future__ import annotations

import re
from typing import Any

from app.errors import AppError
from postgrest.exceptions import APIError

_SOCIAL_CODE = re.compile(r"social:([a-z_]+)")

_SOCIAL_MAP: dict[str, tuple[str, int, str]] = {
    "disabled": ("feature_disabled", 404, "social.errors.disabled"),
    "unauthenticated": ("unauthorized", 401, "social.errors.unauthorized"),
    "actor_mismatch": ("forbidden", 403, "social.errors.forbidden"),
    "handle_invalid": ("validation_error", 422, "social.errors.handleInvalid"),
    "handle_taken": ("conflict", 409, "social.errors.handleTaken"),
    "handle_cooldown": ("conflict", 409, "social.errors.handleCooldown"),
    "unavailable": ("not_found", 404, "social.errors.unavailable"),
    "not_accepting": ("forbidden", 403, "social.errors.notAccepting"),
    "you_blocked": ("conflict", 409, "social.errors.youBlocked"),
    "self": ("validation_error", 422, "social.errors.self"),
    "already_contact": ("conflict", 409, "social.errors.alreadyContact"),
    "duplicate": ("conflict", 409, "social.errors.duplicate"),
    "note_too_long": ("validation_error", 422, "social.errors.noteTooLong"),
    "rate_limited": ("rate_limited", 429, "social.errors.rateLimited"),
    "not_found": ("not_found", 404, "social.errors.notFound"),
    "not_pending": ("conflict", 409, "social.errors.notPending"),
    "invalid_action": ("validation_error", 422, "social.errors.invalidAction"),
    "not_contact": ("forbidden", 403, "social.errors.notContact"),
    "message_invalid": ("validation_error", 422, "social.errors.messageInvalid"),
    "too_many_hashes": ("validation_error", 422, "social.errors.tooManyHashes"),
    "invalid_phone_hash": ("validation_error", 422, "social.errors.invalidPhoneHash"),
}


def _hint_from_api_error(exc: APIError) -> str:
    message = str(getattr(exc, "message", "") or "")
    if isinstance(exc.args[0], dict):
        nested = str(exc.args[0].get("message") or "")
        return nested or message
    return message


def raise_if_social_error_message(message: str) -> None:
    match = _SOCIAL_CODE.search(message)
    if not match:
        return
    code, status, key = _SOCIAL_MAP.get(
        match.group(1), ("social_error", 500, "social.errors.generic")
    )
    raise AppError(
        code=code,
        message=message,
        http_status=status,
        details={"message_key": key, "social_code": f"social:{match.group(1)}"},
    )


def map_social_rpc_error(exc: APIError) -> AppError:
    hint = _hint_from_api_error(exc)
    match = _SOCIAL_CODE.search(hint)
    if match:
        code, status, key = _SOCIAL_MAP.get(
            match.group(1), ("social_error", 500, "social.errors.generic")
        )
        return AppError(
            code=code,
            message=hint,
            http_status=status,
            details={"message_key": key, "social_code": f"social:{match.group(1)}"},
        )
    if getattr(exc, "code", None) == "42501":
        return AppError(
            code="forbidden",
            message=hint or "Forbidden",
            http_status=403,
            details={"message_key": "social.errors.forbidden"},
        )
    return AppError(
        code="internal_error",
        message=hint or "Social request failed",
        http_status=500,
    )


def rpc_rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def rpc_first(response: Any) -> dict[str, Any] | None:
    rows = rpc_rows(response)
    return rows[0] if rows else None