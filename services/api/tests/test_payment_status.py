"""Tests for customer-scoped payment status polling and retry."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.payments.base import CollectionStatus, InitiateCollectionResult
from fastapi.testclient import TestClient

CUSTOMER_A_ID = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B_ID = "22222222-2222-2222-2222-222222222222"
CHECKOUT_GROUP_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
ORDER_A_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
PAYMENT_A_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
TOKEN_A = "customer-a-token"
TOKEN_B = "customer-b-token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("neq", column, value))
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
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = str(uuid4())
            self._parent.rows.append(row)
            return MagicMock(data=[row], count=None)

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._row_matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated, count=len(updated))

        rows = self._apply_filters(list(self._parent.rows))
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: str(row.get(column, "")), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _row_matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            cell = row.get(column)
            if op == "eq" and cell != value:
                return False
            if op == "neq" and cell == value:
                return False
        return True

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if self._row_matches(row)]


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "checkout_groups": FakeTable(),
            "orders": FakeTable(),
            "payments": FakeTable(),
            "audit_log": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _mock_auth(monkeypatch: pytest.MonkeyPatch, user_id: str) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: frozenset({"customer"}),
    )


def _mock_supabase(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabaseClient) -> MagicMock:
    service_wrapper = MagicMock()
    service_wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: service_wrapper)
    return service_wrapper


def _auth_headers(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_group(
    fake: FakeSupabaseClient,
    *,
    customer_id: str = CUSTOMER_A_ID,
    total_ngwee: int = 25_000,
    status: str = "completed",
) -> None:
    fake.tables["checkout_groups"].rows.append(
        {
            "id": CHECKOUT_GROUP_ID,
            "customer_id": customer_id,
            "total_ngwee": total_ngwee,
            "status": status,
        }
    )


def _seed_order(
    fake: FakeSupabaseClient,
    *,
    order_id: str = ORDER_A_ID,
    customer_id: str = CUSTOMER_A_ID,
    cod: bool = False,
) -> None:
    fake.tables["orders"].rows.append(
        {
            "id": order_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "customer_id": customer_id,
            "cod": cod,
            "created_at": "2026-07-10T10:00:00Z",
        }
    )


def _seed_payment(
    fake: FakeSupabaseClient,
    *,
    payment_id: str = PAYMENT_A_ID,
    status: str = "ussd_pushed",
    rail: str = "mtn",
    payer_phone: str = "+260971234567",
    created_at: str = "2026-07-10T10:00:00Z",
) -> None:
    fake.tables["payments"].rows.append(
        {
            "id": payment_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "status": status,
            "amount_ngwee": 25_000,
            "rail": rail,
            "provider": "lenco",
            "lenco_reference": "ord-test-ref",
            "raw": {"payer_phone": payer_phone},
            "created_at": created_at,
            "updated_at": created_at,
        }
    )


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def payment_status_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    _mock_auth(monkeypatch, CUSTOMER_A_ID)
    _seed_group(fake_client)
    _seed_order(fake_client)
    _seed_payment(fake_client, status="ussd_pushed")
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestPaymentStatusPoll:
    def test_poll_returns_m08_status_for_owner(
        self,
        payment_status_client: TestClient,
    ) -> None:
        response = payment_status_client.get(
            f"/payments/status?group={CHECKOUT_GROUP_ID}",
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ussd_pushed"
        assert payload["checkout_group_id"] == CHECKOUT_GROUP_ID
        assert payload["payment_id"] == PAYMENT_A_ID
        assert payload["amount_ngwee"] == 25_000
        assert payload["rail"] == "mtn"
        assert payload["order_id"] == ORDER_A_ID
        assert payload["cod"] is False

    def test_poll_by_payment_id(self, payment_status_client: TestClient) -> None:
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}",
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["payment_id"] == PAYMENT_A_ID

    def test_poll_other_user_returns_403(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _mock_auth(monkeypatch, CUSTOMER_B_ID)
        _seed_group(fake_client, customer_id=CUSTOMER_A_ID)
        _seed_order(fake_client, customer_id=CUSTOMER_A_ID)
        _seed_payment(fake_client)
        service_wrapper = _mock_supabase(monkeypatch, fake_client)
        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: service_wrapper
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                f"/payments/status?group={CHECKOUT_GROUP_ID}",
                headers=_auth_headers(TOKEN_B),
            )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_poll_cod_skips_payment_row(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _mock_auth(monkeypatch, CUSTOMER_A_ID)
        _seed_group(fake_client)
        _seed_order(fake_client, cod=True)
        service_wrapper = _mock_supabase(monkeypatch, fake_client)
        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: service_wrapper
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                f"/payments/status?group={CHECKOUT_GROUP_ID}",
                headers=_auth_headers(),
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "cod"
        assert payload["cod"] is True
        assert payload["payment_id"] is None

    @pytest.mark.parametrize(
        "status",
        ["initiated", "ussd_pushed", "pay_offline", "success", "failed", "expired", "cancelled"],
    )
    def test_poll_reflects_m08_payment_states(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
        status: str,
    ) -> None:
        _mock_auth(monkeypatch, CUSTOMER_A_ID)
        _seed_group(fake_client)
        _seed_order(fake_client)
        _seed_payment(fake_client, status=status)
        service_wrapper = _mock_supabase(monkeypatch, fake_client)
        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: service_wrapper
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                f"/payments/status?group={CHECKOUT_GROUP_ID}",
                headers=_auth_headers(),
            )
        assert response.status_code == 200
        assert response.json()["status"] == status


class TestPaymentRetry:
    @pytest.mark.asyncio
    async def test_retry_creates_new_payment_same_order_count(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _mock_auth(monkeypatch, CUSTOMER_A_ID)
        _seed_group(fake_client)
        _seed_order(fake_client)
        _seed_payment(fake_client, status="expired")
        service_wrapper = _mock_supabase(monkeypatch, fake_client)

        strategy = MagicMock()
        strategy.initiate_collection = AsyncMock(
            return_value=InitiateCollectionResult(
                provider_reference="240730099",
                status=CollectionStatus.PENDING,
                amount_major="250.00",
            )
        )
        monkeypatch.setattr(
            "app.routers.payment_status.get_payment_strategy",
            lambda _provider: strategy,
        )

        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: service_wrapper
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/payments/retry",
                headers=_auth_headers(),
                json={"checkout_group_id": CHECKOUT_GROUP_ID},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["checkout_group_id"] == CHECKOUT_GROUP_ID
        assert payload["order_count"] == 1
        assert payload["payment_id"] != PAYMENT_A_ID
        assert payload["status"] == "ussd_pushed"
        assert len(fake_client.tables["payments"].rows) == 2
        assert len(fake_client.tables["orders"].rows) == 1

    def test_retry_rejected_while_payment_in_progress(
        self,
        payment_status_client: TestClient,
    ) -> None:
        response = payment_status_client.post(
            "/payments/retry",
            headers=_auth_headers(),
            json={"checkout_group_id": CHECKOUT_GROUP_ID},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "payment.in_progress"

    def test_retry_other_user_returns_403(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _mock_auth(monkeypatch, CUSTOMER_B_ID)
        _seed_group(fake_client, customer_id=CUSTOMER_A_ID)
        _seed_order(fake_client, customer_id=CUSTOMER_A_ID)
        _seed_payment(fake_client, status="failed")
        service_wrapper = _mock_supabase(monkeypatch, fake_client)
        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: service_wrapper
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/payments/retry",
                headers=_auth_headers(TOKEN_B),
                json={"checkout_group_id": CHECKOUT_GROUP_ID},
            )
        assert response.status_code == 403
