"""Tests for customer-scoped payment status polling and retry."""

from __future__ import annotations

from collections.abc import Generator
from copy import deepcopy
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import NAMESPACE_URL, uuid4, uuid5

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
VENDOR_A_ID = "33333333-3333-3333-3333-333333333333"
VENDOR_B_ID = "44444444-4444-4444-4444-444444444444"
CONTEXT_VERSION = "2026-07-10T10:00:00Z"


def _context_fixture_id(label: str) -> str:
    return str(uuid5(NAMESPACE_URL, label))


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._columns = "*"

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        self._columns = columns
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("neq", column, value))
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

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        self._parent.operations.append(self._pending_op or "select")
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
        rows = self._embed_graph(rows)
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _embed_graph(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = deepcopy(rows)
        if "product_detail:order_item_products" not in self._columns:
            return rows
        client = self._parent.client
        assert client is not None
        # Model one embedded select snapshot, not separately timed relationship reads.
        database = {name: deepcopy(table.rows) for name, table in client.tables.items()}

        def one(table: str, identity: Any, key: str = "id") -> Any:
            matches = [row for row in database[table] if row.get(key) == identity]
            return matches[0] if len(matches) == 1 else (matches or None)

        for row in rows:
            product = one("order_item_products", row["id"], "order_item_id")
            ticket = one("order_item_tickets", row["id"], "order_item_id")
            service = one("order_item_services", row["id"], "order_item_id")
            if isinstance(product, dict):
                product["listing"] = one("vendor_listings", product.get("listing_id"))
            if isinstance(ticket, dict):
                ticket_type = one("ticket_types", ticket.get("ticket_type_id"))
                instance = one("event_instances", ticket.get("instance_id"))
                if isinstance(ticket_type, dict):
                    ticket_type["event"] = one("events", ticket_type.get("event_id"))
                if isinstance(instance, dict):
                    instance["event"] = one("events", instance.get("event_id"))
                ticket.update(ticket_type=ticket_type, instance=instance)
            if isinstance(service, dict):
                service["job"] = one("jobs", service.get("job_id"))
                service["quote"] = one("job_quotes", service.get("quote_id"))
            row.update(product_detail=product, ticket_detail=ticket, service_detail=service)
        return rows

    def _row_matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            cell = row.get(column)
            if op == "eq" and cell != value:
                return False
            if op == "neq" and cell == value:
                return False
            if op == "in" and cell not in value:
                return False
        return True

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if self._row_matches(row)]


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.operations: list[str] = []
        self.client: FakeSupabaseClient | None = None

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
            **{name: FakeTable() for name in (
                "order_items", "order_item_products", "order_item_tickets",
                "order_item_services", "service_payment_obligations", "vendor_listings",
                "jobs", "job_quotes", "ticket_types", "event_instances", "events",
                "notification_outbox", "ledger_transactions", "ledger_postings",
            )},
        }
        for table in self.tables.values():
            table.client = self

    def rpc(self, name: str, params: dict[str, Any]) -> MagicMock:
        from tests.test_payment_state import FakeSupabaseClient as RpcFake

        return RpcFake.rpc(cast(Any, self), name, params)

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
    monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: service_wrapper)
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
    status: str = "pending",
) -> None:
    fake.tables["checkout_groups"].rows.append(
        {
            "id": CHECKOUT_GROUP_ID,
            "customer_id": customer_id,
            "total_ngwee": total_ngwee,
            "subtotal_ngwee": total_ngwee,
            "delivery_fee_ngwee": 0,
            "platform_fee_ngwee": 0,
            "updated_at": CONTEXT_VERSION,
            "status": status,
        }
    )


def _seed_order(
    fake: FakeSupabaseClient,
    *,
    order_id: str = ORDER_A_ID,
    customer_id: str = CUSTOMER_A_ID,
    cod: bool = False,
    vendor_id: str = VENDOR_A_ID,
) -> None:
    fake.tables["orders"].rows.append(
        {
            "id": order_id,
            "checkout_group_id": CHECKOUT_GROUP_ID,
            "customer_id": customer_id,
            "cod": cod,
            "vendor_id": vendor_id,
            "delivery_fee_ngwee": 0,
            "platform_fee_ngwee": 0,
            "updated_at": CONTEXT_VERSION,
            "commission_snapshot": {},
            "created_at": "2026-07-10T10:00:00Z",
        }
    )
    item_id = _context_fixture_id("item:" + order_id)
    listing_id = _context_fixture_id("listing:" + order_id)
    product_id = _context_fixture_id("product:" + order_id)
    fake.tables["order_items"].rows.append({
        "id": item_id, "order_id": order_id, "item_kind": "product",
        "qty": 1, "unit_price_ngwee": 25_000,
        "updated_at": CONTEXT_VERSION,
    })
    fake.tables["order_item_products"].rows.append({
        "order_item_id": item_id, "listing_id": listing_id, "product_id": product_id,
    })
    fake.tables["vendor_listings"].rows.append({
        "id": listing_id, "vendor_id": vendor_id, "product_id": product_id,
        "updated_at": CONTEXT_VERSION,
    })


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
            "app.services.payments.initiate.get",
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

def _seed_ticket_context(fake: FakeSupabaseClient) -> None:
    fake.tables["order_item_products"].rows.clear()
    fake.tables["vendor_listings"].rows.clear()
    item = fake.tables["order_items"].rows[0]
    item.update(item_kind="ticket", qty=2, unit_price_ngwee=12_500)
    event_id = _context_fixture_id("event")
    type_id = _context_fixture_id("ticket-type")
    instance_id = _context_fixture_id("instance")
    fake.tables["order_item_tickets"].rows.append({
        "order_item_id": item["id"], "ticket_type_id": type_id, "instance_id": instance_id,
    })
    fake.tables["ticket_types"].rows.append({
        "id": type_id, "event_id": event_id, "kind": "fixed", "updated_at": CONTEXT_VERSION,
    })
    fake.tables["event_instances"].rows.append({
        "id": instance_id, "event_id": event_id, "updated_at": CONTEXT_VERSION,
    })
    fake.tables["events"].rows.append({
        "id": event_id, "organiser_vendor_id": VENDOR_A_ID, "updated_at": CONTEXT_VERSION,
    })
    fake.tables["orders"].rows[0]["commission_snapshot"] = {
        "fee_payer": "organiser", "platform_fee_ngwee": 0, "lines": [{
            "ticket_type_id": type_id, "instance_id": instance_id, "qty": 2,
            "unit_price_ngwee": 12_500, "line_total_ngwee": 25_000,
        }],
    }


def _seed_service_context(fake: FakeSupabaseClient, *, leg: str = "deposit") -> None:
    fake.tables["order_item_products"].rows.clear()
    fake.tables["vendor_listings"].rows.clear()
    job_id = _context_fixture_id("job")
    quote_id = _context_fixture_id("quote")
    balance_group_id = _context_fixture_id("balance-group")
    item = fake.tables["order_items"].rows[0]
    item["item_kind"] = "service_deposit"
    fake.tables["order_item_services"].rows.append({
        "order_item_id": item["id"], "job_id": job_id, "quote_id": quote_id,
    })
    fake.tables["jobs"].rows.append({
        "id": job_id, "customer_id": CUSTOMER_A_ID, "updated_at": CONTEXT_VERSION,
    })
    fake.tables["job_quotes"].rows.append({
        "id": quote_id, "job_id": job_id, "provider_vendor_id": VENDOR_A_ID,
        "amount_ngwee": 50_000, "status": "accepted",
        "updated_at": CONTEXT_VERSION,
    })
    fake.tables["orders"].rows[0]["commission_snapshot"] = {
        "job_id": job_id, "quote_id": quote_id, "basis": "total_job_value",
        "lines": [{"line_total_ngwee": 50_000, "qty": 1, "unit_price_ngwee": 50_000}],
    }
    fake.tables["checkout_groups"].rows.append({
        "id": balance_group_id, "customer_id": CUSTOMER_A_ID,
        "total_ngwee": 25_000, "status": "pending",
        "subtotal_ngwee": 25_000, "delivery_fee_ngwee": 0, "platform_fee_ngwee": 0,
        "updated_at": CONTEXT_VERSION,
    })
    for selected_leg, group_id in (
        ("deposit", CHECKOUT_GROUP_ID), ("balance", balance_group_id)
    ):
        fake.tables["service_payment_obligations"].rows.append({
            "id": _context_fixture_id(selected_leg + "-obligation"), "order_id": ORDER_A_ID,
            "job_id": job_id, "checkout_group_id": group_id, "leg": selected_leg,
            "amount_ngwee": 25_000, "can_pay": False,
        })
    if leg == "balance":
        fake.tables["payments"].rows[0]["checkout_group_id"] = balance_group_id


class TestPaymentCheckoutContext:
    @pytest.fixture(autouse=True)
    def no_side_effects(
        self, fake_client: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch,
    ) -> Generator[None, None, None]:
        blocked = MagicMock(side_effect=AssertionError("read context must not mutate or claim"))
        async_blocked = AsyncMock(side_effect=AssertionError("read context must not initiate"))
        monkeypatch.setattr(fake_client, "rpc", blocked)
        monkeypatch.setattr("app.routers.payment_status.initiate_checkout_payment", async_blocked)
        monkeypatch.setattr(
            "app.routers.payment_status._create_retry_payment_attempt", async_blocked
        )
        monkeypatch.setattr("app.services.payments.initiate.get", blocked)
        monkeypatch.setattr("app.routers.payments_card.claim_payment_attempt", blocked)
        monkeypatch.setattr("app.routers.payments_card.verify_card_payment_return", async_blocked)
        yield
        blocked.assert_not_called()
        async_blocked.assert_not_called()
        for table in fake_client.tables.values():
            assert set(table.operations) <= {"select"}

    def test_product_exact_card_attempt_has_complete_context(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
    ) -> None:
        fake_client.tables["payments"].rows[0]["rail"] = "card"
        before = deepcopy({name: table.rows for name, table in fake_client.tables.items()})
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        body = response.json()
        context = body["checkout_context"]
        assert context == {
            "version": 1, "kind": "product", "buyer_id": CUSTOMER_A_ID,
            "payment_id": PAYMENT_A_ID, "checkout_group_id": CHECKOUT_GROUP_ID,
            "order_ids": [ORDER_A_ID], "rail": "card", "cod": False,
            "amount_ngwee": 25_000, "currency": "ZMW",
            "orders": [{"order_id": ORDER_A_ID, "lines": [{
                "order_item_id": _context_fixture_id("item:" + ORDER_A_ID),
                "item_kind": "product", "listing_id": _context_fixture_id("listing:" + ORDER_A_ID),
                "product_id": _context_fixture_id("product:" + ORDER_A_ID),
            }]}],
        }
        assert body["payer_phone"] == "+260971234567"
        assert body["status"] == "ussd_pushed"
        assert before == {name: table.rows for name, table in fake_client.tables.items()}

    def test_product_covers_every_vendor_order(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
    ) -> None:
        second = _context_fixture_id("second-order")
        _seed_order(fake_client, order_id=second, vendor_id=VENDOR_B_ID)
        fake_client.tables["checkout_groups"].rows[0]["total_ngwee"] = 50_000
        fake_client.tables["checkout_groups"].rows[0]["subtotal_ngwee"] = 50_000
        fake_client.tables["payments"].rows[0]["amount_ngwee"] = 50_000
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        context = response.json()["checkout_context"]
        assert set(context["order_ids"]) == {ORDER_A_ID, second}
        assert {order["order_id"] for order in context["orders"]} == {ORDER_A_ID, second}
        assert sum(len(order["lines"]) for order in context["orders"]) == 2

    def test_product_without_catalog_id_does_not_invent_one(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
    ) -> None:
        fake_client.tables["order_item_products"].rows[0]["product_id"] = None
        fake_client.tables["vendor_listings"].rows[0]["product_id"] = None
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        line = response.json()["checkout_context"]["orders"][0]["lines"][0]
        assert "product_id" not in line

    @pytest.mark.parametrize("status", ["ussd_pushed", "success", "failed"])
    def test_ticket_keeps_canonical_paid_line(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient, status: str,
    ) -> None:
        _seed_ticket_context(fake_client)
        fake_client.tables["payments"].rows[0].update(status=status, rail="card")
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        body = response.json()
        context = body["checkout_context"]
        assert body["status"] == status
        assert context["kind"] == "ticket"
        assert context["order_ids"] == [ORDER_A_ID]
        assert context["ticket"] == {"order_id": ORDER_A_ID, "lines": [{
            "order_item_id": _context_fixture_id("item:" + ORDER_A_ID),
            "ticket_type_id": _context_fixture_id("ticket-type"),
            "instance_id": _context_fixture_id("instance"), "qty": 2, "unit_price_ngwee": 12_500,
        }]}

    @pytest.mark.parametrize("leg", ["deposit", "balance"])
    @pytest.mark.parametrize("status", ["ussd_pushed", "success", "failed"])
    def test_service_original_order_and_exact_current_attempt(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        leg: str, status: str,
    ) -> None:
        _seed_service_context(fake_client, leg=leg)
        payment = fake_client.tables["payments"].rows[0]
        payment.update(status=status, rail="card")
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        body = response.json()
        context = body["checkout_context"]
        assert body["status"] == status
        assert body["order_id"] == ORDER_A_ID
        assert context["kind"] == "service"
        assert context["checkout_group_id"] == payment["checkout_group_id"]
        assert context["order_ids"] == [ORDER_A_ID]
        assert context["service"] == {
            "job_id": _context_fixture_id("job"),
            "obligation_id": _context_fixture_id(leg + "-obligation"), "leg": leg,
            "order_id": ORDER_A_ID, "obligation_amount_ngwee": 25_000,
            "current_payment_id": PAYMENT_A_ID,
        }
        # Pending returns remain readable: can_pay=false is not a read gate.
        assert all(not row["can_pay"] for row in
                   fake_client.tables["service_payment_obligations"].rows)

    def test_group_only_is_additive_and_unchanged(
        self, payment_status_client: TestClient,
    ) -> None:
        response = payment_status_client.get(
            f"/payments/status?group={CHECKOUT_GROUP_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        assert response.json()["checkout_context"] is None
        assert response.json()["payment_id"] == PAYMENT_A_ID
        assert response.json()["status"] == "ussd_pushed"

    def test_context_requires_authentication(self, payment_status_client: TestClient) -> None:
        response = payment_status_client.get(f"/payments/status?payment={PAYMENT_A_ID}")
        assert response.status_code == 401

    def test_unknown_exact_payment_does_not_fall_back_to_group_latest(
        self, payment_status_client: TestClient,
    ) -> None:
        response = payment_status_client.get(
            f"/payments/status?payment={_context_fixture_id('unknown')}&group={CHECKOUT_GROUP_ID}",
            headers=_auth_headers(),
        )
        assert response.status_code == 404

    def test_conflicting_group_hint_is_rejected(
        self, payment_status_client: TestClient,
    ) -> None:
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}&group={_context_fixture_id('wrong-group')}",
            headers=_auth_headers(),
        )
        assert response.status_code == 409

    def test_currency_and_domain_are_not_inferred_from_hints_or_provider_raw(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
    ) -> None:
        fake_client.tables["payments"].rows[0]["raw"]["currency"] = "USD"
        fake_client.tables["payments"].rows[0]["raw"]["kind"] = "service"
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}&kind=ticket&currency=USD",
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        context = response.json()["checkout_context"]
        assert context["kind"] == "product"
        assert context["currency"] == "ZMW"

    @pytest.mark.parametrize("case,expected", [
        ("foreign_group", 403), ("foreign_order", 403), ("foreign_second_order", 403),
        ("missing_items", 409), ("missing_extension", 409), ("duplicate_order", 409),
        ("duplicate_item", 409), ("duplicate_extension", 409), ("conflicting_extension", 409),
        ("mixed", 409), ("null_kind", 409), ("missing_listing", 409), ("wrong_product", 409),
        ("wrong_listing_vendor", 409), ("wrong_payment_amount", 409), ("wrong_group_amount", 409),
        ("wrong_line_amount", 409), ("cod", 409), ("rail_cod", 409), ("wrong_provider", 409),
    ])
    def test_product_binding_rejects_ambiguous_or_foreign_data(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        case: str, expected: int,
    ) -> None:
        tables = fake_client.tables
        if case == "foreign_group":
            tables["checkout_groups"].rows[0]["customer_id"] = CUSTOMER_B_ID
        elif case == "foreign_order":
            tables["orders"].rows[0]["customer_id"] = CUSTOMER_B_ID
        elif case == "foreign_second_order":
            _seed_order(fake_client, order_id=_context_fixture_id("foreign-order"),
                        customer_id=CUSTOMER_B_ID)
        elif case == "missing_items":
            tables["order_items"].rows.clear()
        elif case == "missing_extension":
            tables["order_item_products"].rows.clear()
        elif case.startswith("duplicate"):
            name = {"duplicate_order": "orders", "duplicate_item": "order_items",
                    "duplicate_extension": "order_item_products"}[case]
            tables[name].rows.append(deepcopy(tables[name].rows[0]))
        elif case == "conflicting_extension":
            tables["order_item_services"].rows.append({
                "order_item_id": tables["order_items"].rows[0]["id"],
                "job_id": _context_fixture_id("job"), "quote_id": _context_fixture_id("quote"),
            })
        elif case == "mixed":
            tables["order_items"].rows.append({
                "id": _context_fixture_id("mixed"), "order_id": ORDER_A_ID,
                "item_kind": "ticket", "qty": 1, "unit_price_ngwee": 1,
            })
        elif case == "null_kind":
            tables["order_items"].rows[0]["item_kind"] = None
        elif case == "missing_listing":
            tables["vendor_listings"].rows.clear()
        elif case == "wrong_product":
            tables["order_item_products"].rows[0]["product_id"] = _context_fixture_id("wrong")
        elif case == "wrong_listing_vendor":
            tables["vendor_listings"].rows[0]["vendor_id"] = VENDOR_B_ID
        elif case == "wrong_payment_amount":
            tables["payments"].rows[0]["amount_ngwee"] = 30_000
        elif case == "wrong_group_amount":
            tables["checkout_groups"].rows[0]["total_ngwee"] = 30_000
        elif case == "wrong_line_amount":
            tables["order_items"].rows[0]["unit_price_ngwee"] = 30_000
        elif case == "cod":
            tables["orders"].rows[0]["cod"] = True
        elif case == "rail_cod":
            tables["payments"].rows[0]["rail"] = "cod"
        elif case == "wrong_provider":
            tables["payments"].rows[0]["provider"] = "unknown"
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == expected
        assert "checkout_context" not in response.json()

    @pytest.mark.parametrize("field", ["payment", "group", "qty", "unit_price"])
    @pytest.mark.parametrize("value", [0, -1, True, 1.5, "25000", 2**53, None])
    def test_unsafe_or_malformed_integer_is_not_a_context(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        field: str, value: Any,
    ) -> None:
        if field in {"payment", "group"}:
            table = "payments" if field == "payment" else "checkout_groups"
            key = "amount_ngwee" if field == "payment" else "total_ngwee"
        else:
            table = "order_items"
            key = "qty" if field == "qty" else "unit_price_ngwee"
        fake_client.tables[table].rows[0][key] = value
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 409

    @pytest.mark.parametrize("case", [
        "missing_detail", "duplicate_detail", "wrong_type_event", "wrong_instance_event",
        "foreign_organiser", "free_rsvp", "wrong_total", "multiple_lines",
    ])
    def test_ticket_binding_rejects_noncanonical_data(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient, case: str,
    ) -> None:
        _seed_ticket_context(fake_client)
        tables = fake_client.tables
        if case == "missing_detail":
            tables["order_item_tickets"].rows.clear()
        elif case == "duplicate_detail":
            tables["order_item_tickets"].rows.append(deepcopy(tables["order_item_tickets"].rows[0]))
        elif case == "wrong_type_event":
            tables["ticket_types"].rows[0]["event_id"] = _context_fixture_id("other-event")
        elif case == "wrong_instance_event":
            tables["event_instances"].rows[0]["event_id"] = _context_fixture_id("other-event")
        elif case == "foreign_organiser":
            tables["events"].rows[0]["organiser_vendor_id"] = VENDOR_B_ID
        elif case == "free_rsvp":
            tables["ticket_types"].rows[0]["kind"] = "free_rsvp"
        elif case == "wrong_total":
            tables["payments"].rows[0]["amount_ngwee"] = 30_000
            tables["checkout_groups"].rows[0]["total_ngwee"] = 30_000
        elif case == "multiple_lines":
            other = deepcopy(tables["order_items"].rows[0])
            other["id"] = _context_fixture_id("extra-ticket")
            tables["order_items"].rows.append(other)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 409

    @pytest.mark.parametrize("case,expected", [
        ("foreign_job", 403), ("foreign_original_group", 403),
        ("foreign_original_group_order", 403), ("wrong_quote_vendor", 409),
        ("wrong_quote_job", 409), ("wrong_quote_status", 409), ("wrong_snapshot_job", 409),
        ("wrong_snapshot_quote", 409), ("wrong_snapshot_total", 409), ("wrong_amount", 409),
        ("missing_deposit", 409), ("invalid_leg", 409), ("duplicate_obligation", 409),
        ("stale_attempt", 409), ("tied_attempts", 409), ("malformed_attempt_date", 409),
        ("wrong_original_group", 409), ("wrong_sibling_amount", 409),
    ])
    def test_service_binding_checks_immutable_links_and_current_attempt(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        case: str, expected: int,
    ) -> None:
        _seed_service_context(fake_client, leg="balance")
        tables = fake_client.tables
        obligations = tables["service_payment_obligations"].rows
        balance = obligations[1]
        quote = tables["job_quotes"].rows[0]
        snapshot = tables["orders"].rows[0]["commission_snapshot"]
        if case == "foreign_job":
            tables["jobs"].rows[0]["customer_id"] = CUSTOMER_B_ID
        elif case == "foreign_original_group":
            tables["checkout_groups"].rows[0]["customer_id"] = CUSTOMER_B_ID
        elif case == "foreign_original_group_order":
            _seed_order(fake_client, order_id=_context_fixture_id("foreign-original-order"),
                        customer_id=CUSTOMER_B_ID)
        elif case == "wrong_quote_vendor":
            quote["provider_vendor_id"] = VENDOR_B_ID
        elif case == "wrong_quote_job":
            quote["job_id"] = _context_fixture_id("other-job")
        elif case == "wrong_quote_status":
            quote["status"] = "declined"
        elif case == "wrong_snapshot_job":
            snapshot["job_id"] = _context_fixture_id("other-job")
        elif case == "wrong_snapshot_quote":
            snapshot["quote_id"] = _context_fixture_id("other-quote")
        elif case == "wrong_snapshot_total":
            snapshot["lines"][0]["line_total_ngwee"] = 1
        elif case == "wrong_amount":
            balance["amount_ngwee"] = 1
        elif case == "missing_deposit":
            obligations.pop(0)
        elif case == "invalid_leg":
            balance["leg"] = "other"
        elif case == "duplicate_obligation":
            other = deepcopy(balance)
            other["id"] = _context_fixture_id("duplicate-obligation")
            obligations.append(other)
        elif case in {"stale_attempt", "tied_attempts"}:
            other = deepcopy(tables["payments"].rows[0])
            other["id"] = _context_fixture_id("newer-attempt")
            if case == "stale_attempt":
                other["created_at"] = "2026-07-11T10:00:00Z"
            tables["payments"].rows.append(other)
        elif case == "malformed_attempt_date":
            tables["payments"].rows[0]["created_at"] = "not-a-date"
        elif case == "wrong_original_group":
            tables["orders"].rows[0]["checkout_group_id"] = _context_fixture_id("missing-group")
        elif case == "wrong_sibling_amount":
            obligations[0]["amount_ngwee"] = 1
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == expected

    @pytest.mark.parametrize("malformed", ["truncated", "no_count", "non_list"])
    def test_incomplete_postgrest_results_fail_closed(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        monkeypatch: pytest.MonkeyPatch, malformed: str,
    ) -> None:
        execute = FakeQuery.execute

        def incomplete(query: FakeQuery) -> MagicMock:
            response = execute(query)
            if query._parent is fake_client.tables["orders"] and query._order == ("id", False):
                if malformed == "truncated":
                    response.count = len(response.data) + 1
                elif malformed == "no_count":
                    response.count = None
                else:
                    response.data = None
            return response

        monkeypatch.setattr(FakeQuery, "execute", incomplete)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 409

    def test_link_change_during_projection_is_not_returned(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        execute = FakeQuery.execute
        reads = 0

        def changing(query: FakeQuery) -> MagicMock:
            nonlocal reads
            if query._parent is fake_client.tables["payments"] and query._order == ("id", False):
                reads += 1
                if reads == 2:
                    fake_client.tables["order_item_products"].rows[0]["product_id"] = (
                        _context_fixture_id("changed-after-projection")
                    )
            return execute(query)

        monkeypatch.setattr(FakeQuery, "execute", changing)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 409

    def test_database_failure_is_not_empty_product_context(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        execute = FakeQuery.execute

        def failing(query: FakeQuery) -> MagicMock:
            if query._parent is fake_client.tables["order_items"]:
                raise RuntimeError("synthetic read failure")
            return execute(query)

        monkeypatch.setattr(FakeQuery, "execute", failing)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 500

    def test_product_keeps_requested_attempt_even_when_a_newer_one_exists(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
    ) -> None:
        newer = deepcopy(fake_client.tables["payments"].rows[0])
        newer.update(id=_context_fixture_id("newer-product-attempt"), status="success",
                     created_at="2026-07-12T10:00:00Z")
        fake_client.tables["payments"].rows.append(newer)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        assert response.json()["payment_id"] == PAYMENT_A_ID
        assert response.json()["status"] == "ussd_pushed"
        assert response.json()["checkout_context"]["payment_id"] == PAYMENT_A_ID

    def test_maximum_safe_integer_is_supported_without_float_conversion(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
    ) -> None:
        amount = 2**53 - 1
        fake_client.tables["payments"].rows[0]["amount_ngwee"] = amount
        fake_client.tables["checkout_groups"].rows[0]["total_ngwee"] = amount
        fake_client.tables["checkout_groups"].rows[0]["subtotal_ngwee"] = amount
        fake_client.tables["order_items"].rows[0]["unit_price_ngwee"] = amount
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        assert response.json()["checkout_context"]["amount_ngwee"] == amount

    def test_fully_deposited_service_needs_no_balance_obligation(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
    ) -> None:
        _seed_service_context(fake_client)
        fake_client.tables["service_payment_obligations"].rows.pop()
        fake_client.tables["job_quotes"].rows[0]["amount_ngwee"] = 25_000
        line = fake_client.tables["orders"].rows[0]["commission_snapshot"]["lines"][0]
        line.update(line_total_ngwee=25_000, unit_price_ngwee=25_000)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        assert response.json()["checkout_context"]["service"]["leg"] == "deposit"

    def test_service_balance_order_item_keeps_the_original_spine(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
    ) -> None:
        _seed_service_context(fake_client, leg="balance")
        item_id = _context_fixture_id("service-balance-item")
        fake_client.tables["order_items"].rows.append({
            "id": item_id, "order_id": ORDER_A_ID, "item_kind": "service_balance",
            "qty": 1, "unit_price_ngwee": 25_000,
            "updated_at": CONTEXT_VERSION,
        })
        fake_client.tables["order_item_services"].rows.append({
            "order_item_id": item_id, "job_id": _context_fixture_id("job"),
            "quote_id": _context_fixture_id("quote"),
        })
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        assert response.json()["checkout_context"]["order_ids"] == [ORDER_A_ID]

    def test_new_service_attempt_during_read_invalidates_the_context(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _seed_service_context(fake_client, leg="balance")
        execute = FakeQuery.execute
        reads = 0

        def competing_attempt(query: FakeQuery) -> MagicMock:
            nonlocal reads
            if query._parent is fake_client.tables["payments"] and query._order == ("id", False):
                reads += 1
                # Exact attempt read, current-attempt collection, then verification.
                if reads == 3:
                    newer = deepcopy(fake_client.tables["payments"].rows[0])
                    newer.update(id=_context_fixture_id("competing-service-attempt"),
                                 created_at="2026-07-12T10:00:00Z")
                    fake_client.tables["payments"].rows.append(newer)
            return execute(query)

        monkeypatch.setattr(FakeQuery, "execute", competing_attempt)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 409

    @pytest.mark.parametrize("status", ["ussd_pushed", "success", "failed"])
    def test_ticket_buyer_fee_is_part_of_full_charge(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient, status: str,
    ) -> None:
        _seed_ticket_context(fake_client)
        group = fake_client.tables["checkout_groups"].rows[0]
        order = fake_client.tables["orders"].rows[0]
        group.update(platform_fee_ngwee=1_250, total_ngwee=26_250)
        order["platform_fee_ngwee"] = 1_250
        order["commission_snapshot"].update(fee_payer="buyer", platform_fee_ngwee=1_250)
        fake_client.tables["payments"].rows[0].update(amount_ngwee=26_250, status=status)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        context = response.json()["checkout_context"]
        assert context["amount_ngwee"] == 26_250
        assert context["ticket"]["lines"][0]["qty"] == 2
        assert context["ticket"]["lines"][0]["unit_price_ngwee"] == 12_500

    def test_ticket_uses_frozen_fee_not_current_event_policy(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _seed_ticket_context(fake_client)
        policy = MagicMock(side_effect=AssertionError("do not recompute a frozen charge"))
        monkeypatch.setattr("app.services.events.fees.platform_fee_ngwee", policy)
        monkeypatch.setattr("app.services.events.fees.checkout_total_ngwee", policy)
        fee = 1_377  # Deliberately not the current 5% policy result.
        fake_client.tables["events"].rows[0]["platform_fee_payer"] = "organiser"
        fake_client.tables["checkout_groups"].rows[0].update(
            platform_fee_ngwee=fee, total_ngwee=25_000 + fee
        )
        order = fake_client.tables["orders"].rows[0]
        order["platform_fee_ngwee"] = fee
        order["commission_snapshot"].update(fee_payer="buyer", platform_fee_ngwee=fee)
        fake_client.tables["payments"].rows[0]["amount_ngwee"] = 25_000 + fee
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        assert response.json()["checkout_context"]["amount_ngwee"] == 26_377
        policy.assert_not_called()

    def test_ticket_organiser_paid_fee_remains_zero(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
    ) -> None:
        _seed_ticket_context(fake_client)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        assert response.json()["checkout_context"]["amount_ngwee"] == 25_000

    @pytest.mark.parametrize("location", ["group", "order", "snapshot"])
    @pytest.mark.parametrize("fee", [-1, True, 1.5, "1250", 2**53, None])
    def test_ticket_unsafe_fee_is_not_a_binding(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        location: str, fee: Any,
    ) -> None:
        _seed_ticket_context(fake_client)
        rows = {
            "group": fake_client.tables["checkout_groups"].rows[0],
            "order": fake_client.tables["orders"].rows[0],
            "snapshot": fake_client.tables["orders"].rows[0]["commission_snapshot"],
        }
        rows[location]["platform_fee_ngwee"] = fee
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 409

    @pytest.mark.parametrize("location", ["group", "order", "snapshot"])
    def test_ticket_missing_stored_fee_is_not_assumed_zero(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient, location: str,
    ) -> None:
        _seed_ticket_context(fake_client)
        rows = {
            "group": fake_client.tables["checkout_groups"].rows[0],
            "order": fake_client.tables["orders"].rows[0],
            "snapshot": fake_client.tables["orders"].rows[0]["commission_snapshot"],
        }
        rows[location].pop("platform_fee_ngwee")
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 409

    @pytest.mark.parametrize("case", [
        "order_fee", "snapshot_fee", "subtotal", "full_total", "delivery_fee",
        "organiser_with_buyer_fee", "snapshot_line", "unsafe_combined_total",
    ])
    def test_ticket_fee_and_frozen_totals_must_agree(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient, case: str,
    ) -> None:
        _seed_ticket_context(fake_client)
        group = fake_client.tables["checkout_groups"].rows[0]
        order = fake_client.tables["orders"].rows[0]
        snapshot = order["commission_snapshot"]
        group.update(platform_fee_ngwee=1_250, total_ngwee=26_250)
        order["platform_fee_ngwee"] = 1_250
        snapshot.update(fee_payer="buyer", platform_fee_ngwee=1_250)
        fake_client.tables["payments"].rows[0]["amount_ngwee"] = 26_250
        if case == "order_fee":
            order["platform_fee_ngwee"] = 1_200
        elif case == "snapshot_fee":
            snapshot["platform_fee_ngwee"] = 1_200
        elif case == "subtotal":
            group["subtotal_ngwee"] = 24_999
        elif case == "full_total":
            group["total_ngwee"] = 26_251
            fake_client.tables["payments"].rows[0]["amount_ngwee"] = 26_251
        elif case == "delivery_fee":
            group["delivery_fee_ngwee"] = 1
        elif case == "organiser_with_buyer_fee":
            snapshot["fee_payer"] = "organiser"
        elif case == "snapshot_line":
            snapshot["lines"][0]["ticket_type_id"] = _context_fixture_id("other-type")
        elif case == "unsafe_combined_total":
            group["platform_fee_ngwee"] = 2**53 - 1
            order["platform_fee_ngwee"] = 2**53 - 1
            snapshot["platform_fee_ngwee"] = 2**53 - 1
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 409

    def test_ticket_reparenting_cannot_splice_two_different_graph_snapshots(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _seed_ticket_context(fake_client)
        first_event = _context_fixture_id("event")
        second_event = _context_fixture_id("second-event")
        fake_client.tables["events"].rows.append({
            "id": second_event, "organiser_vendor_id": VENDOR_A_ID,
            "updated_at": CONTEXT_VERSION,
        })
        ticket_type = fake_client.tables["ticket_types"].rows[0]
        instance = fake_client.tables["event_instances"].rows[0]
        instance["event_id"] = second_event
        execute = FakeQuery.execute
        snapshots: list[tuple[str, str]] = []
        separate_reads = 0

        def reparenting(query: FakeQuery) -> MagicMock:
            nonlocal separate_reads
            if query._parent is fake_client.tables["event_instances"]:
                separate_reads += 1
                ticket_type["event_id"], instance["event_id"] = second_event, first_event
            elif query._parent is fake_client.tables["ticket_types"]:
                separate_reads += 1
                ticket_type["event_id"], instance["event_id"] = first_event, second_event
            elif query._parent is fake_client.tables["order_item_tickets"]:
                ticket_type["event_id"], instance["event_id"] = first_event, second_event
            snapshots.append((ticket_type["event_id"], instance["event_id"]))
            return execute(query)

        monkeypatch.setattr(FakeQuery, "execute", reparenting)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 409
        assert separate_reads == 0
        assert snapshots and all(left != right for left, right in snapshots)

    @pytest.mark.parametrize("table,domain", [
        ("checkout_groups", "product"), ("orders", "product"), ("order_items", "product"),
        ("vendor_listings", "product"), ("ticket_types", "ticket"),
        ("event_instances", "ticket"), ("events", "ticket"),
        ("jobs", "service"), ("job_quotes", "service"),
    ])
    def test_version_change_with_restored_link_values_is_rejected(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        monkeypatch: pytest.MonkeyPatch, table: str, domain: str,
    ) -> None:
        if domain == "ticket":
            _seed_ticket_context(fake_client)
        elif domain == "service":
            _seed_service_context(fake_client)
        execute = FakeQuery.execute
        payment_reads = 0

        def changed_version(query: FakeQuery) -> MagicMock:
            nonlocal payment_reads
            if query._parent is fake_client.tables["payments"] and query._order == ("id", False):
                payment_reads += 1
                if payment_reads == 2:
                    # Selected link values have returned to their original values,
                    # but the existing mutation token records the intervening write.
                    fake_client.tables[table].rows[0]["updated_at"] = "2026-07-10T10:00:01Z"
            return execute(query)

        monkeypatch.setattr(FakeQuery, "execute", changed_version)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 409

    @pytest.mark.parametrize("domain,budget", [
        ("product", 13), ("ticket", 13), ("deposit", 21), ("balance", 25),
    ])
    def test_batched_read_budget(
        self, payment_status_client: TestClient, fake_client: FakeSupabaseClient,
        domain: str, budget: int, record_property: Any,
    ) -> None:
        if domain == "ticket":
            _seed_ticket_context(fake_client)
        elif domain in {"deposit", "balance"}:
            _seed_service_context(fake_client, leg=domain)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 200
        reads = sum(table.operations.count("select") for table in fake_client.tables.values())
        record_property("context_domain", domain)
        record_property("context_select_count", reads)
        assert 0 < reads <= budget

    @pytest.mark.parametrize("field", ["product_id", "updated_at"])
    def test_incomplete_embedded_listing_is_not_a_context(
        self, payment_status_client: TestClient, monkeypatch: pytest.MonkeyPatch, field: str,
    ) -> None:
        embed = FakeQuery._embed_graph

        def incomplete(query: FakeQuery, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            graph = embed(query, rows)
            for row in graph:
                detail = row.get("product_detail")
                if isinstance(detail, dict) and isinstance(detail.get("listing"), dict):
                    detail["listing"].pop(field, None)
            return graph

        monkeypatch.setattr(FakeQuery, "_embed_graph", incomplete)
        response = payment_status_client.get(
            f"/payments/status?payment={PAYMENT_A_ID}", headers=_auth_headers()
        )
        assert response.status_code == 409
