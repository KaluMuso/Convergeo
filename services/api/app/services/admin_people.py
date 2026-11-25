"""Resolve account ids to display names and emails for admin read surfaces.

``profiles`` holds ``display_name``; the email lives only in ``auth.users`` and is
read through the service-role gotrue admin API. Every lookup degrades to "no name"
rather than failing the admin page that asked for it.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol, TypedDict

from httpx import QueryParams

logger = logging.getLogger(__name__)

MAX_TERM_LEN = 80
MAX_LOOKUP_IDS = 100
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
# PostgREST filter syntax (`,()`), LIKE wildcards and quoting never reach a query.
_UNSAFE_CHARS_RE = re.compile(r"[%_*,()\\\"';:]")


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class Person(TypedDict):
    user_id: str
    display_name: str | None
    email: str | None


def is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


def clean_search_term(raw: str | None, *, max_len: int = MAX_TERM_LEN) -> str | None:
    """Return a term safe for ``ilike``/``or_`` filters, or ``None`` when nothing is left."""
    if raw is None:
        return None
    cleaned = " ".join(_UNSAFE_CHARS_RE.sub(" ", raw).split())[:max_len].strip()
    return cleaned or None


def _str_or_none(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _email_for(service: ServiceRoleClient, user_id: str) -> str | None:
    try:
        response = service.client.auth.admin.get_user_by_id(user_id)
    except Exception:  # noqa: BLE001 - the name still renders without the email
        logger.warning("admin people: email lookup failed", exc_info=True)
        return None
    return _str_or_none(getattr(getattr(response, "user", None), "email", None))


def people_by_ids(
    service: ServiceRoleClient, user_ids: set[str] | list[str], *, with_email: bool = True
) -> dict[str, Person]:
    ids = sorted({uid for uid in user_ids if isinstance(uid, str) and is_uuid(uid)})
    ids = ids[:MAX_LOOKUP_IDS]
    if not ids:
        return {}
    names: dict[str, str | None] = {}
    try:
        response = (
            service.client.table("profiles").select("id,display_name").in_("id", ids).execute()
        )
        for row in _rows(response):
            if isinstance(row.get("id"), str):
                names[row["id"]] = _str_or_none(row.get("display_name"))
    except Exception:  # noqa: BLE001
        logger.warning("admin people: profile lookup failed", exc_info=True)
    return {
        uid: Person(
            user_id=uid,
            display_name=names.get(uid),
            email=_email_for(service, uid) if with_email else None,
        )
        for uid in ids
    }


def _auth_users_matching(service: ServiceRoleClient, term: str, limit: int) -> list[Person]:
    """GoTrue's admin user list accepts ``filter`` (email / name ILIKE)."""
    try:
        response = service.client.auth.admin._request(
            "GET",
            "admin/users",
            query=QueryParams({"filter": term, "page": "1", "per_page": str(limit)}),
        )
        payload = response.json()
    except Exception:  # noqa: BLE001 - fall back to profile-name matches only
        logger.warning("admin people: auth user search failed", exc_info=True)
        return []
    users = payload.get("users") if isinstance(payload, dict) else None
    found: list[Person] = []
    for user in users if isinstance(users, list) else []:
        if not isinstance(user, dict) or not isinstance(user.get("id"), str):
            continue
        email = _str_or_none(user.get("email"))
        if email is None or term.lower() not in email.lower():
            continue
        found.append(Person(user_id=user["id"], display_name=None, email=email))
    return found[:limit]


def search_people(service: ServiceRoleClient, raw: str | None, *, limit: int = 20) -> list[Person]:
    """Accounts whose display name or email contains ``raw`` (an exact UUID matches its id)."""
    term = clean_search_term(raw)
    if term is None:
        return []
    if is_uuid(term):
        return list(people_by_ids(service, [term.lower()]).values())
    matched: dict[str, Person] = {}
    try:
        response = (
            service.client.table("profiles")
            .select("id,display_name")
            .ilike("display_name", f"%{term}%")
            .limit(limit)
            .execute()
        )
        for row in _rows(response):
            if isinstance(row.get("id"), str):
                matched[row["id"]] = Person(
                    user_id=row["id"],
                    display_name=_str_or_none(row.get("display_name")),
                    email=None,
                )
    except Exception:  # noqa: BLE001
        logger.warning("admin people: profile search failed", exc_info=True)
    if len(term) >= 3:
        for person in _auth_users_matching(service, term, limit):
            existing = matched.get(person["user_id"])
            if existing is not None:
                existing["email"] = person["email"]
            else:
                matched[person["user_id"]] = person
    people = list(matched.values())[:limit]
    missing_names = {p["user_id"] for p in people if p["display_name"] is None}
    if missing_names:
        named = people_by_ids(service, missing_names, with_email=False)
        for person in people:
            if person["display_name"] is None and person["user_id"] in named:
                person["display_name"] = named[person["user_id"]]["display_name"]
    for person in people:
        if person["email"] is None:
            person["email"] = _email_for(service, person["user_id"])
    return people
