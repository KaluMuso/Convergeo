"""Convergeo Intelligence 1A-03: the bounded writer against a live, migrated database.

Proves the SQL the writer emits: idempotent ingest on ``event_id`` (a re-sent batch
inserts nothing), and the v1 ``product_view`` projection into ``analytics_events``
with exactly the v1 row shape (only for newly inserted rows).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from app.services.analytics.envelope import LogRow
from app.services.analytics.writer import AnalyticsWriter
from app.services.db import reset_pools
from tests.rls.conftest import PgConn

ANON = "a0a0a0a0-a0a0-4a0a-8a0a-a0a0a0a0a0a0"
PRODUCT = "c0c0c0c0-c0c0-4c0c-8c0c-c0c0c0c0c0c0"


def _row(n: int, name: str = "product_view") -> LogRow:
    props = {"product_id": PRODUCT} if name == "product_view" else {}
    return LogRow(
        event_id=f"f0f0f0f0-f0f0-4f0f-8f0f-{n:012d}",
        event_name=name,
        event_version=1,
        source_app="customer",
        anon_id=ANON,
        session_id=None,
        user_id=None,
        client_ts_ms=None,
        seq=n,
        page_key="pdp",
        entity_type="product" if name == "product_view" else None,
        entity_id=PRODUCT if name == "product_view" else None,
        props=props,
    )


def _cleanup(db: PgConn) -> None:
    db.run("DELETE FROM public.analytics_event_log WHERE event_id::text LIKE 'f0f0f0f0-%'")
    db.run(f"DELETE FROM public.analytics_events WHERE session_id = '{ANON}'")


@pytest.fixture
def live_writer(
    db: PgConn, monkeypatch: pytest.MonkeyPatch
) -> Generator[AnalyticsWriter, None, None]:
    monkeypatch.setenv("SUPABASE_DB_URL", db.dsn)
    _cleanup(db)
    yield AnalyticsWriter(autostart=False)
    _cleanup(db)
    reset_pools()


def test_ingest_is_idempotent_and_projects_v1(db: PgConn, live_writer: AnalyticsWriter) -> None:
    batch = [_row(1), _row(2), _row(3, "page_view")]
    live_writer.submit_rows(batch)
    live_writer.drain_once()
    first = live_writer.stats()
    assert first["errors"] == 0, first
    assert first["inserted_rows"] == 3 and first["projected_v1_rows"] == 2

    # Beacon retry: the same event ids again → nothing new, nothing re-projected.
    live_writer.submit_rows(batch)
    live_writer.drain_once()
    second = live_writer.stats()
    assert second["inserted_rows"] == 3 and second["deduped_rows"] == 3
    assert second["projected_v1_rows"] == 2

    logged = db.run(
        "SELECT count(*)::text FROM public.analytics_event_log "
        "WHERE event_id::text LIKE 'f0f0f0f0-%'"
    )
    assert logged.rows == ["3"]
    # v1 shape: event_type, session_id = legacy visitor id, no entity columns, same props.
    v1 = db.run(
        "SELECT event_type || '|' || coalesce(entity_type, '-') || '|' || props::text "
        f"FROM public.analytics_events WHERE session_id = '{ANON}'"
    )
    assert v1.ok, v1.error
    assert v1.rows == [f'product_view|-|{{"product_id": "{PRODUCT}"}}'] * 2
