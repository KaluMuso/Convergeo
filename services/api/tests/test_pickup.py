from __future__ import annotations

import concurrent.futures
import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.services.orders.state import (
    ActorRole,
    OrderEvent,
    OrderStatus,
    count_audit_events,
    fetch_latest_audit_event,
    transition_order,
)
from app.services.pickup import issue_pickup_tokens, verify_pickup_by_pin, verify_pickup_by_qr
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_A_OWNER = "33333333-3333-3333-3333-333333333333"
VENDOR_B_OWNER = "44444444-4444-4444-4444-444444444444"
SHOP_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SHOP_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TOKEN_B = "vendor-b-token"


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
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    import os

    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def _insert_checkout_group(conn: PgConn, group_id: str, *, key_suffix: str = "") -> None:
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
        ) VALUES (
          '{group_id}', '{CUSTOMER_ID}', 'pickup-{group_id}{key_suffix}', 10000, 0, 10000
        )
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _insert_pickup_order(
    conn: PgConn,
    *,
    order_id: str,
    checkout_group_id: str,
    vendor_id: str = SHOP_A,
    status: str = "ready",
) -> None:
    _insert_checkout_group(conn, checkout_group_id)
    conn.run(
        f"""
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment, cod
        ) VALUES (
          '{order_id}', '{checkout_group_id}', '{vendor_id}', '{CUSTOMER_ID}',
          '{status}', 'pickup', false
        )
        ON CONFLICT (id) DO UPDATE
          SET status = EXCLUDED.status,
              vendor_id = EXCLUDED.vendor_id,
              fulfilment = EXCLUDED.fulfilment,
              checkout_group_id = EXCLUDED.checkout_group_id,
              pickup_qr_secret = NULL,
              pickup_pin_hash = NULL,
              pickup_collected_at = NULL,
              pickup_token_version = 0;
        """
    )


def _order_status(conn: PgConn, order_id: str) -> str:
    result = conn.run(f"SELECT status FROM public.orders WHERE id = '{order_id}';")
    assert result.ok and result.rows
    return result.rows[0]


def _pickup_collected(conn: PgConn, order_id: str) -> bool:
    result = conn.run(
        f"SELECT pickup_collected_at IS NOT NULL FROM public.orders WHERE id = '{order_id}';"
    )
    assert result.ok and result.rows
    return result.rows[0] == "t"


def _prepare_ready_pickup_order(conn: PgConn) -> tuple[str, str]:
    order_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    _insert_pickup_order(conn, order_id=order_id, checkout_group_id=group_id)
    issued = issue_pickup_tokens(order_id=order_id)
    return order_id, issued.qr_token


def _mock_auth(monkeypatch: pytest.MonkeyPatch, user_id: str) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: frozenset({"vendor"}),
    )


@pytest.mark.usefixtures("db", "db_url_env")
class TestPickupIssueAndVerify:
    def test_pin_fallback_verifies_and_transitions(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_pickup_order(db, order_id=order_id, checkout_group_id=group_id)
        issued = issue_pickup_tokens(order_id=order_id)

        result = verify_pickup_by_pin(
            order_id=order_id,
            pin=issued.pin,
            vendor_id=SHOP_A,
            actor_id=VENDOR_A_OWNER,
        )

        assert result.transition.to_status == OrderStatus.DELIVERED
        assert _order_status(db, order_id) == "delivered"
        assert _pickup_collected(db, order_id)

        audit = fetch_latest_audit_event(order_id)
        assert audit is not None
        assert audit["from_status"] == "ready"
        assert audit["to_status"] == "delivered"
        assert audit["actor"] == VENDOR_A_OWNER

    def test_qr_verify_transitions_via_state_machine(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_pickup_order(db, order_id=order_id, checkout_group_id=group_id)
        issued = issue_pickup_tokens(order_id=order_id)
        before_audit = count_audit_events(order_id)

        result = verify_pickup_by_qr(
            qr_token=issued.qr_token,
            vendor_id=SHOP_A,
            actor_id=VENDOR_A_OWNER,
        )

        assert result.transition.event == OrderEvent.VERIFY_PICKUP
        assert result.transition.to_status == OrderStatus.DELIVERED
        assert count_audit_events(order_id) == before_audit + 1


@pytest.mark.usefixtures("db", "db_url_env")
class TestPickupSingleUse:
    def test_second_verify_rejected(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_pickup_order(db, order_id=order_id, checkout_group_id=group_id)
        issued = issue_pickup_tokens(order_id=order_id)

        verify_pickup_by_qr(
            qr_token=issued.qr_token,
            vendor_id=SHOP_A,
            actor_id=VENDOR_A_OWNER,
        )

        with pytest.raises(AppError) as exc:
            verify_pickup_by_qr(
                qr_token=issued.qr_token,
                vendor_id=SHOP_A,
                actor_id=VENDOR_A_OWNER,
            )
        assert exc.value.code == "pickup_already_claimed"
        assert exc.value.http_status == 409

    def test_single_use_race_exactly_one_winner(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_pickup_order(db, order_id=order_id, checkout_group_id=group_id)
        issued = issue_pickup_tokens(order_id=order_id)

        def attempt() -> str:
            try:
                verify_pickup_by_qr(
                    qr_token=issued.qr_token,
                    vendor_id=SHOP_A,
                    actor_id=VENDOR_A_OWNER,
                )
                return "ok"
            except AppError as exc:
                return exc.code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = (executor.submit(attempt), executor.submit(attempt))
            results = [future.result() for future in futures]

        assert results.count("ok") == 1
        assert results.count("pickup_already_claimed") == 1
        assert _order_status(db, order_id) == "delivered"
        assert count_audit_events(order_id) == 1


@pytest.mark.usefixtures("db", "db_url_env")
class TestPickupAuthzAndStaleTokens:
    def test_wrong_vendor_verify_rejected(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_pickup_order(db, order_id=order_id, checkout_group_id=group_id)
        issued = issue_pickup_tokens(order_id=order_id)

        with pytest.raises(AppError) as exc:
            verify_pickup_by_qr(
                qr_token=issued.qr_token,
                vendor_id=SHOP_B,
                actor_id=VENDOR_B_OWNER,
            )
        assert exc.value.http_status == 403
        assert _order_status(db, order_id) == "ready"
        assert not _pickup_collected(db, order_id)

    def test_reissue_invalidates_prior_token(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_pickup_order(db, order_id=order_id, checkout_group_id=group_id)
        first = issue_pickup_tokens(order_id=order_id)
        reissued = issue_pickup_tokens(order_id=order_id, reissue=True)
        assert reissued.token_version == first.token_version + 1

        with pytest.raises(AppError) as exc:
            verify_pickup_by_qr(
                qr_token=first.qr_token,
                vendor_id=SHOP_A,
                actor_id=VENDOR_A_OWNER,
            )
        assert exc.value.code == "pickup_token_stale"

        result = verify_pickup_by_qr(
            qr_token=reissued.qr_token,
            vendor_id=SHOP_A,
            actor_id=VENDOR_A_OWNER,
        )
        assert result.transition.to_status == OrderStatus.DELIVERED


@pytest.mark.usefixtures("db", "db_url_env")
class TestPickupHttp:
    def test_wrong_vendor_http_returns_403(
        self,
        db: PgConn,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        order_id, qr_token = _prepare_ready_pickup_order(db)
        _mock_auth(monkeypatch, VENDOR_B_OWNER)

        service_wrapper = MagicMock()
        real_client = MagicMock()
        real_client.table.side_effect = lambda name: _VendorLookupTable(name)
        service_wrapper.client = real_client

        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: service_wrapper

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/vendor/pickup/verify",
                headers={"Authorization": f"Bearer {TOKEN_B}"},
                json={"qr_token": qr_token},
            )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
        assert _order_status(db, order_id) == "ready"


class _VendorLookupTable:
    def __init__(self, name: str) -> None:
        self._name = name

    def select(self, columns: str) -> _VendorLookupQuery:
        return _VendorLookupQuery(self._name)


class _VendorLookupQuery:
    def __init__(self, name: str) -> None:
        self._name = name

    def eq(self, column: str, value: Any) -> _VendorLookupQuery:
        return self

    def maybe_single(self) -> _VendorLookupQuery:
        return self

    def execute(self) -> MagicMock:
        if self._name != "vendors":
            raise AssertionError(f"unexpected table {self._name}")
        return MagicMock(
            data={
                "id": SHOP_B,
                "owner_user_id": VENDOR_B_OWNER,
            }
        )


@pytest.mark.usefixtures("db", "db_url_env")
class TestMigration0017:
    def test_migration_replays_clean(self, db: PgConn) -> None:
        result = db.run(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'orders'
              AND column_name LIKE 'pickup_%'
            ORDER BY column_name;
            """
        )
        assert result.ok
        assert result.rows == [
            "pickup_collected_at",
            "pickup_pin_hash",
            "pickup_qr_secret",
            "pickup_token_version",
        ]

        trigger = db.run(
            """
            SELECT tgname
            FROM pg_trigger
            WHERE tgname = 'orders_guard_pickup_tokens';
            """
        )
        assert trigger.ok and trigger.rows == ["orders_guard_pickup_tokens"]

    def test_ready_for_pickup_issue_on_transition_path(self, db: PgConn) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        _insert_pickup_order(
            db,
            order_id=order_id,
            checkout_group_id=group_id,
            status="processing",
        )
        transition_order(
            order_id=order_id,
            event=OrderEvent.READY_FOR_PICKUP,
            actor_role=ActorRole.VENDOR,
            actor_id=VENDOR_A_OWNER,
            note="ready for pickup",
        )
        issued = issue_pickup_tokens(order_id=order_id)
        assert issued.token_version == 1
        assert len(issued.pin) == 6
        assert issued.qr_token
