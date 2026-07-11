"""Review submission, edit windows, vendor replies, and verified-purchase gate tests."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    Persona,
    PgConn,
    RoleSession,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_CUSTOMER_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_OWNER_ID = "33333333-3333-3333-3333-333333333333"
OTHER_VENDOR_OWNER_ID = "44444444-4444-4444-4444-444444444444"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_VENDOR_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
LISTING_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
PRODUCT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
ORDER_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
ORDER_ITEM_ID = "f0000000-0000-0000-0000-000000000001"
REVIEW_ID = "a0000000-0000-0000-0000-000000000001"
GROSS_NGEWEE = 150_000


@pytest.fixture(autouse=True)
def _allow_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.reviews.bump_rate_counter",
        lambda **kwargs: (True, 0),
    )


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = list(filters)
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._in_filter: tuple[str, list[Any]] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in_filter = (column, values)
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op is None and self._parent.name == "order_items":
            rows = self._filtered_rows()
            enriched: list[dict[str, Any]] = []
            for row in rows:
                copy = dict(row)
                link = copy.pop("order_item_products", None)
                if link is None:
                    link_rows = self._parent._client.tables["order_item_products"].rows
                    link = next(
                        (
                            {
                                "listing_id": link_row.get("listing_id"),
                                "product_id": link_row.get("product_id"),
                            }
                            for link_row in link_rows
                            if link_row.get("order_item_id") == row.get("id")
                        ),
                        None,
                    )
                copy["order_item_products"] = link
                enriched.append(copy)
            if self._maybe_single:
                return MagicMock(data=enriched[0] if enriched else None, count=len(enriched))
            return MagicMock(data=enriched, count=len(enriched))

        if self._pending_op is None and self._parent.name == "order_item_products":
            rows = self._filtered_rows()
            enriched = []
            for row in rows:
                copy = dict(row)
                listing = copy.pop("vendor_listings", None)
                if listing is None:
                    listing_rows = self._parent._client.tables["vendor_listings"].rows
                    vendor_rows = self._parent._client.tables["vendors"].rows
                    listing_row = next(
                        (lr for lr in listing_rows if lr.get("id") == row.get("listing_id")),
                        None,
                    )
                    vendor_row = next(
                        (vr for vr in vendor_rows if vr.get("id") == VENDOR_ID),
                        None,
                    )
                    if listing_row and vendor_row:
                        listing = {
                            "vendor_id": listing_row.get("vendor_id"),
                            "vendors": vendor_row,
                        }
                copy["vendor_listings"] = listing
                enriched.append(copy)
            if self._maybe_single:
                return MagicMock(data=enriched[0] if enriched else None, count=len(enriched))
            return MagicMock(data=enriched, count=len(enriched))

        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = str(uuid.uuid4())
            if "created_at" not in row:
                row["created_at"] = datetime.now(tz=UTC).isoformat()
            if "updated_at" not in row:
                row["updated_at"] = row["created_at"]
            for existing in self._parent.rows:
                if (
                    self._parent.name == "reviews"
                    and existing.get("order_item_id") == row.get("order_item_id")
                ):
                    raise RuntimeError(
                        'duplicate key value violates unique constraint "reviews_order_item_id_key"'
                    )
            self._parent.rows.append(row)
            return MagicMock(data=[row], count=None)

        rows = self._filtered_rows()
        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in rows:
                row.update(self._payload)
                updated.append(row)
            rows = updated

        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        if self._in_filter is not None:
            column, values = self._in_filter
            allowed = set(values)
            rows = [row for row in rows if row.get(column) in allowed]
        return rows


class FakeTable:
    def __init__(self, name: str, client: FakeSupabaseClient) -> None:
        self.name = name
        self._client = client
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}
        for table_name in (
            "orders",
            "order_items",
            "order_item_products",
            "reviews",
            "vendors",
            "vendor_listings",
        ):
            self.tables[table_name] = FakeTable(table_name, self)

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable(name, self)
        return self.tables[name]


class _FakeServiceWrapper:
    def __init__(self, client: FakeSupabaseClient) -> None:
        self.client = client


def _make_client(
    *,
    user_id: str,
    fake: FakeSupabaseClient,
    roles: frozenset[str] | None = None,
) -> TestClient:
    app: FastAPI = create_app()

    async def override_current_user() -> CurrentUser:
        return CurrentUser(
            id=user_id,
            roles=roles or frozenset({"customer"}),
            token="test-token",
        )

    def override_service_client() -> _FakeServiceWrapper:
        return _FakeServiceWrapper(fake)

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_supabase_client] = override_service_client
    return TestClient(app, raise_server_exceptions=False)


def _seed_order_context(
    fake: FakeSupabaseClient,
    *,
    order_id: str = ORDER_ID,
    order_item_id: str = ORDER_ITEM_ID,
    customer_id: str = CUSTOMER_ID,
    status: str = "delivered",
    vendor_owner_id: str = VENDOR_OWNER_ID,
) -> None:
    fake.tables["orders"].rows.append(
        {
            "id": order_id,
            "customer_id": customer_id,
            "status": status,
            "vendor_id": VENDOR_ID,
        }
    )
    fake.tables["order_items"].rows.append(
        {
            "id": order_item_id,
            "order_id": order_id,
            "title_snapshot": "Test phone",
            "order_item_products": {
                "listing_id": LISTING_ID,
                "product_id": PRODUCT_ID,
            },
        }
    )
    fake.tables["order_item_products"].rows.append(
        {
            "order_item_id": order_item_id,
            "listing_id": LISTING_ID,
            "product_id": PRODUCT_ID,
            "vendor_listings": {
                "vendor_id": VENDOR_ID,
                "vendors": {
                    "id": VENDOR_ID,
                    "owner_user_id": vendor_owner_id,
                },
            },
        }
    )
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": vendor_owner_id,
        }
    )
    fake.tables["vendor_listings"].rows.append(
        {
            "id": LISTING_ID,
            "vendor_id": VENDOR_ID,
        }
    )


def _review_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "order_item_id": ORDER_ITEM_ID,
        "rating": 5,
        "body": "Great product",
        "photos": ["reviews/photo-1"],
    }
    payload.update(overrides)
    return payload


class TestVerifiedPurchaseGate:
    def test_non_purchaser_cannot_submit(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order_context(fake, customer_id=CUSTOMER_ID)
        client = _make_client(user_id=OTHER_CUSTOMER_ID, fake=fake)

        response = client.post("/reviews", json=_review_payload())

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_purchaser_on_non_delivered_cannot_submit(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order_context(fake, status="shipped")
        client = _make_client(user_id=CUSTOMER_ID, fake=fake)

        response = client.post("/reviews", json=_review_payload())

        assert response.status_code == 403
        assert "delivery" in response.json()["error"]["message"].lower()

    def test_delivered_purchaser_can_submit(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order_context(fake, status="delivered")
        client = _make_client(user_id=CUSTOMER_ID, fake=fake)

        response = client.post("/reviews", json=_review_payload())

        assert response.status_code == 200
        payload = response.json()
        assert payload["rating"] == 5
        assert payload["order_item_id"] == ORDER_ITEM_ID
        assert payload["status"] == "published"
        assert len(fake.tables["reviews"].rows) == 1


class TestOnePerItem:
    def test_existing_review_updates_within_window(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order_context(fake)
        fake.tables["reviews"].rows.append(
            {
                "id": REVIEW_ID,
                "order_item_id": ORDER_ITEM_ID,
                "rating": 4,
                "body": "First",
                "photos": [],
                "status": "published",
                "created_at": datetime.now(tz=UTC).isoformat(),
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
        )
        client = _make_client(user_id=CUSTOMER_ID, fake=fake)

        response = client.post("/reviews", json=_review_payload(rating=3, body="Updated"))

        assert response.status_code == 200
        assert response.json()["rating"] == 3
        assert len(fake.tables["reviews"].rows) == 1

    def test_insert_unique_violation_returns_409(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeSupabaseClient()
        _seed_order_context(fake)
        client = _make_client(user_id=CUSTOMER_ID, fake=fake)
        original_insert = FakeTable.insert

        def flaky_insert(self: FakeTable, payload: dict[str, Any]) -> FakeQuery:
            query = original_insert(self, payload)
            if self.name == "reviews":

                def raise_duplicate() -> MagicMock:
                    raise RuntimeError(
                        'duplicate key value violates unique constraint "reviews_order_item_id_key"'
                    )

                query.execute = raise_duplicate  # type: ignore[method-assign]
            return query

        monkeypatch.setattr(FakeTable, "insert", flaky_insert)

        response = client.post("/reviews", json=_review_payload())

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"


class TestEditWindows:
    def test_review_edit_allowed_within_7_days(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order_context(fake)
        created_at = (datetime.now(tz=UTC) - timedelta(days=6, hours=23)).isoformat()
        fake.tables["reviews"].rows.append(
            {
                "id": REVIEW_ID,
                "order_item_id": ORDER_ITEM_ID,
                "rating": 4,
                "body": "Good",
                "photos": [],
                "status": "published",
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        client = _make_client(user_id=CUSTOMER_ID, fake=fake)

        response = client.post("/reviews", json=_review_payload(rating=5, body="Even better"))

        assert response.status_code == 200
        assert response.json()["rating"] == 5

    def test_review_edit_blocked_after_7_days(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order_context(fake)
        created_at = (datetime.now(tz=UTC) - timedelta(days=7, hours=1)).isoformat()
        fake.tables["reviews"].rows.append(
            {
                "id": REVIEW_ID,
                "order_item_id": ORDER_ITEM_ID,
                "rating": 4,
                "body": "Good",
                "photos": [],
                "status": "published",
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        client = _make_client(user_id=CUSTOMER_ID, fake=fake)

        response = client.post("/reviews", json=_review_payload(rating=1, body="Too late"))

        assert response.status_code == 403
        assert "edit window" in response.json()["error"]["message"].lower()

    def test_vendor_reply_edit_allowed_within_24_hours(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order_context(fake)
        reply_at = (datetime.now(tz=UTC) - timedelta(hours=12)).isoformat()
        fake.tables["reviews"].rows.append(
            {
                "id": REVIEW_ID,
                "order_item_id": ORDER_ITEM_ID,
                "rating": 4,
                "body": "Good",
                "photos": [],
                "status": "published",
                "vendor_reply": "Thanks",
                "vendor_reply_at": reply_at,
                "created_at": datetime.now(tz=UTC).isoformat(),
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
        )
        client = _make_client(
            user_id=VENDOR_OWNER_ID,
            fake=fake,
            roles=frozenset({"vendor"}),
        )

        response = client.post(
            f"/reviews/{REVIEW_ID}/reply",
            json={"reply": "Thanks again for your feedback"},
        )

        assert response.status_code == 200
        assert response.json()["vendor_reply"] == "Thanks again for your feedback"

    def test_vendor_reply_edit_blocked_after_24_hours(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order_context(fake)
        reply_at = (datetime.now(tz=UTC) - timedelta(hours=25)).isoformat()
        fake.tables["reviews"].rows.append(
            {
                "id": REVIEW_ID,
                "order_item_id": ORDER_ITEM_ID,
                "rating": 4,
                "body": "Good",
                "photos": [],
                "status": "published",
                "vendor_reply": "Thanks",
                "vendor_reply_at": reply_at,
                "created_at": datetime.now(tz=UTC).isoformat(),
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
        )
        client = _make_client(
            user_id=VENDOR_OWNER_ID,
            fake=fake,
            roles=frozenset({"vendor"}),
        )

        response = client.post(
            f"/reviews/{REVIEW_ID}/reply",
            json={"reply": "Too late"},
        )

        assert response.status_code == 403
        assert "reply edit window" in response.json()["error"]["message"].lower()


class TestReplyAuthz:
    def test_other_vendor_cannot_reply(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order_context(fake)
        fake.tables["reviews"].rows.append(
            {
                "id": REVIEW_ID,
                "order_item_id": ORDER_ITEM_ID,
                "rating": 4,
                "body": "Good",
                "photos": [],
                "status": "published",
                "created_at": datetime.now(tz=UTC).isoformat(),
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
        )
        client = _make_client(
            user_id=OTHER_VENDOR_OWNER_ID,
            fake=fake,
            roles=frozenset({"vendor"}),
        )

        response = client.post(
            f"/reviews/{REVIEW_ID}/reply",
            json={"reply": "Not my review"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_vendor_reply_threading(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order_context(fake)
        fake.tables["reviews"].rows.append(
            {
                "id": REVIEW_ID,
                "order_item_id": ORDER_ITEM_ID,
                "rating": 4,
                "body": "Good",
                "photos": [],
                "status": "published",
                "created_at": datetime.now(tz=UTC).isoformat(),
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
        )
        client = _make_client(
            user_id=VENDOR_OWNER_ID,
            fake=fake,
            roles=frozenset({"vendor"}),
        )

        response = client.post(
            f"/reviews/{REVIEW_ID}/reply",
            json={"reply": "We appreciate your purchase"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["vendor_reply"] == "We appreciate your purchase"
        assert payload["vendor_reply_at"] is not None
        assert payload["id"] == REVIEW_ID


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    import shutil

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
        seed_matrix_fixtures(conn)
    yield conn


@pytest.fixture
def role_factory(db: PgConn) -> Callable[[Persona], RoleSession]:
    def _make(persona: Persona) -> RoleSession:
        return RoleSession(db, persona)

    return _make


def _insert_checkout_group(conn: PgConn, group_id: str, customer_id: str = CUSTOMER_ID) -> None:
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{group_id}', '{customer_id}', 'cg-{group_id}',
          {GROSS_NGEWEE}, 0, {GROSS_NGEWEE}, 'completed'
        ) ON CONFLICT (id) DO NOTHING;
        """
    )


def _insert_delivered_order_with_item(
    conn: PgConn,
    *,
    order_id: str,
    order_item_id: str,
    customer_id: str = CUSTOMER_ID,
    status: str = "delivered",
) -> None:
    group_id = str(uuid.uuid4())
    _insert_checkout_group(conn, group_id, customer_id)
    conn.run(
        f"""
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
          delivery_fee_ngwee, cod, commission_snapshot
        ) VALUES (
          '{order_id}', '{group_id}', '{VENDOR_ID}', '{customer_id}',
          '{status}', 'delivery', 0, false, '{{}}'::jsonb
        ) ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.order_items (
          id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES (
          '{order_item_id}', '{order_id}', 'product', 1, {GROSS_NGEWEE}, 'RLS phone'
        ) ON CONFLICT (id) DO NOTHING;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.order_item_products (order_item_id, listing_id, product_id)
        VALUES ('{order_item_id}', '{LISTING_ID}', '{PRODUCT_ID}')
        ON CONFLICT (order_item_id) DO NOTHING;
        """
    )


class TestReviewsRls:
    def test_other_customer_insert_denied(
        self,
        db: PgConn,
        role_factory: Callable[[Persona], RoleSession],
    ) -> None:
        order_id = str(uuid.uuid4())
        order_item_id = str(uuid.uuid4())
        _insert_delivered_order_with_item(db, order_id=order_id, order_item_id=order_item_id)

        customer = role_factory(Persona.CUSTOMER)
        other = role_factory(Persona.OTHER_CUSTOMER)

        ok = customer.execute(
            f"""
            INSERT INTO public.reviews (order_item_id, rating, body)
            VALUES ('{order_item_id}', 5, 'Verified purchase');
            """
        )
        assert ok.ok, ok.error

        denied = other.execute(
            f"""
            INSERT INTO public.reviews (order_item_id, rating, body)
            VALUES ('{order_item_id}', 1, 'Fake review');
            """
        )
        assert not denied.ok
        assert denied.sqlstate in {"42501", "P0001"}

    def test_non_delivered_insert_trigger_denied(
        self,
        db: PgConn,
        role_factory: Callable[[Persona], RoleSession],
    ) -> None:
        order_id = str(uuid.uuid4())
        order_item_id = str(uuid.uuid4())
        _insert_delivered_order_with_item(
            db,
            order_id=order_id,
            order_item_id=order_item_id,
            status="shipped",
        )

        customer = role_factory(Persona.CUSTOMER)
        denied = customer.execute(
            f"""
            INSERT INTO public.reviews (order_item_id, rating, body)
            VALUES ('{order_item_id}', 5, 'Too early');
            """
        )
        assert not denied.ok
        assert "delivered" in (denied.error or "").lower()
