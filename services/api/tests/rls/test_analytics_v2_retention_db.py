"""Convergeo Intelligence 1A-07: v2 retention sweep + storage report on a live DB."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from app.services.analytics.retention import analytics_storage_report, sweep_v2_retention
from app.services.db import reset_pools
from tests.rls.conftest import PgConn

OLD = "a7a7a7a7-a7a7-4a7a-8a7a-"
SESSION = "b7b7b7b7-b7b7-4b7b-8b7b-b7b7b7b7b7b7"


def _cleanup(db: PgConn) -> None:
    db.run(f"DELETE FROM public.analytics_event_log WHERE event_id::text LIKE '{OLD}%'")
    db.run(f"DELETE FROM public.listing_view_dedup WHERE session_id = '{SESSION}'")
    db.run("DELETE FROM public.search_query_log WHERE normalized_term LIKE 'zz-retention-%'")


@pytest.fixture
def live(db: PgConn, monkeypatch: pytest.MonkeyPatch) -> Generator[PgConn, None, None]:
    monkeypatch.setenv("SUPABASE_DB_URL", db.dsn)
    _cleanup(db)
    yield db
    _cleanup(db)
    reset_pools()


def _seed(db: PgConn) -> None:
    listing = db.run("SELECT id::text FROM public.vendor_listings ORDER BY id LIMIT 1")
    assert listing.ok and listing.rows, listing.error
    lid = listing.rows[0]
    statements = []
    # 7 expired raw events + 2 fresh ones
    for n in range(9):
        age = "40 days" if n < 7 else "1 day"
        statements.append(
            "INSERT INTO public.analytics_event_log "
            "(event_id, received_at, event_name, source_app) VALUES "
            f"('{OLD}{n:012d}', now() - interval '{age}', 'page_view', 'customer');"
        )
    for days, kind in ((10, "impression"), (3, "impression"), (0, "pdp_view")):
        statements.append(
            "INSERT INTO public.listing_view_dedup (session_id, listing_id, day, view_kind) "
            f"VALUES ('{SESSION}', '{lid}', current_date - {days}, '{kind}');"
        )
    for age, n in (("45 days", 1), ("2 days", 2)):
        statements.append(
            "INSERT INTO public.search_query_log (kind, term, normalized_term, created_at) "
            f"VALUES ('search', 'ZZ-Retention-{n} Raw', 'zz-retention-{n} raw', "
            f"now() - interval '{age}');"
        )
    result = db.run_script("BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;\n")
    assert result.ok, result.error


def test_v2_sweep_is_batched_bounded_and_idempotent(live: PgConn) -> None:
    _seed(live)
    first = sweep_v2_retention(batch_size=3, max_batches=50)
    assert first.complete
    assert first.event_log_deleted >= 7
    assert first.listing_dedup_purged >= 2
    assert first.search_terms_scrubbed >= 1

    remaining = live.run(
        f"SELECT count(*)::text FROM public.analytics_event_log WHERE event_id::text LIKE '{OLD}%'"
    )
    assert remaining.rows == ["2"]
    dedup = live.run(
        f"SELECT view_kind FROM public.listing_view_dedup WHERE session_id = '{SESSION}'"
    )
    assert dedup.rows == ["pdp_view"]  # today's key survives, 3- and 10-day-old purged
    terms = live.run(
        "SELECT term FROM public.search_query_log "
        "WHERE normalized_term LIKE 'zz-retention-%' ORDER BY normalized_term"
    )
    assert terms.rows == ["zz-retention-1 raw", "ZZ-Retention-2 Raw"]

    second = sweep_v2_retention(batch_size=3, max_batches=50)
    assert (second.event_log_deleted, second.search_terms_scrubbed) == (0, 0)


def test_max_batches_reports_incomplete(live: PgConn) -> None:
    _seed(live)
    result = sweep_v2_retention(batch_size=2, max_batches=1)
    assert result.complete is False
    assert result.event_log_deleted == 2


def test_storage_report(live: PgConn) -> None:
    report = analytics_storage_report()
    tables = report["tables"]
    assert isinstance(tables, dict)
    assert "analytics_event_log" in tables and "listing_view_dedup" in tables
    assert isinstance(report["database_bytes"], int) and report["database_bytes"] > 0
    # FC-1: Supabase Free (500 MB), alert at 70% = 350 MB.
    assert report["quota_bytes"] == 500 * 1024 * 1024
    assert report["alert_threshold_bytes"] == 350 * 1024 * 1024
    assert report["alert"] is (report["database_bytes"] >= 350 * 1024 * 1024)
