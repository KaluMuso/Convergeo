from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.stock.revalidate import CartLineSnapshot, RevalidateResult
from fastapi.testclient import TestClient

USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
LISTING_A_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
LISTING_B_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
PRODUCT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
ORDER_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
ORDER_ITEM_ID = "10101010-1010-1010-1010-101010101010"
TOKEN_A = "vendor-a-token"
TOKEN_B = "vendor-b-token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._selected_columns = "*"
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        self._selected_columns = columns
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("neq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
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

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            if self._maybe_single:
                return MagicMock(data=updated[0] if updated else None, count=len(updated))
            return MagicMock(data=updated, count=len(updated))

        rows = self._filtered_rows()
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
                if column == "carts.status":
                    rows = [
                        row
                        for row in rows
                        if isinstance(row.get("carts"), dict)
                        and row["carts"].get("status") == value
                    ]
                else:
                    rows = [row for row in rows if row.get(column) == value]
            elif op == "neq":
                rows = [row for row in rows if row.get(column) != value]
            elif op == "in":
                allowed = set(value)
                rows = [row for row in rows if row.get(column) in allowed]
        return rows

    def _matches(self, row: dict[str, Any]) -> bool:
        return all(row.get(column) == value for op, column, value in self._filters if op == "eq")


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "vendor_listings": FakeTable(),
            "products": FakeTable(),
            "order_item_products": FakeTable(),
            "order_items": FakeTable(),
            "orders": FakeTable(),
            "cart_items": FakeTable(),
            "carts": FakeTable(),
            "kyc_records": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _seed_base(fake: FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.extend(
        [
            {
                "id": VENDOR_A_ID,
                "owner_user_id": USER_A_ID,
                "status": "active",
                "kyc_tier": 2,
                "preferred_badge": False,
            },
            {
                "id": VENDOR_B_ID,
                "owner_user_id": USER_B_ID,
                "status": "active",
                "kyc_tier": 1,
                "preferred_badge": False,
            },
        ]
    )
    fake.tables["kyc_records"].rows.extend(
        [
            {
                "id": "kyc-a",
                "vendor_id": VENDOR_A_ID,
                "tier": 2,
                "status": "approved",
                "doc_storage_paths": ["kyc/a.jpg"],
                "momo_name_match": {"matched": True},
            },
            {
                "id": "kyc-b",
                "vendor_id": VENDOR_B_ID,
                "tier": 1,
                "status": "approved",
                "doc_storage_paths": ["kyc/b.jpg"],
                "momo_name_match": {"matched": True},
            },
        ]
    )
    fake.tables["products"].rows.append(
        {
            "id": PRODUCT_ID,
            "name": "Demo Phone",
            "status": "active",
        }
    )
    fake.tables["vendor_listings"].rows.extend(
        [
            {
                "id": LISTING_A_ID,
                "vendor_id": VENDOR_A_ID,
                "product_id": PRODUCT_ID,
                "title_override": None,
                "price_ngwee": 100_000,
                "condition": "new",
                "stock_mode": "tracked",
                "stock_qty": 5,
                "wholesale": False,
                "price_tiers": None,
                "moq": 1,
                "returnable": False,
                "return_window_hours": None,
                "status": "active",
                "products": {"name": "Demo Phone"},
                "updated_at": "2026-07-09T10:00:00Z",
            },
            {
                "id": LISTING_B_ID,
                "vendor_id": VENDOR_B_ID,
                "product_id": PRODUCT_ID,
                "title_override": "Vendor B listing",
                "price_ngwee": 50_000,
                "condition": "new",
                "stock_mode": "tracked",
                "stock_qty": 2,
                "wholesale": False,
                "price_tiers": None,
                "moq": 1,
                "returnable": False,
                "return_window_hours": None,
                "status": "active",
                "products": {"name": "Demo Phone"},
                "updated_at": "2026-07-09T09:00:00Z",
            },
        ]
    )


def _seed_open_order(fake: FakeSupabaseClient) -> None:
    fake.tables["order_item_products"].rows.append(
        {
            "listing_id": LISTING_A_ID,
            "order_item_id": ORDER_ITEM_ID,
            "order_items": {"order_id": ORDER_ID},
        }
    )
    fake.tables["orders"].rows.append(
        {
            "id": ORDER_ID,
            "status": "confirmed",
            "vendor_id": VENDOR_A_ID,
        }
    )


def _seed_cart_item(fake: FakeSupabaseClient) -> None:
    fake.tables["cart_items"].rows.append(
        {
            "listing_id": LISTING_A_ID,
            "qty": 1,
            "unit_price_ngwee": 100_000,
            "carts": {"status": "active"},
        }
    )


def _mock_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    def verify(token: str, settings: Any) -> dict[str, Any]:
        _ = settings
        if token == TOKEN_A:
            return {"sub": USER_A_ID, "exp": 9_999_999_999}
        if token == TOKEN_B:
            return {"sub": USER_B_ID, "exp": 9_999_999_999}
        raise ValueError("invalid token")

    def roles(user_id: str, service_client: Any) -> frozenset[str]:
        _ = service_client
        return frozenset({"vendor"})

    monkeypatch.setattr("app.core.auth.verify_supabase_jwt", verify)
    monkeypatch.setattr("app.core.auth._load_user_roles", roles)


def _mock_supabase(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabaseClient) -> MagicMock:
    service_wrapper = MagicMock()
    service_wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.deps.get_supabase_client", lambda: iter([service_wrapper]))
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: service_wrapper)
    return service_wrapper


def _apply_supabase_overrides(app: Any, service_wrapper: MagicMock) -> None:
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def manage_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    _mock_auth(monkeypatch)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    _seed_base(fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_delete_blocked_with_open_orders_pauses_instead(
    manage_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    _seed_open_order(fake_client)

    response = manage_client.delete(
        f"/vendor/listings/{LISTING_A_ID}",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] is False
    assert body["paused_instead"] is True
    assert body["status"] == "paused"
    assert body["message_key"] == "vendor.listings.manage.delete.paused_instead"

    listing = fake_client.tables["vendor_listings"].rows[0]
    assert listing["status"] == "paused"


def test_delete_without_open_orders_sets_removed(
    manage_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    response = manage_client.delete(
        f"/vendor/listings/{LISTING_A_ID}",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] is True
    assert body["paused_instead"] is False
    assert body["status"] == "removed"

    listing = fake_client.tables["vendor_listings"].rows[0]
    assert listing["status"] == "removed"


def test_compare_at_update_sets_and_clears(
    manage_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    # Set a compare-at above the price → persisted and echoed in the summary.
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}",
        headers=_auth_headers(),
        json={"compare_at_ngwee": 150_000},
    )
    assert response.status_code == 200
    assert response.json()["listing"]["compare_at_ngwee"] == 150_000
    assert fake_client.tables["vendor_listings"].rows[0]["compare_at_ngwee"] == 150_000

    # An explicit null clears it (ends the sale) — model_fields_set, not None-skip.
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}",
        headers=_auth_headers(),
        json={"compare_at_ngwee": None},
    )
    assert response.status_code == 200
    assert response.json()["listing"]["compare_at_ngwee"] is None
    assert fake_client.tables["vendor_listings"].rows[0]["compare_at_ngwee"] is None


def test_compare_at_update_rejects_not_above_price(manage_client: TestClient) -> None:
    # Compare-at at or below the stored price is a friendly 422, not a DB error.
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}",
        headers=_auth_headers(),
        json={"compare_at_ngwee": 1},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_compare_at"


def test_tier_validation_rejects_bad_shape(manage_client: TestClient) -> None:
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}",
        headers=_auth_headers(),
        json={
            "wholesale": True,
            "price_tiers": [
                {"min_qty": 10, "price_ngwee": 90_000},
                {"min_qty": 10, "price_ngwee": 85_000},
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_price_tiers"
    assert (
        response.json()["error"]["details"]["message_key"]
        == "vendor.listings.errors.invalid_tiers"
    )


def test_tier_validation_rejects_non_descending_prices(manage_client: TestClient) -> None:
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}",
        headers=_auth_headers(),
        json={
            "wholesale": True,
            "price_tiers": [
                {"min_qty": 5, "price_ngwee": 90_000},
                {"min_qty": 10, "price_ngwee": 95_000},
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_price_tiers"


def test_price_change_triggers_cart_revalidation(
    manage_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_cart_item(fake_client)
    calls: list[list[CartLineSnapshot]] = []

    def fake_revalidate(lines: list[CartLineSnapshot]) -> RevalidateResult:
        calls.append(lines)
        return RevalidateResult(
            notices=tuple(),
            has_changes=True,
        )

    monkeypatch.setattr(
        "app.routers.vendor_listings_manage.revalidate_lines",
        fake_revalidate,
    )

    response = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}",
        headers=_auth_headers(),
        json={"price_ngwee": 120_000},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["listing"]["price_ngwee"] == 120_000
    assert body["cart_revalidation"]["triggered"] is True
    assert body["cart_revalidation"]["has_changes"] is True
    assert len(calls) == 1
    assert calls[0][0].listing_id == LISTING_A_ID
    assert calls[0][0].unit_price_ngwee == 100_000


def test_authz_vendor_cannot_edit_other_vendor_listing(manage_client: TestClient) -> None:
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_B_ID}",
        headers=_auth_headers(TOKEN_A),
        json={"price_ngwee": 99_000},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_list_vendor_listings_scoped_to_owner(manage_client: TestClient) -> None:
    response = manage_client.get("/vendor/listings", headers=_auth_headers(TOKEN_A))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == LISTING_A_ID


def test_stock_adjust_updates_qty(manage_client: TestClient) -> None:
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}/stock",
        headers=_auth_headers(),
        json={"delta": -1},
    )

    assert response.status_code == 200
    assert response.json()["listing"]["stock_qty"] == 4
