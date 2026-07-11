"""Bayesian review aggregation (M15-P02).

Pure Bayesian goldens run everywhere; the DB-backed tests (incremental-on-write, boost merge,
incremental-vs-nightly consistency, report->flags) require a real Postgres and otherwise skip.
The suite is isolation-clean: every DB test seeds its own rows and tears them down (shared PG).
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Generator, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from app.services.reviews.aggregate import (
    DEFAULT_CONFIDENCE_C,
    DEFAULT_PRIOR_M,
    BayesConfig,
    bayesian_average,
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

# Fixture entities seeded by seed_matrix_fixtures (see tests/fixtures/demo/ids.json).
CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
VENDOR_SHOP_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PRODUCT_PHONE = "b0000000-0000-0000-0000-000000000001"
LISTING_PHONE_A = "b1000000-0000-0000-0000-000000000001"

LAUNCH_CONFIG = BayesConfig(prior_m=DEFAULT_PRIOR_M, confidence_c=DEFAULT_CONFIDENCE_C)


# ---------------------------------------------------------------------------
# Bayesian goldens — pure, no DB.  bayes = (C*m + sum) / (C + n), m=4.0, C=10.
# ---------------------------------------------------------------------------


def test_bayes_zero_reviews_returns_prior() -> None:
    """No reviews -> the platform prior m (a brand-new item is not '5 stars')."""
    assert bayesian_average(0, 0, LAUNCH_CONFIG) == Decimal("4.000")


def test_bayes_single_five_star_is_shrunk_toward_prior() -> None:
    """One 5-star review shrinks to (10*4 + 5)/(10+1) = 45/11 = 4.091 — anti-gaming."""
    value = bayesian_average(5, 1, LAUNCH_CONFIG)
    assert value == Decimal("4.091")
    assert value < Decimal("5.000")


def test_bayes_single_one_star_is_shrunk_toward_prior() -> None:
    """One 1-star review lifts to (40 + 1)/11 = 41/11 = 3.727 — low-n both ways."""
    assert bayesian_average(1, 1, LAUNCH_CONFIG) == Decimal("3.727")


def test_bayes_many_reviews_converge_to_true_mean() -> None:
    """100 five-star reviews -> (40 + 500)/110 = 540/110 = 4.909 (approaches 5)."""
    assert bayesian_average(500, 100, LAUNCH_CONFIG) == Decimal("4.909")


def test_bayes_many_low_reviews_converge_down() -> None:
    """100 one-star reviews -> (40 + 100)/110 = 140/110 = 1.273 (approaches 1)."""
    assert bayesian_average(100, 100, LAUNCH_CONFIG) == Decimal("1.273")


def test_bayes_custom_config_matches_formula() -> None:
    config = BayesConfig(prior_m=Decimal("3.0"), confidence_c=Decimal("5"))
    # (5*3 + 20) / (5 + 5) = 35/10 = 3.500
    assert bayesian_average(20, 5, config) == Decimal("3.500")


# ---------------------------------------------------------------------------
# Internal nightly-tick router — token-guarded, delegates to recompute_all.
# ---------------------------------------------------------------------------


def test_internal_tick_requires_token() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/internal/review-aggregate/tick")
    assert response.status_code == 401


def test_internal_tick_recomputes_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app

    class _FakeRpc:
        def execute(self) -> SimpleNamespace:
            return SimpleNamespace(data=7)

    class _FakeClient:
        def rpc(self, name: str, params: dict[str, Any]) -> _FakeRpc:
            assert name == "recompute_all_review_aggregates"
            assert params == {}
            return _FakeRpc()

    def _fake_supabase() -> Iterator[SimpleNamespace]:
        yield SimpleNamespace(client=_FakeClient())

    monkeypatch.setattr("app.deps.get_supabase_client", _fake_supabase)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/internal/review-aggregate/tick",
            headers={"X-Internal-Token": "dev-internal-review-aggregate"},
        )
    assert response.status_code == 200
    assert response.json() == {"entities": 7}


# ---------------------------------------------------------------------------
# DB-backed tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    if shutil.which("psql") is None:
        pytest.skip("psql not available")
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


@dataclass
class SeededGraph:
    """Tracks rows created for a test so teardown can be exact and isolation-clean."""

    order_item_ids: list[str] = field(default_factory=list)
    order_ids: list[str] = field(default_factory=list)
    group_ids: list[str] = field(default_factory=list)
    review_ids: list[str] = field(default_factory=list)


def _seed_order_item(conn: PgConn, graph: SeededGraph) -> str:
    """Create a delivered order + item + product link on shop_a / phone / phone_a."""
    group_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    order_item_id = str(uuid.uuid4())
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{group_id}', '{CUSTOMER_A}', 'cg-{group_id}', 150000, 0, 150000, 'completed'
        );
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment
        ) VALUES (
          '{order_id}', '{group_id}', '{VENDOR_SHOP_A}', '{CUSTOMER_A}', 'delivered', 'delivery'
        );
        INSERT INTO public.order_items (
          id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES (
          '{order_item_id}', '{order_id}', 'product', 1, 150000, 'Aggregate phone'
        );
        INSERT INTO public.order_item_products (order_item_id, listing_id, product_id)
        VALUES ('{order_item_id}', '{LISTING_PHONE_A}', '{PRODUCT_PHONE}');
        """
    )
    graph.group_ids.append(group_id)
    graph.order_ids.append(order_id)
    graph.order_item_ids.append(order_item_id)
    return order_item_id


def _insert_review(conn: PgConn, order_item_id: str, rating: int) -> str:
    review_id = str(uuid.uuid4())
    result = conn.run(
        f"""
        INSERT INTO public.reviews (id, order_item_id, rating, body, status)
        VALUES ('{review_id}', '{order_item_id}', {rating}, 'agg test', 'published');
        """
    )
    assert result.ok, result.error
    return review_id


def _teardown(conn: PgConn, graph: SeededGraph) -> None:
    if graph.order_item_ids:
        ids = ", ".join(f"'{i}'" for i in graph.order_item_ids)
        conn.run(f"DELETE FROM public.reviews WHERE order_item_id IN ({ids});")
        conn.run(f"DELETE FROM public.order_item_products WHERE order_item_id IN ({ids});")
        conn.run(f"DELETE FROM public.order_items WHERE id IN ({ids});")
    if graph.order_ids:
        oids = ", ".join(f"'{i}'" for i in graph.order_ids)
        conn.run(f"DELETE FROM public.orders WHERE id IN ({oids});")
    if graph.group_ids:
        gids = ", ".join(f"'{i}'" for i in graph.group_ids)
        conn.run(f"DELETE FROM public.checkout_groups WHERE id IN ({gids});")
    # Reset the aggregates + search boost for the shared fixture entities.
    conn.run(
        f"""
        DELETE FROM public.review_aggregates
        WHERE (entity_kind, entity_id) IN (
          ('product', '{PRODUCT_PHONE}'), ('listing', '{LISTING_PHONE_A}'),
          ('vendor', '{VENDOR_SHOP_A}')
        );
        UPDATE public.search_documents
        SET boost_signals = boost_signals - 'rating_bayes' - 'rating_count'
        WHERE entity_id IN ('{PRODUCT_PHONE}', '{LISTING_PHONE_A}', '{VENDOR_SHOP_A}');
        """
    )


def _aggregate(conn: PgConn, entity_kind: str, entity_id: str) -> tuple[int, int, str]:
    result = conn.run(
        f"""
        SELECT rating_count, rating_sum, rating_bayes::text
        FROM public.review_aggregates
        WHERE entity_kind = '{entity_kind}' AND entity_id = '{entity_id}'
        """
    )
    assert result.ok, result.error
    assert result.rows, f"no aggregate for {entity_kind} {entity_id}"
    count, total, bayes = result.rows[0].split("|")
    return int(count), int(total), bayes


def test_migration_0028_replay_shipped_table_and_config(db: PgConn) -> None:
    """0028 replays with the rest of MIGRATIONS_DIR: table + config land."""
    assert MIGRATIONS_DIR.joinpath("0028_review_aggregates.sql").exists()
    table = db.run(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'review_aggregates'"
    )
    assert table.ok and table.rows == ["1"]
    config = db.run(
        "SELECT count(*)::int FROM public.platform_config "
        "WHERE key IN ('review_bayes_prior_m', 'review_bayes_confidence_c')"
    )
    assert config.ok and config.rows == ["2"]


def test_sql_bayes_matches_python_goldens(db: PgConn) -> None:
    """The 0028 SQL formula agrees with the pure-Python mirror on every golden."""
    cases = [(0, 0), (5, 1), (1, 1), (500, 100), (100, 100)]
    for rating_sum, rating_count in cases:
        result = db.run(
            f"SELECT public.review_bayes_value({rating_sum}, {rating_count})::text"
        )
        assert result.ok, result.error
        expected = str(bayesian_average(rating_sum, rating_count, LAUNCH_CONFIG))
        assert result.rows[0] == expected, (rating_sum, rating_count, result.rows[0], expected)


def test_incremental_on_write_and_boost_merge(db: PgConn) -> None:
    """A published review write recomputes all three aggregates and merges the boost signal."""
    graph = SeededGraph()
    try:
        order_item_id = _seed_order_item(db, graph)
        _insert_review(db, order_item_id, rating=5)

        expected_bayes = str(bayesian_average(5, 1, LAUNCH_CONFIG))  # 4.091
        for kind, entity_id in (
            ("product", PRODUCT_PHONE),
            ("listing", LISTING_PHONE_A),
            ("vendor", VENDOR_SHOP_A),
        ):
            count, total, bayes = _aggregate(db, kind, entity_id)
            assert (count, total) == (1, 5), (kind, count, total)
            assert bayes == expected_bayes, (kind, bayes)

        # boost_signals merged: rating keys present AND pre-existing keys preserved.
        boost = db.run(
            f"""
            SELECT boost_signals->>'rating_bayes',
                   (boost_signals->>'rating_count')::int,
                   boost_signals ? 'in_stock'
            FROM public.search_documents
            WHERE entity_kind = 'listing' AND entity_id = '{LISTING_PHONE_A}'
            """
        )
        assert boost.ok, boost.error
        assert boost.rows, "listing search_document missing"
        bayes_signal, count_signal, has_in_stock = boost.rows[0].split("|")
        assert bayes_signal == expected_bayes
        assert count_signal == "1"
        assert has_in_stock == "t"
    finally:
        _teardown(db, graph)


def test_incremental_equals_nightly_recompute(db: PgConn) -> None:
    """apply-on-write (trigger) result == recompute_all_review_aggregates() (nightly)."""
    graph = SeededGraph()
    try:
        for rating in (5, 4, 3):
            order_item_id = _seed_order_item(db, graph)
            _insert_review(db, order_item_id, rating=rating)

        entities = (
            ("product", PRODUCT_PHONE),
            ("listing", LISTING_PHONE_A),
            ("vendor", VENDOR_SHOP_A),
        )
        incremental = {(k, e): _aggregate(db, k, e) for k, e in entities}
        expected_bayes = str(bayesian_average(12, 3, LAUNCH_CONFIG))
        for value in incremental.values():
            assert value[0] == 3 and value[1] == 12
            assert value[2] == expected_bayes

        # Wipe the aggregate rows, then run the nightly bulk recompute from source.
        db.run(
            "DELETE FROM public.review_aggregates "
            f"WHERE (entity_kind, entity_id) IN "
            f"(('product', '{PRODUCT_PHONE}'), ('listing', '{LISTING_PHONE_A}'), "
            f"('vendor', '{VENDOR_SHOP_A}'))"
        )
        recomputed = db.run("SELECT public.recompute_all_review_aggregates()")
        assert recomputed.ok, recomputed.error

        nightly = {(k, e): _aggregate(db, k, e) for k, e in entities}
        assert nightly == incremental
    finally:
        _teardown(db, graph)


def test_review_delete_recomputes_to_prior(db: PgConn) -> None:
    """Removing the only review drops the aggregate back to count 0 / prior m."""
    graph = SeededGraph()
    try:
        order_item_id = _seed_order_item(db, graph)
        review_id = _insert_review(db, order_item_id, rating=1)
        count, _, _ = _aggregate(db, "listing", LISTING_PHONE_A)
        assert count == 1

        db.run(f"DELETE FROM public.reviews WHERE id = '{review_id}'")
        graph.review_ids.clear()
        count, total, bayes = _aggregate(db, "listing", LISTING_PHONE_A)
        assert (count, total) == (0, 0)
        assert bayes == str(bayesian_average(0, 0, LAUNCH_CONFIG))
    finally:
        _teardown(db, graph)


def test_report_review_lands_in_flags_queue(db: PgConn) -> None:
    """A reported review inserts into the shared M13-P04 flags queue (entity_type='review')."""
    graph = SeededGraph()
    flag_id = str(uuid.uuid4())
    try:
        order_item_id = _seed_order_item(db, graph)
        review_id = _insert_review(db, order_item_id, rating=2)
        result = db.run(
            f"""
            INSERT INTO public.flags (id, entity_type, entity_id, reason, reporter_user_id)
            VALUES ('{flag_id}', 'review', '{review_id}', 'spam', '{CUSTOMER_A}');
            """
        )
        assert result.ok, result.error
        queued = db.run(
            f"SELECT entity_type, status FROM public.flags WHERE id = '{flag_id}'"
        )
        assert queued.ok and queued.rows == ["review|open"]
    finally:
        db.run(f"DELETE FROM public.flags WHERE id = '{flag_id}'")
        _teardown(db, graph)
