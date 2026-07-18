"""Task 3 governance: analytics PII retention sweep, the retention tick, the
AI-spend tile, and the /health alias.

DB-backed tests skip cleanly when Postgres is unreachable; the endpoint/tile tests
are DB-free (patched).
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.routers import admin_dashboards as dash
from app.services.analytics.retention import sweep_analytics_retention
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
SESSION_ID = "22222222-2222-2222-2222-222222222222"
OLD = "timezone('utc', now()) - interval '40 days'"
FRESH = "timezone('utc', now()) - interval '2 days'"


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    seed_matrix_fixtures(conn)
    yield conn


@pytest.fixture
def seeded_db(db: PgConn) -> Generator[PgConn, None, None]:
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    for table in ("search_query_log", "funnel_events", "analytics_events"):
        db.run(f"DELETE FROM public.{table};")
    try:
        yield db
    finally:
        for table in ("search_query_log", "funnel_events", "analytics_events"):
            db.run(f"DELETE FROM public.{table};")
        if previous is None:
            os.environ.pop("SUPABASE_DB_URL", None)
        else:
            os.environ["SUPABASE_DB_URL"] = previous


def _count(db: PgConn, table: str, where: str) -> int:
    result = db.run(f"SELECT count(*)::text FROM public.{table} WHERE {where};")
    assert result.ok and result.rows
    return int(result.rows[0])


def _seed_person_linked_rows(db: PgConn) -> None:
    db.run(
        f"""
        INSERT INTO public.search_query_log
          (kind, term, normalized_term, entity_counts, zero_result, usd_micros, user_id, created_at)
        VALUES
          ('search', 'old', 'old', '{{}}'::jsonb, false, 0, '{CUSTOMER_ID}', {OLD}),
          ('search', 'new', 'new', '{{}}'::jsonb, false, 0, '{CUSTOMER_ID}', {FRESH});
        """
    )
    db.run(
        f"""
        INSERT INTO public.funnel_events
          (stage, checkout_group_id, customer_id, snapshot, created_at)
        VALUES
          ('cart_add', null, '{CUSTOMER_ID}',
           jsonb_build_object('customer_id', '{CUSTOMER_ID}', 'total_ngwee', 100), {OLD}),
          ('cart_add', null, '{CUSTOMER_ID}',
           jsonb_build_object('customer_id', '{CUSTOMER_ID}'), {FRESH});
        """
    )
    db.run(
        f"""
        INSERT INTO public.analytics_events (event_type, session_id, user_id, props, created_at)
        VALUES
          ('product_view', '{SESSION_ID}', '{CUSTOMER_ID}', '{{}}'::jsonb, {OLD}),
          ('product_view', '{SESSION_ID}', '{CUSTOMER_ID}', '{{}}'::jsonb, {FRESH});
        """
    )


class TestRetentionSweep:
    def test_nulls_old_links_keeps_fresh_and_aggregates(self, seeded_db: PgConn) -> None:
        db = seeded_db
        _seed_person_linked_rows(db)

        result = sweep_analytics_retention()
        assert (result.search_query_log, result.funnel_events, result.analytics_events) == (1, 1, 1)

        # search_query_log: old user_id NULLed, fresh kept, aggregate (normalized_term) intact.
        assert _count(db, "search_query_log", "user_id IS NULL AND normalized_term = 'old'") == 1
        assert (
            _count(db, "search_query_log", "user_id IS NOT NULL AND normalized_term = 'new'") == 1
        )

        # funnel_events: old customer_id NULLed + snapshot.customer_id stripped; money kept.
        assert (
            _count(
                db,
                "funnel_events",
                "customer_id IS NULL AND NOT (snapshot ? 'customer_id') "
                "AND (snapshot ->> 'total_ngwee') = '100'",
            )
            == 1
        )
        assert _count(db, "funnel_events", "customer_id IS NOT NULL") == 1  # fresh row untouched

        # analytics_events: old user_id + session_id NULLed; fresh kept.
        assert _count(db, "analytics_events", "user_id IS NULL AND session_id IS NULL") == 1
        assert _count(db, "analytics_events", "user_id IS NOT NULL AND session_id IS NOT NULL") == 1

    def test_sweep_is_idempotent(self, seeded_db: PgConn) -> None:
        _seed_person_linked_rows(seeded_db)
        first = sweep_analytics_retention()
        second = sweep_analytics_retention()
        assert (first.search_query_log, first.funnel_events, first.analytics_events) == (1, 1, 1)
        assert (second.search_query_log, second.funnel_events, second.analytics_events) == (0, 0, 0)


class TestRetentionTickEndpoint:
    def test_requires_internal_token(self, client: TestClient) -> None:
        assert client.post("/internal/analytics/retention-tick").status_code == 401

    def test_runs_sweep_with_token(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = type(
            "R", (), {"search_query_log": 2, "funnel_events": 1, "analytics_events": 0}
        )()
        monkeypatch.setattr(
            "app.routers.internal_analytics.sweep_analytics_retention", lambda: result
        )
        response = client.post(
            "/internal/analytics/retention-tick",
            headers={"X-Internal-Token": "dev-internal-analytics"},
        )
        assert response.status_code == 200
        assert response.json() == {
            "search_query_log": 2,
            "funnel_events": 1,
            "analytics_events": 0,
        }


class TestHealthAlias:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestAiUsageTile:
    def _patch_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dash, "_ai_monthly_cap_usd", lambda _sc: 15)

    def test_shows_real_spend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_cap(monkeypatch)
        monkeypatch.setattr(dash, "current_month_total_usd_micros", lambda **_k: 3_000_000)
        monkeypatch.setattr(dash, "is_killed", lambda **_k: False)
        tile = dash._build_ai_usage_tile(MagicMock())
        assert tile.data_available is True
        assert tile.spend_usd == 3.0
        assert tile.killed is False
        assert tile.cap_usd == 15

    def test_reflects_kill_switch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_cap(monkeypatch)
        monkeypatch.setattr(dash, "current_month_total_usd_micros", lambda **_k: 15_000_000)
        monkeypatch.setattr(dash, "is_killed", lambda **_k: True)
        tile = dash._build_ai_usage_tile(MagicMock())
        assert tile.killed is True
        assert tile.flagged is True

    def test_falls_back_on_read_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_cap(monkeypatch)

        def _boom(**_k: Any) -> int:
            raise RuntimeError("spend read failed")

        monkeypatch.setattr(dash, "current_month_total_usd_micros", _boom)
        tile = dash._build_ai_usage_tile(MagicMock())
        assert tile.data_available is False
        assert tile.spend_usd is None
        assert tile.cap_usd == 15  # cap still shown
