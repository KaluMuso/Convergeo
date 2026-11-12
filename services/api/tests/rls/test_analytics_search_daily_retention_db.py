"""Founder decision OD-10: analytics_search_daily retention on a live DB.

Below-k terms are deleted after 30 days; terms that met k (distinct sessions, OD-8) in
their calendar month are kept for 13 whole months. Batched and idempotent. "Today" is the
Lusaka reporting day 2026-11-12, so the 30-day cutoff is 2026-10-13 and the 13-month
cutoff is 2025-10-01 (months before October 2025 are dropped).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from app.services.analytics.retention import purge_search_daily, sweep_v2_retention
from app.services.db import reset_pools
from tests.rls.conftest import PgConn

NOW = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)  # 10:00 CAT

# (day, term, sessions (None = legacy NULL), unsessioned_searches)
ROWS: list[tuple[str, str, int | None, int]] = [
    ("2026-10-05", "zzod10 rare", 1, 0),  # below k, 38 days old -> deleted
    ("2026-10-20", "zzod10 rare", 1, 0),  # below k, 23 days old -> kept (< 30 days)
    *[(f"2026-09-0{d}", "zzod10 popular", 1, 0) for d in range(1, 6)],  # 5 sessions in Sep
    *[(f"2026-09-0{d}", "zzod10 nojs", 0, 3) for d in range(1, 6)],  # session-less: 1
    *[(f"2026-09-1{d}", "zzod10 legacy", None, 0) for d in range(1, 6)],  # NULL: 1
    ("2025-09-15", "zzod10 popular", 9, 0),  # met k, month older than 13 months -> deleted
    ("2025-10-15", "zzod10 popular", 9, 0),  # met k, inside 13 months -> kept
]


def _cleanup(db: PgConn) -> None:
    db.run("DELETE FROM public.analytics_search_daily WHERE normalized_term LIKE 'zzod10 %'")


@pytest.fixture
def live(db: PgConn, monkeypatch: pytest.MonkeyPatch) -> Generator[PgConn, None, None]:
    monkeypatch.setenv("SUPABASE_DB_URL", db.dsn)
    _cleanup(db)
    values = ", ".join(
        f"('{day}', '{term}', 5, 0, {'NULL' if s is None else s}, {u})" for day, term, s, u in ROWS
    )
    assert db.run(
        "INSERT INTO public.analytics_search_daily "
        "(day, normalized_term, searches, zero_results, sessions, unsessioned_searches) "
        f"VALUES {values}"
    ).ok
    yield db
    _cleanup(db)
    reset_pools()


def _remaining(db: PgConn) -> list[str]:
    result = db.run(
        "SELECT day::text || ' ' || normalized_term FROM public.analytics_search_daily "
        "WHERE normalized_term LIKE 'zzod10 %' ORDER BY day, normalized_term"
    )
    assert result.ok, result.error
    return result.rows


EXPECTED = [
    "2025-10-15 zzod10 popular",
    *[f"2026-09-0{d} zzod10 popular" for d in range(1, 6)],
    "2026-10-20 zzod10 rare",
]


def test_below_k_after_30_days_and_met_k_after_13_months(live: PgConn) -> None:
    purged, complete = purge_search_daily(NOW, batch_size=3, max_batches=50)
    assert complete
    assert purged >= 12  # 1 rare + 5 nojs + 5 legacy + 1 old popular
    assert _remaining(live) == EXPECTED


def test_purge_is_idempotent(live: PgConn) -> None:
    purge_search_daily(NOW, batch_size=1000, max_batches=5)
    assert purge_search_daily(NOW, batch_size=1000, max_batches=5) == (0, True)
    assert _remaining(live) == EXPECTED


def test_purge_is_batched_and_reports_incomplete(live: PgConn) -> None:
    purged, complete = purge_search_daily(NOW, batch_size=2, max_batches=1)
    assert (purged, complete) == (2, False)
    assert len(_remaining(live)) == len(ROWS) - 2


def test_v2_sweep_includes_search_daily_purge(live: PgConn) -> None:
    result = sweep_v2_retention(NOW, batch_size=500, max_batches=50)
    assert result.complete and result.search_daily_purged >= 12
    assert _remaining(live) == EXPECTED


def test_purge_function_is_service_role_only(live: PgConn) -> None:
    sig = "'public.analytics_search_daily_purge(date, integer)'"
    acl = live.run(
        f"SELECT has_function_privilege('authenticated', {sig}, 'EXECUTE')::text || ',' || "
        f"has_function_privilege('anon', {sig}, 'EXECUTE')::text || ',' || "
        f"has_function_privilege('service_role', {sig}, 'EXECUTE')::text"
    )
    assert acl.rows == ["false,false,true"]
    bad = live.run("SELECT public.analytics_search_daily_purge('2026-11-12', 0)")
    assert not bad.ok and "limit out of range" in (bad.error or "")
