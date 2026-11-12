"""Convergeo Intelligence 1B-04: admin analytics builders on a live DB.

* k-threshold: a term seen in 4 searches is hidden (folded into "other"), 5 is shown.
* raw terms never leave the DB: the legacy search-insights reads return the normalized
  term as ``sample_term``.
* overview commercial numbers equal ``analytics_commercial_daily`` (authoritative).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pytest
from app.routers.admin_analytics import build_overview, build_search_demand
from app.services.analytics.metrics import commercial_summary
from app.services.analytics.search_log import top_terms
from app.services.db import reset_pools
from tests.rls.conftest import PgConn

DAY = date(2026, 1, 20)


def _cleanup(db: PgConn) -> None:
    db.run(f"DELETE FROM public.analytics_search_daily WHERE day = '{DAY.isoformat()}'")
    db.run(f"DELETE FROM public.analytics_daily_rollup WHERE day = '{DAY.isoformat()}'")
    db.run("DELETE FROM public.search_query_log WHERE normalized_term LIKE 'zz1b04 %'")


@pytest.fixture
def live(db: PgConn, monkeypatch: pytest.MonkeyPatch) -> Generator[PgConn, None, None]:
    monkeypatch.setenv("SUPABASE_DB_URL", db.dsn)
    _cleanup(db)
    yield db
    _cleanup(db)
    reset_pools()


def test_k_threshold_hides_four_shows_five(live: PgConn) -> None:
    rows = [("zz1b04 four", 4, 4), ("zz1b04 five", 5, 5), ("zz1b04 big", 30, 1)]
    for term, searches, zero in rows:
        assert live.run(
            "INSERT INTO public.analytics_search_daily (day, normalized_term, searches, "
            f"zero_results) VALUES ('{DAY.isoformat()}', '{term}', {searches}, {zero})"
        ).ok
    out = build_search_demand(DAY, DAY)
    terms = [t["normalized_term"] for t in out["top_terms"]]
    assert terms == ["zz1b04 big", "zz1b04 five"]
    assert "zz1b04 four" not in str(out)
    assert out["zero_result_terms"] == [
        {"normalized_term": "zz1b04 five", "searches": 5, "zero_results": 5}
    ]
    assert out["other"] == {"terms": 1, "searches": 4, "zero_results": 4}
    assert out["totals"]["searches"] == 39
    assert out["totals"]["zero_results"] == 10
    assert out["totals"]["zero_result_share_bps"] == 2564  # 10 / 39, n = 39 >= 20
    assert out["k"] == 5


def test_legacy_search_insights_never_return_raw_terms(live: PgConn) -> None:
    for raw in ("ZZ1B04 Phone 0977 123456", "zz1b04 phone 0977 123456"):
        assert live.run(
            "INSERT INTO public.search_query_log (kind, term, normalized_term) VALUES "
            f"('search', '{raw}', 'zz1b04 phone #')"
        ).ok
    (row,) = [r for r in top_terms(days=30) if r.normalized_term == "zz1b04 phone #"]
    assert row.sample_term == "zz1b04 phone #"
    assert row.count == 2


def test_overview_reads_rollups_and_authoritative_commerce(live: PgConn) -> None:
    for metric, value, n in (
        ("sessions", 40, 40),
        ("bounced_sessions", 10, 40),
        ("active_span_seconds_total", 4_000, 40),
        ("visitors", 30, 40),
        ("searches", 25, 20),
        ("zero_result_searches", 5, 25),
    ):
        assert live.run(
            "INSERT INTO public.analytics_daily_rollup (day, metric, value, sample_n) VALUES "
            f"('{DAY.isoformat()}', '{metric}', {value}, {n})"
        ).ok
    out = build_overview(DAY, DAY)
    assert out["behaviour"] == {
        "sessions": 40,
        "visitor_days": 30,
        "bounce_rate_bps": 2500,
        "avg_active_span_seconds": 100,
        "searches": 25,
        "zero_result_share_bps": 2000,
    }
    summary = commercial_summary(DAY, DAY)
    assert out["commercial"]["gmv_paid_ngwee"] == summary.gmv_paid_ngwee
    assert out["commercial"]["orders_paid"] == summary.orders_paid
    assert out["daily"] == [
        {
            "day": DAY.isoformat(),
            "sessions": 40,
            "orders_paid": summary.orders_paid,
            "gmv_paid_ngwee": summary.gmv_paid_ngwee,
        }
    ]
