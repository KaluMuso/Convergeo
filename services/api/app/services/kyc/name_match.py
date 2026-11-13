from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any, Literal

import httpx
from app.errors import AppError

LENCO_API_BASE = "https://api.lenco.co/access/v2"
MomoOperator = Literal["mtn", "airtel", "zamtel"]


@dataclass(frozen=True, slots=True)
class MomoNameMatchResult:
    phone: str
    operator: MomoOperator
    resolved_name: str | None
    legal_name: str
    match_score: float
    matched: bool
    recorded_at: str
    raw: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "phone": self.phone,
            "operator": self.operator,
            "resolved_name": self.resolved_name,
            "legal_name": self.legal_name,
            "match_score": self.match_score,
            "matched": self.matched,
            "recorded_at": self.recorded_at,
            "raw": self.raw,
        }


def _normalize_name(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value.strip().lower())
    return collapsed


def score_name_match(resolved_name: str | None, legal_name: str) -> tuple[float, bool]:
    if not resolved_name or not legal_name.strip():
        return 0.0, False

    left = _normalize_name(resolved_name)
    right = _normalize_name(legal_name)
    if not left or not right:
        return 0.0, False

    score = SequenceMatcher(None, left, right).ratio()
    return score, score >= 0.85


def detect_momo_operator(phone: str) -> MomoOperator:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("260"):
        prefix = digits[3:5]
    elif digits.startswith("0"):
        prefix = digits[1:3]
    else:
        prefix = digits[:2]

    if prefix in {"97", "77"}:
        return "airtel"
    if prefix in {"95", "96"}:
        return "mtn"
    return "zamtel"


async def resolve_momo_account_name(
  phone: str,
  operator: MomoOperator | None = None,
  *,
  client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    token = os.environ.get("LENCO_API_TOKEN", "").strip()
    if not token:
        raise AppError(
            code="configuration_error",
            message="LENCO_API_TOKEN is not configured",
            http_status=503,
        )

    resolved_operator = operator or detect_momo_operator(phone)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"phone": phone, "operator": resolved_operator}
    owns_client = client is None
    http = client or httpx.AsyncClient(base_url=LENCO_API_BASE, timeout=15.0)
    try:
        response = await http.post("/resolve/mobile-money", json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as exc:
        raise AppError(
            code="lenco_resolve_failed",
            message="Failed to resolve mobile-money account",
            http_status=502,
            details={"status_code": exc.response.status_code},
        ) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            code="lenco_resolve_failed",
            message="Failed to resolve mobile-money account",
            http_status=502,
        ) from exc
    finally:
        if owns_client:
            await http.aclose()

    if not isinstance(body, dict) or body.get("status") is not True:
        message = body.get("message") if isinstance(body, dict) else "resolve failed"
        raise AppError(
            code="lenco_resolve_failed",
            message=str(message),
            http_status=502,
        )

    data = body.get("data")
    if not isinstance(data, dict):
        raise AppError(
            code="lenco_resolve_failed",
            message="Lenco resolve response missing data",
            http_status=502,
        )
    return data


async def resolve_and_score_momo_name(
    *,
    phone: str,
    legal_name: str,
    operator: MomoOperator | None = None,
    client: httpx.AsyncClient | None = None,
) -> MomoNameMatchResult:
    data = await resolve_momo_account_name(phone, operator, client=client)
    resolved_name = data.get("accountName")
    if not isinstance(resolved_name, str):
        resolved_name = None

    resolved_operator = operator or detect_momo_operator(phone)
    score, matched = score_name_match(resolved_name, legal_name)
    return MomoNameMatchResult(
        phone=phone,
        operator=resolved_operator,
        resolved_name=resolved_name,
        legal_name=legal_name,
        match_score=score,
        matched=matched,
        recorded_at=datetime.now(UTC).isoformat(),
        raw=data,
    )
