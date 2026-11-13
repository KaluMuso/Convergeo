"""analytics_v2 sign-in linking (Convergeo Intelligence 1A-08, plan §R-B, OD-2).

``analytics_session_links(session_id pk, user_id, linked_at)`` ties an anonymous v2
session to a customer once they sign in. Raw events are never back-filled; rollups join
this table. Rows are hard-deleted after :data:`LINK_RETENTION_DAYS` (same window as the
raw event log) by the rollups-gated retention tick, and cascade on account deletion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.analytics.retention import V2_BATCH_SIZE, V2_MAX_BATCHES, _batched
from app.services.orders.audit import run_sql_script, sql_literal

#: Links are deleted this many days after ``linked_at`` (founder decision OD-2: 30 d).
LINK_RETENTION_DAYS = 30


def link_session(*, user_id: str, session_id: str) -> bool:
    """Idempotently link ``session_id`` to ``user_id``.

    The first account to claim a session keeps it. Returns True when the link now exists
    for this user (newly written or already present), False when the session belongs to a
    different account. ``user_id``/``session_id`` must already be validated UUIDs.
    """
    result = run_sql_script(
        f"""
INSERT INTO public.analytics_session_links (session_id, user_id)
VALUES ({sql_literal(session_id)}::uuid, {sql_literal(user_id)}::uuid)
ON CONFLICT (session_id) DO UPDATE SET session_id = EXCLUDED.session_id
  WHERE public.analytics_session_links.user_id = EXCLUDED.user_id
RETURNING 1;
"""
    )
    if not result.ok:
        raise RuntimeError(f"analytics session link failed: {result.error}")
    return bool(result.rows)


def purge_expired_links(
    now: datetime | None = None,
    *,
    batch_size: int = V2_BATCH_SIZE,
    max_batches: int = V2_MAX_BATCHES,
) -> tuple[int, bool]:
    """Delete links older than the retention window. Returns ``(deleted, complete)``.

    Batched and idempotent; the caller owns the ``analytics_v2_rollups`` gate.
    """
    cutoff = (now or datetime.now(UTC)) - timedelta(days=LINK_RETENTION_DAYS)
    return _batched(
        f"""
  DELETE FROM public.analytics_session_links
  WHERE ctid IN (
    SELECT ctid FROM public.analytics_session_links
    WHERE linked_at < {sql_literal(cutoff.isoformat())}::timestamptz
    LIMIT {{batch}}
  )""",
        batch_size=batch_size,
        max_batches=max_batches,
    )
