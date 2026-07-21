from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

VALID_TOKEN = "dev-internal-n8n"
USER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
KYC_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
PAYOUT_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
LISTING_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
ORDER_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
CART_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
FOUNDER_PHONE = "+260971234567"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._selected_columns = "*"
        self._inserted_dedupe: set[str] = set()

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        self._selected_columns = columns
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("gte", column, value))
        return self

    def lt(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("lt", column, value))
        return self

    def lte(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("lte", column, value))
        return self

    def like(self, column: str, value: str) -> FakeQuery:
        self._filters.append(("like", column, value))
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

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            dedupe = self._payload.get("dedupe_key")
            if isinstance(dedupe, str) and dedupe in self._parent.store.inserted_dedupe:
                return MagicMock(data=None)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = f"{len(self._parent.rows):08x}-fake-fake-fake-fakefakefake"
            if isinstance(dedupe, str):
                self._parent.store.inserted_dedupe.add(dedupe)
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = rows
        for op, column, value in self._filters:
            if op == "eq":
                filtered = [row for row in filtered if row.get(column) == value]
            elif op == "in":
                allowed = set(value)
                filtered = [row for row in filtered if row.get(column) in allowed]
            elif op == "gte":
                filtered = [
                    row for row in filtered if str(row.get(column, "")) >= str(value)
                ]
            elif op == "lt":
                filtered = [
                    row for row in filtered if str(row.get(column, "")) < str(value)
                ]
            elif op == "lte":
                filtered = [
                    row for row in filtered if str(row.get(column, "")) <= str(value)
                ]
            elif op == "like":
                prefix = value.rstrip("%")
                filtered = [
                    row
                    for row in filtered
                    if isinstance(row.get(column), str)
                    and str(row[column]).startswith(prefix)
                ]
        return filtered


class FakeTable:
    def __init__(self, store: FakeSupabaseClient) -> None:
        self.store = store
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.inserted_dedupe: set[str] = set()
        self.tables: dict[str, FakeTable] = {
            "kyc_records": FakeTable(self),
            "vendors": FakeTable(self),
            "profiles": FakeTable(self),
            "payouts": FakeTable(self),
            "vendor_listings": FakeTable(self),
            "platform_config": FakeTable(self),
            "orders": FakeTable(self),
            "order_events": FakeTable(self),
            "notification_outbox": FakeTable(self),
            "feature_flags": FakeTable(self),
            "carts": FakeTable(self),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _stale_iso(hours: int) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _recent_iso(hours: int) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _seed_common(fake: FakeSupabaseClient) -> None:
    fake.tables["profiles"].rows.append(
        {
            "id": USER_ID,
            "phone": "+260971111111",
            "locale": "en",
            "display_name": "Test User",
        }
    )
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": USER_ID,
            "display_name": "Test Vendor",
            "slug": "test-vendor",
            "status": "pending_kyc",
        }
    )
    fake.tables["platform_config"].rows.append(
        {"key": "low_stock_threshold", "value": 5}
    )
    fake.tables["feature_flags"].rows.append(
        {"flag": "abandoned_cart", "enabled": False}
    )


def _mock_supabase(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabaseClient) -> None:
    service = MagicMock()
    service.client = fake

    def _get_client() -> Generator[MagicMock, None, None]:
        yield service

    monkeypatch.setattr("app.routers.internal_n8n.get_supabase_client", _get_client)


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def n8n_client(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeSupabaseClient
) -> TestClient:
    os.environ["INTERNAL_N8N_TOKEN"] = VALID_TOKEN
    os.environ["FOUNDER_WHATSAPP_E164"] = FOUNDER_PHONE
    _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


class TestInternalTokenGuard:
    def test_missing_token_returns_401(self, n8n_client: TestClient) -> None:
        response = n8n_client.get("/internal/n8n/kyc-stalled")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"

    def test_wrong_token_returns_401(self, n8n_client: TestClient) -> None:
        response = n8n_client.get(
            "/internal/n8n/kyc-stalled",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 401


class TestKycStalledEndpoint:
    def test_returns_stalled_pending_kyc(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["kyc_records"].rows.append(
            {
                "id": KYC_ID,
                "vendor_id": VENDOR_ID,
                "tier": 1,
                "status": "pending",
                "updated_at": _stale_iso(50),
            }
        )
        response = n8n_client.get(
            "/internal/n8n/kyc-stalled",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        item = body["items"][0]
        assert item["kyc_record_id"] == KYC_ID
        assert item["vendor_id"] == VENDOR_ID
        assert item["phone_e164"] == "+260971111111"
        assert item["recipient_id"] == USER_ID

    def test_excludes_recent_pending(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["kyc_records"].rows.append(
            {
                "id": KYC_ID,
                "vendor_id": VENDOR_ID,
                "tier": 1,
                "status": "pending",
                "updated_at": _recent_iso(1),
            }
        )
        response = n8n_client.get(
            "/internal/n8n/kyc-stalled",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        assert response.json()["count"] == 0


class TestPayoutFailuresEndpoint:
    def test_returns_recent_failed_payouts_with_founder_payload(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["payouts"].rows.append(
            {
                "id": PAYOUT_ID,
                "vendor_id": VENDOR_ID,
                "amount_ngwee": 125_000,
                "lenco_reference": "pay-test-001",
                "status": "failed",
                "updated_at": _recent_iso(2),
            }
        )
        response = n8n_client.get(
            "/internal/n8n/payout-failures",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        item = body["items"][0]
        assert item["payout_id"] == PAYOUT_ID
        assert item["amount_ngwee"] == 125_000
        assert item["lenco_reference"] == "pay-test-001"
        assert item["recipient_id"] == "founder"
        assert item["phone_e164"] == FOUNDER_PHONE
        assert item["vendor_name"] == "Test Vendor"


class TestLowStockEndpoint:
    def test_returns_listings_under_threshold(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["vendor_listings"].rows.append(
            {
                "id": LISTING_ID,
                "vendor_id": VENDOR_ID,
                "title_override": "Low Widget",
                "stock_mode": "tracked",
                "stock_qty": 2,
                "status": "active",
            }
        )
        response = n8n_client.get(
            "/internal/n8n/low-stock",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        item = body["items"][0]
        assert item["listing_id"] == LISTING_ID
        assert item["stock_qty"] == 2
        assert item["threshold"] == 5
        assert item["phone_e164"] == "+260971111111"


class TestReviewRequestsEndpoint:
    def test_returns_completed_orders_after_24h(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["orders"].rows.append(
            {
                "id": ORDER_ID,
                "customer_id": USER_ID,
                "vendor_id": VENDOR_ID,
                "status": "completed",
                "updated_at": _stale_iso(30),
            }
        )
        fake_client.tables["order_events"].rows.append(
            {
                "order_id": ORDER_ID,
                "to_status": "completed",
                "created_at": _stale_iso(30),
            }
        )
        response = n8n_client.get(
            "/internal/n8n/review-requests",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        item = body["items"][0]
        assert item["order_id"] == ORDER_ID
        assert item["customer_id"] == USER_ID
        assert item["vendor_name"] == "Test Vendor"

    def test_skips_already_requested(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["orders"].rows.append(
            {
                "id": ORDER_ID,
                "customer_id": USER_ID,
                "vendor_id": VENDOR_ID,
                "status": "completed",
                "updated_at": _stale_iso(30),
            }
        )
        fake_client.tables["order_events"].rows.append(
            {
                "order_id": ORDER_ID,
                "to_status": "completed",
                "created_at": _stale_iso(30),
            }
        )
        fake_client.tables["notification_outbox"].rows.append(
            {
                "dedupe_key": f"review_request:{ORDER_ID}:whatsapp",
                "channel": "whatsapp",
                "template": "review_request",
                "payload": {},
                "status": "sent",
            }
        )
        response = n8n_client.get(
            "/internal/n8n/review-requests",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        assert response.json()["count"] == 0


class TestAbandonedCartFlagGating:
    def test_returns_empty_while_flag_off(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["carts"].rows.append(
            {
                "id": CART_ID,
                "user_id": USER_ID,
                "status": "abandoned",
                "updated_at": _stale_iso(30),
            }
        )
        response = n8n_client.get(
            "/internal/n8n/abandoned-carts",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        assert response.json() == {"items": [], "count": 0}

    def test_returns_carts_when_flag_on(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["feature_flags"].rows[0]["enabled"] = True
        fake_client.tables["carts"].rows.append(
            {
                "id": CART_ID,
                "user_id": USER_ID,
                "status": "abandoned",
                "updated_at": _stale_iso(30),
            }
        )
        response = n8n_client.get(
            "/internal/n8n/abandoned-carts",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        assert response.json()["count"] == 1


class TestTickEnqueue:
    def test_payout_failure_tick_enqueues_outbox(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["payouts"].rows.append(
            {
                "id": PAYOUT_ID,
                "vendor_id": VENDOR_ID,
                "amount_ngwee": 99_000,
                "lenco_reference": "pay-tick-001",
                "status": "failed",
                "updated_at": _recent_iso(1),
            }
        )
        response = n8n_client.post(
            "/internal/n8n/payout-failures/tick",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["enqueued"] == 1
        assert body["skipped"] == 0
        outbox = fake_client.tables["notification_outbox"].rows
        assert len(outbox) == 1
        assert outbox[0]["template"] == "payout_failure_alert"
        assert outbox[0]["dedupe_key"] == f"payout_failure_alert:{PAYOUT_ID}:whatsapp"

    def test_abandoned_cart_tick_enqueues_nothing_while_flag_off(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["carts"].rows.append(
            {
                "id": CART_ID,
                "user_id": USER_ID,
                "status": "abandoned",
                "updated_at": _stale_iso(30),
            }
        )
        response = n8n_client.post(
            "/internal/n8n/abandoned-carts/tick",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        assert response.json()["enqueued"] == 0
        assert len(fake_client.tables["notification_outbox"].rows) == 0

    def test_review_request_tick_skips_opted_out_recipient(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["profiles"].rows[0]["notif_prefs"] = {
            "whatsapp": False,
            "sms": False,
            "email": False,
        }
        fake_client.tables["orders"].rows.append(
            {
                "id": ORDER_ID,
                "customer_id": USER_ID,
                "vendor_id": VENDOR_ID,
                "status": "completed",
                "updated_at": _stale_iso(30),
            }
        )
        fake_client.tables["order_events"].rows.append(
            {
                "order_id": ORDER_ID,
                "to_status": "completed",
                "created_at": _stale_iso(30),
            }
        )
        response = n8n_client.post(
            "/internal/n8n/review-requests/tick",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["enqueued"] == 0
        assert body["skipped"] == 1
        assert len(fake_client.tables["notification_outbox"].rows) == 0

    def test_payout_failure_tick_still_enqueues_for_opted_out_vendor(
        self, n8n_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_common(fake_client)
        fake_client.tables["profiles"].rows[0]["notif_prefs"] = {
            "whatsapp": False,
            "sms": False,
            "email": False,
        }
        fake_client.tables["payouts"].rows.append(
            {
                "id": PAYOUT_ID,
                "vendor_id": VENDOR_ID,
                "amount_ngwee": 99_000,
                "lenco_reference": "pay-opt-out-001",
                "status": "failed",
                "updated_at": _recent_iso(1),
            }
        )
        response = n8n_client.post(
            "/internal/n8n/payout-failures/tick",
            headers={"X-Internal-Token": VALID_TOKEN},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["enqueued"] == 1
        assert body["skipped"] == 0
        assert len(fake_client.tables["notification_outbox"].rows) == 1
