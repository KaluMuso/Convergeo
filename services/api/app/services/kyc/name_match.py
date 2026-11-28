from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any, Literal

import httpx
from app.errors import AppError
from app.services.payments.lenco.config import get_base_url

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
    if score >= 0.85:
        return score, True

    # Zambian MoMo wallets are often registered with first + surname only, or
    # surname first ("MUSONDA KALUBA"), while the NRC carries every name. When
    # one name's words are all in the other (at least two words, so a lone
    # surname never passes), it is the same person.
    left_tokens = set(re.findall(r"[a-z]+", left))
    right_tokens = set(re.findall(r"[a-z]+", right))
    shorter, longer = sorted((left_tokens, right_tokens), key=len)
    if len(shorter) >= 2 and shorter <= longer:
        return max(score, 0.9), True
    return score, False


def detect_momo_operator(phone: str) -> MomoOperator:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("260"):
        prefix = digits[3:5]
    elif digits.startswith("0"):
        prefix = digits[1:3]
    else:
        prefix = digits[:2]

    # ZICTA numbering: MTN 096/076, Airtel 097/077, Zamtel 095/075.
    if prefix in {"97", "77"}:
        return "airtel"
    if prefix in {"96", "76"}:
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
    # Same sandbox/production split (and staging guard) as every other Lenco
    # call, so a sandbox token is never sent to the live host or vice versa.
    http = client or httpx.AsyncClient(base_url=get_base_url(), timeout=15.0)
    try:
        response = await http.post("/resolve/mobile-money", json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as exc:
        if 400 <= exc.response.status_code < 500 and exc.response.status_code not in (401, 403):
            # Lenco could not find a wallet for this number on this network: the
            # vendor's input is wrong, not our upstream. Tell them, don't say 502.
            raise AppError(
                code="momo_account_not_found",
                message="No mobile money account found for this number on this network",
                http_status=422,
                details={"operator": resolved_operator},
            ) from exc
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
