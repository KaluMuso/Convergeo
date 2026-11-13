"""Founder decisions OD-6/OD-8: the search-term k-threshold counts DISTINCT sessions.

End to end on a live DB: search_query_log rows (with and without an anonymous analytics
session id) -> analytics_rollup_day -> admin build_search_demand.

* one session searching a term 5 times does NOT pass k = 5;
* 5 distinct sessions do;
* session-less rows (legacy / no-JS / counts-only) count as at most ONE session across
  the whole window, even when spread over 5 days.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta

import pytest
from app.routers.admin_analytics import build_search_demand, clear_analytics_cache
from app.services.analytics.rollup import rollup_day
from app.services.db import reset_pools
from tests.rls.conftest import PgConn

DAY = date(2026, 2, 10)
DAYS = [DAY + timedelta(days=n) for n in range(5)]
SESSION = "0d080000-0000-4000-8000-{:012d}"


def _cleanup(db: PgConn) -> None:
    db.run("DELETE FROM public.search_query_log WHERE normalized_term LIKE 'zzod8 %'")
    first, last = DAYS[0].isoformat(), DAYS[-1].isoformat()
    for table in ("analytics_daily_rollup", "analytics_search_daily", "analytics_rollup_runs"):
        db.run(f"DELETE FROM public.{table} WHERE day BETWEEN '{first}' AND '{last}'")


@pytest.fixture
def live(db: PgConn, monkeypatch: pytest.MonkeyPatch) -> Generator[PgConn, None, None]:
    monkeypatch.setenv("SUPABASE_DB_URL", db.dsn)
    _cleanup(db)
    clear_analytics_cache()
    yield db
    _cleanup(db)
    reset_pools()


def _search(term: str, day: date, session: int | None, minute: int) -> str:
    sid = f"'{SESSION.format(session)}'" if session is not None else "NULL"
    # 10:00 UTC = 12:00 Lusaka: well inside the reporting day.
    return (
        "INSERT INTO public.search_query_log "
        "(kind, term, normalized_term, zero_result, created_at, analytics_session_id) VALUES "
        f"('search', '{term}', '{term}', false, '{day.isoformat()} 10:{minute:02d}:00+00', {sid});"
    )


def _seed_and_roll(db: PgConn, statements: list[str]) -> None:
    result = db.run_script("BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;\n")
    assert result.ok, result.error
    for day in DAYS:
        assert rollup_day(day).ok


def _shown(out: dict[str, object]) -> list[str]:
    top = out["top_terms"]
    assert isinstance(top, list)
    return [t["normalized_term"] for t in top if str(t["normalized_term"]).startswith("zzod8")]


def test_one_session_five_searches_does_not_pass_k(live: PgConn) -> None:
    _seed_and_roll(live, [_search("zzod8 repeat", DAY, 1, m) for m in range(5)])
    row = live.run(
        "SELECT searches || '|' || sessions || '|' || unsessioned_searches "
        f"FROM public.analytics_search_daily WHERE day = '{DAY}' AND normalized_term = "
        "'zzod8 repeat'"
    )
    assert row.rows == ["5|1|0"]
    out = build_search_demand(DAYS[0], DAYS[-1])
    assert _shown(out) == []
    assert "zzod8 repeat" not in str(out)


def test_five_distinct_sessions_pass_k(live: PgConn) -> None:
    _seed_and_roll(live, [_search("zzod8 crowd", DAY, n, n) for n in range(5)])
    assert _shown(build_search_demand(DAYS[0], DAYS[-1])) == ["zzod8 crowd"]


def test_sessionless_rows_never_top_up_real_sessions(live: PgConn) -> None:
    # Session-less rows may belong to one of the 4 sessions' owners, so they add nothing
    # once real sessions exist: 4 sessions + 3 no-JS searches stays at 4 < k.
    statements = [_search("zzod8 mixed", DAY, n, n) for n in range(4)]
    statements += [_search("zzod8 mixed", DAY, None, 10 + n) for n in range(3)]
    statements += [_search("zzod8 five", DAY, n, n) for n in range(5)]
    statements += [_search("zzod8 five", DAY, None, 20)]
    _seed_and_roll(live, statements)
    row = live.run(
        "SELECT sessions || '|' || unsessioned_searches FROM public.analytics_search_daily "
        f"WHERE day = '{DAY}' AND normalized_term = 'zzod8 mixed'"
    )
    assert row.rows == ["4|3"]
    assert _shown(build_search_demand(DAYS[0], DAYS[-1])) == ["zzod8 five"]


def test_sessionless_rows_over_five_days_count_as_one_session(live: PgConn) -> None:
    _seed_and_roll(live, [_search("zzod8 nojs", day, None, 0) for day in DAYS])
    out = build_search_demand(DAYS[0], DAYS[-1])
    assert _shown(out) == []
    assert "zzod8 nojs" not in str(out)


def test_legacy_rows_with_null_sessions_are_conservative(live: PgConn) -> None:
    # Rows written before 20261113200300 carry sessions = NULL: never more than one.
    for day in DAYS:
        assert live.run(
            "INSERT INTO public.analytics_search_daily (day, normalized_term, searches, "
            f"zero_results) VALUES ('{day}', 'zzod8 legacy', 9, 0)"
        ).ok
    assert _shown(build_search_demand(DAYS[0], DAYS[-1])) == []


def test_pii_trim_nulls_session_id_after_30_days(live: PgConn) -> None:
    from app.services.analytics.search_log import trim_search_pii

    for age, n in (("40 days", 1), ("2 days", 2)):
        assert live.run(
            "INSERT INTO public.search_query_log (kind, term, normalized_term, created_at, "
            f"analytics_session_id) VALUES ('search', 'zzod8 trim{n}', 'zzod8 trim{n}', "
            f"now() - interval '{age}', '{SESSION.format(n)}')"
        ).ok
    assert trim_search_pii() >= 1
    rows = live.run(
        "SELECT normalized_term || '|' || (analytics_session_id IS NULL)::text "
        "FROM public.search_query_log WHERE normalized_term LIKE 'zzod8 trim%' ORDER BY 1"
    )
    assert rows.rows == ["zzod8 trim1|true", "zzod8 trim2|false"]
    assert trim_search_pii() == 0
