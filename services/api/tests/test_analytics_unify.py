"""M16-P05 analytics unification: one queryable schema over funnel + search.

Verifies the unified `analytics_event_stream` view yields a full funnel
(search -> product_view -> cart -> checkout -> pay) from seeded events, that the
existing funnel/search emits still land in their own tables, that the server log is
anonymized (raw PII rejected; raw search term never exposed), and that the unified
table is RLS-locked (admin read, no client/anon read).

DB-backed tests skip cleanly when Postgres is unreachable.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Generator

import pytest
from app.services.analytics.events import (
    EVENT_TYPE_TO_STEP,
    FUNNEL_STEPS,
    query_funnel,
    record_event,
)
from app.services.analytics.funnel import record_event as funnel_record_event
from app.services.analytics.search_log import log_search_query
from tests.rls.conftest import (
    MIGRATIONS_DIR,
    Persona,
    PgConn,
    RoleSession,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"


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
    _truncate(db)
    try:
        yield db
    finally:
        _truncate(db)
        if previous is None:
            os.environ.pop("SUPABASE_DB_URL", None)
        else:
            os.environ["SUPABASE_DB_URL"] = previous


def _truncate(db: PgConn) -> None:
    db.run("DELETE FROM public.analytics_events;")
    db.run("DELETE FROM public.funnel_events;")
    db.run("DELETE FROM public.search_query_log;")


def _insert_checkout_group(db: PgConn, group_id: str, *, total: int = 55_000) -> None:
    db.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
        ) VALUES (
          '{group_id}', '{CUSTOMER_ID}', 'idem-{group_id}', {total}, 0, {total}
        );
        """
    )


def _seed_full_funnel(db: PgConn) -> str:
    """Emit one event per funnel step through the real emitters + record_event."""
    group_id = str(uuid.uuid4())
    _insert_checkout_group(db, group_id)

    # search -> search_query_log stream
    log_search_query(term="Blue Phone", entity_counts={"products": 3}, zero_result=False)

    # product_view (PDP) -> analytics_events superset (no dedicated stream table)
    record_event(
        event_type="product_view",
        session_id=group_id,
        user_id=CUSTOMER_ID,
        entity_type="product",
        entity_id=str(uuid.uuid4()),
        props={"listing_id": str(uuid.uuid4())},
    )

    # cart -> checkout -> pay via the funnel stream
    funnel_record_event(
        stage="cart_add",
        checkout_group_id=group_id,
        customer_id=CUSTOMER_ID,
        snapshot={"line_count": 1, "subtotal_ngwee": 55_000},
    )
    funnel_record_event(
        stage="checkout_start",
        checkout_group_id=group_id,
        customer_id=CUSTOMER_ID,
        snapshot={"step": "session_created"},
    )
    funnel_record_event(
        stage="payment_start",
        checkout_group_id=group_id,
        customer_id=CUSTOMER_ID,
        snapshot={"method": "momo", "total_ngwee": 55_000},
    )
    funnel_record_event(
        stage="order_placed",
        checkout_group_id=group_id,
        customer_id=CUSTOMER_ID,
        snapshot={"order_count": 1},
    )
    return group_id


class TestUnifiedFunnel:
    def test_full_funnel_queryable_from_unified_stream(self, seeded_db: PgConn) -> None:
        _seed_full_funnel(seeded_db)

        report = query_funnel(days=30)
        assert report.window_days == 30
        # Every canonical step is present end-to-end.
        assert report.count("search") == 1
        assert report.count("product_view") == 1
        assert report.count("cart") == 1
        # checkout_start + payment_start both fold onto the checkout step.
        assert report.count("checkout") == 2
        assert report.count("pay") == 1
        assert set(report.steps.keys()) == set(FUNNEL_STEPS)

    def test_event_type_to_step_covers_every_stream_event(self) -> None:
        # Each mapped step is a declared canonical funnel step.
        for step in EVENT_TYPE_TO_STEP.values():
            assert step in FUNNEL_STEPS

    def test_existing_funnel_and_search_emits_still_land(self, seeded_db: PgConn) -> None:
        group_id = _seed_full_funnel(seeded_db)

        funnel = seeded_db.run(
            f"SELECT count(*)::text FROM public.funnel_events "
            f"WHERE checkout_group_id = '{group_id}';"
        )
        assert funnel.ok and funnel.rows and int(funnel.rows[0]) == 4

        search = seeded_db.run(
            "SELECT count(*)::text FROM public.search_query_log WHERE kind = 'search';"
        )
        assert search.ok and search.rows and int(search.rows[0]) == 1

        pdp = seeded_db.run(
            "SELECT count(*)::text FROM public.analytics_events "
            "WHERE event_type = 'product_view';"
        )
        assert pdp.ok and pdp.rows and int(pdp.rows[0]) == 1


class TestAnonymization:
    def test_stream_exposes_normalized_term_never_raw_term(self, seeded_db: PgConn) -> None:
        log_search_query(term="BIG Raw   Term", zero_result=True)

        row = seeded_db.run(
            "SELECT props::text FROM public.analytics_event_stream "
            "WHERE source = 'search' LIMIT 1;"
        )
        assert row.ok and row.rows
        props = json.loads(row.rows[0])
        assert props["normalized_term"] == "big raw term"
        # The raw, un-normalized term must never surface through the unified view.
        assert "term" not in props
        assert "BIG Raw   Term" not in row.rows[0]

    def test_record_event_rejects_raw_pii(self, seeded_db: PgConn) -> None:
        with pytest.raises(ValueError, match="PII"):
            record_event(event_type="product_view", props={"phone": "+260971000001"})

    def test_record_event_rejects_float_money(self, seeded_db: PgConn) -> None:
        with pytest.raises(ValueError, match="ngwee"):
            record_event(event_type="cart_add", props={"unit_price_ngwee": 10.5})

    def test_record_event_rejects_bool_money(self, seeded_db: PgConn) -> None:
        with pytest.raises(ValueError, match="ngwee"):
            record_event(event_type="cart_add", props={"unit_price_ngwee": True})

    def test_analytics_events_has_no_raw_pii_column(self, seeded_db: PgConn) -> None:
        cols = seeded_db.run(
            "SELECT string_agg(column_name, ',') FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'analytics_events';"
        )
        assert cols.ok and cols.rows
        names = set(cols.rows[0].split(","))
        for pii in ("phone", "email", "term", "address"):
            assert pii not in names


class TestRls:
    def _seed_one_event(self, db: PgConn) -> None:
        record_event(
            event_type="product_view",
            user_id=CUSTOMER_ID,
            props={"product_id": str(uuid.uuid4())},
        )

    def test_admin_reads_raw_events(self, seeded_db: PgConn) -> None:
        self._seed_one_event(seeded_db)
        admin = RoleSession(seeded_db, Persona.ADMIN)
        result = admin.execute("SELECT count(*)::int FROM public.analytics_events")
        assert result.ok
        assert result.rows and int(result.rows[0]) >= 1

    def test_non_admin_customer_is_filtered_to_zero(self, seeded_db: PgConn) -> None:
        self._seed_one_event(seeded_db)
        customer = RoleSession(seeded_db, Persona.CUSTOMER)
        result = customer.execute("SELECT count(*)::int FROM public.analytics_events")
        assert result.ok
        assert result.rows and int(result.rows[0]) == 0

    def test_anon_has_no_read_grant(self, seeded_db: PgConn) -> None:
        self._seed_one_event(seeded_db)
        anon = RoleSession(seeded_db, Persona.ANON)
        result = anon.execute("SELECT count(*)::int FROM public.analytics_events")
        # anon holds no SELECT grant on the raw events table.
        assert not result.ok


class TestMigration:
    def test_0029_present_and_reversible(self) -> None:
        migration = MIGRATIONS_DIR / "0029_analytics_unify.sql"
        assert migration.exists(), "0029_analytics_unify.sql missing"
        text = migration.read_text()
        assert "create table public.analytics_events" in text
        assert "create view public.analytics_event_stream" in text
        assert "security_invoker = true" in text
        assert "force row level security" in text
        # documented down path
        assert "drop view public.analytics_event_stream" in text
        assert "drop table public.analytics_events" in text

    def test_0029_replay_shape_is_stable(self, seeded_db: PgConn) -> None:
        replay = """
CREATE TABLE IF NOT EXISTS public.analytics_events (
  id uuid primary key default gen_random_uuid(),
  event_type text not null,
  session_id uuid,
  user_id uuid,
  entity_type text,
  entity_id uuid,
  props jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);
"""
        result = seeded_db.run(replay)
        assert result.ok
        count = seeded_db.run("SELECT count(*)::text FROM public.analytics_events;")
        assert count.ok and count.rows
