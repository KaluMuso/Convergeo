from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.orders.create import (
    CartLineInput,
    VendorFulfilmentInput,
    create_orders_atomic,
)
from app.services.stock.claim import claim_reservation
from app.supabase_client import SupabaseServiceClient
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    seed_matrix_fixtures,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "demo"
CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ADDRESS_ID = "a0000000-0000-0000-0000-000000000001"
VALID_TOKEN = "valid-test-token"


def _load_ids() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES_DIR / "ids.json").read_text()))


@dataclass
class _Query:
    conn: PgConn
    table: str
    columns: str = "*"
    filters: list[tuple[str, str, Any]] | None = None
    order_by: tuple[str, bool] | None = None
    row_limit: int | None = None
    single: bool = False
    payload: dict[str, Any] | None = None
    operation: str = "select"

    def select(self, columns: str) -> _Query:
        self.columns = columns
        self.operation = "select"
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self.filters = (self.filters or []) + [("eq", column, value)]
        return self

    def in_(self, column: str, values: list[str]) -> _Query:
        self.filters = (self.filters or []) + [("in", column, values)]
        return self

    def order(self, column: str, *, desc: bool = False) -> _Query:
        self.order_by = (column, desc)
        return self

    def limit(self, value: int) -> _Query:
        self.row_limit = value
        return self

    def maybe_single(self) -> _Query:
        self.single = True
        return self

    def update(self, payload: dict[str, Any]) -> _Query:
        self.payload = payload
        self.operation = "update"
        return self

    def execute(self) -> MagicMock:
        if self.operation == "update":
            return MagicMock(data=self._run_update())
        return MagicMock(data=self._run_select())

    def _where_sql(self) -> str:
        clauses: list[str] = []
        if not self.filters:
            return ""
        for op, column, value in self.filters:
            if op == "eq":
                if isinstance(value, str):
                    clauses.append(f"{column} = '{value}'")
                else:
                    clauses.append(f"{column} = {value}")
            elif op == "in" and isinstance(value, list):
                quoted = ", ".join(f"'{item}'" for item in value)
                clauses.append(f"{column} IN ({quoted})")
        return " AND ".join(clauses)

    def _run_update(self) -> list[dict[str, Any]]:
        assert self.payload is not None
        where = self._where_sql()
        sets = ", ".join(
            f"{key} = '{val}'" if isinstance(val, str) else f"{key} = {val}"
            for key, val in self.payload.items()
        )
        sql = f"UPDATE public.{self.table} SET {sets}"
        if where:
            sql += f" WHERE {where}"
        sql += ";"
        result = self.conn.run(sql)
        assert result.ok, result.error
        return []

    def _run_select(self) -> Any:
        if self.table == "vendor_listings" and "categories(commission_key)" in self.columns:
            return self._listing_commission_rows()
        where = self._where_sql()
        sql = f"SELECT row_to_json(t)::text FROM public.{self.table} t"
        if where:
            sql += f" WHERE {where}"
        if self.order_by is not None:
            column, desc = self.order_by
            sql += f" ORDER BY t.{column} {'DESC' if desc else 'ASC'}"
        if self.row_limit is not None:
            sql += f" LIMIT {self.row_limit}"
        sql += ";"
        result = self.conn.run(sql)
        assert result.ok, result.error
        rows = [json.loads(line) for line in result.rows]
        if self.single:
            return rows[0] if rows else None
        return rows

    def _listing_commission_rows(self) -> list[dict[str, Any]]:
        in_filter = next((f for f in (self.filters or []) if f[0] == "in"), None)
        listing_ids = in_filter[2] if in_filter else []
        quoted = ", ".join(f"'{listing_id}'" for listing_id in listing_ids)
        sql = f"""
        SELECT
          vl.id::text,
          vl.product_id::text,
          c.commission_key
        FROM public.vendor_listings vl
        LEFT JOIN public.products p ON p.id = vl.product_id
        LEFT JOIN public.categories c ON c.id = p.category_id
        WHERE vl.id IN ({quoted});
        """
        result = self.conn.run(sql)
        assert result.ok, result.error
        rows: list[dict[str, Any]] = []
        for line in result.rows:
            parts = line.split("|")
            if len(parts) != 3:
                continue
            listing_id, product_id, commission_key = parts
            category = {"commission_key": commission_key} if commission_key else None
            product: dict[str, Any] = {"category_id": None, "categories": category}
            if product_id:
                product["category_id"] = product_id
            rows.append(
                {
                    "id": listing_id,
                    "product_id": product_id or None,
                    "products": product if product_id else None,
                }
            )
        return rows


class _PgClient:
    def __init__(self, conn: PgConn) -> None:
        self._conn = conn

    def table(self, name: str) -> _Query:
        return _Query(conn=self._conn, table=name)


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    admin = PgConn("postgresql://postgres:postgres@127.0.0.1:5432/postgres")
    if not admin.run("SELECT 1").ok:
        pytest.skip("Postgres not reachable on 127.0.0.1:5432")
    admin.run("DROP DATABASE IF EXISTS vergeo5_order_test;")
    admin.run("CREATE DATABASE vergeo5_order_test;")

    url = "postgresql://postgres:postgres@127.0.0.1:5432/vergeo5_order_test"
    conn = PgConn(url)
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


@pytest.fixture
def pg_service(db: PgConn) -> SupabaseServiceClient:
    return SupabaseServiceClient(_PgClient(db))  # type: ignore[arg-type]


def _insert_checkout_group(
    conn: PgConn,
    *,
    session_id: str,
    idempotency_key: str,
    subtotal: int,
    delivery_fee: int,
    total: int,
    status: str = "pending",
) -> None:
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key,
          subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{session_id}', '{CUSTOMER_ID}', '{idempotency_key}',
          {subtotal}, {delivery_fee}, {total}, '{status}'
        )
        ON CONFLICT (id) DO UPDATE
          SET subtotal_ngwee = EXCLUDED.subtotal_ngwee,
              delivery_fee_ngwee = EXCLUDED.delivery_fee_ngwee,
              total_ngwee = EXCLUDED.total_ngwee,
              status = EXCLUDED.status,
              idempotency_key = EXCLUDED.idempotency_key;
        """
    )


def _insert_cart_with_items(
    conn: PgConn,
    *,
    cart_id: str,
    items: list[tuple[str, int, int]],
) -> None:
    conn.run(
        f"""
        INSERT INTO public.carts (id, user_id, status)
        VALUES ('{cart_id}', '{CUSTOMER_ID}', 'active')
        ON CONFLICT (id) DO UPDATE SET status = 'active';
        """
    )
    conn.run(f"DELETE FROM public.cart_items WHERE cart_id = '{cart_id}';")
    for listing_id, qty, unit_price in items:
        item_id = str(uuid.uuid4())
        conn.run(
            f"""
            INSERT INTO public.cart_items (
              id, cart_id, listing_id, qty, unit_price_ngwee, wholesale
            ) VALUES (
              '{item_id}', '{cart_id}', '{listing_id}', {qty}, {unit_price}, false
            );
            """
        )


def _insert_tracked_listing(
    conn: PgConn,
    *,
    listing_id: str,
    vendor_id: str,
    product_id: str,
    stock_qty: int,
    price_ngwee: int,
) -> None:
    conn.run(
        f"""
        INSERT INTO public.vendor_listings (
          id, vendor_id, product_id, price_ngwee, condition, stock_mode, stock_qty, status
        ) VALUES (
          '{listing_id}', '{vendor_id}', '{product_id}', {price_ngwee},
          'new', 'tracked', {stock_qty}, 'active'
        )
        ON CONFLICT (id) DO UPDATE
          SET stock_qty = EXCLUDED.stock_qty,
              price_ngwee = EXCLUDED.price_ngwee,
              vendor_id = EXCLUDED.vendor_id,
              product_id = EXCLUDED.product_id,
              status = 'active';
        """
    )


def _reservation_count(conn: PgConn, checkout_group_id: str) -> int:
    result = conn.run(
        f"""
        SELECT count(*)::text FROM public.stock_reservations
        WHERE checkout_group_id = '{checkout_group_id}';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _order_count(conn: PgConn, checkout_group_id: str) -> int:
    result = conn.run(
        f"""
        SELECT count(*)::text FROM public.orders
        WHERE checkout_group_id = '{checkout_group_id}';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _outbox_count(conn: PgConn, order_id: str) -> int:
    result = conn.run(
        f"""
        SELECT count(*)::text FROM public.notification_outbox
        WHERE dedupe_key = 'order.placed:{order_id}:whatsapp';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _group_status(conn: PgConn, session_id: str) -> str:
    result = conn.run(
        f"SELECT status FROM public.checkout_groups WHERE id = '{session_id}';"
    )
    assert result.ok and result.rows
    return result.rows[0]


def _build_lines(
    listing_a: str,
    listing_b: str,
    qty_a: int,
    qty_b: int,
    price_a: int,
    price_b: int,
) -> list[CartLineInput]:
    return [
        CartLineInput(
            cart_item_id=str(uuid.uuid4()),
            listing_id=listing_a,
            vendor_id=VENDOR_A,
            qty=qty_a,
            unit_price_ngwee=price_a,
            title_snapshot="Phone",
        ),
        CartLineInput(
            cart_item_id=str(uuid.uuid4()),
            listing_id=listing_b,
            vendor_id=VENDOR_B,
            qty=qty_b,
            unit_price_ngwee=price_b,
            title_snapshot="Chitenge",
        ),
    ]


class TestCreateOrdersAtomic:
    def test_idempotency_replay_returns_identical_group(
        self, db: PgConn, db_url_env: None, pg_service: SupabaseServiceClient
    ) -> None:
        ids = _load_ids()
        session_id = str(uuid.uuid4())
        listing_a = str(uuid.uuid4())
        listing_b = str(uuid.uuid4())
        price_a = 150_000
        price_b = 85_000
        subtotal = price_a + price_b
        delivery_a = 3_000
        delivery_b = 0
        total = subtotal + delivery_a + delivery_b
        idem_key = f"client-idem-{uuid.uuid4()}"

        _insert_tracked_listing(
            db,
            listing_id=listing_a,
            vendor_id=VENDOR_A,
            product_id=ids["products"]["phone"],
            stock_qty=5,
            price_ngwee=price_a,
        )
        _insert_tracked_listing(
            db,
            listing_id=listing_b,
            vendor_id=VENDOR_B,
            product_id=ids["products"]["chitenge"],
            stock_qty=5,
            price_ngwee=price_b,
        )
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=subtotal,
            delivery_fee=delivery_a,
            total=total,
        )
        claim_reservation(
            listing_id=listing_a, checkout_group_id=session_id, qty=1, ttl_minutes=15
        )
        claim_reservation(
            listing_id=listing_b, checkout_group_id=session_id, qty=1, ttl_minutes=15
        )

        lines = _build_lines(listing_a, listing_b, 1, 1, price_a, price_b)
        groups = [
            VendorFulfilmentInput(
                vendor_id=VENDOR_A,
                fulfilment="delivery",
                delivery_zone="lusaka_a",
                delivery_fee_ngwee=delivery_a,
                subtotal_ngwee=price_a,
            ),
            VendorFulfilmentInput(
                vendor_id=VENDOR_B,
                fulfilment="pickup",
                delivery_zone=None,
                delivery_fee_ngwee=delivery_b,
                subtotal_ngwee=price_b,
            ),
        ]

        first = create_orders_atomic(
            client=pg_service.client,
            customer_id=CUSTOMER_ID,
            session_id=session_id,
            idempotency_key=idem_key,
            payment_method="momo",
            cart_lines=lines,
            vendor_groups=groups,
            address_id=ADDRESS_ID,
        )
        second = create_orders_atomic(
            client=pg_service.client,
            customer_id=CUSTOMER_ID,
            session_id=session_id,
            idempotency_key=idem_key,
            payment_method="momo",
            cart_lines=lines,
            vendor_groups=groups,
            address_id=ADDRESS_ID,
        )

        assert first.replayed is False
        assert second.replayed is True
        assert first.checkout_group_id == second.checkout_group_id
        assert first.idempotency_key == second.idempotency_key == idem_key
        assert _order_count(db, session_id) == 2

    def test_rollback_injection_writes_nothing(
        self, db: PgConn, db_url_env: None, pg_service: SupabaseServiceClient
    ) -> None:
        ids = _load_ids()
        session_id = str(uuid.uuid4())
        listing_id = str(uuid.uuid4())
        price = 100_000
        idem_key = f"rollback-{uuid.uuid4()}"

        _insert_tracked_listing(
            db,
            listing_id=listing_id,
            vendor_id=VENDOR_A,
            product_id=ids["products"]["phone"],
            stock_qty=3,
            price_ngwee=price,
        )
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=price,
            delivery_fee=0,
            total=price,
        )
        claim_reservation(
            listing_id=listing_id, checkout_group_id=session_id, qty=1, ttl_minutes=15
        )
        lines = [
            CartLineInput(
                cart_item_id=str(uuid.uuid4()),
                listing_id=listing_id,
                vendor_id=VENDOR_A,
                qty=1,
                unit_price_ngwee=price,
                title_snapshot="Phone",
            )
        ]
        groups = [
            VendorFulfilmentInput(
                vendor_id=VENDOR_A,
                fulfilment="pickup",
                delivery_zone=None,
                delivery_fee_ngwee=0,
                subtotal_ngwee=price,
            )
        ]

        with pytest.raises(RuntimeError, match="order creation failed"):
            create_orders_atomic(
                client=pg_service.client,
                customer_id=CUSTOMER_ID,
                session_id=session_id,
                idempotency_key=idem_key,
                payment_method="card",
                cart_lines=lines,
                vendor_groups=groups,
                inject_failure="before_commit",
            )

        assert _group_status(db, session_id) == "pending"
        assert _order_count(db, session_id) == 0
        assert _reservation_count(db, session_id) == 1

    def test_multi_vendor_split_math_ngwee_exact(
        self, db: PgConn, db_url_env: None, pg_service: SupabaseServiceClient
    ) -> None:
        ids = _load_ids()
        session_id = str(uuid.uuid4())
        listing_a = str(uuid.uuid4())
        listing_b = str(uuid.uuid4())
        price_a = 200_000
        price_b = 50_000
        subtotal = price_a + price_b
        delivery_a = 5_000
        delivery_b = 0
        total = subtotal + delivery_a

        _insert_tracked_listing(
            db,
            listing_id=listing_a,
            vendor_id=VENDOR_A,
            product_id=ids["products"]["phone"],
            stock_qty=4,
            price_ngwee=price_a,
        )
        _insert_tracked_listing(
            db,
            listing_id=listing_b,
            vendor_id=VENDOR_B,
            product_id=ids["products"]["chitenge"],
            stock_qty=4,
            price_ngwee=price_b,
        )
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=subtotal,
            delivery_fee=delivery_a,
            total=total,
        )
        claim_reservation(
            listing_id=listing_a, checkout_group_id=session_id, qty=1, ttl_minutes=15
        )
        claim_reservation(
            listing_id=listing_b, checkout_group_id=session_id, qty=1, ttl_minutes=15
        )

        result = create_orders_atomic(
            client=pg_service.client,
            customer_id=CUSTOMER_ID,
            session_id=session_id,
            idempotency_key=f"math-{uuid.uuid4()}",
            payment_method="cod",
            cart_lines=_build_lines(listing_a, listing_b, 1, 1, price_a, price_b),
            vendor_groups=[
                VendorFulfilmentInput(
                    vendor_id=VENDOR_A,
                    fulfilment="delivery",
                    delivery_zone="lusaka_b",
                    delivery_fee_ngwee=delivery_a,
                    subtotal_ngwee=price_a,
                ),
                VendorFulfilmentInput(
                    vendor_id=VENDOR_B,
                    fulfilment="pickup",
                    delivery_zone=None,
                    delivery_fee_ngwee=delivery_b,
                    subtotal_ngwee=price_b,
                ),
            ],
            address_id=ADDRESS_ID,
        )

        assert result.subtotal_ngwee == subtotal
        assert result.delivery_fee_ngwee == delivery_a
        assert result.total_ngwee == total
        assert len(result.orders) == 2
        vendor_a = next(order for order in result.orders if order.vendor_id == VENDOR_A)
        vendor_b = next(order for order in result.orders if order.vendor_id == VENDOR_B)
        assert vendor_a.subtotal_ngwee + vendor_b.subtotal_ngwee == subtotal
        assert vendor_a.delivery_fee_ngwee + vendor_b.delivery_fee_ngwee == delivery_a
        assert (
            vendor_a.subtotal_ngwee
            + vendor_b.subtotal_ngwee
            + vendor_a.delivery_fee_ngwee
            + vendor_b.delivery_fee_ngwee
            == total
        )
        assert vendor_a.cod is True
        assert _reservation_count(db, session_id) == 0

    def test_commission_snapshot_immutable_after_rate_change(
        self, db: PgConn, db_url_env: None, pg_service: SupabaseServiceClient
    ) -> None:
        ids = _load_ids()
        session_id = str(uuid.uuid4())
        listing_id = str(uuid.uuid4())
        price = 450_000
        idem_key = f"snapshot-{uuid.uuid4()}"

        _insert_tracked_listing(
            db,
            listing_id=listing_id,
            vendor_id=VENDOR_A,
            product_id=ids["products"]["phone"],
            stock_qty=2,
            price_ngwee=price,
        )
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=price,
            delivery_fee=0,
            total=price,
        )
        claim_reservation(
            listing_id=listing_id, checkout_group_id=session_id, qty=1, ttl_minutes=15
        )

        result = create_orders_atomic(
            client=pg_service.client,
            customer_id=CUSTOMER_ID,
            session_id=session_id,
            idempotency_key=idem_key,
            payment_method="momo",
            cart_lines=[
                CartLineInput(
                    cart_item_id=str(uuid.uuid4()),
                    listing_id=listing_id,
                    vendor_id=VENDOR_A,
                    qty=1,
                    unit_price_ngwee=price,
                    title_snapshot="Phone",
                )
            ],
            vendor_groups=[
                VendorFulfilmentInput(
                    vendor_id=VENDOR_A,
                    fulfilment="pickup",
                    delivery_zone=None,
                    delivery_fee_ngwee=0,
                    subtotal_ngwee=price,
                )
            ],
        )
        snapshot = result.orders[0].commission_snapshot
        assert snapshot["rate_bps"] == 500
        assert snapshot["lines"][0]["category_key"] == "electronics"

        db.run(
            "UPDATE public.commission_rates SET rate_bps = 1500 WHERE category_key = 'electronics';"
        )
        stored = db.run(
            f"""
            SELECT commission_snapshot::text
            FROM public.orders
            WHERE checkout_group_id = '{session_id}'
            LIMIT 1;
            """
        )
        assert stored.ok and stored.rows
        persisted = json.loads(stored.rows[0])
        assert persisted == snapshot
        assert persisted["rate_bps"] == 500

    def test_order_placed_enqueued(
        self, db: PgConn, db_url_env: None, pg_service: SupabaseServiceClient
    ) -> None:
        ids = _load_ids()
        session_id = str(uuid.uuid4())
        listing_id = str(uuid.uuid4())
        price = 120_000

        _insert_tracked_listing(
            db,
            listing_id=listing_id,
            vendor_id=VENDOR_A,
            product_id=ids["products"]["phone"],
            stock_qty=2,
            price_ngwee=price,
        )
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=price,
            delivery_fee=0,
            total=price,
        )
        claim_reservation(
            listing_id=listing_id, checkout_group_id=session_id, qty=1, ttl_minutes=15
        )

        result = create_orders_atomic(
            client=pg_service.client,
            customer_id=CUSTOMER_ID,
            session_id=session_id,
            idempotency_key=f"outbox-{uuid.uuid4()}",
            payment_method="card",
            cart_lines=[
                CartLineInput(
                    cart_item_id=str(uuid.uuid4()),
                    listing_id=listing_id,
                    vendor_id=VENDOR_A,
                    qty=1,
                    unit_price_ngwee=price,
                    title_snapshot=None,
                )
            ],
            vendor_groups=[
                VendorFulfilmentInput(
                    vendor_id=VENDOR_A,
                    fulfilment="pickup",
                    delivery_zone=None,
                    delivery_fee_ngwee=0,
                    subtotal_ngwee=price,
                )
            ],
        )
        assert len(result.orders) == 1
        assert _outbox_count(db, result.orders[0].order_id) == 1


def _current_user() -> CurrentUser:
    return CurrentUser(id=CUSTOMER_ID, roles=frozenset({"customer"}), token=VALID_TOKEN)


def _make_api_client(pg_service: SupabaseServiceClient) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _current_user

    def _override_service() -> Generator[SupabaseServiceClient, None, None]:
        yield pg_service

    app.dependency_overrides[get_supabase_client] = _override_service
    return TestClient(app, raise_server_exceptions=False)


class TestCreateOrdersEndpoint:
    def test_post_orders_happy_path(
        self,
        db: PgConn,
        db_url_env: None,
        pg_service: SupabaseServiceClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ids = _load_ids()
        session_id = str(uuid.uuid4())
        cart_id = str(uuid.uuid4())
        listing_id = ids["listings"]["phone_a"]
        price = 450_000
        expires = (datetime.now(UTC) + timedelta(minutes=15)).isoformat()

        # Seed auditable T2 approval so D9 first-order cap does not apply (orphan
        # vendors.kyc_tier alone stays at T1 baseline — MR-D02 / cap_tier_for_quotas).
        db.run(
            f"""
            INSERT INTO public.kyc_records (
              id, vendor_id, tier, status, doc_storage_paths,
              momo_name_match, reviewed_by, reviewed_at, decision_reason
            ) VALUES (
              '{uuid.uuid4()}', '{VENDOR_A}', 2, 'approved',
              ARRAY['kyc/seed.jpg'],
              '{{"matched": true}}'::jsonb,
              '{ids["users"]["admin"]}',
              timezone('utc', now()),
              'test seed'
            ) ON CONFLICT DO NOTHING;
            """
        )

        _insert_cart_with_items(db, cart_id=cart_id, items=[(listing_id, 1, price)])
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=price,
            delivery_fee=0,
            total=price,
        )
        db.run(
            f"""
            INSERT INTO public.stock_reservations (
              listing_id, checkout_group_id, qty, expires_at
            ) VALUES (
              '{listing_id}', '{session_id}', 1, '{expires}'
            )
            ON CONFLICT (listing_id, checkout_group_id) DO UPDATE
              SET expires_at = EXCLUDED.expires_at;
            """
        )

        def user_table(name: str) -> MagicMock:
            table = MagicMock()
            if name == "carts":
                carts_chain = (
                    table.select.return_value.eq.return_value.eq.return_value.limit.return_value
                )
                carts_chain.execute.return_value = MagicMock(
                    data=[{"id": cart_id, "user_id": CUSTOMER_ID, "status": "active"}]
                )
            elif name == "cart_items":
                table.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[
                        {
                            "id": str(uuid.uuid4()),
                            "cart_id": cart_id,
                            "listing_id": listing_id,
                            "qty": 1,
                            "unit_price_ngwee": price,
                            "wholesale": False,
                        }
                    ]
                )
            return table

        user_client = MagicMock()
        user_client.table.side_effect = user_table
        monkeypatch.setattr(
            "app.routers.orders_create.get_user_client",
            lambda *_args, **_kwargs: user_client,
        )

        client = _make_api_client(pg_service)
        response = client.post(
            "/orders",
            json={
                "session_id": session_id,
                "idempotency_key": f"api-{uuid.uuid4()}",
                "method": "card",
                "groups": [
                    {
                        "vendor_id": VENDOR_A,
                        "fulfilment": "pickup",
                        "delivery_fee_ngwee": 0,
                        "subtotal_ngwee": price,
                    }
                ],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["total_ngwee"] == price
        assert len(body["orders"]) == 1
