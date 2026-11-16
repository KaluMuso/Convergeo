"""Analytics v2 event envelope: registry, validation and v1 -> v2 normalisation.

Pure (no I/O). The collect endpoint (``analytics_v2_collect`` flag) turns a beacon
batch into validated :class:`LogRow` objects with :func:`normalize_batch` and hands
them to the bounded writer. Nothing here touches the database.

Privacy by construction (plan §R-B/§R-E):

* Event names are an allowlist (:data:`REGISTRY`); unknown events are rejected.
* Props are an allowlist per event, each with a type spec; unknown props are dropped,
  PII keys reject the event outright, and no money prop is accepted from a browser
  (commercial figures come only from authoritative tables — plan §R-I).
* Identifiers are only well-formed UUIDs; timestamps are clamped; sizes are bounded.

The registry mirrors ``packages/analytics/registry/events.v2.json`` (the single source
of truth); ``tests/test_analytics_v2_envelope.py`` asserts parity.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

ENVELOPE_VERSION: Final = 2

#: Events the server already records authoritatively (funnel/search). Accepted from a
#: beacon but never persisted from it — same contract as the v1 endpoint.
SERVER_RECORDED_EVENTS: Final[frozenset[str]] = frozenset(
    {"cart_add", "cart_remove", "checkout_start", "step_complete", "payment_start", "order_placed"}
)

SOURCE_APPS: Final[tuple[str, ...]] = ("customer", "vendor", "admin", "server")

SourceApp = Literal["customer", "vendor", "admin", "server"]


@dataclass(frozen=True, slots=True)
class EventSpec:
    version: int
    entity_type: str | None
    entity_prop: str | None
    props: dict[str, str] = field(default_factory=dict)


#: Mirror of ``packages/analytics/registry/events.v2.json``. Add an event in BOTH places.
REGISTRY: Final[dict[str, EventSpec]] = {
    "session_start": EventSpec(
        version=1,
        entity_type=None,
        entity_prop=None,
        props={
            "entry_page_key": "key",
            "referrer_kind": "enum:direct|search|social|internal|other",
        },
    ),
    "page_view": EventSpec(version=1, entity_type=None, entity_prop=None, props={}),
    "search": EventSpec(
        version=1,
        entity_type=None,
        entity_prop=None,
        props={"zero_result": "bool", "result_count": "int"},
    ),
    "product_view": EventSpec(
        version=1,
        entity_type="product",
        entity_prop="product_id",
        props={"product_id": "uuid!", "listing_id": "uuid"},
    ),
    "product_share": EventSpec(
        version=1,
        entity_type="product",
        entity_prop="product_id",
        props={"product_id": "uuid!", "channel": "enum:whatsapp|copy|native|other"},
    ),
    "recommendation_impression": EventSpec(
        version=1,
        entity_type="product",
        entity_prop="product_id",
        props={"product_id": "uuid!", "slot": "key", "rank": "int"},
    ),
    "recommendation_click": EventSpec(
        version=1,
        entity_type="product",
        entity_prop="product_id",
        props={"product_id": "uuid!", "slot": "key", "rank": "int"},
    ),
}

# Raw-PII keys are never permitted, even if a future registry entry lists one.
PII_KEYS: Final[frozenset[str]] = frozenset(
    {
        "phone",
        "phone_e164",
        "msisdn",
        "email",
        "password",
        "token",
        "access_token",
        "full_name",
        "display_name",
        "name",
        "address",
        "landmark",
        "ip",
        "ip_address",
        "user_agent",
        "url",
        "referrer",
        "query",
        "term",
        "nrc",
    }
)

MAX_EVENTS_PER_BATCH: Final = 20
MAX_PROPS_CHARS: Final = 2_000
MAX_INT_PROP: Final = 1_000_000_000
# Client clocks are untrusted: accept [now - 7d, now + 5min]; otherwise store NULL.
MAX_CLIENT_TS_PAST_MS: Final = 7 * 86_400_000
MAX_CLIENT_TS_FUTURE_MS: Final = 5 * 60_000

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_KEY_RE = re.compile(r"^[a-z0-9_.-]{1,48}$")
_EVENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class RawEvent(BaseModel):
    """One wire event. Lenient: unknown keys ignored so version skew never drops a batch."""

    model_config = ConfigDict(extra="ignore")

    event: str = Field(min_length=1, max_length=64)
    props: dict[str, Any] = Field(default_factory=dict)
    ts: int | None = None
    # v2-only fields (absent on v1 clients)
    id: str | None = Field(default=None, max_length=36)
    ev: int | None = None
    seq: int | None = None
    page: str | None = Field(default=None, max_length=64)


class RawBatch(BaseModel):
    """A beacon body: v1 ``{session_id?, events}`` or its v2 superset."""

    model_config = ConfigDict(extra="ignore")

    v: int | None = None
    session_id: str | None = Field(default=None, max_length=36)
    anon: str | None = Field(default=None, max_length=36)
    sid: str | None = Field(default=None, max_length=36)
    app: str | None = Field(default=None, max_length=16)
    consent: str | None = Field(default=None, max_length=16)
    events: list[RawEvent] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class LogRow:
    """A validated row for ``public.analytics_event_log``."""

    event_id: str
    event_name: str
    event_version: int
    source_app: str
    anon_id: str | None
    session_id: str | None
    user_id: str | None
    client_ts_ms: int | None
    seq: int | None
    page_key: str | None
    entity_type: str | None
    entity_id: str | None
    props: dict[str, Any]


@dataclass(slots=True)
class NormalizedBatch:
    rows: list[LogRow] = field(default_factory=list)
    skipped: int = 0  # server-recorded events (accepted, not persisted)
    rejected_invalid: int = 0
    rejected_unknown: int = 0

    @property
    def rejected(self) -> int:
        return self.rejected_invalid + self.rejected_unknown


class InvalidEvent(ValueError):
    """A registered event whose payload fails validation."""


def is_uuid(value: object) -> bool:
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def _uuid_or_none(value: str | None) -> str | None:
    return value.lower() if is_uuid(value) and value is not None else None


def _check_prop(spec: str, value: Any) -> Any:
    """Return the validated value, or raise :class:`InvalidEvent`."""
    base = spec.rstrip("!")
    if base == "uuid":
        if not is_uuid(value):
            raise InvalidEvent("expected uuid")
        return str(value).lower()
    if base == "bool":
        if not isinstance(value, bool):
            raise InvalidEvent("expected bool")
        return value
    if base == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidEvent("expected int")
        if value < 0 or value > MAX_INT_PROP:
            raise InvalidEvent("int out of range")
        return value
    if base == "key":
        if not isinstance(value, str) or not _KEY_RE.match(value):
            raise InvalidEvent("expected key")
        return value
    if base.startswith("enum:"):
        allowed = base.removeprefix("enum:").split("|")
        if value not in allowed:
            raise InvalidEvent("value not in enum")
        return value
    raise InvalidEvent(f"unknown spec {spec!r}")  # pragma: no cover — registry bug


def validate_props(spec: EventSpec, props: dict[str, Any]) -> dict[str, Any]:
    """Allowlist + type-check props. Unknown keys dropped; PII keys reject the event.

    A present-but-invalid optional prop is dropped (lenient, keeps the count); an
    invalid or missing *required* prop (``uuid!``) rejects the event.
    """
    if len(json.dumps(props, separators=(",", ":"), default=str)) > MAX_PROPS_CHARS:
        raise InvalidEvent("props too large")
    for key in props:
        if key.lower() in PII_KEYS or key.lower().endswith("_ngwee"):
            raise InvalidEvent(f"forbidden prop key {key!r}")
    clean: dict[str, Any] = {}
    for key, type_spec in spec.props.items():
        required = type_spec.endswith("!")
        if key not in props or props[key] is None:
            if required:
                raise InvalidEvent(f"missing required prop {key!r}")
            continue
        try:
            clean[key] = _check_prop(type_spec, props[key])
        except InvalidEvent:
            if required:
                raise
    return clean


def _clamp_ts(ts: int | None, now_ms: int) -> int | None:
    if ts is None or isinstance(ts, bool):
        return None
    if ts < now_ms - MAX_CLIENT_TS_PAST_MS or ts > now_ms + MAX_CLIENT_TS_FUTURE_MS:
        return None
    return ts


def _page_key(value: str | None) -> str | None:
    if value is None or not _KEY_RE.match(value):
        return None
    return value


def _source_app(value: str | None) -> str:
    return value if value in SOURCE_APPS and value != "server" else "customer"


def normalize_event(
    raw: RawEvent,
    *,
    is_v2: bool,
    anon_id: str | None,
    session_id: str | None,
    user_id: str | None,
    source_app: str,
    now_ms: int,
) -> LogRow:
    """Validate one registered event into a :class:`LogRow` (raises InvalidEvent)."""
    spec = REGISTRY[raw.event]
    if is_v2 and raw.ev is not None and raw.ev != spec.version:
        raise InvalidEvent("unsupported event version")
    props = validate_props(spec, raw.props)
    # v2 clients supply a stable id (dedup on retry); v1 clients cannot, so the server
    # synthesises one (no cross-flush dedup is possible for v1 — documented in §F.4).
    event_id = _uuid_or_none(raw.id) if is_v2 else None
    if is_v2 and event_id is None:
        raise InvalidEvent("v2 event requires a uuid id")
    seq = raw.seq if isinstance(raw.seq, int) and not isinstance(raw.seq, bool) else None
    if seq is not None and not 0 <= seq <= MAX_INT_PROP:
        seq = None
    entity_id = props.get(spec.entity_prop) if spec.entity_prop else None
    return LogRow(
        event_id=event_id or str(uuid.uuid4()),
        event_name=raw.event,
        event_version=spec.version,
        source_app=source_app,
        anon_id=anon_id,
        session_id=session_id,
        user_id=user_id,
        client_ts_ms=_clamp_ts(raw.ts, now_ms),
        seq=seq,
        page_key=_page_key(raw.page) if is_v2 else None,
        entity_type=spec.entity_type if entity_id else None,
        entity_id=entity_id,
        props=props,
    )


def normalize_batch(
    batch: RawBatch,
    *,
    now_ms: int,
    user_id: str | None = None,
) -> NormalizedBatch:
    """Turn a v1 or v2 beacon batch into validated rows plus counters. Never raises.

    v1 batch (no ``v``): the persistent legacy ``session_id`` becomes ``anon_id`` and the
    v2 ``session_id`` is NULL (v1 has no notion of a rotating session).
    v2 batch: ``anon``/``sid`` are used; when the client is in counts-only mode
    (opt-out / GPC) it omits them and the rows carry NULL identifiers.
    """
    out = NormalizedBatch()
    is_v2 = batch.v == ENVELOPE_VERSION
    if is_v2:
        anon_id = _uuid_or_none(batch.anon)
        session_id = _uuid_or_none(batch.sid)
    else:
        anon_id = _uuid_or_none(batch.session_id)
        session_id = None
    if batch.consent == "denied":
        # Defence in depth: a counts-only client should not send ids; drop them if it did.
        anon_id = None
        session_id = None
    source_app = _source_app(batch.app)
    seen: set[str] = set()
    for raw in batch.events[:MAX_EVENTS_PER_BATCH]:
        if raw.event in SERVER_RECORDED_EVENTS:
            out.skipped += 1
            continue
        if not _EVENT_RE.match(raw.event) or raw.event not in REGISTRY:
            out.rejected_unknown += 1
            continue
        try:
            row = normalize_event(
                raw,
                is_v2=is_v2,
                anon_id=anon_id,
                session_id=session_id,
                user_id=user_id,
                source_app=source_app,
                now_ms=now_ms,
            )
        except InvalidEvent:
            out.rejected_invalid += 1
            continue
        if row.event_id in seen:  # duplicate id within one batch
            continue
        seen.add(row.event_id)
        out.rows.append(row)
    out.rejected_invalid += max(0, len(batch.events) - MAX_EVENTS_PER_BATCH)
    return out
