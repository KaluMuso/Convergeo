from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.kyc.caps import (
    VendorCapLimits,
    VendorQuota,
    clear_vendor_cap_cache,
    get_vendor_cap_limits,
)
from app.supabase_client import get_supabase_service_client
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PRODUCT_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CATEGORY_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
LISTING_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
VALID_TOKEN = "valid.jwt.token"
COD_CAP_NGWEE = 50_000


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._count_exact = False
        self._selected_columns = "*"
        self._order: tuple[str, bool] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        self._selected_columns = columns
        if count == "exact":
            self._count_exact = True
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = f"{len(self._parent.rows):08x}-fake-fake-fake-fakefakefake"
            self._parent.rows.append(row)
            return MagicMock(data=[row], count=None)

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        count = len(rows) if self._count_exact else None
        return MagicMock(data=rows, count=count)

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = rows
        for op, column, value in self._filters:
            if op == "eq":
                filtered = [row for row in filtered if row.get(column) == value]
            elif op == "in":
                allowed = set(value)
                filtered = [row for row in filtered if row.get(column) in allowed]
        return filtered


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "vendor_listings": FakeTable(),
            "products": FakeTable(),
            "categories": FakeTable(),
            "commission_rates": FakeTable(),
            "vendor_quotas": FakeTable(),
            "platform_config": FakeTable(),
            "orders": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _seed_base(fake: FakeSupabaseClient, *, kyc_tier: int = 1, listing_count: int = 0) -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": USER_ID,
            "status": "active",
            "kyc_tier": kyc_tier,
        }
    )
    fake.tables["categories"].rows.append(
        {
            "id": CATEGORY_ID,
            "name": "Electronics",
            "commission_key": "electronics",
        }
    )
    fake.tables["products"].rows.append(
        {
            "id": PRODUCT_ID,
            "name": "Smartphone X1",
            "slug": "smartphone-x1",
            "brand": "Demo",
            "spec": {"storage": "128GB"},
            "category_id": CATEGORY_ID,
            "status": "active",
            "categories": {"name": "Electronics", "commission_key": "electronics"},
        }
    )
    fake.tables["commission_rates"].rows.extend(
        [
            {"category_key": "electronics", "rate_bps": 500},
            {"category_key": "default", "rate_bps": 800},
        ]
    )
    fake.tables["vendor_quotas"].rows.append(
        {
            "tier": kyc_tier,
            "max_listings": 30 if kyc_tier == 1 else 9999,
            "first_orders_cap_ngwee": COD_CAP_NGWEE if kyc_tier == 1 else None,
            "first_orders_count": 5 if kyc_tier == 1 else None,
            "payout_velocity": {"max_payouts_per_day": 1, "max_amount_ngwee_per_day": 100_000},
        }
    )
    fake.tables["platform_config"].rows.append(
        {"key": "cod_cap_ngwee", "value": COD_CAP_NGWEE}
    )
    for index in range(listing_count):
        fake.tables["vendor_listings"].rows.append(
            {
                "id": f"listing-{index:02d}",
                "vendor_id": VENDOR_ID,
                "status": "active",
            }
        )


def _mock_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": USER_ID, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"vendor"}),
    )


def _mock_supabase(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabaseClient) -> MagicMock:
    service_wrapper = MagicMock()
    service_wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.deps.get_supabase_client", lambda: iter([service_wrapper]))
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: service_wrapper)
    return service_wrapper


def _apply_supabase_overrides(app: Any, service_wrapper: MagicMock) -> None:
    def mock_get_supabase_client() -> MagicMock:
        return service_wrapper

    app.dependency_overrides[get_supabase_client] = mock_get_supabase_client
    app.dependency_overrides[get_supabase_service_client] = lambda: service_wrapper


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    clear_vendor_cap_cache()
    return FakeSupabaseClient()


@pytest.fixture
def listing_client(
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


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def _base_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "attach",
        "product_id": PRODUCT_ID,
        "price_ngwee": 123_456,
        "condition": "new",
        "stock_mode": "tracked",
        "stock_qty": 5,
        "publish": True,
    }
    payload.update(overrides)
    return payload


def test_attach_creation_path(listing_client: TestClient) -> None:
    response = listing_client.post(
        "/vendor/listings",
        headers=_auth_headers(),
        json=_base_payload(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "attach"
    assert body["status"] == "active"
    assert body["product_id"] == PRODUCT_ID
    assert body["commission"]["rate_bps"] == 500
    assert body["commission"]["rate_percent"] == 5.0


def test_new_canonical_creation_path(
    listing_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    response = listing_client.post(
        "/vendor/listings",
        headers=_auth_headers(),
        json=_base_payload(
            mode="new_canonical",
            product_id=None,
            product_name="New Gadget Pro",
            category_id=CATEGORY_ID,
            brand="Acme",
            spec={"color": "black"},
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "new_canonical"
    assert body["status"] == "draft"
    assert body["product_status"] == "pending_moderation"
    assert len(fake_client.tables["products"].rows) == 2
    created_product = fake_client.tables["products"].rows[-1]
    assert created_product["status"] == "pending_moderation"


def test_quick_list_creation_path(listing_client: TestClient) -> None:
    response = listing_client.post(
        "/vendor/listings",
        headers=_auth_headers(),
        json=_base_payload(
            mode="quick_list",
            product_id=None,
            title_override="Fresh tomatoes per kg",
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "quick_list"
    assert body["status"] == "active"
    assert body["product_id"] is None


def test_t1_wholesale_denied(listing_client: TestClient) -> None:
    response = listing_client.post(
        "/vendor/listings",
        headers=_auth_headers(),
        json=_base_payload(
            wholesale=True,
            price_tiers=[{"min_qty": 10, "price_ngwee": 100_000}],
            moq=10,
        ),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wholesale_requires_t2"
    assert (
        response.json()["error"]["details"]["message_key"]
        == "vendor.listings.errors.wholesale_requires_t2"
    )


def test_price_conversion_exactness_rejects_float() -> None:
    from app.routers.vendor_listings import ListingCreateRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ListingCreateRequest.model_validate(
            {
                **_base_payload(),
                "price_ngwee": 123_456.56,
            }
        )


def test_price_exact_ngwee_k1234_56(listing_client: TestClient) -> None:
    response = listing_client.post(
        "/vendor/listings",
        headers=_auth_headers(),
        json=_base_payload(price_ngwee=123_456),
    )
    assert response.status_code == 200
    assert response.json()["listing_id"]


def test_cap_integration_31st_t1_listing_returns_403(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_auth(monkeypatch)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    _seed_base(fake_client, listing_count=30)

    async def at_cap_limits() -> VendorCapLimits:
        quota = VendorQuota(
            tier=1,
            max_listings=30,
            first_orders_cap_ngwee=COD_CAP_NGWEE,
            first_orders_count=5,
            payout_velocity={"max_payouts_per_day": 1, "max_amount_ngwee_per_day": 100_000},
        )
        return VendorCapLimits(
            vendor_id=VENDOR_ID,
            kyc_tier=1,
            quota=quota,
            cod_cap_ngwee=COD_CAP_NGWEE,
            listing_count=30,
            order_count=0,
        )

    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)
    app.dependency_overrides[get_vendor_cap_limits] = at_cap_limits
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/vendor/listings",
            headers=_auth_headers(),
            json=_base_payload(),
        )
    app.dependency_overrides.clear()
    assert response.status_code == 403
    assert response.json()["error"]["details"]["message_key"] == "vendor.caps.listing_limit"


def test_canonical_preview_returns_commission(listing_client: TestClient) -> None:
    response = listing_client.get(
        f"/vendor/listings/canonical/{PRODUCT_ID}",
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Smartphone X1"
    assert body["commission"]["rate_bps"] == 500
    assert body["commission"]["rate_percent"] == 5.0


def test_t2_wholesale_allowed(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    clear_vendor_cap_cache()
    _mock_auth(monkeypatch)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    _seed_base(fake_client, kyc_tier=2)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/vendor/listings",
            headers=_auth_headers(),
            json=_base_payload(
                wholesale=True,
                price_tiers=[
                    {"min_qty": 10, "price_ngwee": 110_000},
                    {"min_qty": 50, "price_ngwee": 100_000},
                ],
                moq=10,
            ),
        )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["status"] == "active"
