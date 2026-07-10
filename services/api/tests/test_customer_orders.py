from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.customer_orders import TimelineStepOut, build_customer_timeline
from fastapi.testclient import TestClient

CUSTOMER_A_ID = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORDER_A_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
ORDER_B_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
CHECKOUT_GROUP_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
TOKEN_A = "customer-a-token"
TOKEN_B = "customer-b-token"

DELIVERY_TIMELINE = [
    "placed",
    "payment_held",
    "confirmed",
    "processing",
    "shipped",
    "delivered",
    "completed",
]

PICKUP_TIMELINE = [
    "placed",
    "payment_held",
    "confirmed",
    "processing",
    "ready",
    "delivered",
    "completed",
]

CANCELLED_TIMELINE = [
    *DELIVERY_TIMELINE,
    "cancelled",
    "refunded",
]


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[str]) -> FakeQuery:
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

    def execute(self) -> MagicMock:
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
                rows = [row for row in rows if row.get(column) == value]
            elif op == "in":
                allowed = set(value)
                rows = [row for row in rows if row.get(column) in allowed]
        return rows


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "orders": FakeTable(),
            "order_items": FakeTable(),
            "order_events": FakeTable(),
            "payments": FakeTable(),
            "vendors": FakeTable(),
            "invoices": FakeTable(),
            "refunds": FakeTable(),
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


def _apply_supabase_overrides(app: Any, service_wrapper: MagicMock) -> None:
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper


def _seed_vendor(fake: FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_A_ID,
            "display_name": "Kamwala Trading",
        }
    )


def _seed_order(
    fake: FakeSupabaseClient,
    *,
    order_id: str,
    customer_id: str = CUSTOMER_A_ID,
    status: str = "placed",
    fulfilment: str = "delivery",
    cod: bool = False,
) -> None:
    fake.tables["orders"].rows.append(
        {
            "id": order_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "vendor_id": VENDOR_A_ID,
            "customer_id": customer_id,
            "status": status,
            "fulfilment": fulfilment,
            "cod": cod,
            "delivery_fee_ngwee": 5000,
            "created_at": "2026-07-10T10:00:00Z",
        }
    )


def _seed_items(fake: FakeSupabaseClient, order_id: str) -> None:
    fake.tables["order_items"].rows.append(
        {
            "id": str(uuid4()),
            "order_id": order_id,
            "qty": 2,
            "unit_price_ngwee": 25000,
            "title_snapshot": "Solar lamp",
        }
    )


def _seed_payment(fake: FakeSupabaseClient, *, status: str = "success") -> None:
    fake.tables["payments"].rows.append(
        {
            "id": str(uuid4()),
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "status": status,
        }
    )


def _seed_events(
    fake: FakeSupabaseClient,
    order_id: str,
    transitions: list[tuple[str | None, str, str]],
) -> None:
    for index, (from_status, to_status, created_at) in enumerate(transitions):
        fake.tables["order_events"].rows.append(
            {
                "id": str(uuid4()),
                "order_id": order_id,
                "from_status": from_status,
                "to_status": to_status,
                "note": None,
                "created_at": created_at,
                "actor": CUSTOMER_A_ID,
            }
        )
        _ = index


def _auth_headers(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def orders_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    _mock_auth(monkeypatch, CUSTOMER_A_ID)
    _seed_vendor(fake_client)
    _seed_order(fake_client, order_id=ORDER_A_ID, status="confirmed")
    _seed_items(fake_client, ORDER_A_ID)
    _seed_payment(fake_client)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _step_keys(timeline: list[TimelineStepOut]) -> list[str]:
    return [step.step_key for step in timeline]


def _step_states(timeline: list[TimelineStepOut]) -> dict[str, str]:
    return {step.step_key: step.state for step in timeline}


@pytest.mark.parametrize(
    ("status", "fulfilment", "cod", "paid", "refunded", "expected_keys"),
    [
        (
            "placed",
            "delivery",
            False,
            True,
            False,
            DELIVERY_TIMELINE,
        ),
        (
            "confirmed",
            "delivery",
            False,
            True,
            False,
            DELIVERY_TIMELINE,
        ),
        (
            "processing",
            "pickup",
            False,
            True,
            False,
            PICKUP_TIMELINE,
        ),
        (
            "ready",
            "pickup",
            False,
            True,
            False,
            PICKUP_TIMELINE,
        ),
        (
            "shipped",
            "delivery",
            False,
            True,
            False,
            DELIVERY_TIMELINE,
        ),
        (
            "delivered",
            "delivery",
            False,
            True,
            False,
            DELIVERY_TIMELINE,
        ),
        (
            "completed",
            "delivery",
            False,
            True,
            False,
            DELIVERY_TIMELINE,
        ),
        (
            "cancelled",
            "delivery",
            False,
            True,
            True,
            CANCELLED_TIMELINE,
        ),
    ],
)
def test_timeline_mapping_per_state(
    status: str,
    fulfilment: str,
    cod: bool,
    paid: bool,
    refunded: bool,
    expected_keys: list[str],
) -> None:
    events: list[dict[str, Any]] = [
        {"to_status": "placed", "created_at": "2026-07-10T10:00:00Z"},
        {"from_status": "placed", "to_status": "confirmed", "created_at": "2026-07-10T10:05:00Z"},
    ]
    if status == "cancelled":
        events.append(
            {
                "from_status": "confirmed",
                "to_status": "cancelled",
                "created_at": "2026-07-10T10:10:00Z",
            }
        )
    elif status != "placed":
        events.append({"to_status": status, "created_at": "2026-07-10T11:00:00Z"})

    timeline = build_customer_timeline(
        status=status,
        fulfilment=fulfilment,
        cod=cod,
        paid=paid,
        refunded=refunded,
        created_at="2026-07-10T10:00:00Z",
        events=events,
    )
    assert _step_keys(timeline) == expected_keys
    states = _step_states(timeline)
    assert states[status if status != "cancelled" else "cancelled"] in {"current", "completed"}


def test_timeline_cod_uses_payment_cod_step() -> None:
    timeline = build_customer_timeline(
        status="placed",
        fulfilment="delivery",
        cod=True,
        paid=False,
        refunded=False,
        created_at="2026-07-10T10:00:00Z",
        events=[{"to_status": "placed", "created_at": "2026-07-10T10:00:00Z"}],
    )
    assert _step_keys(timeline)[1] == "payment_cod"
    assert timeline[1].escrow_copy_key == "cod"


def test_timeline_prepaid_uses_payment_held_step() -> None:
    timeline = build_customer_timeline(
        status="confirmed",
        fulfilment="delivery",
        cod=False,
        paid=True,
        refunded=False,
        created_at="2026-07-10T10:00:00Z",
        events=[
            {"to_status": "placed", "created_at": "2026-07-10T10:00:00Z"},
            {"to_status": "confirmed", "created_at": "2026-07-10T10:05:00Z"},
        ],
    )
    assert _step_keys(timeline)[1] == "payment_held"
    assert timeline[1].escrow_copy_key == "held"
    completed_keys = [step.step_key for step in timeline if step.state == "completed"]
    assert "payment_held" in completed_keys
    assert next(step for step in timeline if step.step_key == "confirmed").state == "current"


def test_timeline_completed_marks_escrow_released() -> None:
    timeline = build_customer_timeline(
        status="completed",
        fulfilment="delivery",
        cod=False,
        paid=True,
        refunded=False,
        created_at="2026-07-10T10:00:00Z",
        events=[{"to_status": "completed", "created_at": "2026-07-10T12:00:00Z"}],
    )
    completed_step = next(step for step in timeline if step.step_key == "completed")
    assert completed_step.state == "current"
    assert completed_step.escrow_copy_key == "released"


def test_list_orders_groups_by_checkout_group(orders_client: TestClient) -> None:
    response = orders_client.get("/account/orders", headers=_auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["groups"]) == 1
    group = payload["groups"][0]
    assert group["checkout_group_id"] == CHECKOUT_GROUP_ID
    assert len(group["orders"]) == 1
    assert group["orders"][0]["vendor_name"] == "Kamwala Trading"
    assert group["orders"][0]["payment_mode"] == "prepaid"
    assert group["orders"][0]["total_ngwee"] == 55000


def test_get_order_detail_includes_timeline(orders_client: TestClient) -> None:
    response = orders_client.get(f"/account/orders/{ORDER_A_ID}", headers=_auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "confirmed"
    assert payload["payment_mode"] == "prepaid"
    assert len(payload["timeline"]) >= 5
    assert payload["timeline"][1]["step_key"] == "payment_held"


def test_other_customer_gets_404(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_auth(monkeypatch, CUSTOMER_B_ID)
    _seed_vendor(fake_client)
    _seed_order(fake_client, order_id=ORDER_A_ID, customer_id=CUSTOMER_A_ID)
    _seed_items(fake_client, ORDER_A_ID)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/account/orders/{ORDER_A_ID}", headers=_auth_headers(TOKEN_B))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    app.dependency_overrides.clear()


def test_cod_order_detail_payment_mode(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_auth(monkeypatch, CUSTOMER_A_ID)
    _seed_vendor(fake_client)
    _seed_order(fake_client, order_id=ORDER_A_ID, status="placed", cod=True)
    _seed_items(fake_client, ORDER_A_ID)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/account/orders/{ORDER_A_ID}", headers=_auth_headers())
        assert response.status_code == 200
        payload = response.json()
        assert payload["payment_mode"] == "cod"
        assert payload["paid"] is False
        assert payload["timeline"][1]["step_key"] == "payment_cod"

    app.dependency_overrides.clear()


def test_pickup_only_on_ready_pickup_owner(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_auth(monkeypatch, CUSTOMER_A_ID)
    _seed_vendor(fake_client)
    _seed_order(
        fake_client,
        order_id=ORDER_A_ID,
        status="ready",
        fulfilment="pickup",
    )
    _seed_items(fake_client, ORDER_A_ID)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    with TestClient(app, raise_server_exceptions=False) as client:
        ready_response = client.get(f"/account/orders/{ORDER_A_ID}", headers=_auth_headers())
        assert ready_response.status_code == 200
        pickup = ready_response.json()["pickup"]
        assert pickup is not None
        assert pickup["stub"] is True

        for row in fake_client.tables["orders"].rows:
            if row["id"] == ORDER_A_ID:
                row["status"] = "processing"
        processing_response = client.get(
            f"/account/orders/{ORDER_A_ID}",
            headers=_auth_headers(),
        )
        assert processing_response.json()["pickup"] is None

    app.dependency_overrides.clear()


def test_pickup_with_credentials_not_stubbed(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_auth(monkeypatch, CUSTOMER_A_ID)
    _seed_vendor(fake_client)
    _seed_order(
        fake_client,
        order_id=ORDER_A_ID,
        status="ready",
        fulfilment="pickup",
    )
    for row in fake_client.tables["orders"].rows:
        if row["id"] == ORDER_A_ID:
            row["pickup_qr_token"] = "qr-token-abc"
            row["pickup_pin"] = "123456"
    _seed_items(fake_client, ORDER_A_ID)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/account/orders/{ORDER_A_ID}", headers=_auth_headers())
        pickup = response.json()["pickup"]
        assert pickup["qr_token"] == "qr-token-abc"
        assert pickup["pin"] == "123456"
        assert pickup["stub"] is False

    app.dependency_overrides.clear()


def test_invoice_link_stub_when_invoice_exists(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_auth(monkeypatch, CUSTOMER_A_ID)
    _seed_vendor(fake_client)
    _seed_order(fake_client, order_id=ORDER_A_ID, status="completed")
    _seed_items(fake_client, ORDER_A_ID)
    fake_client.tables["invoices"].rows.append(
        {
            "id": "99999999-9999-9999-9999-999999999999",
            "series": "VG",
            "no": 1,
            "order_id": ORDER_A_ID,
            "created_at": "2026-07-10T12:00:00Z",
        }
    )
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/account/orders/{ORDER_A_ID}", headers=_auth_headers())
        invoice = response.json()["invoice"]
        assert invoice is not None
        assert invoice["stub"] is True
        assert invoice["download_url"] == f"/account/orders/{ORDER_A_ID}/invoice"

    app.dependency_overrides.clear()
