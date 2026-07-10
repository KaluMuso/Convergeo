"""M11-P03 — RFQ quote lifecycle tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.rfq.broadcast import RFQ_MATCH_EVENT
from fastapi import FastAPI
from fastapi.testclient import TestClient

CUSTOMER_A_ID = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_OWNER_A = "33333333-3333-3333-3333-333333333333"
VENDOR_OWNER_B = "44444444-4444-4444-4444-444444444444"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
JOB_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
QUOTE_A_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
QUOTE_B_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = list(filters)
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
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

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            rows: list[dict[str, Any]]
            if isinstance(self._payload, list):
                rows = []
                for item in self._payload:
                    row = dict(item)
                    if "id" not in row:
                        row["id"] = str(uuid4())
                    if "created_at" not in row:
                        row["created_at"] = datetime.now(UTC).isoformat()
                    if "updated_at" not in row:
                        row["updated_at"] = row["created_at"]
                    self._parent.rows.append(row)
                    rows.append(row)
            else:
                assert isinstance(self._payload, dict)
                row = dict(self._payload)
                if "id" not in row:
                    row["id"] = str(uuid4())
                if "created_at" not in row:
                    row["created_at"] = datetime.now(UTC).isoformat()
                if "updated_at" not in row:
                    row["updated_at"] = row["created_at"]
                self._parent.rows.append(row)
                rows = [row]
            return MagicMock(data=rows[0] if self._maybe_single and rows else rows, count=len(rows))

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

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
        if self._in_filter is not None:
            column, values = self._in_filter
            if row.get(column) not in values:
                return False
        return True

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        if self._in_filter is not None:
            column, values = self._in_filter
            rows = [row for row in rows if row.get(column) in values]
        return rows


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "jobs": FakeTable(),
            "job_quotes": FakeTable(),
            "vendors": FakeTable(),
            "services": FakeTable(),
            "audit_log": FakeTable(),
            "notification_outbox": FakeTable(),
            "vendor_listings": FakeTable(),
            "order_item_products": FakeTable(),
            "reviews": FakeTable(),
            "orders": FakeTable(),
            "order_items": FakeTable(),
            "rate_counters": FakeTable(),
        }

    @property
    def client(self) -> FakeSupabaseClient:
        return self

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


def _seed_vendor(
    fake: FakeSupabaseClient,
    *,
    vendor_id: str,
    owner_user_id: str,
    display_name: str,
    slug: str | None = None,
    preferred_badge: bool = False,
) -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": vendor_id,
            "owner_user_id": owner_user_id,
            "display_name": display_name,
            "slug": slug or display_name.lower().replace(" ", "-"),
            "preferred_badge": preferred_badge,
            "status": "active",
            "caps_snapshot": {},
        }
    )


def _seed_service(
    fake: FakeSupabaseClient,
    *,
    service_id: str,
    vendor_id: str,
    category: str,
    service_area: str,
) -> None:
    fake.tables["services"].rows.append(
        {
            "id": service_id,
            "vendor_id": vendor_id,
            "category": category,
            "service_area": service_area,
            "status": "active",
        }
    )


def _seed_job(
    fake: FakeSupabaseClient,
    *,
    job_id: str = JOB_ID,
    customer_id: str = CUSTOMER_A_ID,
    category: str = "home_services",
    status: str = "open",
    service_area: str = "Lusaka, Woodlands",
) -> None:
    now = datetime.now(UTC).isoformat()
    fake.tables["jobs"].rows.append(
        {
            "id": job_id,
            "customer_id": customer_id,
            "category": category,
            "description": "Fix leaking kitchen tap",
            "preferred_date": None,
            "budget_band_min_ngwee": 50_000,
            "budget_band_max_ngwee": 200_000,
            "status": status,
            "created_at": now,
            "updated_at": now,
        }
    )
    fake.tables["audit_log"].rows.append(
        {
            "id": str(uuid4()),
            "actor": customer_id,
            "action": "job.created",
            "entity_type": "job",
            "entity_id": job_id,
            "before": None,
            "after": {"service_area": service_area, "category": category},
            "created_at": now,
        }
    )


def _seed_quote(
    fake: FakeSupabaseClient,
    *,
    quote_id: str,
    job_id: str,
    provider_vendor_id: str,
    amount_ngwee: int,
    status: str = "submitted",
    expires_at: datetime | None = None,
    message: str | None = "I can help",
) -> None:
    now = datetime.now(UTC)
    fake.tables["job_quotes"].rows.append(
        {
            "id": quote_id,
            "job_id": job_id,
            "provider_vendor_id": provider_vendor_id,
            "amount_ngwee": amount_ngwee,
            "message": message,
            "status": status,
            "expires_at": (expires_at or now + timedelta(days=7)).isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
    )


def _seed_match_outbox(
    fake: FakeSupabaseClient,
    *,
    job_id: str,
    vendor_id: str,
) -> None:
    fake.tables["notification_outbox"].rows.append(
        {
            "id": str(uuid4()),
            "event_type": RFQ_MATCH_EVENT,
            "entity_id": f"{job_id}:{vendor_id}",
            "channel": "whatsapp",
            "payload": {},
        }
    )


def _make_client_app(fake: FakeSupabaseClient, user: CurrentUser) -> TestClient:
    app: FastAPI = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _allow_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.quotes.bump_rate_counter",
        lambda **kwargs: (True, 0),
    )


@pytest.fixture
def seeded_fake() -> FakeSupabaseClient:
    fake = FakeSupabaseClient()
    _seed_vendor(
        fake,
        vendor_id=VENDOR_A_ID,
        owner_user_id=VENDOR_OWNER_A,
        display_name="Alpha Plumbing",
        preferred_badge=True,
    )
    _seed_vendor(
        fake,
        vendor_id=VENDOR_B_ID,
        owner_user_id=VENDOR_OWNER_B,
        display_name="Beta Repairs",
    )
    _seed_service(
        fake,
        service_id="service-a",
        vendor_id=VENDOR_A_ID,
        category="home_services",
        service_area="Lusaka, Woodlands",
    )
    _seed_service(
        fake,
        service_id="service-b",
        vendor_id=VENDOR_B_ID,
        category="home_services",
        service_area="Lusaka, Woodlands",
    )
    _seed_job(fake)
    _seed_match_outbox(fake, job_id=JOB_ID, vendor_id=VENDOR_A_ID)
    _seed_match_outbox(fake, job_id=JOB_ID, vendor_id=VENDOR_B_ID)
    _seed_quote(
        fake,
        quote_id=QUOTE_A_ID,
        job_id=JOB_ID,
        provider_vendor_id=VENDOR_A_ID,
        amount_ngwee=150_000,
    )
    _seed_quote(
        fake,
        quote_id=QUOTE_B_ID,
        job_id=JOB_ID,
        provider_vendor_id=VENDOR_B_ID,
        amount_ngwee=120_000,
    )
    return fake


class TestRivalQuoteIsolation:
    def test_provider_a_sees_only_own_quote(self, seeded_fake: FakeSupabaseClient) -> None:
        client = _make_client_app(
            seeded_fake,
            CurrentUser(id=VENDOR_OWNER_A, roles=frozenset({"vendor"}), token="token-a"),
        )
        response = client.get(f"/jobs/{JOB_ID}/quotes")
        assert response.status_code == 200
        body = response.json()
        assert body["view"] == "provider_own"
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == QUOTE_A_ID
        assert body["items"][0]["provider_vendor_id"] == VENDOR_A_ID

    def test_provider_b_sees_only_own_quote(self, seeded_fake: FakeSupabaseClient) -> None:
        client = _make_client_app(
            seeded_fake,
            CurrentUser(id=VENDOR_OWNER_B, roles=frozenset({"vendor"}), token="token-b"),
        )
        response = client.get(f"/jobs/{JOB_ID}/quotes")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == QUOTE_B_ID


class TestQuoteValidityExpiry:
    def test_expired_quote_dropped_from_compare(self, seeded_fake: FakeSupabaseClient) -> None:
        for row in seeded_fake.tables["job_quotes"].rows:
            if row["id"] == QUOTE_B_ID:
                row["expires_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        client = _make_client_app(
            seeded_fake,
            CurrentUser(id=CUSTOMER_A_ID, roles=frozenset({"customer"}), token="token-c"),
        )
        response = client.get(f"/jobs/{JOB_ID}/quotes")
        assert response.status_code == 200
        body = response.json()
        assert body["view"] == "customer_compare"
        quote_ids = {item["id"] for item in body["items"]}
        assert QUOTE_A_ID in quote_ids
        assert QUOTE_B_ID not in quote_ids

        expired_row = next(
            row for row in seeded_fake.tables["job_quotes"].rows if row["id"] == QUOTE_B_ID
        )
        assert expired_row["status"] == "expired"


class TestCompareOrdering:
    def test_customer_compare_sorted_by_price_then_rating(
        self, seeded_fake: FakeSupabaseClient
    ) -> None:
        seeded_fake.tables["reviews"].rows.extend(
            [
                {
                    "id": str(uuid4()),
                    "order_item_id": str(uuid4()),
                    "vendor_id": VENDOR_A_ID,
                    "rating": 5,
                },
                {
                    "id": str(uuid4()),
                    "order_item_id": str(uuid4()),
                    "vendor_id": VENDOR_B_ID,
                    "rating": 3,
                },
            ]
        )
        listing_a = str(uuid4())
        listing_b = str(uuid4())
        seeded_fake.tables["vendor_listings"].rows.extend(
            [
                {"id": listing_a, "vendor_id": VENDOR_A_ID, "status": "active"},
                {"id": listing_b, "vendor_id": VENDOR_B_ID, "status": "active"},
            ]
        )
        item_a = str(uuid4())
        item_b = str(uuid4())
        seeded_fake.tables["order_item_products"].rows.extend(
            [
                {"order_item_id": item_a, "listing_id": listing_a},
                {"order_item_id": item_b, "listing_id": listing_b},
            ]
        )
        seeded_fake.tables["reviews"].rows[0]["order_item_id"] = item_a
        seeded_fake.tables["reviews"].rows[1]["order_item_id"] = item_b

        client = _make_client_app(
            seeded_fake,
            CurrentUser(id=CUSTOMER_A_ID, roles=frozenset({"customer"}), token="token-c"),
        )
        response = client.get(f"/jobs/{JOB_ID}/quotes")
        assert response.status_code == 200
        items = response.json()["items"]
        assert [item["id"] for item in items] == [QUOTE_B_ID, QUOTE_A_ID]
        assert items[0]["amount_ngwee"] < items[1]["amount_ngwee"]


class TestWithdrawal:
    def test_provider_can_withdraw_before_acceptance(self, seeded_fake: FakeSupabaseClient) -> None:
        client = _make_client_app(
            seeded_fake,
            CurrentUser(id=VENDOR_OWNER_A, roles=frozenset({"vendor"}), token="token-a"),
        )
        response = client.post(f"/quotes/{QUOTE_A_ID}/withdraw")
        assert response.status_code == 200
        assert response.json()["quote"]["status"] == "declined"

        compare_client = _make_client_app(
            seeded_fake,
            CurrentUser(id=CUSTOMER_A_ID, roles=frozenset({"customer"}), token="token-c"),
        )
        compare = compare_client.get(f"/jobs/{JOB_ID}/quotes")
        quote_ids = {item["id"] for item in compare.json()["items"]}
        assert QUOTE_A_ID not in quote_ids


class TestAuthz:
    def test_non_matched_provider_cannot_submit_quote(self, seeded_fake: FakeSupabaseClient) -> None:
        unmatched_vendor_id = "99999999-9999-9999-9999-999999999999"
        unmatched_owner = "88888888-8888-8888-8888-888888888888"
        _seed_vendor(
            seeded_fake,
            vendor_id=unmatched_vendor_id,
            owner_user_id=unmatched_owner,
            display_name="Gamma Odd",
        )
        _seed_service(
            seeded_fake,
            service_id="service-g",
            vendor_id=unmatched_vendor_id,
            category="cleaning",
            service_area="Ndola",
        )

        client = _make_client_app(
            seeded_fake,
            CurrentUser(id=unmatched_owner, roles=frozenset({"vendor"}), token="token-g"),
        )
        response = client.post(
            f"/jobs/{JOB_ID}/quotes",
            json={"amount_ngwee": 100_000, "message": "Hello", "validity_days": 7},
        )
        assert response.status_code == 403

    def test_non_owner_customer_cannot_view_compare(self, seeded_fake: FakeSupabaseClient) -> None:
        client = _make_client_app(
            seeded_fake,
            CurrentUser(id=CUSTOMER_B_ID, roles=frozenset({"customer"}), token="token-b2"),
        )
        response = client.get(f"/jobs/{JOB_ID}/quotes")
        assert response.status_code == 403

    def test_submit_quote_succeeds_for_matched_provider(
        self, seeded_fake: FakeSupabaseClient
    ) -> None:
        seeded_fake.tables["job_quotes"].rows.clear()
        client = _make_client_app(
            seeded_fake,
            CurrentUser(id=VENDOR_OWNER_A, roles=frozenset({"vendor"}), token="token-a"),
        )
        response = client.post(
            f"/jobs/{JOB_ID}/quotes",
            json={"amount_ngwee": 175_000, "message": "Tomorrow works", "validity_days": 5},
        )
        assert response.status_code == 200
        assert response.json()["quote"]["amount_ngwee"] == 175_000
