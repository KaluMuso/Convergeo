"""M07-P08 funnel analytics: sequence integrity, abandonment, flag gating."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Generator
from typing import Any
from unittest.mock import patch

import pytest
from app.services.analytics.funnel import FUNNEL_STAGES, record_event, sweep_abandoned
from app.services.cart.events import emit_cart_add, emit_checkout_start, emit_step_complete
from app.services.orders.events import emit_order_placed_funnel, emit_payment_start_funnel
from app.services.stock.claim import claim_reservation
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


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


@pytest.fixture(autouse=True)
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    import os

    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


@pytest.fixture(autouse=True)
def clean_funnel_events(db: PgConn) -> Generator[None, None, None]:
    db.run("DELETE FROM public.notification_outbox WHERE dedupe_key LIKE 'abandoned_checkout:%';")
    db.run("DELETE FROM public.funnel_events;")
    yield
    db.run("DELETE FROM public.notification_outbox WHERE dedupe_key LIKE 'abandoned_checkout:%';")
    db.run("DELETE FROM public.funnel_events;")


def _insert_checkout_group(
    db: PgConn,
    group_id: str,
    *,
    subtotal: int = 10_000,
    total: int = 10_000,
) -> None:
    db.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
        ) VALUES (
          '{group_id}', '{CUSTOMER_ID}', 'idem-{group_id}', {subtotal}, 0, {total}
        );
        """
    )


def _insert_tracked_listing(db: PgConn, listing_id: str, stock_qty: int = 5) -> None:
    db.run(
        f"""
        INSERT INTO public.vendor_listings (
          id, vendor_id, product_id, price_ngwee, condition, stock_mode, stock_qty, status
        )
        SELECT
          '{listing_id}', '{VENDOR_ID}', p.id, 10000, 'new', 'tracked', {stock_qty}, 'active'
        FROM public.products p
        LIMIT 1
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _funnel_rows(db: PgConn, checkout_group_id: str) -> list[dict[str, Any]]:
    result = db.run(
        f"""
        SELECT stage, snapshot::text
        FROM public.funnel_events
        WHERE checkout_group_id = '{checkout_group_id}'
        ORDER BY created_at ASC;
        """
    )
    assert result.ok
    rows: list[dict[str, Any]] = []
    for line in result.rows:
        parts = line.split("|", 1)
        if len(parts) != 2:
            continue
        rows.append({"stage": parts[0], "snapshot": json.loads(parts[1])})
    return rows


def _outbox_count(db: PgConn, checkout_group_id: str) -> int:
    result = db.run(
        f"""
        SELECT count(*)::text
        FROM public.notification_outbox
        WHERE dedupe_key LIKE 'abandoned_checkout:{checkout_group_id}:%';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _ensure_customer_phone(db: PgConn) -> None:
    db.run(
        f"""
        UPDATE public.profiles
        SET phone = '+260971000001'
        WHERE id = '{CUSTOMER_ID}';
        """
    )


def _set_flag(db: PgConn, enabled: bool) -> bool:
    prior = db.run(
        "SELECT enabled::text FROM public.feature_flags WHERE flag = 'abandoned_cart';"
    )
    previous = prior.rows[0] if prior.ok and prior.rows else "false"
    db.run(
        f"""
        UPDATE public.feature_flags
        SET enabled = {'true' if enabled else 'false'}
        WHERE flag = 'abandoned_cart';
        """
    )
    return previous in {"t", "true"}


class TestFunnelSequenceIntegrity:
    def test_stages_recorded_in_order_and_idempotent_per_group_stage(self, db: PgConn) -> None:
        group_id = str(uuid.uuid4())
        _insert_checkout_group(db, group_id)

        emitters: list[tuple[str, Callable[[], dict[str, Any] | None]]] = [
            ("checkout_start", lambda: emit_checkout_start(
                checkout_group_id=group_id,
                customer_id=CUSTOMER_ID,
                snapshot={"step": "session_created"},
            )),
            ("step_complete", lambda: emit_step_complete(
                checkout_group_id=group_id,
                customer_id=CUSTOMER_ID,
                snapshot={"step": "fulfilment"},
            )),
            ("payment_start", lambda: emit_payment_start_funnel(
                checkout_group_id=group_id,
                customer_id=CUSTOMER_ID,
                snapshot={"method": "momo"},
            )),
            ("order_placed", lambda: emit_order_placed_funnel(
                checkout_group_id=group_id,
                customer_id=CUSTOMER_ID,
                snapshot={"order_count": 1},
            )),
        ]

        for _stage, emit in emitters:
            first = emit()
            second = emit()
            assert first is not None
            assert second is None

        rows = _funnel_rows(db, group_id)
        recorded_stages = [row["stage"] for row in rows]
        assert recorded_stages == [
            "checkout_start",
            "step_complete",
            "payment_start",
            "order_placed",
        ]

        duplicate = record_event(
            stage="payment_start",
            checkout_group_id=group_id,
            customer_id=CUSTOMER_ID,
            snapshot={"method": "momo"},
        )
        assert duplicate is None
        assert len(_funnel_rows(db, group_id)) == 4

    def test_cart_add_without_checkout_group(self, db: PgConn) -> None:
        cart_id = str(uuid.uuid4())
        row = emit_cart_add(
            checkout_group_id=None,
            customer_id=CUSTOMER_ID,
            snapshot={"cart_id": cart_id, "line_count": 1},
        )
        assert row is not None
        result = db.run(
            f"""
            SELECT count(*)::text
            FROM public.funnel_events
            WHERE stage = 'cart_add' AND customer_id = '{CUSTOMER_ID}';
            """
        )
        assert result.ok and result.rows
        assert int(result.rows[0]) == 1

    def test_funnel_stages_constant_matches_migration(self) -> None:
        assert FUNNEL_STAGES == (
            "cart_add",
            "checkout_start",
            "step_complete",
            "payment_start",
            "order_placed",
            "abandoned",
        )


class TestAbandonmentTrigger:
    def test_expired_reservation_without_order_placed_records_abandoned_with_snapshot(
        self, db: PgConn
    ) -> None:
        listing_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id)
        _insert_checkout_group(db, group_id, subtotal=20_000, total=20_000)

        claimed = claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=2,
            ttl_minutes=15,
        )
        assert claimed.claimed

        db.run(
            f"""
            UPDATE public.stock_reservations
            SET expires_at = timezone('utc', now()) - interval '1 minute'
            WHERE checkout_group_id = '{group_id}';
            """
        )

        result = sweep_abandoned()
        assert result.abandoned >= 1
        assert _funnel_rows(db, group_id)[-1]["stage"] == "abandoned"

        rows = _funnel_rows(db, group_id)
        abandoned_rows = [row for row in rows if row["stage"] == "abandoned"]
        assert len(abandoned_rows) == 1
        snapshot = abandoned_rows[0]["snapshot"]
        assert snapshot["checkout_group_id"] == group_id
        assert snapshot["customer_id"] == CUSTOMER_ID
        assert snapshot["total_ngwee"] == 20_000
        assert snapshot["lines"] == [{"listing_id": listing_id, "qty": 2}]

    def test_order_placed_prevents_abandonment(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id)
        _insert_checkout_group(db, group_id)

        claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=1,
            ttl_minutes=15,
        )
        emit_order_placed_funnel(
            checkout_group_id=group_id,
            customer_id=CUSTOMER_ID,
            snapshot={},
        )
        db.run(
            f"""
            UPDATE public.stock_reservations
            SET expires_at = timezone('utc', now()) - interval '1 minute'
            WHERE checkout_group_id = '{group_id}';
            """
        )

        sweep_abandoned()
        rows = _funnel_rows(db, group_id)
        assert [row["stage"] for row in rows] == ["order_placed"]
        assert not any(row["stage"] == "abandoned" for row in rows)

    def test_sweep_is_idempotent(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id)
        _insert_checkout_group(db, group_id)

        claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=1,
            ttl_minutes=15,
        )
        db.run(
            f"""
            UPDATE public.stock_reservations
            SET expires_at = timezone('utc', now()) - interval '1 minute'
            WHERE checkout_group_id = '{group_id}';
            """
        )

        first = sweep_abandoned()
        second = sweep_abandoned()
        assert first.abandoned >= 1
        assert second.abandoned == 0
        abandoned_rows = [row for row in _funnel_rows(db, group_id) if row["stage"] == "abandoned"]
        assert len(abandoned_rows) == 1


class TestFlagGating:
    def test_flag_off_does_not_enqueue_abandoned_checkout_outbox(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id)
        _insert_checkout_group(db, group_id)
        _ensure_customer_phone(db)
        previous_flag = _set_flag(db, False)

        claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=1,
            ttl_minutes=15,
        )
        db.run(
            f"""
            UPDATE public.stock_reservations
            SET expires_at = timezone('utc', now()) - interval '1 minute'
            WHERE checkout_group_id = '{group_id}';
            """
        )

        sweep_abandoned()
        assert any(row["stage"] == "abandoned" for row in _funnel_rows(db, group_id))
        assert _outbox_count(db, group_id) == 0
        _set_flag(db, previous_flag)

    def test_flag_on_enqueues_abandoned_checkout_outbox(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id)
        _insert_checkout_group(db, group_id)
        _ensure_customer_phone(db)
        previous_flag = _set_flag(db, True)

        claim_reservation(
            listing_id=listing_id,
            checkout_group_id=group_id,
            qty=1,
            ttl_minutes=15,
        )
        db.run(
            f"""
            UPDATE public.stock_reservations
            SET expires_at = timezone('utc', now()) - interval '1 minute'
            WHERE checkout_group_id = '{group_id}';
            """
        )

        sweep_abandoned()
        assert any(row["stage"] == "abandoned" for row in _funnel_rows(db, group_id))
        assert _outbox_count(db, group_id) == 1
        _set_flag(db, previous_flag)

        outbox = db.run(
            f"""
            SELECT payload::text
            FROM public.notification_outbox
            WHERE dedupe_key LIKE 'abandoned_checkout:{group_id}:%'
            LIMIT 1;
            """
        )
        assert outbox.ok and outbox.rows
        payload = json.loads(outbox.rows[0])
        assert payload["checkout_group_id"] == group_id
        assert payload["recipient_id"] == CUSTOMER_ID


class TestMigrationReplay:
    def test_0025_replay_is_idempotent(self, db: PgConn) -> None:
        """Re-applying 0025_funnel_events statements must not fail on existing objects."""
        replay = """
CREATE TABLE IF NOT EXISTS public.funnel_events (
  id uuid primary key default gen_random_uuid(),
  stage text not null,
  checkout_group_id uuid,
  customer_id uuid,
  snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);
"""
        result = db.run(replay)
        assert result.ok
        count = db.run("SELECT count(*)::text FROM public.funnel_events;")
        assert count.ok and count.rows


class TestInternalFunnelEndpoint:
    def test_abandon_tick_requires_internal_token(self, client: Any) -> None:
        app_client: TestClient = client
        denied = app_client.post("/internal/funnel/abandon-tick")
        assert denied.status_code == 401

        with patch(
            "app.routers.internal_funnel.sweep_abandoned",
            return_value=type(
                "Stats",
                (),
                {"scanned": 0, "abandoned": 0, "notifications_enqueued": 0},
            )(),
        ):
            allowed = app_client.post(
                "/internal/funnel/abandon-tick",
                headers={"X-Internal-Token": "dev-internal-funnel"},
            )
        assert allowed.status_code == 200
        assert allowed.json() == {
            "scanned": 0,
            "abandoned": 0,
            "notifications_enqueued": 0,
        }
