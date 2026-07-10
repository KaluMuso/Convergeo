"""Order scheduled job tests — auto-confirm, auto-release, internal token guard."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from app.services.escrow.release import (
    DEFAULT_RELEASE_AFTER_DELIVERED_HOURS,
    DEFAULT_RELEASE_AFTER_SHIPPED_DAYS,
    release_idempotency_key,
)
from app.services.orders.state import SYSTEM_ACTOR_ID, OrderEvent, OrderTransitionError
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
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PLATFORM_CASH_ID = "c1000000-0000-0000-0000-000000000001"
ESCROW_ID = "c2000000-0000-0000-0000-000000000002"
COMMISSION_ID = "c3000000-0000-0000-0000-000000000003"
VENDOR_PAYABLE_ID = "c5000000-0000-0000-0000-000000000005"

GROSS_NGEWEE = 200_000
COMMISSION_BPS = 800
COMMISSION_SNAPSHOT = {
    "lines": [
        {
            "listing_id": str(uuid.uuid4()),
            "category_key": "electronics",
            "rate_bps": COMMISSION_BPS,
            "qty": 1,
            "unit_price_ngwee": GROSS_NGEWEE,
            "line_total_ngwee": GROSS_NGEWEE,
            "wholesale": False,
        }
    ]
}

INTERNAL_TOKEN = "test-order-jobs-token"
AUTO_CONFIRM_PATH = "/internal/order-jobs/auto-confirm"
AUTO_RELEASE_PATH = "/internal/order-jobs/auto-release"


class _ServiceWrapper:
    client: Any = None


_SERVICE = _ServiceWrapper()


def ensure_idempotency_column(conn: PgConn) -> None:
    result = conn.run(
        """
        SELECT count(*)::text
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'ledger_transactions'
          AND column_name = 'idempotency_key';
        """
    )
    if result.ok and result.rows and result.rows[0] == "0":
        migration = MIGRATIONS_DIR / "0015_ledger_idempotency.sql"
        applied = conn.run_file(migration)
        if not applied.ok:
            raise RuntimeError(f"failed to apply {migration.name}: {applied.error}")


def seed_ledger_accounts(conn: PgConn) -> None:
    script = f"""
BEGIN;
SET LOCAL role service_role;
INSERT INTO public.ledger_accounts (id, kind) VALUES
  ('{PLATFORM_CASH_ID}', 'platform_cash'),
  ('{ESCROW_ID}', 'escrow'),
  ('{COMMISSION_ID}', 'commission_revenue')
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.ledger_accounts (id, kind, vendor_id) VALUES
  ('{VENDOR_PAYABLE_ID}', 'vendor_payable', '{VENDOR_A}')
ON CONFLICT (id) DO NOTHING;
COMMIT;
"""
    result = conn.run_script(script)
    if not result.ok:
        raise RuntimeError(f"ledger account seed failed: {result.error}")


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
    else:
        ensure_idempotency_column(conn)
        seed_matrix_fixtures(conn)
    seed_ledger_accounts(conn)
    yield conn


@pytest.fixture
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    import os

    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


@pytest.fixture
def jobs_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("INTERNAL_ORDER_JOBS_TOKEN", INTERNAL_TOKEN)
    from app.main import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _insert_checkout_group(conn: PgConn, group_id: str) -> None:
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{group_id}', '{CUSTOMER_ID}', 'cg-{group_id}',
          {GROSS_NGEWEE}, 0, {GROSS_NGEWEE}, 'completed'
        ) ON CONFLICT (id) DO NOTHING;
        """
    )


def _insert_order(
    conn: PgConn,
    *,
    order_id: str,
    group_id: str,
    status: str,
) -> None:
    snapshot_sql = json.dumps(COMMISSION_SNAPSHOT).replace("'", "''")
    _insert_checkout_group(conn, group_id)
    conn.run(
        f"""
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
          delivery_fee_ngwee, cod, commission_snapshot
        ) VALUES (
          '{order_id}', '{group_id}', '{VENDOR_A}', '{CUSTOMER_ID}',
          '{status}', 'delivery', 0, false, '{snapshot_sql}'::jsonb
        ) ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.order_items (
          id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', 'product', 1, {GROSS_NGEWEE}, 'Test item'
        );
        """
    )


def _insert_order_event(
    conn: PgConn,
    *,
    order_id: str,
    from_status: str | None,
    to_status: str,
    actor: str | None,
    created_at: datetime,
    note: str | None = None,
) -> None:
    actor_sql = f"'{actor}'::uuid" if actor else "NULL"
    from_sql = f"'{from_status}'" if from_status else "NULL"
    note_sql = f"'{note.replace(chr(39), chr(39) * 2)}'" if note else "NULL"
    ts = created_at.astimezone(UTC).isoformat()
    conn.run(
        f"""
        INSERT INTO public.order_events (
          id, order_id, actor, from_status, to_status, note, created_at
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', {actor_sql}, {from_sql},
          '{to_status}', {note_sql}, '{ts}'::timestamptz
        );
        """
    )


def _insert_dispute(conn: PgConn, *, order_id: str, status: str = "open") -> None:
    conn.run(
        f"""
        INSERT INTO public.disputes (
          id, order_id, opener_user_id, status
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', '{CUSTOMER_ID}', '{status}'
        );
        """
    )


def _order_status(conn: PgConn, order_id: str) -> str:
    result = conn.run(f"SELECT status FROM public.orders WHERE id = '{order_id}';")
    assert result.ok and result.rows
    return result.rows[0]


def _auto_confirm_event_count(conn: PgConn, order_id: str) -> int:
    result = conn.run(
        f"""
        SELECT count(*)::text
        FROM public.order_events
        WHERE order_id = '{order_id}'
          AND to_status = 'completed'
          AND actor = '{SYSTEM_ACTOR_ID}'::uuid;
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _release_txn_count(conn: PgConn, order_id: str) -> int:
    key = release_idempotency_key(order_id)
    result = conn.run(
        f"""
        SELECT count(*)::text
        FROM public.ledger_transactions
        WHERE idempotency_key = '{key}';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _seed_escrow(conn: PgConn, *, suffix: str) -> None:
    from app.services.ledger.engine import post_transaction
    from app.services.ledger.templates import LedgerTemplate

    post_transaction(
        idempotency_key=f"charge-{suffix}",
        template=LedgerTemplate.CHARGE_RECEIVED,
        gross_ngwee=GROSS_NGEWEE,
    )
    post_transaction(
        idempotency_key=f"commission-{suffix}",
        template=LedgerTemplate.COMMISSION_CAPTURE,
        gross_ngwee=GROSS_NGEWEE,
        commission_bps=COMMISSION_BPS,
    )


def _auth_headers() -> dict[str, str]:
    return {"X-Internal-Token": INTERNAL_TOKEN}


class TestInternalTokenGuard:
    def test_auto_confirm_requires_token(self, jobs_client: TestClient) -> None:
        denied = jobs_client.post(AUTO_CONFIRM_PATH, json={"limit": 10})
        assert denied.status_code == 401

        wrong = jobs_client.post(
            AUTO_CONFIRM_PATH,
            json={"limit": 10},
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert wrong.status_code == 401

    def test_auto_release_requires_token(self, jobs_client: TestClient) -> None:
        denied = jobs_client.post(AUTO_RELEASE_PATH, json={"limit": 10})
        assert denied.status_code == 401


@pytest.mark.usefixtures("db_url_env")
class TestAutoConfirmJob:
    def test_double_run_idempotent(
        self,
        db: PgConn,
        jobs_client: TestClient,
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        delivered_at = now - timedelta(hours=DEFAULT_RELEASE_AFTER_DELIVERED_HOURS, minutes=1)

        _insert_order(db, order_id=order_id, group_id=group_id, status="delivered")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="shipped",
            to_status="delivered",
            actor=VENDOR_A,
            created_at=delivered_at,
        )
        _seed_escrow(db, suffix=order_id)

        with patch("app.routers.internal_order_jobs.datetime") as mocked_dt:
            mocked_dt.now.return_value = now
            mocked_dt.UTC = UTC
            first = jobs_client.post(AUTO_CONFIRM_PATH, json={"limit": 10}, headers=_auth_headers())
            second = jobs_client.post(
                AUTO_CONFIRM_PATH, json={"limit": 10}, headers=_auth_headers()
            )

        assert first.status_code == 200
        assert first.json()["confirmed"] == 1
        assert second.status_code == 200
        assert second.json()["confirmed"] == 0
        assert _order_status(db, order_id) == "completed"
        assert _auto_confirm_event_count(db, order_id) == 1
        assert _release_txn_count(db, order_id) == 1

    def test_skips_disputed_order(
        self,
        db: PgConn,
        jobs_client: TestClient,
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        delivered_at = now - timedelta(hours=DEFAULT_RELEASE_AFTER_DELIVERED_HOURS + 1)

        _insert_order(db, order_id=order_id, group_id=group_id, status="delivered")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="shipped",
            to_status="delivered",
            actor=VENDOR_A,
            created_at=delivered_at,
        )
        _insert_dispute(db, order_id=order_id)
        _seed_escrow(db, suffix=order_id)

        with patch("app.routers.internal_order_jobs.datetime") as mocked_dt:
            mocked_dt.now.return_value = now
            mocked_dt.UTC = UTC
            response = jobs_client.post(
                AUTO_CONFIRM_PATH, json={"limit": 10}, headers=_auth_headers()
            )

        assert response.status_code == 200
        assert response.json()["confirmed"] == 0
        assert _order_status(db, order_id) == "delivered"
        assert _auto_confirm_event_count(db, order_id) == 0

    def test_window_boundary(
        self,
        db: PgConn,
        jobs_client: TestClient,
    ) -> None:
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        too_early_id = str(uuid.uuid4())
        ready_id = str(uuid.uuid4())

        for order_id, hours_ago in (
            (too_early_id, DEFAULT_RELEASE_AFTER_DELIVERED_HOURS - (1 / 60)),
            (ready_id, DEFAULT_RELEASE_AFTER_DELIVERED_HOURS + (1 / 60)),
        ):
            group_id = str(uuid.uuid4())
            _insert_order(db, order_id=order_id, group_id=group_id, status="delivered")
            _insert_order_event(
                db,
                order_id=order_id,
                from_status="shipped",
                to_status="delivered",
                actor=VENDOR_A,
                created_at=now - timedelta(hours=hours_ago),
            )
            _seed_escrow(db, suffix=order_id)

        with patch("app.routers.internal_order_jobs.datetime") as mocked_dt:
            mocked_dt.now.return_value = now
            mocked_dt.UTC = UTC
            response = jobs_client.post(
                AUTO_CONFIRM_PATH, json={"limit": 10}, headers=_auth_headers()
            )

        assert response.status_code == 200
        assert _order_status(db, too_early_id) == "delivered"
        assert _order_status(db, ready_id) == "completed"
        assert response.json()["confirmed"] == 1


@pytest.mark.usefixtures("db_url_env")
class TestAutoReleaseJob:
    def test_double_run_idempotent(
        self,
        db: PgConn,
        jobs_client: TestClient,
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        shipped_at = now - timedelta(days=DEFAULT_RELEASE_AFTER_SHIPPED_DAYS, hours=1)

        _insert_order(db, order_id=order_id, group_id=group_id, status="shipped")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="processing",
            to_status="shipped",
            actor=VENDOR_A,
            created_at=shipped_at,
        )
        _seed_escrow(db, suffix=order_id)

        with patch("app.routers.internal_order_jobs.datetime") as mocked_dt:
            mocked_dt.now.return_value = now
            mocked_dt.UTC = UTC
            first = jobs_client.post(AUTO_RELEASE_PATH, json={"limit": 10}, headers=_auth_headers())
            second = jobs_client.post(
                AUTO_RELEASE_PATH, json={"limit": 10}, headers=_auth_headers()
            )

        assert first.status_code == 200
        assert first.json()["released"] == 1
        assert second.status_code == 200
        assert second.json()["released"] == 0
        assert second.json()["already_released"] == 1
        assert _release_txn_count(db, order_id) == 1

    def test_skips_disputed_order(
        self,
        db: PgConn,
        jobs_client: TestClient,
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        shipped_at = now - timedelta(days=DEFAULT_RELEASE_AFTER_SHIPPED_DAYS + 1)

        _insert_order(db, order_id=order_id, group_id=group_id, status="shipped")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="processing",
            to_status="shipped",
            actor=VENDOR_A,
            created_at=shipped_at,
        )
        _insert_dispute(db, order_id=order_id)
        _seed_escrow(db, suffix=order_id)

        with patch("app.routers.internal_order_jobs.datetime") as mocked_dt:
            mocked_dt.now.return_value = now
            mocked_dt.UTC = UTC
            response = jobs_client.post(
                AUTO_RELEASE_PATH, json={"limit": 10}, headers=_auth_headers()
            )

        assert response.status_code == 200
        assert response.json()["released"] == 0
        assert response.json()["scanned"] == 0
        assert _release_txn_count(db, order_id) == 0

    def test_window_boundary(
        self,
        db: PgConn,
        jobs_client: TestClient,
    ) -> None:
        now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        too_early_id = str(uuid.uuid4())
        ready_id = str(uuid.uuid4())

        for order_id, days_ago in (
            (too_early_id, DEFAULT_RELEASE_AFTER_SHIPPED_DAYS - (1 / 1440)),
            (ready_id, DEFAULT_RELEASE_AFTER_SHIPPED_DAYS + (1 / 1440)),
        ):
            group_id = str(uuid.uuid4())
            _insert_order(db, order_id=order_id, group_id=group_id, status="shipped")
            _insert_order_event(
                db,
                order_id=order_id,
                from_status="processing",
                to_status="shipped",
                actor=VENDOR_A,
                created_at=now - timedelta(days=days_ago),
            )
            _seed_escrow(db, suffix=order_id)

        with patch("app.routers.internal_order_jobs.datetime") as mocked_dt:
            mocked_dt.now.return_value = now
            mocked_dt.UTC = UTC
            response = jobs_client.post(
                AUTO_RELEASE_PATH, json={"limit": 10}, headers=_auth_headers()
            )

        assert response.status_code == 200
        assert _release_txn_count(db, too_early_id) == 0
        assert _release_txn_count(db, ready_id) == 1
        assert response.json()["released"] == 1


class TestAutoConfirmJobMocked:
    def test_double_run_idempotent_mocked(
        self,
        jobs_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.services.orders.state import OrderStatus, TransitionOutcome

        order_id = str(uuid.uuid4())
        transition_calls = 0
        release_calls = 0

        def fake_candidates(**_kwargs: object) -> list[str]:
            return [order_id]

        def fake_transition(**_kwargs: object) -> TransitionOutcome:
            nonlocal transition_calls
            transition_calls += 1
            if transition_calls > 1:
                raise OrderTransitionError(
                    "already completed",
                    from_status=OrderStatus.DELIVERED.value,
                    event="auto_confirm",
                    actor_role="system",
                )
            return TransitionOutcome(
                order_id=order_id,
                from_status=OrderStatus.DELIVERED,
                to_status=OrderStatus.COMPLETED,
                event=OrderEvent.AUTO_CONFIRM,
                actor_id=SYSTEM_ACTOR_ID,
                note="Auto-confirmed after delivery window",
            )

        def fake_release(_service: object, candidate_id: str) -> object:
            nonlocal release_calls
            assert candidate_id == order_id
            release_calls += 1
            from app.services.escrow.release import ReleaseResult

            return ReleaseResult(
                order_id=candidate_id,
                outcome="released",
                reason="buyer_confirm_received",
                rule="buyer_confirm",
            )

        monkeypatch.setattr(
            "app.routers.internal_order_jobs._list_auto_confirm_candidates",
            fake_candidates,
        )
        monkeypatch.setattr("app.routers.internal_order_jobs.transition_order", fake_transition)
        monkeypatch.setattr("app.routers.internal_order_jobs.evaluate_and_release", fake_release)

        first = jobs_client.post(AUTO_CONFIRM_PATH, json={"limit": 10}, headers=_auth_headers())
        second = jobs_client.post(AUTO_CONFIRM_PATH, json={"limit": 10}, headers=_auth_headers())

        assert first.status_code == 200
        assert first.json()["confirmed"] == 1
        assert second.status_code == 200
        assert second.json()["confirmed"] == 0
        assert transition_calls == 2
        assert release_calls == 1


class TestAutoReleaseJobMocked:
    def test_double_run_idempotent_mocked(
        self,
        jobs_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.services.escrow.release import ReleaseResult

        order_id = str(uuid.uuid4())
        release_calls = 0

        def fake_candidates(**_kwargs: object) -> list[str]:
            return [order_id]

        def fake_release(_service: object, candidate_id: str) -> ReleaseResult:
            nonlocal release_calls
            release_calls += 1
            if release_calls == 1:
                return ReleaseResult(
                    order_id=candidate_id,
                    outcome="released",
                    reason="shipped_fallback",
                    rule="shipped_fallback",
                )
            return ReleaseResult(
                order_id=candidate_id,
                outcome="already_released",
                reason="release_already_posted",
            )

        monkeypatch.setattr(
            "app.routers.internal_order_jobs._list_auto_release_candidates",
            fake_candidates,
        )
        monkeypatch.setattr("app.routers.internal_order_jobs.evaluate_and_release", fake_release)

        first = jobs_client.post(AUTO_RELEASE_PATH, json={"limit": 10}, headers=_auth_headers())
        second = jobs_client.post(
            AUTO_RELEASE_PATH, json={"limit": 10}, headers=_auth_headers()
        )

        assert first.status_code == 200
        assert first.json()["released"] == 1
        assert second.status_code == 200
        assert second.json()["released"] == 0
        assert second.json()["already_released"] == 1
        assert release_calls == 2
