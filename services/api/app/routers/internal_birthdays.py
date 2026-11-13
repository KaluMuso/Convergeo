"""n8n daily tick (08:00 Africa/Lusaka): birthday greeting + single-use coupon.

Idempotent: ``issue_birthday_greeting`` inserts one ``birthday_greetings`` row per
user per calendar year under a unique key, and creates the coupon, the in-app
notification and the WhatsApp outbox row in the same transaction — a re-run (or
two concurrent runs) issues nothing twice. No row = no consent = no greeting.
Minors are never targeted (an 18+ confirmation is required to store a birthday,
and a stored year is re-checked here). 29 February birthdays are greeted on
28 February in non-leap years.
"""

from __future__ import annotations

import calendar
import secrets
from datetime import date, datetime
from typing import Annotated, Any

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.account_birthday import ADULT_AGE, age_on
from app.services.coupons.rules import LUSAKA
from app.services.coupons.store import (
    BIRTHDAY_FLAG,
    COUPONS_FLAG,
    ServiceRoleClient,
    flag_enabled,
)
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

router = APIRouter(prefix="/internal/birthdays", tags=["internal-birthdays"])

_INTERNAL_TOKEN_ENV = "INTERNAL_BIRTHDAY_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-birthday"
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DEFAULT_CONFIG: dict[str, Any] = {
    "value_ngwee": 2000,
    "min_spend_ngwee": 20000,
    "valid_days": 14,
    "require_completed_order": True,
}


async def require_internal_birthday_token(request: Request) -> None:
    try:
        expected = resolve_internal_token(_INTERNAL_TOKEN_ENV, dev_default=_DEFAULT_INTERNAL_TOKEN)
    except InternalTokenMisconfigured as exc:
        raise AppError(code="configuration_error", message=str(exc), http_status=503) from exc
    provided = request.headers.get("X-Internal-Token")
    if not provided or not secrets.compare_digest(provided, expected):
        raise AppError(
            code="unauthorized", message="Invalid or missing internal token", http_status=401
        )


class BirthdayTickResult(BaseModel):
    date: str
    skipped: str | None = None
    candidates: int = 0
    issued: int = 0
    already_issued: int = 0
    not_eligible: int = 0


def birthday_keys_for(today: date) -> list[tuple[int, int]]:
    """(month, day) pairs greeted on ``today`` (29 Feb → 28 Feb in non-leap years)."""
    keys = [(today.month, today.day)]
    if today.month == 2 and today.day == 28 and not calendar.isleap(today.year):
        keys.append((2, 29))
    return keys


def birthday_code() -> str:
    return "BDAY-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _config(service: ServiceRoleClient) -> dict[str, Any]:
    rows = _rows(
        service.client.table("platform_config")
        .select("value")
        .eq("key", "birthday_coupon")
        .execute()
    )
    value = rows[0].get("value") if rows else None
    merged = dict(DEFAULT_CONFIG)
    if isinstance(value, dict):
        merged.update({key: value[key] for key in DEFAULT_CONFIG if key in value})
    for key in ("value_ngwee", "min_spend_ngwee", "valid_days"):
        if not isinstance(merged[key], int) or isinstance(merged[key], bool) or merged[key] < 0:
            merged[key] = DEFAULT_CONFIG[key]
    merged["valid_days"] = max(1, min(int(merged["valid_days"]), 60))
    if int(merged["value_ngwee"]) <= 0:
        merged["value_ngwee"] = DEFAULT_CONFIG["value_ngwee"]
    return merged


def _eligible(
    service: ServiceRoleClient, rows: list[dict[str, Any]], *, today: date, require_order: bool
) -> list[str]:
    adults: list[str] = []
    for row in rows:
        if not row.get("consent_at") or not row.get("adult_confirmed_at"):
            continue
        year = row.get("birth_year")
        if (
            isinstance(year, int)
            and age_on(today, day=int(row["birth_day"]), month=int(row["birth_month"]), year=year)
            < ADULT_AGE
        ):
            continue
        adults.append(str(row["user_id"]))
    if not adults:
        return []
    profiles = _rows(
        service.client.table("profiles").select("id, phone, deleted_at").in_("id", adults).execute()
    )
    live = {str(row["id"]) for row in profiles if row.get("phone") and not row.get("deleted_at")}
    eligible = [user_id for user_id in adults if user_id in live]
    if require_order and eligible:
        orders = _rows(
            service.client.table("orders")
            .select("customer_id")
            .in_("customer_id", eligible)
            .eq("status", "completed")
            .execute()
        )
        buyers = {str(row["customer_id"]) for row in orders}
        eligible = [user_id for user_id in eligible if user_id in buyers]
    return sorted(eligible)


@router.post(
    "/tick",
    response_model=BirthdayTickResult,
    dependencies=[Depends(require_internal_birthday_token)],
)
def birthday_tick(
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    on: str | None = None,
) -> BirthdayTickResult:
    today = datetime.strptime(on, "%Y-%m-%d").date() if on else datetime.now(LUSAKA).date()
    result = BirthdayTickResult(date=today.isoformat())
    if not (flag_enabled(service, BIRTHDAY_FLAG) and flag_enabled(service, COUPONS_FLAG)):
        result.skipped = "disabled"
        return result
    config = _config(service)
    candidates: list[dict[str, Any]] = []
    for month, day in birthday_keys_for(today):
        candidates.extend(
            _rows(
                service.client.table("profile_birthdays")
                .select(
                    "user_id, birth_day, birth_month, birth_year, consent_at, adult_confirmed_at"
                )
                .eq("birth_month", month)
                .eq("birth_day", day)
                .execute()
            )
        )
    result.candidates = len(candidates)
    eligible = _eligible(
        service, candidates, today=today, require_order=bool(config["require_completed_order"])
    )
    result.not_eligible = len(candidates) - len(eligible)
    for user_id in eligible:
        response = service.client.rpc(
            "issue_birthday_greeting",
            {
                "p_user_id": user_id,
                "p_year": today.year,
                "p_today": today.isoformat(),
                "p_code": birthday_code(),
                "p_value_ngwee": int(config["value_ngwee"]),
                "p_min_spend_ngwee": int(config["min_spend_ngwee"]),
                "p_valid_days": int(config["valid_days"]),
            },
        ).execute()
        if getattr(response, "data", None):
            result.issued += 1
        else:
            result.already_issued += 1
    return result
