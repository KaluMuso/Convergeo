"""Task 2 — public analytics beacon ingest (the server sink for the client's
``navigator.sendBeacon`` batch).

Consumes ``{session_id?, events:[{event, props, ts?}]}`` and writes the
client-authoritative events (the PDP ``product_view``, which has no dedicated
server stream) into ``analytics_events`` via ``events.record_event`` — which
enforces anonymization server-side (rejects raw-PII prop keys and non-integer
money). This is a **server operational** endpoint: writes are anonymized and
**independent of GA consent** (consent gates only the client's GA4 mirror).

Hardening: public (unauthenticated) but rate-limited per IP, hard-capped per
batch, and per-event props size-bounded. Fire-and-forget per event — a bad
event is skipped, never 500s the batch. When a bearer token is present the
events are stitched to that ``user_id`` (the row then links ``session_id`` ↔
``user_id`` — the forward identity stitch; no historical backfill).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import timedelta
from typing import Any, Final

from app.core.auth import get_current_user
from app.core.inproc_ratelimit import InProcessRateLimiter
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.errors import AppError
from app.services.analytics.client_key import trusted_client_key
from app.services.analytics.envelope import RawBatch, normalize_batch
from app.services.analytics.events import record_event
from app.services.analytics.flags import collect_v2_enabled_async
from app.services.analytics.writer import get_writer
from app.settings import get_settings
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# The client batches at most MAX_BATCH (=20) events per sendBeacon; a larger batch
# is malformed/abusive.
MAX_EVENTS_PER_BATCH = 20
# Generous per-IP cap — a beacon fires roughly once per page-session (on tab-hide).
COLLECT_RATE_LIMIT_PER_MINUTE = 120
# Bound a single event's serialized props so a giant payload cannot be persisted.
MAX_PROPS_CHARS = 4_000

# ``analytics_events`` is the superset sink for events WITHOUT a dedicated server
# stream. The funnel (cart_add/checkout_start/payment_start/order_placed) and search
# are already recorded authoritatively server-side (Task 1), so persisting them here
# too would double-count them in ``analytics_event_stream``. Only genuinely
# client-authoritative events (the PDP ``product_view``) are persisted; every other
# known/unknown event is accepted-but-skipped.
SERVER_PERSIST_EVENTS: frozenset[str] = frozenset({"product_view"})

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


class BeaconEvent(BaseModel):
    # Lenient: ignore unknown keys so client/server version skew never drops a batch.
    model_config = ConfigDict(extra="ignore")

    event: str = Field(min_length=1, max_length=64)
    props: dict[str, Any] = Field(default_factory=dict)
    ts: int | None = None


class CollectRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str | None = None
    events: list[BeaconEvent] = Field(default_factory=list)


class CollectResponse(BaseModel):
    accepted: int
    skipped: int
    rejected: int


def _valid_uuid_or_none(value: str | None) -> str | None:
    """Accept only a well-formed UUID; drop anything else (never reject the batch)."""
    if value is None or not _UUID_RE.match(value):
        return None
    return value


async def _optional_user_id(request: Request) -> str | None:
    """Resolve the caller's user id from a bearer token if present; else anonymous."""
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        user = await get_current_user(request, get_settings())
    except AppError:
        return None
    return user.id


def _enforce_rate_limit(request: Request) -> None:
    """Per-IP cap. Fail-open: a rate-limiter outage must not drop analytics."""
    try:
        allowed, retry_after = bump_rate_counter(
            scope="analytics_collect_ip",
            key=get_client_ip(request),
            window=timedelta(minutes=1),
            limit=COLLECT_RATE_LIMIT_PER_MINUTE,
        )
    except Exception:  # noqa: BLE001 — analytics ingest is non-critical; allow on failure.
        logger.debug("analytics collect rate-limit check failed (allowing)", exc_info=True)
        return
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="analytics.rate_limited",
            message="Too many analytics beacons",
        )


# ---------------------------------------------------------------------------
# analytics_v2 collect path (Convergeo Intelligence 1A-03, plan §R-C/§R-D).
# Active only when feature flag ``analytics_v2_collect`` is ON; otherwise the v1 path
# below runs exactly as before. The v2 path does NO DB I/O on the request: in-process
# rate limit -> pure validation -> non-blocking hand-off to the bounded writer.
# ---------------------------------------------------------------------------

# Per WORKER (the API runs 2 workers, so effective ceilings are 2x these figures).
V2_GLOBAL_BATCHES_PER_SEC: Final = 40.0
V2_GLOBAL_BURST: Final = 80
# Generous per key: many real visitors share one key (Vercel egress / CF edge IPs).
V2_KEY_BATCHES_PER_MIN: Final = 240
V2_KEY_BURST: Final = 60

_v2_limiter = InProcessRateLimiter(
    global_rate_per_sec=V2_GLOBAL_BATCHES_PER_SEC,
    global_burst=V2_GLOBAL_BURST,
    key_rate_per_sec=V2_KEY_BATCHES_PER_MIN / 60.0,
    key_burst=V2_KEY_BURST,
)

_INGEST_COUNTER_KEYS: Final = (
    "batches",
    "accepted",
    "skipped",
    "rejected_invalid",
    "rejected_unknown",
    "rejected_malformed",
    "dropped_rate_limited",
    "dropped_overload",
)
_ingest_counters: dict[str, int] = dict.fromkeys(_INGEST_COUNTER_KEYS, 0)
_ingest_lock = threading.Lock()


def _count(**deltas: int) -> None:
    with _ingest_lock:
        for key, delta in deltas.items():
            _ingest_counters[key] = _ingest_counters.get(key, 0) + delta


def ingest_counters() -> dict[str, int]:
    """Per-worker v2 ingest counters (served by /internal/analytics/ingest-stats)."""
    with _ingest_lock:
        return dict(_ingest_counters)


def v2_limiter_keys() -> int:
    return _v2_limiter.tracked_keys()


def reset_v2_state_for_tests(limiter: InProcessRateLimiter | None = None) -> None:
    global _v2_limiter
    with _ingest_lock:
        for key in _INGEST_COUNTER_KEYS:
            _ingest_counters[key] = 0
    if limiter is not None:
        _v2_limiter = limiter


async def _collect_v2(request: Request) -> CollectResponse:
    if not _v2_limiter.allow(trusted_client_key(request)):
        _count(dropped_rate_limited=1)
        raise_rate_limited(
            retry_after=1,
            message_key="analytics.rate_limited",
            message="Too many analytics beacons",
        )
    try:
        # FastAPI already read (and cached) the body to build the v1 model; re-parse
        # it leniently as the v1/v2 superset so the v2 fields are not discarded.
        batch = RawBatch.model_validate(await request.json())
    except (ValidationError, ValueError):
        _count(batches=1, rejected_malformed=1)
        return CollectResponse(accepted=0, skipped=0, rejected=0)

    # Beacons cannot carry a bearer token (sendBeacon has no headers), so v2 never
    # resolves a user here; the sign-in link is the separate identify call (1A-08).
    normalized = normalize_batch(batch, now_ms=int(time.time() * 1000))
    accepted = len(normalized.rows)
    if accepted and not get_writer().submit_rows(normalized.rows):
        _count(dropped_overload=accepted)
        accepted = 0
    _count(
        batches=1,
        accepted=accepted,
        skipped=normalized.skipped,
        rejected_invalid=normalized.rejected_invalid,
        rejected_unknown=normalized.rejected_unknown,
    )
    return CollectResponse(
        accepted=accepted,
        skipped=normalized.skipped,
        rejected=normalized.rejected,
    )


@router.post("/collect", response_model=CollectResponse)
async def collect(request: Request, body: CollectRequest) -> CollectResponse:
    if len(body.events) > MAX_EVENTS_PER_BATCH:
        raise AppError(
            code="analytics.batch_too_large",
            message="Too many events in one beacon",
            http_status=413,
            details={"max": MAX_EVENTS_PER_BATCH},
        )

    if await collect_v2_enabled_async():
        return await _collect_v2(request)

    # ----- v1 path (flag OFF): unchanged -----
    _enforce_rate_limit(request)

    session_id = _valid_uuid_or_none(body.session_id)
    user_id = await _optional_user_id(request)

    accepted = 0
    skipped = 0
    rejected = 0
    for ev in body.events:
        if ev.event not in SERVER_PERSIST_EVENTS:
            # Already recorded authoritatively server-side (funnel/search), or unknown —
            # accept the beacon but do not double-write it into analytics_events.
            skipped += 1
            continue
        if len(json.dumps(ev.props, separators=(",", ":"), default=str)) > MAX_PROPS_CHARS:
            rejected += 1
            continue
        try:
            record_event(
                event_type=ev.event,
                session_id=session_id,
                user_id=user_id,
                props=ev.props,
            )
            accepted += 1
        except (ValueError, TypeError):
            # Failed anonymization/validation (raw PII, non-int money, bad shape) — skip.
            rejected += 1
        except RuntimeError:
            # DB write failed — fire-and-forget: never 500 the batch.
            logger.debug("analytics collect record_event failed (swallowed)", exc_info=True)
            rejected += 1

    return CollectResponse(accepted=accepted, skipped=skipped, rejected=rejected)
