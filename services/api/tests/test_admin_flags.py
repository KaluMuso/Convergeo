from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LISTING_ID = "10101010-1010-1010-1010-101010101010"
REVIEW_ID = "20202020-2020-2020-2020-202020202020"
ORDER_ID = "30303030-3030-3030-3030-303030303030"
ORDER_ITEM_ID = "40404040-4040-4040-4040-404040404040"
PAYOUT_ID = "50505050-5050-5050-5050-505050505050"
FLAG_LISTING_ID = "60606060-6060-6060-6060-606060606060"
FLAG_REVIEW_ID = "70707070-7070-7070-7070-707070707070"
FLAG_PROHIBITED_ID = "80808080-8080-8080-8080-808080808080"
PRIOR_FLAG_ID = "90909090-9090-9090-9090-909090909090"
VALID_TOKEN = "valid.jwt.token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._selected_columns = "*"

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        self._selected_columns = columns
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
                row["id"] = f"{len(self._parent.rows):08x}-fake-fake-fake-fakefakefake"
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if all(
                    row.get(column) == value
                    for op, column, value in self._filters
                    if op == "eq"
                ):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

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
                filtered = [row for row in filtered if row.get(column) in value]
        return filtered


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
            "flags": FakeTable(),
            "vendors": FakeTable(),
            "vendor_listings": FakeTable(),
            "reviews": FakeTable(),
            "order_items": FakeTable(),
            "orders": FakeTable(),
            "payouts": FakeTable(),
            "audit_log": FakeTable(),
            "notification_outbox": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


@pytest.fixture
def admin_flags_app() -> Any:
    return create_app()


@pytest.fixture
def admin_flags_client(admin_flags_app: Any) -> Generator[TestClient, None, None]:
    with TestClient(admin_flags_app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    service_wrapper = MagicMock()
    service_wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.routers.admin_flags.get_supabase_client", lambda: service_wrapper)
    return client


def _mock_verify(monkeypatch: pytest.MonkeyPatch, user_id: str = USER_ID) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )


def _mock_roles(monkeypatch: pytest.MonkeyPatch, roles_by_user: dict[str, frozenset[str]]) -> None:
    def fake_load(user_id: str, service_client: Any) -> frozenset[str]:
        _ = service_client
        return roles_by_user.get(user_id, frozenset())

    monkeypatch.setattr("app.core.auth._load_user_roles", fake_load)


def _mock_audit_insert(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    inserted: list[dict[str, Any]] = []

    class AuditFakeQuery:
        def __init__(self, row: dict[str, Any]) -> None:
            self._row = row

        def execute(self) -> MagicMock:
            inserted.append(self._row)
            return MagicMock(data=[{**self._row, "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}])

    class AuditFakeTable:
        def insert(self, row: dict[str, Any]) -> AuditFakeQuery:
            return AuditFakeQuery(row)

    service_client = MagicMock()
    service_client.client.table.side_effect = (
        lambda name: AuditFakeTable() if name == "audit_log" else MagicMock()
    )
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client",
        lambda: service_client,
    )
    return inserted


def _seed_base(fake: FakeSupabaseClient) -> None:
    now = datetime.now(UTC).isoformat()
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": OTHER_USER_ID,
            "slug": "acme-shop",
            "display_name": "Acme Shop",
            "status": "active",
        }
    )
    fake.tables["vendor_listings"].rows.append(
        {
            "id": LISTING_ID,
            "vendor_id": VENDOR_ID,
            "title_override": "Test Listing",
            "status": "active",
            "products": {"name": "Widget"},
        }
    )
    fake.tables["order_items"].rows.append(
        {
            "id": ORDER_ITEM_ID,
            "order_id": ORDER_ID,
        }
    )
    fake.tables["orders"].rows.append(
        {
            "id": ORDER_ID,
            "vendor_id": VENDOR_ID,
            "status": "shipped",
        }
    )
    fake.tables["reviews"].rows.append(
        {
            "id": REVIEW_ID,
            "order_item_id": ORDER_ITEM_ID,
            "rating": 2,
            "body": "Misleading product",
            "status": "published",
        }
    )
    fake.tables["payouts"].rows.append(
        {
            "id": PAYOUT_ID,
            "vendor_id": VENDOR_ID,
            "status": "pending",
        }
    )
    fake.tables["flags"].rows.extend(
        [
            {
                "id": FLAG_LISTING_ID,
                "entity_type": "listing",
                "entity_id": LISTING_ID,
                "reason": "Counterfeit suspicion",
                "reporter_user_id": USER_ID,
                "status": "open",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": FLAG_REVIEW_ID,
                "entity_type": "review",
                "entity_id": REVIEW_ID,
                "reason": "Abusive language",
                "reporter_user_id": USER_ID,
                "status": "open",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": FLAG_PROHIBITED_ID,
                "entity_type": "prohibited",
                "entity_id": LISTING_ID,
                "reason": "Prohibited category attempt",
                "reporter_user_id": USER_ID,
                "status": "open",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": PRIOR_FLAG_ID,
                "entity_type": "listing",
                "entity_id": LISTING_ID,
                "reason": "Prior offence",
                "reporter_user_id": USER_ID,
                "status": "actioned",
                "created_at": now,
                "updated_at": now,
            },
        ]
    )


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def _flag_row(fake: FakeSupabaseClient, flag_id: str) -> dict[str, Any]:
    return next(row for row in fake.tables["flags"].rows if row["id"] == flag_id)


@pytest.mark.parametrize(
    ("flag_id", "endpoint", "expected_flag_status", "expected_template"),
    [
        (FLAG_LISTING_ID, "dismiss", "dismissed", "flag_dismissed"),
        (FLAG_LISTING_ID, "unpublish", "actioned", "listing_unpublished"),
        (FLAG_LISTING_ID, "remove", "actioned", "listing_removed"),
        (FLAG_LISTING_ID, "warn-vendor", "actioned", "vendor_warned"),
        (FLAG_LISTING_ID, "escalate-suspend", "actioned", "vendor_suspended"),
        (FLAG_REVIEW_ID, "remove", "actioned", "review_removed"),
    ],
)
def test_action_semantics_matrix(
    admin_flags_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
    flag_id: str,
    endpoint: str,
    expected_flag_status: str,
    expected_template: str,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    audit_rows = _mock_audit_insert(monkeypatch)
    _seed_base(fake_client)

    response = admin_flags_client.post(
        f"/admin/flags/{flag_id}/{endpoint}",
        headers=_auth_headers(),
        json={"note": "Moderator note"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["flag_status"] == expected_flag_status
    assert body["notification_enqueued"] is True
    assert _flag_row(fake_client, flag_id)["status"] == expected_flag_status
    assert len(audit_rows) == 1
    assert audit_rows[0]["action"] == f"admin.flags.{endpoint.replace('-', '_')}"
    outbox = fake_client.tables["notification_outbox"].rows
    assert len(outbox) >= 1
    assert outbox[-1]["template"] == expected_template


def test_unpublish_sets_listing_paused(
    admin_flags_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_base(fake_client)

    response = admin_flags_client.post(
        f"/admin/flags/{FLAG_LISTING_ID}/unpublish",
        headers=_auth_headers(),
        json={},
    )
    assert response.status_code == 200
    listing = next(
        row for row in fake_client.tables["vendor_listings"].rows if row["id"] == LISTING_ID
    )
    assert listing["status"] == "paused"
    assert response.json()["entity_status"] == "paused"


def test_remove_review_sets_removed_status(
    admin_flags_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_base(fake_client)

    response = admin_flags_client.post(
        f"/admin/flags/{FLAG_REVIEW_ID}/remove",
        headers=_auth_headers(),
        json={},
    )
    assert response.status_code == 200
    review = next(row for row in fake_client.tables["reviews"].rows if row["id"] == REVIEW_ID)
    assert review["status"] == "removed"


def test_suspension_side_effects(
    admin_flags_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)
    _seed_base(fake_client)

    listing_before = next(
        row for row in fake_client.tables["vendor_listings"].rows if row["id"] == LISTING_ID
    )
    order_before = next(row for row in fake_client.tables["orders"].rows if row["id"] == ORDER_ID)
    payout_before = next(
        row for row in fake_client.tables["payouts"].rows if row["id"] == PAYOUT_ID
    )

    response = admin_flags_client.post(
        f"/admin/flags/{FLAG_LISTING_ID}/escalate-suspend",
        headers=_auth_headers(),
        json={"note": "Repeat offender"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["vendor_status"] == "suspended"

    vendor = next(row for row in fake_client.tables["vendors"].rows if row["id"] == VENDOR_ID)
    assert vendor["status"] == "suspended"

    listing_after = next(
        row for row in fake_client.tables["vendor_listings"].rows if row["id"] == LISTING_ID
    )
    order_after = next(row for row in fake_client.tables["orders"].rows if row["id"] == ORDER_ID)
    payout_after = next(row for row in fake_client.tables["payouts"].rows if row["id"] == PAYOUT_ID)

    assert listing_after["status"] == listing_before["status"]
    assert order_after["status"] == order_before["status"]
    assert payout_after["status"] == payout_before["status"]


def test_repeat_offender_counter(
    admin_flags_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _seed_base(fake_client)

    response = admin_flags_client.get("/admin/flags", headers=_auth_headers())
    assert response.status_code == 200
    items = response.json()
    listing_item = next(item for item in items if item["id"] == FLAG_LISTING_ID)
    assert listing_item["repeat_offender_count"] == 1


def test_list_flags_filters_entity_type(
    admin_flags_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _seed_base(fake_client)

    response = admin_flags_client.get(
        "/admin/flags?entity_type=review",
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["entity_type"] == "review"


def test_non_admin_gets_403(
    admin_flags_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, OTHER_USER_ID)
    _mock_roles(monkeypatch, {OTHER_USER_ID: frozenset({"customer"})})
    _seed_base(fake_client)

    response = admin_flags_client.get("/admin/flags", headers=_auth_headers())
    assert response.status_code == 403

    response = admin_flags_client.post(
        f"/admin/flags/{FLAG_LISTING_ID}/dismiss",
        headers=_auth_headers(),
        json={},
    )
    assert response.status_code == 403
