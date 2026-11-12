"""Convergeo Intelligence 1B-01: daily rollup on a live DB (exact values).

Seeds one fixed, past UTC day with known events and asserts the rollup exactly:
sessionisation by the 30-minute idle rule (29 min = same session, 31 min = new one),
bounce, active span, page/entry/product breakdowns, search demand and idempotency.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pytest
from app.services.analytics.rollup import rollup_day, run_rollup_tick
from app.services.db import reset_pools
from tests.rls.conftest import PgConn

DAY = date(2026, 1, 15)
EV = "1b01e000-0000-4000-8000-"
S1 = "1b01a000-0000-4000-8000-000000000001"
S2 = "1b01a000-0000-4000-8000-000000000002"
A1 = "1b01b000-0000-4000-8000-000000000001"
A2 = "1b01b000-0000-4000-8000-000000000002"
PRODUCT = "1b01c000-0000-4000-8000-000000000001"


def _cleanup(db: PgConn) -> None:
    db.run(f"DELETE FROM public.analytics_event_log WHERE event_id::text LIKE '{EV}%'")
    db.run("DELETE FROM public.search_query_log WHERE normalized_term LIKE 'zz1b01 %'")
    for table in ("analytics_daily_rollup", "analytics_search_daily", "analytics_rollup_runs"):
        db.run(f"DELETE FROM public.{table} WHERE day = '{DAY.isoformat()}'")


@pytest.fixture
def live(db: PgConn, monkeypatch: pytest.MonkeyPatch) -> Generator[PgConn, None, None]:
    monkeypatch.setenv("SUPABASE_DB_URL", db.dsn)
    _cleanup(db)
    yield db
    _cleanup(db)
    reset_pools()


def _event(
    n: int,
    clock: str,
    name: str,
    *,
    session: str | None,
    anon: str | None,
    page: str | None = None,
    entity: str | None = None,
    props: str = "{}",
) -> str:
    ts = f"'{DAY.isoformat()} {clock}+00'"
    sid = f"'{session}'" if session else "NULL"
    aid = f"'{anon}'" if anon else "NULL"
    pk = f"'{page}'" if page else "NULL"
    etype, eid = ("'product'", f"'{entity}'") if entity else ("NULL", "NULL")
    return (
        "INSERT INTO public.analytics_event_log (event_id, received_at, client_ts, event_name, "
        "source_app, anon_id, session_id, page_key, entity_type, entity_id, props) VALUES "
        f"('{EV}{n:012d}', {ts}, {ts}, '{name}', 'customer', {aid}, {sid}, {pk}, "
        f"{etype}, {eid}, '{props}'::jsonb);"
    )


def _seed(db: PgConn) -> None:
    statements = [
        # S1: one session — the 29-minute gap does NOT split it. 2 interactions, span 1741 s.
        _event(1, "10:00:00", "session_start", session=S1, anon=A1, page="home"),
        _event(2, "10:00:01", "page_view", session=S1, anon=A1, page="home"),
        _event(3, "10:29:01", "product_view", session=S1, anon=A1, page="pdp", entity=PRODUCT),
        # S2: the 31-minute gap DOES split it into two single-interaction (bounced) sessions.
        _event(4, "11:00:00", "page_view", session=S2, anon=A2, page="search"),
        _event(
            5,
            "11:31:00",
            "search",
            session=S2,
            anon=A2,
            page="search",
            props='{"zero_result": true, "result_count": 0}',
        ),
        # Counts-only (opt-out) row: an event, never a session.
        _event(6, "12:00:00", "page_view", session=None, anon=None, page="plp"),
    ]
    for n, (term, zero) in enumerate(
        [("zz1b01 phones", False), ("zz1b01 phones", True), ("zz1b01 phones", False)]
        + [("zz1b01 solar", True)]
    ):
        statements.append(
            "INSERT INTO public.search_query_log "
            "(kind, term, normalized_term, zero_result, created_at) VALUES "
            f"('search', '{term}', '{term}', {str(zero).lower()}, "
            f"'{DAY.isoformat()} 09:0{n}:00+00');"
        )
    # An 'ask' row is not search demand.
    statements.append(
        "INSERT INTO public.search_query_log (kind, term, normalized_term, created_at) VALUES "
        f"('ask', 'zz1b01 phones', 'zz1b01 phones', '{DAY.isoformat()} 09:30:00+00');"
    )
    result = db.run_script("BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;\n")
    assert result.ok, result.error


def _rollup(db: PgConn) -> dict[tuple[str, str, str], tuple[int, int]]:
    result = db.run(
        "SELECT metric || '|' || dim_key || '|' || dim_value || '|' || value || '|' || sample_n "
        f"FROM public.analytics_daily_rollup WHERE day = '{DAY.isoformat()}' "
        "AND metric NOT IN ('funnel_cart_adds') ORDER BY 1"
    )
    assert result.ok, result.error
    out: dict[tuple[str, str, str], tuple[int, int]] = {}
    for row in result.rows:
        metric, dim_key, dim_value, value, sample_n = row.split("|")
        out[(metric, dim_key, dim_value)] = (int(value), int(sample_n))
    return out


def _search(db: PgConn) -> list[str]:
    result = db.run(
        "SELECT normalized_term || '|' || searches || '|' || zero_results || '|' || "
        "coalesce(sessions::text, 'null') || '|' || unsessioned_searches "
        "FROM public.analytics_search_daily "
        f"WHERE day = '{DAY.isoformat()}' AND normalized_term LIKE 'zz1b01 %' ORDER BY 1"
    )
    assert result.ok, result.error
    return result.rows


def test_rollup_day_exact_values(live: PgConn) -> None:
    _seed(live)
    out = rollup_day(DAY)
    assert out.ok, out.error

    r = _rollup(live)
    assert r[("sessions", "", "")] == (3, 3)  # S1 + S2 split in two
    assert r[("bounced_sessions", "", "")] == (2, 3)
    assert r[("visitors", "", "")] == (2, 3)
    assert r[("active_span_seconds_total", "", "")] == (1741, 3)
    assert r[("active_span_seconds_p50", "", "")] == (0, 3)
    assert r[("searches", "", "")] == (1, 1)
    assert r[("zero_result_searches", "", "")] == (1, 1)
    assert r[("funnel_sessions", "step", "session")] == (3, 3)
    assert r[("funnel_sessions", "step", "search")] == (1, 3)
    assert r[("funnel_sessions", "step", "product_view")] == (1, 3)
    # Events include the counts-only row (sample_n = distinct sessions, NULL not counted).
    assert r[("events", "event_name", "page_view")] == (3, 2)
    assert r[("events", "event_name", "session_start")] == (1, 1)
    assert r[("page_views", "page_key", "home")] == (1, 1)
    assert r[("page_views", "page_key", "search")] == (1, 1)
    assert r[("page_views", "page_key", "plp")] == (1, 0)
    assert r[("session_entries", "page_key", "home")] == (1, 1)
    assert r[("session_entries", "page_key", "search")] == (2, 2)
    assert r[("product_views", "product_id", PRODUCT)] == (1, 1)

    # No session ids on these rows: 0 distinct sessions, every search is session-less.
    assert _search(live) == ["zz1b01 phones|3|1|0|3", "zz1b01 solar|1|1|0|1"]


def test_29_minutes_is_one_session_31_minutes_is_two(live: PgConn) -> None:
    statements = [
        _event(11, "15:00:00", "page_view", session=S1, anon=A1, page="home"),
        _event(12, "15:29:00", "page_view", session=S1, anon=A1, page="plp"),
        _event(21, "15:00:00", "page_view", session=S2, anon=A2, page="home"),
        _event(22, "15:31:00", "page_view", session=S2, anon=A2, page="plp"),
    ]
    assert live.run_script("BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;\n").ok
    assert rollup_day(DAY).ok
    r = _rollup(live)
    assert r[("sessions", "", "")] == (3, 3)
    assert r[("active_span_seconds_total", "", "")] == (29 * 60, 3)


def test_rollup_is_idempotent(live: PgConn) -> None:
    _seed(live)
    first = rollup_day(DAY)
    snapshot_rollup, snapshot_search = _rollup(live), _search(live)
    second = rollup_day(DAY)
    assert first.ok and second.ok and first.rows == second.rows
    assert _rollup(live) == snapshot_rollup
    assert _search(live) == snapshot_search
    runs = live.run(
        "SELECT status || ':' || rows FROM public.analytics_rollup_runs "
        f"WHERE day = '{DAY.isoformat()}' ORDER BY started_at"
    )
    assert runs.rows == [f"ok:{first.rows}", f"ok:{first.rows}"]


def test_explicit_day_tick_and_future_day_rejected(live: PgConn) -> None:
    _seed(live)
    tick = run_rollup_tick(day=DAY).as_dict()
    assert tick["ok"] is True
    future = live.run("SELECT public.analytics_rollup_day(current_date + 1)")
    assert not future.ok and "future" in (future.error or "")


def test_rollup_function_is_service_role_only(live: PgConn) -> None:
    acl = live.run(
        "SELECT has_function_privilege('authenticated', "
        "'public.analytics_rollup_day(date, integer)', 'EXECUTE')::text || ',' || "
        "has_function_privilege('anon', 'public.analytics_rollup_day(date, integer)', "
        "'EXECUTE')::text || ',' || has_function_privilege('service_role', "
        "'public.analytics_rollup_day(date, integer)', 'EXECUTE')::text"
    )
    assert acl.rows == ["false,false,true"]
    for table in ("analytics_daily_rollup", "analytics_search_daily", "analytics_rollup_runs"):
        rls = live.run(
            "SELECT relrowsecurity::text || ',' || relforcerowsecurity::text FROM pg_class "
            f"WHERE oid = 'public.{table}'::regclass"
        )
        assert rls.rows == ["true,true"], table
        anon = live.run(f"SELECT has_table_privilege('anon', 'public.{table}', 'SELECT')::text")
        assert anon.rows == ["false"], table
