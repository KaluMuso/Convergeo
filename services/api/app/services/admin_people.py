"""Resolve account ids to display names and emails for admin read surfaces.

``profiles`` holds ``display_name``; the email lives only in ``auth.users`` and is
read through the service-role gotrue admin API. Every lookup degrades to "no name"
rather than failing the admin page that asked for it.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol, TypedDict

logger = logging.getLogger(__name__)

MAX_TERM_LEN = 80
MAX_LOOKUP_IDS = 100
_DISTINCT_ACTOR_SCAN = 10_000
_MAX_EMAIL_FALLBACK = 20
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
    except Exception:
        logger.warning("admin people: email lookup failed for %s", user_id, exc_info=True)
        return None
    return _str_or_none(getattr(getattr(response, "user", None), "email", None))


def _emails_for_user_ids(
    service: ServiceRoleClient, user_ids: list[str]
) -> dict[str, str | None]:
    """Resolve emails for a bounded set of user ids via paginated ``list_users``."""
    want = {uid for uid in user_ids if is_uuid(uid)}
    emails: dict[str, str | None] = {uid: None for uid in user_ids}
    if not want:
        return emails
    page = 1
    while want and page <= 50:
        try:
            users = service.client.auth.admin.list_users(page=page, per_page=1000)
        except Exception:
            logger.warning("admin people: list_users failed", exc_info=True)
            break
        if not users:
            break
        for user in users:
            uid = getattr(user, "id", None)
            if isinstance(uid, str) and uid in want:
                emails[uid] = _str_or_none(getattr(user, "email", None))
                want.discard(uid)
        if len(users) < 1000:
            break
        page += 1
    # Fallback only for the stragglers (e.g. list_users failed); bounded so a bad page
    # can never turn into a per-id GoTrue storm.
    for uid in sorted(want)[:_MAX_EMAIL_FALLBACK]:
        emails[uid] = _email_for(service, uid)
    if len(want) > _MAX_EMAIL_FALLBACK:
        logger.warning("admin people: %d emails left unresolved", len(want) - _MAX_EMAIL_FALLBACK)
    return emails


def people_by_ids(
    service: ServiceRoleClient, user_ids: set[str] | list[str], *, with_email: bool = True
) -> dict[str, Person]:
    ids = sorted({uid for uid in user_ids if isinstance(uid, str) and is_uuid(uid)})
    if not ids:
        return {}
    result: dict[str, Person] = {}
    for offset in range(0, len(ids), MAX_LOOKUP_IDS):
        chunk = ids[offset : offset + MAX_LOOKUP_IDS]
        names: dict[str, str | None] = {}
        try:
            response = (
                service.client.table("profiles")
                .select("id,display_name")
                .in_("id", chunk)
                .execute()
            )
            for row in _rows(response):
                if isinstance(row.get("id"), str):
                    names[row["id"]] = _str_or_none(row.get("display_name"))
        except Exception:
            logger.warning("admin people: profile lookup failed", exc_info=True)
        email_map = _emails_for_user_ids(service, chunk) if with_email else {}
        for uid in chunk:
            result[uid] = Person(
                user_id=uid,
                display_name=names.get(uid),
                email=email_map.get(uid) if with_email else None,
            )
    return result


def _auth_users_matching(service: ServiceRoleClient, term: str, limit: int) -> list[Person]:
    """GoTrue admin ``list_users`` with client-side email contains match."""
    needle = term.lower()
    found: list[Person] = []
    page = 1
    while len(found) < limit and page <= 20:
        try:
            users = service.client.auth.admin.list_users(page=page, per_page=min(200, limit * 5))
        except Exception:
            logger.warning("admin people: auth user search failed", exc_info=True)
            break
        if not users:
            break
        for user in users:
            uid = getattr(user, "id", None)
            email = _str_or_none(getattr(user, "email", None))
            if isinstance(uid, str) and email and needle in email.lower():
                found.append(Person(user_id=uid, display_name=None, email=email))
                if len(found) >= limit:
                    return found[:limit]
        if len(users) < 200:
            break
        page += 1
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
    except Exception:
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
    missing_email = [p["user_id"] for p in people if p["email"] is None]
    if missing_email:
        email_map = _emails_for_user_ids(service, missing_email)
        for person in people:
            if person["email"] is None:
                person["email"] = email_map.get(person["user_id"])
    return people


def distinct_audit_actor_ids(service: ServiceRoleClient) -> set[str]:
    try:
        response = (
            service.client.table("audit_log")
            .select("actor")
            .limit(_DISTINCT_ACTOR_SCAN)
            .execute()
        )
    except Exception:
        logger.warning("admin people: audit actor id scan failed", exc_info=True)
        return set()
    return {str(row["actor"]) for row in _rows(response) if row.get("actor")}


def search_audit_actors(
    service: ServiceRoleClient, raw: str | None, *, limit: int = 50
) -> list[Person]:
    """Accounts that have acted in the audit log and match ``raw`` by id, name or email."""
    term = clean_search_term(raw)
    if term is None:
        return []
    actor_ids = distinct_audit_actor_ids(service)
    if not actor_ids:
        return []
    if is_uuid(term):
        uid = term.lower()
        if uid not in actor_ids:
            return []
        return list(people_by_ids(service, [uid]).values())
    needle = term.casefold()
    matched: dict[str, Person] = {}
    sorted_actors = sorted(actor_ids)
    for offset in range(0, len(sorted_actors), MAX_LOOKUP_IDS):
        chunk = sorted_actors[offset : offset + MAX_LOOKUP_IDS]
        for person in people_by_ids(service, chunk).values():
            name = (person["display_name"] or "").casefold()
            email = (person["email"] or "").casefold()
            if needle in name or (email and needle in email):
                matched[person["user_id"]] = person
                if len(matched) >= limit:
                    return list(matched.values())[:limit]
    return list(matched.values())[:limit]