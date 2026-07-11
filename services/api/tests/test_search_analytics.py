"""M06-P06 query analytics: fire-and-forget logging, aggregates, retention, authz.

DB-backed tests skip cleanly when Postgres is unreachable. This module owns the
`search_query_log` table exclusively (nothing else writes it), so the seed/teardown
deletes every row — isolation-clean on the shared CI Postgres.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.services.analytics import search_log
from app.services.analytics.search_log import (
    ask_cost_by_day,
    log_ask_query,
    log_search_query,
    normalize_term,
    top_terms,
    trim_search_pii,
    zero_result_terms,
)
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    MIGRATIONS_DIR,
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
VALID_TOKEN = "valid.jwt.token"


# ---------------------------------------------------------------------------
# DB fixtures (skip without Postgres)
# ---------------------------------------------------------------------------
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
    db.run("DELETE FROM public.search_query_log;")
    try:
        yield db
    finally:
        db.run("DELETE FROM public.search_query_log;")
        if previous is None:
            os.environ.pop("SUPABASE_DB_URL", None)
        else:
            os.environ["SUPABASE_DB_URL"] = previous


def _count_rows(db: PgConn, where: str = "true") -> int:
    result = db.run(f"SELECT count(*)::text FROM public.search_query_log WHERE {where};")
    assert result.ok and result.rows
    return int(result.rows[0])


def _insert_row(
    db: PgConn,
    *,
    kind: str,
    term: str,
    normalized: str,
    zero_result: bool = False,
    usd_micros: int = 0,
    user_id: str | None = None,
    created_at: str = "timezone('utc', now())",
) -> None:
    user_sql = "NULL" if user_id is None else f"'{user_id}'"
    db.run(
        f"""
        INSERT INTO public.search_query_log (
          kind, term, normalized_term, zero_result, usd_micros, user_id, created_at
        ) VALUES (
          '{kind}', '{term}', '{normalized}', {str(zero_result).lower()},
          {usd_micros}, {user_sql}, {created_at}
        );
        """
    )


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def test_normalize_term_lowercases_and_collapses_whitespace() -> None:
    assert normalize_term("  Blue   Widget ") == "blue widget"
    assert normalize_term("iPhone\t15") == "iphone 15"


# ---------------------------------------------------------------------------
# Fire-and-forget logging
# ---------------------------------------------------------------------------
class TestLogging:
    def test_log_search_query_inserts_row(self, seeded_db: PgConn) -> None:
        log_search_query(
            term="Blue Widget",
            entity_counts={"products": 4},
            zero_result=False,
            user_id=CUSTOMER_ID,
        )
        assert _count_rows(seeded_db, "kind = 'search'") == 1
        row = seeded_db.run(
            "SELECT normalized_term, zero_result::text, usd_micros::text, "
            "entity_counts::text FROM public.search_query_log LIMIT 1;"
        )
        assert row.ok and row.rows
        normalized, zero, cost, counts = row.rows[0].split("|", 3)
        assert normalized == "blue widget"
        assert zero == "false"
        assert cost == "0"
        assert '"products":4' in counts.replace(" ", "")

    def test_log_ask_query_records_spend(self, seeded_db: PgConn) -> None:
        log_ask_query(term="What phones ship today?", usd_micros=1500)
        assert _count_rows(seeded_db, "kind = 'ask' AND usd_micros = 1500") == 1

    def test_logging_swallows_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_script: str) -> Any:
            raise RuntimeError("db exploded")

        monkeypatch.setattr(search_log, "run_sql_script", _boom)
        # Must not raise despite the failing write.
        log_search_query(term="anything", zero_result=True)
        log_ask_query(term="anything", usd_micros=99)

    def test_logging_swallows_not_ok_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            search_log,
            "run_sql_script",
            lambda _script: MagicMock(ok=False, error="boom", rows=[]),
        )
        log_search_query(term="anything", zero_result=False)  # no raise


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------
class TestAggregates:
    def _seed(self, db: PgConn) -> None:
        log_search_query(term="Blue Widget", zero_result=False)
        log_search_query(term="blue widget", zero_result=False)
        log_search_query(term="Missing Thing", zero_result=True)
        log_search_query(term="missing thing", zero_result=True)
        log_search_query(term="MISSING THING", zero_result=True)
        log_ask_query(term="blue widget", usd_micros=1500)
        log_ask_query(term="Pricey Ask", usd_micros=2500)

    def test_top_terms_match_fixtures(self, seeded_db: PgConn) -> None:
        self._seed(seeded_db)
        rows = top_terms(days=30)
        counts = {r.normalized_term: r.count for r in rows}
        assert counts["blue widget"] == 3  # 2 search + 1 ask
        assert counts["missing thing"] == 3
        assert counts["pricey ask"] == 1
        # count desc, then normalized asc → the two 3-count terms lead, blue first.
        assert rows[0].normalized_term == "blue widget"
        assert rows[1].normalized_term == "missing thing"

    def test_zero_result_terms_only_returns_misses(self, seeded_db: PgConn) -> None:
        self._seed(seeded_db)
        rows = zero_result_terms(days=30)
        assert [(r.normalized_term, r.count) for r in rows] == [("missing thing", 3)]

    def test_ask_cost_by_day_sums_spend(self, seeded_db: PgConn) -> None:
        self._seed(seeded_db)
        rows = ask_cost_by_day(days=30)
        assert len(rows) == 1
        assert rows[0].usd_micros == 4000  # 1500 + 2500
        assert rows[0].query_count == 2

    def test_window_excludes_old_rows(self, seeded_db: PgConn) -> None:
        _insert_row(
            seeded_db,
            kind="search",
            term="ancient",
            normalized="ancient",
            created_at="timezone('utc', now()) - interval '90 days'",
        )
        _insert_row(seeded_db, kind="search", term="recent", normalized="recent")
        rows = top_terms(days=30)
        terms = {r.normalized_term for r in rows}
        assert "recent" in terms
        assert "ancient" not in terms


# ---------------------------------------------------------------------------
# 30-day PII retention trim
# ---------------------------------------------------------------------------
class TestRetentionTrim:
    def test_trim_nulls_old_user_id_only(self, seeded_db: PgConn) -> None:
        _insert_row(
            seeded_db,
            kind="search",
            term="old",
            normalized="old",
            user_id=CUSTOMER_ID,
            created_at="timezone('utc', now()) - interval '40 days'",
        )
        _insert_row(
            seeded_db,
            kind="ask",
            term="fresh",
            normalized="fresh",
            usd_micros=10,
            user_id=CUSTOMER_ID,
            created_at="timezone('utc', now()) - interval '2 days'",
        )

        trimmed = trim_search_pii()
        assert trimmed == 1

        assert _count_rows(seeded_db, "user_id IS NULL AND normalized_term = 'old'") == 1
        assert (
            _count_rows(seeded_db, "user_id IS NOT NULL AND normalized_term = 'fresh'")
            == 1
        )

    def test_trim_is_idempotent(self, seeded_db: PgConn) -> None:
        _insert_row(
            seeded_db,
            kind="search",
            term="old",
            normalized="old",
            user_id=CUSTOMER_ID,
            created_at="timezone('utc', now()) - interval '40 days'",
        )
        assert trim_search_pii() == 1
        assert trim_search_pii() == 0  # nothing left to trim


# ---------------------------------------------------------------------------
# Admin-only endpoint authz
# ---------------------------------------------------------------------------
def _mock_auth(
    monkeypatch: pytest.MonkeyPatch, user_id: str, roles: frozenset[str]
) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: roles if uid == user_id else frozenset(),
    )


class TestAdminAuthz:
    @pytest.mark.parametrize(
        "path",
        ["/admin/search-insights/top-terms", "/admin/search-insights/zero-results",
         "/admin/search-insights/ask-cost"],
    )
    def test_non_admin_gets_403(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        _mock_auth(monkeypatch, OTHER_USER_ID, frozenset({"customer"}))
        response = client.get(path, headers={"Authorization": f"Bearer {VALID_TOKEN}"})
        assert response.status_code == 403

    def test_missing_auth_rejected(self, client: TestClient) -> None:
        assert client.get("/admin/search-insights/top-terms").status_code == 401

    def test_admin_reads_insights(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        seeded_db: PgConn,
    ) -> None:
        log_search_query(term="Blue Widget", zero_result=False)
        log_search_query(term="missing", zero_result=True)
        log_ask_query(term="cost me", usd_micros=1200)
        _mock_auth(monkeypatch, CUSTOMER_ID, frozenset({"admin"}))
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}

        top = client.get("/admin/search-insights/top-terms", headers=headers)
        assert top.status_code == 200
        assert any(item["normalized_term"] == "blue widget" for item in top.json())

        zero = client.get("/admin/search-insights/zero-results", headers=headers)
        assert zero.status_code == 200
        assert [i["normalized_term"] for i in zero.json()] == ["missing"]

        cost = client.get(
            "/admin/search-insights/ask-cost?days=7", headers=headers
        )
        assert cost.status_code == 200
        assert cost.json()[0]["usd_micros"] == 1200

    def test_window_param_validated(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_auth(monkeypatch, CUSTOMER_ID, frozenset({"admin"}))
        response = client.get(
            "/admin/search-insights/top-terms?days=9999",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Migration 0027 shape / replay
# ---------------------------------------------------------------------------
class TestMigration:
    def test_0027_file_present_and_reversible(self) -> None:
        migration = MIGRATIONS_DIR / "0027_search_analytics.sql"
        assert migration.exists(), "0027_search_analytics.sql missing"
        text = migration.read_text()
        assert "create table public.search_query_log" in text
        assert "force row level security" in text
        assert "drop table public.search_query_log" in text  # documented down path

    def test_0027_replay_shape_is_stable(self, seeded_db: PgConn) -> None:
        """The table shape is idempotent-replay-safe (CREATE TABLE IF NOT EXISTS)."""
        replay = """
CREATE TABLE IF NOT EXISTS public.search_query_log (
  id uuid primary key default gen_random_uuid(),
  kind text not null,
  term text not null,
  normalized_term text not null,
  entity_counts jsonb not null default '{}'::jsonb,
  zero_result boolean not null default false,
  usd_micros bigint not null default 0,
  user_id uuid,
  created_at timestamptz not null default timezone('utc', now())
);
"""
        result = seeded_db.run(replay)
        assert result.ok
        count = seeded_db.run("SELECT count(*)::text FROM public.search_query_log;")
        assert count.ok and count.rows
