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
from datetime import timedelta
from typing import Any

from app.core.auth import get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.errors import AppError
from app.services.analytics.events import record_event
from app.settings import get_settings
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

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


@router.post("/collect", response_model=CollectResponse)
async def collect(request: Request, body: CollectRequest) -> CollectResponse:
    if len(body.events) > MAX_EVENTS_PER_BATCH:
        raise AppError(
            code="analytics.batch_too_large",
            message="Too many events in one beacon",
            http_status=413,
            details={"max": MAX_EVENTS_PER_BATCH},
        )

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
