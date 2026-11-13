"""Optional birthday (day + month, optional year) with explicit marketing consent.

* Stored apart from ``profiles`` so it can be withdrawn by deleting one row.
* Saving requires an unticked-by-default consent box AND an 18+ confirmation;
  a year that makes the person a minor is refused and never stored.
* Once set, day/month can change at most once every 12 months (stops people
  moving their birthday to collect the treat again).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.coupons.rules import LUSAKA
from app.services.coupons.store import BIRTHDAY_FLAG, ServiceRoleClient, require_flag
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/account/birthday", tags=["account"])

CHANGE_COOLDOWN = timedelta(days=365)
ADULT_AGE = 18
WRITE_LIMIT = 10
WRITE_WINDOW = timedelta(hours=1)


class BirthdayIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    day: int = Field(ge=1, le=31)
    month: int = Field(ge=1, le=12)
    year: int | None = Field(default=None, ge=1900, le=2100)
    #: "Tell us your birthday for a treat each year" — must be ticked by the user.
    consent: bool
    #: "I am 18 or older" — birthday offers are never sent to minors.
    adult_confirmed: bool


class BirthdayOut(BaseModel):
    day: int | None = None
    month: int | None = None
    year: int | None = None
    consented: bool = False
    #: ISO date from which the day/month may be changed again (None = now).
    can_change_from: str | None = None


def valid_birthday(day: int, month: int, year: int | None) -> bool:
    try:
        date(year or 2000, month, day)  # 2000 is a leap year: 29 Feb is allowed without a year
    except ValueError:
        return False
    return True


def age_on(today: date, *, day: int, month: int, year: int) -> int:
    had_birthday = (today.month, today.day) >= (month, day)
    return today.year - year - (0 if had_birthday else 1)


def _row(service: ServiceRoleClient, user_id: str) -> dict[str, Any] | None:
    response = (
        service.client.table("profile_birthdays")
        .select("birth_day, birth_month, birth_year, consent_at, last_changed_at")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    data: Any = getattr(response, "data", None)
    if isinstance(data, list):
        data = data[0] if data else None
    return data if isinstance(data, dict) else None


def _out(row: dict[str, Any] | None) -> BirthdayOut:
    if row is None:
        return BirthdayOut()
    changed_raw = row.get("last_changed_at")
    can_change: str | None = None
    if isinstance(changed_raw, str):
        unlock = datetime.fromisoformat(changed_raw.replace("Z", "+00:00")) + CHANGE_COOLDOWN
        if unlock > datetime.now(UTC):
            can_change = unlock.astimezone(LUSAKA).date().isoformat()
    return BirthdayOut(
        day=row.get("birth_day"),
        month=row.get("birth_month"),
        year=row.get("birth_year"),
        consented=bool(row.get("consent_at")),
        can_change_from=can_change,
    )


def _error(code: str, key: str, status: int = 422, **details: Any) -> AppError:
    return AppError(
        code=code,
        message="Birthday not saved",
        http_status=status,
        details={"message_key": f"account.birthday.errors.{key}", **details},
    )


@router.get("", response_model=BirthdayOut)
def get_birthday(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BirthdayOut:
    return _out(_row(service, current_user.id))


@router.put("", response_model=BirthdayOut)
def put_birthday(
    body: BirthdayIn,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BirthdayOut:
    require_flag(service, BIRTHDAY_FLAG)
    allowed, retry_after = bump_rate_counter(
        scope="birthday_write", key=current_user.id, window=WRITE_WINDOW, limit=WRITE_LIMIT
    )
    if not allowed:
        raise_rate_limited(retry_after=retry_after, message_key="account.birthday.errors.tooMany")
    if not body.consent:
        raise _error("birthday.consent_required", "consent")
    if not body.adult_confirmed:
        raise _error("birthday.adult_required", "adult")
    if not valid_birthday(body.day, body.month, body.year):
        raise _error("birthday.invalid", "invalid")
    today = datetime.now(LUSAKA).date()
    if body.year is not None:
        if body.year > today.year:
            raise _error("birthday.invalid", "invalid")
        if age_on(today, day=body.day, month=body.month, year=body.year) < ADULT_AGE:
            # Never store a minor's birthday.
            raise _error("birthday.minor", "minor")

    existing = _row(service, current_user.id)
    now = datetime.now(UTC)
    changes_date = existing is None or (
        existing.get("birth_day") != body.day or existing.get("birth_month") != body.month
    )
    if existing is not None and changes_date:
        out = _out(existing)
        if out.can_change_from is not None:
            raise _error(
                "birthday.change_locked", "changeLocked", 409, can_change_from=out.can_change_from
            )
    service.client.table("profile_birthdays").upsert(
        {
            "user_id": current_user.id,
            "birth_day": body.day,
            "birth_month": body.month,
            "birth_year": body.year,
            "consent_at": now.isoformat(),
            "adult_confirmed_at": now.isoformat(),
            "last_changed_at": (
                now.isoformat()
                if changes_date or existing is None
                else existing.get("last_changed_at")
            ),
        },
        on_conflict="user_id",
    ).execute()
    service.client.table("audit_log").insert(
        {
            "actor": current_user.id,
            "action": "birthday.consented",
            "entity_type": "profile",
            "entity_id": current_user.id,
            "before": None,
            "after": {"date_changed": changes_date},
        }
    ).execute()
    return _out(_row(service, current_user.id))


@router.delete("", response_model=BirthdayOut)
def delete_birthday(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> BirthdayOut:
    """Withdraw consent: the birthday is erased and no greeting is ever sent."""
    service.client.table("profile_birthdays").delete().eq("user_id", current_user.id).execute()
    service.client.table("audit_log").insert(
        {
            "actor": current_user.id,
            "action": "birthday.withdrawn",
            "entity_type": "profile",
            "entity_id": current_user.id,
            "before": None,
            "after": {},
        }
    ).execute()
    return BirthdayOut()
