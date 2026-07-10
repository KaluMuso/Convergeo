from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.routers.admin_disputes import (
    ORDER_EVIDENCE_BUCKET,
    SIGNED_URL_TTL_SECONDS,
    compute_order_total_ngwee,
    compute_sla_badge,
    sign_evidence_documents,
)
from app.services.disputes.state import DisputeTransitionError
from fastapi.testclient import TestClient

ADMIN_ID = "66666666-6666-6666-6666-666666666666"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORDER_ID = "30303030-3030-3030-3030-303030303030"
ORDER_B_ID = "31313131-3131-3131-3131-313131313131"
DISPUTE_ID = "40404040-4040-4040-4040-404040404040"
DISPUTE_B_ID = "41414141-4141-4141-4141-414141414141"
DISPUTE_RESOLVED_ID = "42424242-4242-4242-4242-424242424242"
CHECKOUT_GROUP_ID = "50505050-5050-5050-5050-505050505050"
CHECKOUT_GROUP_B_ID = "51515151-5151-5151-5151-515151515151"
ITEM_ID = "61616161-6161-6161-6161-616161616161"
PAYMENT_ID = "71717171-7171-7171-7171-717171717171"
VALID_TOKEN = "valid.jwt.token"
CUSTOMER_MOMO = "260971234567"
ORDER_TOTAL_NGEWEE = 200_000


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

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeStorageBucket:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def create_signed_url(self, path: str, expires_in: int) -> dict[str, Any]:
        self.calls.append((path, expires_in))
        return {
            "signedURL": f"https://example.supabase.co/storage/v1/object/sign/{ORDER_EVIDENCE_BUCKET}/{path}?token=abc",
            "expires_in": expires_in,
        }


class FakeStorage:
    def __init__(self) -> None:
        self.bucket = FakeStorageBucket()

    def from_(self, bucket: str) -> FakeStorageBucket:
        assert bucket == ORDER_EVIDENCE_BUCKET
        return self.bucket


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "disputes": FakeTable(),
            "orders": FakeTable(),
            "order_items": FakeTable(),
            "vendors": FakeTable(),
            "profiles": FakeTable(),
            "payments": FakeTable(),
            "ledger_transactions": FakeTable(),
            "ledger_postings": FakeTable(),
            "audit_log": FakeTable(),
        }
        self.storage = FakeStorage()

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


@pytest.fixture
def admin_disputes_app() -> Any:
    return create_app()


@pytest.fixture
def admin_disputes_client(admin_disputes_app: Any) -> Generator[TestClient, None, None]:
    with TestClient(admin_disputes_app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    service_wrapper = MagicMock()
    service_wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.routers.admin_disputes.get_supabase_client", lambda: service_wrapper)
    return client


def _mock_verify(monkeypatch: pytest.MonkeyPatch, user_id: str = ADMIN_ID) -> None:
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
            return MagicMock(data=[{**self._row, "id": "audit-fake-id"}])

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


def _seed_order_bundle(
    fake: FakeSupabaseClient,
    *,
    order_id: str,
    checkout_group_id: str,
    order_total: int = ORDER_TOTAL_NGEWEE,
) -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "display_name": "Acme Shop",
            "slug": "acme-shop",
        }
    )
    fake.tables["profiles"].rows.append(
        {
            "id": CUSTOMER_ID,
            "phone": CUSTOMER_MOMO,
            "display_name": "John Banda",
        }
    )
    fake.tables["orders"].rows.append(
        {
            "id": order_id,
            "checkout_group_id": checkout_group_id,
            "vendor_id": VENDOR_ID,
            "customer_id": CUSTOMER_ID,
            "status": "completed",
            "fulfilment": "delivery",
            "delivery_fee_ngwee": 0,
            "cod": False,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    fake.tables["order_items"].rows.append(
        {
            "id": ITEM_ID,
            "order_id": order_id,
            "item_kind": "product",
            "qty": 1,
            "unit_price_ngwee": order_total,
            "title_snapshot": "Test item",
        }
    )
    fake.tables["payments"].rows.append(
        {
            "id": PAYMENT_ID,
            "checkout_group_id": checkout_group_id,
            "rail": "mtn",
            "amount_ngwee": order_total,
            "status": "captured",
            "lenco_reference": "pay-ref",
            "created_at": datetime.now(UTC).isoformat(),
        }
    )


def _seed_dispute(
    fake: FakeSupabaseClient,
    *,
    dispute_id: str,
    order_id: str,
    status: str = "under_review",
    evidence_paths: list[str] | None = None,
) -> None:
    now = datetime.now(UTC)
    fake.tables["disputes"].rows.append(
        {
            "id": dispute_id,
            "order_id": order_id,
            "opener_user_id": CUSTOMER_ID,
            "status": status,
            "evidence_paths": evidence_paths
            or [
                f"orders/{CUSTOMER_ID}/{order_id}/evidence-1.jpg",
                f"orders/{CUSTOMER_ID}/{order_id}/vendor-evidence-1.jpg",
            ],
            "vendor_response": "Item was delivered as described.",
            "admin_decision": None,
            "created_at": (now - timedelta(hours=30)).isoformat(),
            "updated_at": now.isoformat(),
        }
    )


def _seed_queue(fake: FakeSupabaseClient) -> None:
    _seed_order_bundle(fake, order_id=ORDER_ID, checkout_group_id=CHECKOUT_GROUP_ID)
    _seed_order_bundle(
        fake,
        order_id=ORDER_B_ID,
        checkout_group_id=CHECKOUT_GROUP_B_ID,
        order_total=50_000,
    )
    _seed_dispute(fake, dispute_id=DISPUTE_ID, order_id=ORDER_ID, status="under_review")
    _seed_dispute(fake, dispute_id=DISPUTE_B_ID, order_id=ORDER_B_ID, status="open")


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def test_sla_badge_thresholds() -> None:
    now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)
    badge, hours = compute_sla_badge(now - timedelta(hours=10), now=now)
    assert badge == "on_track"
    assert hours == pytest.approx(10.0)
    badge, _ = compute_sla_badge(now - timedelta(hours=30), now=now)
    assert badge == "due_soon"
    badge, _ = compute_sla_badge(now - timedelta(hours=60), now=now)
    assert badge == "overdue"


def test_signed_evidence_url_ttl(fake_client: FakeSupabaseClient) -> None:
    service_wrapper = MagicMock()
    service_wrapper.client = fake_client
    documents, available = sign_evidence_documents(
        service_wrapper,
        [f"orders/{CUSTOMER_ID}/{ORDER_ID}/evidence-1.jpg"],
    )
    assert available is True
    assert fake_client.storage.bucket.calls
    for _, expires_in in fake_client.storage.bucket.calls:
        assert expires_in <= 300
    assert documents[0].ttl_seconds <= SIGNED_URL_TTL_SECONDS
    assert documents[0].signed_url is not None


def test_non_admin_gets_403(
    admin_disputes_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_queue(fake_client)
    _mock_verify(monkeypatch, OTHER_USER_ID)
    _mock_roles(monkeypatch, {OTHER_USER_ID: frozenset({"customer"})})

    response = admin_disputes_client.get("/admin/disputes", headers=_auth_headers())
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "forbidden"


@pytest.mark.parametrize(
    ("decision", "expected_resolve_decision", "partial"),
    [
        ("full_refund", "resolved_refund", None),
        ("partial_refund", "resolved_partial", 50_000),
        ("release", "resolved_release", None),
    ],
)
def test_decide_maps_to_resolve(
    admin_disputes_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
    expected_resolve_decision: str,
    partial: int | None,
) -> None:
    _seed_order_bundle(fake_client, order_id=ORDER_ID, checkout_group_id=CHECKOUT_GROUP_ID)
    _seed_dispute(fake_client, dispute_id=DISPUTE_ID, order_id=ORDER_ID)
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)

    resolve_calls: list[dict[str, Any]] = []

    def fake_resolve(service_client: Any, **kwargs: Any) -> MagicMock:
        resolve_calls.append(kwargs)
        return MagicMock(
            id=DISPUTE_ID,
            order_id=ORDER_ID,
            status=expected_resolve_decision,
            admin_decision=kwargs["admin_decision"],
        )

    monkeypatch.setattr("app.routers.admin_disputes.resolve", fake_resolve)

    payload: dict[str, Any] = {
        "decision": decision,
        "note": "Admin reviewed evidence and decided.",
        "customer_momo": CUSTOMER_MOMO,
        "customer_rail": "mtn",
    }
    if partial is not None:
        payload["partial_refund_ngwee"] = partial

    response = admin_disputes_client.post(
        f"/admin/disputes/{DISPUTE_ID}/decide",
        headers=_auth_headers(),
        json=payload,
    )
    assert response.status_code == 200
    assert len(resolve_calls) == 1
    call = resolve_calls[0]
    assert call["dispute_id"] == DISPUTE_ID
    assert call["admin_user_id"] == ADMIN_ID
    assert call["decision"] == expected_resolve_decision
    assert call["admin_decision"] == "Admin reviewed evidence and decided."
    assert call["customer_momo"] == CUSTOMER_MOMO
    if partial is not None:
        assert call["partial_refund_ngwee"] == partial


def test_partial_bounds_rejected_before_resolve(
    admin_disputes_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_order_bundle(fake_client, order_id=ORDER_ID, checkout_group_id=CHECKOUT_GROUP_ID)
    _seed_dispute(fake_client, dispute_id=DISPUTE_ID, order_id=ORDER_ID)
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})

    resolve_called = False

    def fake_resolve(*_args: Any, **_kwargs: Any) -> MagicMock:
        nonlocal resolve_called
        resolve_called = True
        return MagicMock()

    monkeypatch.setattr("app.routers.admin_disputes.resolve", fake_resolve)

    response = admin_disputes_client.post(
        f"/admin/disputes/{DISPUTE_ID}/decide",
        headers=_auth_headers(),
        json={
            "decision": "partial_refund",
            "note": "Partial refund attempt.",
            "partial_refund_ngwee": ORDER_TOTAL_NGEWEE + 1,
            "customer_momo": CUSTOMER_MOMO,
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert resolve_called is False


def test_note_mandatory_returns_400(
    admin_disputes_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_order_bundle(fake_client, order_id=ORDER_ID, checkout_group_id=CHECKOUT_GROUP_ID)
    _seed_dispute(fake_client, dispute_id=DISPUTE_ID, order_id=ORDER_ID)
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})

    resolve_called = False

    def fake_resolve(*_args: Any, **_kwargs: Any) -> MagicMock:
        nonlocal resolve_called
        resolve_called = True
        return MagicMock()

    monkeypatch.setattr("app.routers.admin_disputes.resolve", fake_resolve)

    response = admin_disputes_client.post(
        f"/admin/disputes/{DISPUTE_ID}/decide",
        headers=_auth_headers(),
        json={
            "decision": "release",
            "note": "   ",
            "customer_momo": CUSTOMER_MOMO,
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert resolve_called is False


def test_double_decision_surfaces_409(
    admin_disputes_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_order_bundle(fake_client, order_id=ORDER_ID, checkout_group_id=CHECKOUT_GROUP_ID)
    _seed_dispute(
        fake_client,
        dispute_id=DISPUTE_RESOLVED_ID,
        order_id=ORDER_ID,
        status="resolved_release",
    )
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})

    def fake_resolve(*_args: Any, **_kwargs: Any) -> MagicMock:
        raise DisputeTransitionError(
            "Dispute cannot be resolved from its current state",
            from_status="resolved_release",
            event="resolve_release",
            actor_role="admin",
        )

    monkeypatch.setattr("app.routers.admin_disputes.resolve", fake_resolve)

    response = admin_disputes_client.post(
        f"/admin/disputes/{DISPUTE_RESOLVED_ID}/decide",
        headers=_auth_headers(),
        json={
            "decision": "release",
            "note": "Second decision attempt.",
            "customer_momo": CUSTOMER_MOMO,
        },
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "dispute_invalid_transition"


def test_queue_sorted_by_age(
    admin_disputes_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_queue(fake_client)
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})

    response = admin_disputes_client.get("/admin/disputes?sort=age", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["id"] == DISPUTE_ID
    assert body[1]["id"] == DISPUTE_B_ID


def test_detail_includes_signed_evidence_and_context(
    admin_disputes_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_order_bundle(fake_client, order_id=ORDER_ID, checkout_group_id=CHECKOUT_GROUP_ID)
    _seed_dispute(fake_client, dispute_id=DISPUTE_ID, order_id=ORDER_ID)
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})

    response = admin_disputes_client.get(
        f"/admin/disputes/{DISPUTE_ID}",
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["order"]["order_total_ngwee"] == ORDER_TOTAL_NGEWEE
    assert len(body["evidence"]) == 2
    assert all(doc["signed_url"] for doc in body["evidence"])
    assert body["order"]["payments"]
    assert body["decidable"] is True


def test_compute_order_total_ngwee(fake_client: FakeSupabaseClient) -> None:
    _seed_order_bundle(fake_client, order_id=ORDER_ID, checkout_group_id=CHECKOUT_GROUP_ID)
    service_wrapper = MagicMock()
    service_wrapper.client = fake_client
    order_row = fake_client.tables["orders"].rows[0]
    total = compute_order_total_ngwee(service_wrapper, order_row)
    assert total == ORDER_TOTAL_NGEWEE
