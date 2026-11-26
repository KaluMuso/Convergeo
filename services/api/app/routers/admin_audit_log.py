"""Read-only audit-log viewer (2026-11 governance; audit report S5).

Superadmins, and operators whose `rbac_*` role carries `audit.read`, may read
`public.audit_log`. The unrestricted `admin` role does not imply `audit.read`.
Nothing here writes: the table is append-only in the database as well.

Personal data inside `before` / `after` (phones, emails, names, addresses, account
numbers, codes, tokens) is masked before it leaves the API; the viewer is for "who did
what, when, with what outcome", not for reading customer details.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from app.core.auth import CurrentUser, require_route_permission
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.admin_people import (
    MAX_TERM_LEN,
    Person,
    clean_search_term,
    is_uuid,
    people_by_ids,
    search_audit_actors,
)
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["admin-audit-log"])

MAX_PAGE = 100
_ACTION_RE = re.compile(r"^[a-z0-9_.:-]{1,80}$")
_ENTITY_RE = re.compile(r"^[a-z0-9_]{1,60}$")

# Keys whose values are personal data or secrets. Matched on the lower-cased key with
# word-ish boundaries, at any depth of the JSON payload.
_SENSITIVE_KEY_RE = re.compile(
    r"(^|_)(phone|msisdn|whatsapp|email|e164|name|display_name|full_name|first_name|"
    r"last_name|address|landmark|street|lat|lng|latitude|longitude|nrc|national_id|"
    r"passport|tpin|account|account_number|iban|momo|customer_momo|ip|ip_address|"
    r"user_agent|code|otp|token|secret|password|dob|birthday|birth_date)($|_)"
)
_PHONE_VALUE_RE = re.compile(r"^\+?[0-9][0-9 ()-]{6,}$")
_EMAIL_VALUE_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MASK = "•••"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def mask_pii(value: Any, *, key: str | None = None) -> Any:
    """Return a copy of a JSON value with personal data replaced by a mask."""
    if isinstance(value, dict):
        return {k: mask_pii(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_pii(item, key=key) for item in value]
    if key is not None and _SENSITIVE_KEY_RE.search(key.lower()) and value is not None:
        return MASK
    if isinstance(value, str) and (_PHONE_VALUE_RE.match(value) or _EMAIL_VALUE_RE.match(value)):
        return MASK
    return value


class AuditEntryOut(BaseModel):
    id: str
    at: datetime
    actor: str | None
    actor_name: str | None = None
    actor_email: str | None = None
    actor_roles: list[str] | None
    action: str
    entity_type: str
    entity_id: str | None
    entity_label: str | None = None
    outcome: str
    request_id: str | None
    reason: str | None
    before: Any
    after: Any


# Entities whose id is an administrator account (role assignments, deactivation).
_ADMIN_ACCOUNT_ENTITIES = frozenset({"admin_role", "admin_account"})
# entity_type -> (table, label column). Customer-owned records are never labelled.
_ENTITY_LABELS: dict[str, tuple[str, str]] = {
    "vendor": ("vendors", "display_name"),
    "product": ("products", "name"),
    "service": ("services", "title"),
    "event": ("events", "title"),
}


def _person_field(
    people: dict[str, Person], user_id: Any, field: Literal["display_name", "email"]
) -> str | None:
    person = people.get(str(user_id)) if user_id else None
    return person[field] if person else None


def _entity_labels(
    service: ServiceRoleClient, rows: list[dict[str, Any]], people: dict[str, Person]
) -> dict[tuple[str, str], str]:
    wanted: dict[str, set[str]] = {}
    for row in rows:
        entity_type, entity_id = row.get("entity_type"), row.get("entity_id")
        if entity_type in _ENTITY_LABELS and entity_id and is_uuid(str(entity_id)):
            wanted.setdefault(str(entity_type), set()).add(str(entity_id))
    labels: dict[tuple[str, str], str] = {}
    for entity_type, ids in wanted.items():
        table, column = _ENTITY_LABELS[entity_type]
        try:
            response = (
                service.client.table(table).select(f"id,{column}").in_("id", sorted(ids)).execute()
            )
        except Exception:  # noqa: BLE001 - the entry still renders with its id
            continue
        data = getattr(response, "data", None)
        for found in data if isinstance(data, list) else []:
            label = found.get(column) if isinstance(found, dict) else None
            if isinstance(label, str) and label.strip():
                labels[(entity_type, str(found.get("id")))] = label.strip()
    for row in rows:
        entity_type, entity_id = row.get("entity_type"), row.get("entity_id")
        if entity_type in _ADMIN_ACCOUNT_ENTITIES and entity_id:
            person = people.get(str(entity_id))
            label = (person["display_name"] or person["email"]) if person else None
            if label:
                labels[(str(entity_type), str(entity_id))] = label
    return labels


class AuditPageOut(BaseModel):
    items: list[AuditEntryOut]
    next_before: datetime | None
    next_before_id: str | None = None


@router.get("/audit-log", response_model=AuditPageOut)
def read_audit_log(
    viewer: Annotated[CurrentUser, Depends(require_route_permission)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    actor: Annotated[UUID | None, Query()] = None,
    actor_q: Annotated[str | None, Query(max_length=MAX_TERM_LEN)] = None,
    action: Annotated[str | None, Query(max_length=80)] = None,
    entity_type: Annotated[str | None, Query(max_length=60)] = None,
    entity_id: Annotated[UUID | None, Query()] = None,
    outcome: Annotated[Literal["success", "denied", "failed"] | None, Query()] = None,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
    before: Annotated[datetime | None, Query()] = None,
    before_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
) -> AuditPageOut:
    if action is not None and not _ACTION_RE.match(action):
        raise AppError(code="validation_error", message="Invalid action filter", http_status=422)
    if entity_type is not None and not _ENTITY_RE.match(entity_type):
        raise AppError(code="validation_error", message="Invalid resource filter", http_status=422)
    if since is not None and until is not None and since > until:
        raise AppError(code="validation_error", message="from must precede to", http_status=422)
    actor_ids: list[str] | None = None
    if actor_q is not None and actor is None:
        if clean_search_term(actor_q) is None:
            raise AppError(code="validation_error", message="Invalid actor filter", http_status=422)
        actor_ids = [
            person["user_id"] for person in search_audit_actors(service, actor_q, limit=50)
        ]
        if not actor_ids:
            return AuditPageOut(items=[], next_before=None, next_before_id=None)

    query = (
        service.client.table("audit_log")
        .select(
            "id,at,actor,actor_roles,action,entity_type,entity_id,outcome,request_id,"
            "reason,before,after"
        )
        .order("at", desc=True)
        .order("id", desc=True)
        .limit(limit + 1)
    )
    if actor is not None:
        query = query.eq("actor", str(actor))
    elif actor_ids is not None:
        query = query.in_("actor", actor_ids)
    if action is not None:
        # A trailing dot filters a family ("admin.orders.") — prefix match, no wildcards
        # from the caller (the regex above already refuses % and _ misuse).
        query = (
            query.like("action", action + "%")
            if action.endswith(".")
            else query.eq("action", action)
        )
    if entity_type is not None:
        query = query.eq("entity_type", entity_type)
    if entity_id is not None:
        query = query.eq("entity_id", str(entity_id))
    if outcome is not None:
        query = query.eq("outcome", outcome)
    if since is not None:
        query = query.gte("at", since.isoformat())
    if until is not None:
        query = query.lte("at", until.isoformat())
    if before is not None:
        before_iso = before.isoformat()
        if before_id is not None:
            bid = str(before_id)
            query = query.or_(f"at.lt.{before_iso},and(at.eq.{before_iso},id.lt.{bid})")
        else:
            query = query.lt("at", before_iso)

    data = getattr(query.execute(), "data", None)
    rows = [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
    page = rows[:limit]
    account_ids = {str(row["actor"]) for row in page if row.get("actor")} | {
        str(row["entity_id"])
        for row in page
        if row.get("entity_type") in _ADMIN_ACCOUNT_ENTITIES and row.get("entity_id")
    }
    people = people_by_ids(service, account_ids)
    labels = _entity_labels(service, page, people)
    show_actor_email = "superadmin" in viewer.roles
    items = [
        AuditEntryOut(
            id=str(row.get("id")),
            at=row["at"],
            actor=str(row["actor"]) if row.get("actor") else None,
            actor_name=_person_field(people, row.get("actor"), "display_name"),
            actor_email=(
                _person_field(people, row.get("actor"), "email") if show_actor_email else None
            ),
            actor_roles=row.get("actor_roles"),
            action=str(row.get("action") or ""),
            entity_type=str(row.get("entity_type") or ""),
            entity_id=str(row["entity_id"]) if row.get("entity_id") else None,
            entity_label=labels.get(
                (str(row.get("entity_type") or ""), str(row.get("entity_id") or ""))
            ),
            outcome=str(row.get("outcome") or "success"),
            request_id=row.get("request_id"),
            reason=mask_pii(row.get("reason")),
            before=mask_pii(row.get("before")),
            after=mask_pii(row.get("after")),
        )
        for row in page
        if row.get("at")
    ]
    next_before = items[-1].at if len(rows) > limit and items else None
    next_before_id = items[-1].id if next_before is not None else None
    return AuditPageOut(items=items, next_before=next_before, next_before_id=next_before_id)
