"""M18-P07 — scoped internal endpoints for WAHA intake operations (D35).

n8n schedules; the API decides. Every endpoint here is called by a workflow that
holds only a shared token — **never** a Supabase service-role key and never a
direct database connection (D35 §5). The logic lives in this module so an
operator can read what the automation actually does without parsing workflow
JSON.

Four concerns, deliberately separate endpoints rather than one "tick":

* ``/expire-sessions`` — stale intake sessions past ``expires_at`` move to
  ``expired`` through P01's **guarded transition**, so the audit trail records
  each one. Terminal sessions are skipped, not force-updated.
* ``/purge-messages`` — D35 §12 retention. Nulls ``raw_excerpt`` past
  ``purge_after`` while **keeping** the message id, kind and timestamps, so
  dispositions stay auditable after the content is minimised.
* ``/purge-links`` — expired, never-redeemed review links are deleted. A
  redeemed link is kept: it is evidence that a vendor opened a session.
* ``/metrics`` — read-only disposition counts for the operator digest.

**Idempotency.** Every sweep is naturally idempotent: it selects only rows that
still need work and re-running finds none. `/expire-sessions` additionally
tolerates losing a transition race — a session another writer already moved is
counted as skipped, not an error.

Nothing here sends a WhatsApp message. Vendor-facing status notifications go
through the **Lane 1 outbox** from M18-P06; this module has no outbound path at
all, which keeps the inbound-only invariant true for the operational lane too.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any, Final, Protocol

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.intake import state_machine
from fastapi import APIRouter, Depends, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/intake", tags=["internal-intake"])

_INTERNAL_TOKEN_ENV: Final = "INTERNAL_INTAKE_TOKEN"
_DEFAULT_INTERNAL_TOKEN: Final = "dev-internal-intake"

SESSIONS_TABLE: Final = "intake_sessions"
MESSAGES_TABLE: Final = "intake_messages"
LINKS_TABLE: Final = "intake_deep_links"
EVENTS_TABLE: Final = "intake_events"

# Bounded per tick so a backlog degrades into several runs rather than one
# request that times out and never makes progress.
BATCH_LIMIT: Final = 200


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _expected_internal_token() -> str:
    try:
        return resolve_internal_token(
            _INTERNAL_TOKEN_ENV,
            dev_default=_DEFAULT_INTERNAL_TOKEN,
        )
    except InternalTokenMisconfigured as exc:
        raise AppError(
            code="configuration_error",
            message=str(exc),
            http_status=503,
        ) from exc


async def require_internal_intake_token(request: Request) -> None:
    """Guard the intake ops endpoints — not callable without the shared token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal intake token",
            http_status=401,
        )


def _table(service_client: ServiceRoleClient, name: str) -> Any:
    return service_client.client.table(name)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# --- Sweeps -----------------------------------------------------------------
def sweep_expired_sessions(service_client: ServiceRoleClient) -> dict[str, Any]:
    """Expire sessions past ``expires_at`` via the guarded transition.

    Uses P01's ``state_machine.transition`` rather than a bulk UPDATE so each
    expiry lands in ``intake_events``. A session another writer moved first
    raises a conflict, which is counted as ``skipped`` — the desired end state
    was reached either way.
    """
    now = _now_iso()
    candidates = _rows(
        _table(service_client, SESSIONS_TABLE)
        .select("id, status, expires_at")
        .in_("status", sorted(state_machine.SESSION_STATUSES - state_machine.TERMINAL_STATUSES))
        .lt("expires_at", now)
        .limit(BATCH_LIMIT)
        .execute()
    )

    expired = 0
    skipped = 0
    for row in candidates:
        try:
            state_machine.expire(service_client, session_id=str(row["id"]))
            expired += 1
        except AppError:
            # Lost the race, or the row moved to a terminal state between the
            # select and the update. Not an error for a sweep.
            skipped += 1

    return {"scanned": len(candidates), "expired": expired, "skipped": skipped}


def sweep_purge_messages(service_client: ServiceRoleClient) -> dict[str, Any]:
    """D35 §12: minimise raw content past its retention instant.

    Only ``raw_excerpt`` is cleared. The row itself — provider message id, kind,
    received_at — survives, because those are what make the audit trail and the
    replay-idempotency guarantee meaningful. Deleting the row would silently
    re-open a message to reprocessing.
    """
    now = _now_iso()
    candidates = _rows(
        _table(service_client, MESSAGES_TABLE)
        .select("id")
        .lt("purge_after", now)
        .not_.is_("raw_excerpt", "null")
        .limit(BATCH_LIMIT)
        .execute()
    )

    purged = 0
    for row in candidates:
        updated = _rows(
            _table(service_client, MESSAGES_TABLE)
            .update({"raw_excerpt": None})
            .eq("id", row["id"])
            .execute()
        )
        purged += 1 if updated else 0

    return {"scanned": len(candidates), "purged": purged}


def sweep_expired_links(service_client: ServiceRoleClient) -> dict[str, Any]:
    """Delete expired links that were never redeemed.

    A **redeemed** link is deliberately kept: it records that a vendor actually
    opened the session, which matters during an incident review. An unredeemed
    expired link records nothing and is only a hash taking up space.
    """
    now = _now_iso()
    candidates = _rows(
        _table(service_client, LINKS_TABLE)
        .select("id")
        .lt("expires_at", now)
        .is_("redeemed_at", "null")
        .limit(BATCH_LIMIT)
        .execute()
    )

    deleted = 0
    for row in candidates:
        _table(service_client, LINKS_TABLE).delete().eq("id", row["id"]).is_(
            "redeemed_at", "null"
        ).execute()
        deleted += 1

    return {"scanned": len(candidates), "deleted": deleted}


def collect_metrics(service_client: ServiceRoleClient) -> dict[str, Any]:
    """Read-only operational counters for the digest. Never mutates anything."""
    dispositions: dict[str, int] = {name: 0 for name in sorted(state_machine.DISPOSITIONS)}
    for row in _rows(
        _table(service_client, EVENTS_TABLE)
        .select("disposition")
        .eq("kind", "ingestion")
        .execute()
    ):
        name = row.get("disposition")
        if isinstance(name, str) and name in dispositions:
            dispositions[name] += 1

    statuses: dict[str, int] = {name: 0 for name in sorted(state_machine.SESSION_STATUSES)}
    for row in _rows(
        _table(service_client, SESSIONS_TABLE).select("status, listing_id").execute()
    ):
        name = row.get("status")
        if isinstance(name, str) and name in statuses:
            statuses[name] += 1

    listings = sum(
        1
        for row in _rows(_table(service_client, SESSIONS_TABLE).select("listing_id").execute())
        if row.get("listing_id")
    )

    return {
        "dispositions": dispositions,
        "session_statuses": statuses,
        "listings_created": listings,
    }


# --- Routes -----------------------------------------------------------------
@router.post("/expire-sessions", dependencies=[Depends(require_internal_intake_token)])
async def expire_sessions_tick(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return sweep_expired_sessions(service_client)


@router.post("/purge-messages", dependencies=[Depends(require_internal_intake_token)])
async def purge_messages_tick(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return sweep_purge_messages(service_client)


@router.post("/purge-links", dependencies=[Depends(require_internal_intake_token)])
async def purge_links_tick(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return sweep_expired_links(service_client)


@router.get("/metrics", dependencies=[Depends(require_internal_intake_token)])
async def intake_metrics(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return collect_metrics(service_client)
