"""M16-P05: unified analytics query/emit surface over the server event streams.

One queryable schema for analytics. ``record_event`` writes generic / client-mirrored
events (e.g. the ``product_view`` / PDP funnel step, which has no dedicated stream
table) into the superset ``analytics_events`` table (migration 0029). ``query_funnel``
reads the canonical ``analytics_event_stream`` view — a union of ``analytics_events``,
``funnel_events`` (0025) and ``search_query_log`` (0027) — to return the end-to-end
funnel (search -> product_view -> cart -> checkout -> pay).

The existing streams (``funnel.py``, ``search_log.py``) are UNCHANGED: their rows
surface through the view, so no hot write path is touched. The server log is
anonymized regardless of consent — ``record_event`` rejects raw-PII props and any
money prop that is not an integer number of ngwee.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.services.orders.audit import run_sql_script, sql_literal

# ---------------------------------------------------------------------------
# Canonical funnel steps (search -> product_view -> cart -> checkout -> pay).
# ---------------------------------------------------------------------------
FUNNEL_STEPS: tuple[str, ...] = (
    "search",
    "product_view",
    "cart",
    "checkout",
    "pay",
)

# Maps a raw stream event_type onto a canonical funnel step. Multiple event types
# (checkout_start, payment_start) collapse onto one step (checkout).
EVENT_TYPE_TO_STEP: dict[str, str] = {
    "search": "search",
    "product_view": "product_view",
    "cart_add": "cart",
    "checkout_start": "checkout",
    "step_complete": "checkout",
    "payment_start": "checkout",
    "order_placed": "pay",
}

# Anonymization guard: raw-PII keys are never permitted in a server analytics prop.
_PII_KEYS: frozenset[str] = frozenset(
    {
        "phone",
        "phone_e164",
        "msisdn",
        "email",
        "password",
        "full_name",
        "display_name",
        "address",
        "landmark",
        "ip",
        "ip_address",
    }
)

_EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class FunnelReport:
    """Counts per canonical funnel step within the query window."""

    window_days: int
    steps: dict[str, int] = field(default_factory=dict)

    def count(self, step: str) -> int:
        return self.steps.get(step, 0)


def _validate_event_type(event_type: str) -> None:
    if not _EVENT_TYPE_RE.match(event_type):
        raise ValueError(f"Invalid event_type: {event_type!r}")


def _uuid_sql(value: str | None, field_name: str) -> str:
    if value is None:
        return "null"
    if not _UUID_RE.match(value):
        raise ValueError(f"Invalid UUID for {field_name}")
    UUID(value)
    return f"{sql_literal(value)}::uuid"


def _assert_anonymized(props: dict[str, Any]) -> None:
    """Reject raw PII and non-integer money — server log must never carry PII."""
    for key, value in props.items():
        if key.lower() in _PII_KEYS:
            raise ValueError(f"Raw PII key not allowed in analytics props: {key!r}")
        # Money must be a plain int. bool is an int subclass, so reject it explicitly.
        if key.endswith("_ngwee") and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            raise ValueError(f"Money prop {key!r} must be integer ngwee")


def _sql_json(value: dict[str, Any]) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return "'" + payload.replace("'", "''") + "'::jsonb"


def _clamp_window_days(days: int) -> int:
    if days < 1:
        return 1
    if days > 365:
        return 365
    return days


def record_event(
    *,
    event_type: str,
    session_id: str | None = None,
    user_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    props: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Insert a unified analytics event into ``analytics_events``.

    Used for events that have no dedicated stream table (e.g. ``product_view``/PDP).
    Anonymized: raises on raw-PII props and on non-integer money props. Returns the
    inserted row, or ``None`` if the write produced no row.
    """
    _validate_event_type(event_type)
    payload = dict(props or {})
    _assert_anonymized(payload)

    entity_type_sql = "null" if entity_type is None else sql_literal(entity_type)

    insert_sql = f"""
INSERT INTO public.analytics_events
  (event_type, session_id, user_id, entity_type, entity_id, props)
VALUES (
  {sql_literal(event_type)},
  {_uuid_sql(session_id, "session_id")},
  {_uuid_sql(user_id, "user_id")},
  {entity_type_sql},
  {_uuid_sql(entity_id, "entity_id")},
  {_sql_json(payload)}
)
RETURNING id::text, event_type, created_at::text;
"""
    result = run_sql_script(insert_sql)
    if not result.ok:
        raise RuntimeError(f"record_event failed: {result.error}")
    if not result.rows:
        return None
    parts = result.rows[0].split("|")
    if len(parts) < 3:
        return None
    return {"id": parts[0], "event_type": parts[1], "created_at": parts[2]}


def query_funnel(days: int = 30) -> FunnelReport:
    """Return per-step counts of the end-to-end funnel from the unified view.

    Reads ``analytics_event_stream`` (analytics_events ∪ funnel_events ∪
    search_query_log) and folds each stream's event_type onto a canonical funnel step.
    """
    window = _clamp_window_days(days)
    script = f"""
SELECT event_type, count(*)::text
FROM public.analytics_event_stream
WHERE created_at >= timezone('utc', now()) - (interval '1 day' * {window})
GROUP BY event_type;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"query_funnel failed: {result.error}")

    steps: dict[str, int] = {step: 0 for step in FUNNEL_STEPS}
    for line in result.rows:
        parts = line.split("|")
        if len(parts) != 2 or not parts[1].isdigit():
            continue
        event_type, count = parts[0], int(parts[1])
        step = EVENT_TYPE_TO_STEP.get(event_type)
        if step is not None:
            steps[step] += count
    return FunnelReport(window_days=window, steps=steps)
