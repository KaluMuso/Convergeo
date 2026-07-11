"""Ask Vergeo quota enforcement, abuse filters, and spend metering.

Guest lifetime quota is keyed by ``guest_key`` (device cookie) with a best-effort
``client_ip`` heuristic so clearing cookies does not reset the 3-question lifetime cap
on the same network path. This is intentionally approximate (shared NAT, mobile
carrier rotation) and documented for operators.
"""

from __future__ import annotations

import hashlib
import importlib
import logging
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.errors import AppError
from app.services.ask.spend import (
    raise_if_killed,
    record_spend,
)

logger = logging.getLogger(__name__)

ServiceClient = Any

MAX_QUESTION_LENGTH = 500
ASK_RATE_LIMIT_PER_MINUTE = 10
ASK_DUPLICATE_WINDOW_SECONDS = 300

_OFF_TOPIC_PATTERNS = (
    re.compile(r"\b(write|generate|compose)\b.{0,40}\b(essay|poem|story|code)\b", re.I),
    re.compile(r"\b(homework|assignment)\b", re.I),
    re.compile(r"\b(weather|football|soccer|nba|premier league)\b", re.I),
)
_PII_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"\b(?:\+?260|0)(?:7[5-9]|9[6-9])\d{7}\b"),
    re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
)

_reservation_lock = threading.Lock()
_active_reservations: dict[str, str] = {}


@dataclass(frozen=True, slots=True)
class QuotaReservation:
    id: str


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _quota_error(
    *,
    code: str,
    i18n_key: str,
    http_status: int = 429,
    details: dict[str, Any] | None = None,
) -> AppError:
    payload = {"i18n_key": i18n_key}
    if details:
        payload.update(details)
    return AppError(
        code=code,
        message=i18n_key,
        http_status=http_status,
        details=payload,
    )


def _service_client() -> Any:
    return importlib.import_module("app.supabase_client").get_supabase_service_client().client


def normalize_question(question: str) -> str:
    return " ".join(question.strip().split())


def question_hash(question: str) -> str:
    normalized = normalize_question(question).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _abuse_key(*, guest_key: str | None, client_ip: str | None) -> str:
    if guest_key:
        return f"guest:{guest_key}"
    if client_ip:
        return f"ip:{client_ip}"
    return "anon:unknown"


def _screen_abuse(
    *,
    client: ServiceClient,
    question: str,
    guest_key: str | None,
    client_ip: str | None,
) -> None:
    normalized = normalize_question(question)
    if not normalized:
        raise _quota_error(
            code="ai_quota_empty",
            i18n_key="ai.quota.offTopic",
            http_status=400,
        )

    if len(normalized) > MAX_QUESTION_LENGTH:
        raise _quota_error(
            code="ai_quota_too_long",
            i18n_key="ai.quota.tooLong",
            http_status=400,
            details={"max_length": MAX_QUESTION_LENGTH},
        )

    for pattern in _OFF_TOPIC_PATTERNS:
        if pattern.search(normalized):
            raise _quota_error(
                code="ai_quota_off_topic",
                i18n_key="ai.quota.offTopic",
                http_status=400,
            )

    for pattern in _PII_PATTERNS:
        if pattern.search(normalized):
            raise _quota_error(
                code="ai_quota_pii",
                i18n_key="ai.quota.offTopic",
                http_status=400,
            )

    rate_key = _abuse_key(guest_key=guest_key, client_ip=client_ip)
    allowed, retry_after = bump_rate_counter(
        client=client,
        scope="auth_ip",
        key=f"ask:{rate_key}",
        window=timedelta(seconds=60),
        limit=ASK_RATE_LIMIT_PER_MINUTE,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="ai.quota.rateLimited",
            message="Too many questions",
        )

    q_hash = question_hash(normalized)
    recent = (
        client.table("ask_usage")
        .select("id,created_at")
        .eq("question_hash", q_hash)
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    row = _single_row(recent)
    if row is not None:
        created_at = row.get("created_at")
        if isinstance(created_at, datetime):
            created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
        elif isinstance(created_at, str):
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created = None
        if created is not None and created >= datetime.now(UTC) - timedelta(
            seconds=ASK_DUPLICATE_WINDOW_SECONDS
        ):
            raise _quota_error(
                code="ai_quota_duplicate",
                i18n_key="ai.quota.duplicate",
                http_status=429,
            )


def _reserve_quota(
    *,
    client: ServiceClient,
    user_id: str | None,
    guest_key: str | None,
    client_ip: str | None,
    q_hash: str,
) -> QuotaReservation:
    response = client.rpc(
        "reserve_ask_quota",
        {
            "p_user_id": user_id,
            "p_guest_key": guest_key,
            "p_client_ip": client_ip,
            "p_question_hash": q_hash,
        },
    ).execute()
    rows = _rows(response)
    if not rows:
        raise RuntimeError("reserve_ask_quota returned no rows")

    row = rows[0]
    if not row.get("allowed"):
        reason = str(row.get("reason", ""))
        if reason == "guest_exceeded":
            raise _quota_error(
                code="ai_quota_guest_exceeded",
                i18n_key="ai.quota.guestExceeded",
                http_status=429,
                details={"signup_prompt_key": "ai.quota.signupPrompt"},
            )
        if reason == "monthly_exceeded":
            raise _quota_error(
                code="ai_quota_monthly_exceeded",
                i18n_key="ai.quota.monthlyExceeded",
                http_status=429,
            )
        raise _quota_error(
            code="ai_quota_exceeded",
            i18n_key="ai.quota.monthlyExceeded",
            http_status=429,
        )

    reservation_id = row.get("reservation_id")
    if not isinstance(reservation_id, str) or not reservation_id:
        raise RuntimeError("reserve_ask_quota missing reservation_id")
    return QuotaReservation(id=reservation_id)


def check_and_reserve(
    *,
    client: ServiceClient | None = None,
    user_id: str | None = None,
    guest_key: str | None = None,
    client_ip: str | None = None,
    question: str,
) -> QuotaReservation:
    """Validate abuse filters, kill-switch, and atomically reserve one quota slot."""
    service = client or _service_client()

    raise_if_killed(client=service)
    _screen_abuse(
        client=service,
        question=question,
        guest_key=guest_key,
        client_ip=client_ip,
    )

    reservation = _reserve_quota(
        client=service,
        user_id=user_id,
        guest_key=guest_key,
        client_ip=client_ip,
        q_hash=question_hash(question),
    )

    request_key = user_id or _abuse_key(guest_key=guest_key, client_ip=client_ip)
    with _reservation_lock:
        _active_reservations[request_key] = reservation.id
    return reservation


def record_answer(
    *,
    client: ServiceClient | None = None,
    reservation: QuotaReservation | str | None = None,
    user_id: str | None = None,
    guest_key: str | None = None,
    client_ip: str | None = None,
    tokens: int,
    model: str,
) -> None:
    """Finalize one answered (non-cached) question and meter token spend."""
    service = client or _service_client()

    reservation_id: str | None
    if isinstance(reservation, QuotaReservation):
        reservation_id = reservation.id
    elif isinstance(reservation, str):
        reservation_id = reservation
    else:
        request_key = user_id or _abuse_key(guest_key=guest_key, client_ip=client_ip)
        with _reservation_lock:
            reservation_id = _active_reservations.pop(request_key, None)

    if not reservation_id:
        raise AppError(
            code="ai_quota_missing_reservation",
            message="Ask quota reservation missing",
            http_status=500,
        )

    record_spend(
        reservation_id=reservation_id,
        tokens=tokens,
        model=model,
        client=service,
    )


def clear_active_reservations_for_tests() -> None:
    with _reservation_lock:
        _active_reservations.clear()


__all__ = [
    "QuotaReservation",
    "check_and_reserve",
    "clear_active_reservations_for_tests",
    "question_hash",
    "record_answer",
]
