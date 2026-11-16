"""Promo-code usage limit under concurrent checkouts (fix/event-ticket-integrity).

Before: ``resolve_promo_discount`` counted redemptions and ``record_promo_redemption``
inserted later, in separate statements, so N concurrent buyers could all pass the
count and redeem a ``max_redemptions = 1`` code N times. The redemption insert is
now serialised on the promo row (DB trigger) and over-limit inserts are refused.
"""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Generator

import pytest
from app.errors import AppError
from app.services.events.promo import record_promo_redemption
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


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
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = conn.dsn
    yield conn
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def _seed_promo(db: PgConn, *, max_redemptions: int | None) -> tuple[str, str]:
    event_id = str(uuid.uuid4())
    promo_id = str(uuid.uuid4())
    max_sql = "NULL" if max_redemptions is None else str(max_redemptions)
    result = db.run(
        f"""
        INSERT INTO public.events (id, organiser_vendor_id, title, slug, status)
        VALUES ('{event_id}', '{VENDOR_A}', 'Promo Event', 'promo-{event_id[:8]}', 'published');
        INSERT INTO public.event_promo_codes (
          id, event_id, code, discount_kind, discount_value, max_redemptions
        ) VALUES ('{promo_id}', '{event_id}', 'EARLY', 'percent', 10, {max_sql});
        """
    )
    assert result.ok, result.error
    return event_id, promo_id


def _seed_order(db: PgConn) -> str:
    group_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    result = db.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee,
          total_ngwee, status
        ) VALUES ('{group_id}', '{CUSTOMER_ID}', 'promo-{group_id}', 1000, 0, 1000, 'pending');
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
          delivery_fee_ngwee, cod, commission_snapshot
        ) VALUES (
          '{order_id}', '{group_id}', '{VENDOR_A}', '{CUSTOMER_ID}', 'placed', 'pickup',
          0, false, '{{}}'::jsonb
        );
        """
    )
    assert result.ok, result.error
    return order_id


def _redemptions(db: PgConn, promo_id: str) -> int:
    result = db.run(
        f"SELECT count(*)::text FROM public.event_promo_redemptions WHERE promo_id = '{promo_id}';"
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _race(event_id: str, promo_id: str, order_ids: list[str]) -> tuple[int, list[str]]:
    barrier = threading.Barrier(len(order_ids))
    successes = 0
    errors: list[str] = []
    lock = threading.Lock()

    def worker(order_id: str) -> None:
        nonlocal successes
        barrier.wait()
        try:
            record_promo_redemption(
                promo_id=promo_id,
                event_id=event_id,
                order_id=order_id,
                customer_id=CUSTOMER_ID,
                discount_ngwee=100,
            )
        except AppError as exc:
            with lock:
                errors.append(str(exc.code))
            return
        with lock:
            successes += 1

    threads = [threading.Thread(target=worker, args=(oid,)) for oid in order_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return successes, errors


@pytest.mark.parametrize("limit", [1, 3])
def test_concurrent_redemptions_never_exceed_limit(db: PgConn, limit: int) -> None:
    event_id, promo_id = _seed_promo(db, max_redemptions=limit)
    orders = [_seed_order(db) for _ in range(8)]

    successes, errors = _race(event_id, promo_id, orders)

    assert successes == limit
    assert _redemptions(db, promo_id) == limit
    assert errors == ["promo_exhausted"] * (len(orders) - limit)


def test_same_order_replay_is_idempotent_at_limit(db: PgConn) -> None:
    event_id, promo_id = _seed_promo(db, max_redemptions=1)
    order_id = _seed_order(db)
    for _ in range(2):
        record_promo_redemption(
            promo_id=promo_id,
            event_id=event_id,
            order_id=order_id,
            customer_id=CUSTOMER_ID,
            discount_ngwee=100,
        )
    assert _redemptions(db, promo_id) == 1


def test_unlimited_code_accepts_all_concurrent_redemptions(db: PgConn) -> None:
    event_id, promo_id = _seed_promo(db, max_redemptions=None)
    orders = [_seed_order(db) for _ in range(6)]
    successes, errors = _race(event_id, promo_id, orders)
    assert successes == 6
    assert errors == []
