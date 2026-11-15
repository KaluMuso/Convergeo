"""Audit-log coverage for admin mutations that live outside the audited /admin router.

`AdminAuditedRoute` only enforces an `audit_log` row on routes of the shared admin
router. Translation overrides and admin COD confirmation are standalone routers, and
before the 2026-11 analytics/RBAC audit they wrote nothing: a deleted override left no
trace, and an administrator confirming cash collection was booked as SYSTEM.

DB-free: the audit sink is an in-memory fake behind the real `AdminAuditRecorder`.
"""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from typing import Any

import pytest
from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.routers import cod as cod_router
from app.services.orders.state import ActorRole
from app.services.payments.cod import CodCollectionResult, CodError, CodRefusalResult
from fastapi.testclient import TestClient

ADMIN_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORDER_ID = "0d0d0d0d-0000-0000-0000-000000000001"


class _Query:
    def __init__(self, sink: _Sink, table: str) -> None:
        self._sink = sink
        self._table = table
        self._op = "select"
        self._payload: dict[str, Any] | None = None

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def order(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def eq(self, *_a: Any) -> _Query:
        return self

    def in_(self, *_a: Any) -> _Query:
        return self

    def insert(self, payload: dict[str, Any]) -> _Query:
        self._op, self._payload = "insert", payload
        return self

    def upsert(self, payload: dict[str, Any], **_k: Any) -> _Query:
        self._op, self._payload = "upsert", payload
        return self

    def delete(self) -> _Query:
        self._op = "delete"
        return self

    def execute(self) -> SimpleNamespace:
        if self._table == "audit_log" and self._op == "insert":
            assert self._payload is not None
            self._sink.audit.append(self._payload)
            return SimpleNamespace(data=[self._payload])
        if self._op == "upsert":
            assert self._payload is not None
            return SimpleNamespace(data=[{**self._payload, "updated_at": "2026-11-13T00:00:00Z"}])
        if self._op == "delete":
            return SimpleNamespace(data=self._sink.deleted_rows)
        return SimpleNamespace(data=[])


class _Sink:
    def __init__(self) -> None:
        self.audit: list[dict[str, Any]] = []
        self.deleted_rows: list[dict[str, Any]] = []
        self.client = self

    def table(self, name: str) -> _Query:
        return _Query(self, name)


@pytest.fixture
def harness() -> Generator[tuple[TestClient, _Sink], None, None]:
    sink = _Sink()
    app = create_app()
    admin = CurrentUser(id=ADMIN_ID, roles=frozenset({"admin"}), token="t")
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_supabase_client] = lambda: sink
    # Real recorder, fake sink: the handler must call `.record(...)` for a row to land.
    app.dependency_overrides[get_admin_audit_recorder] = lambda: AdminAuditRecorder(
        ADMIN_ID,
        sink,  # type: ignore[arg-type]
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, sink


def test_translation_upsert_writes_audit_row(harness: tuple[TestClient, _Sink]) -> None:
    client, sink = harness
    body = {"locale": "fr", "namespace": "events", "message_key": "title", "value": "Billets"}
    response = client.put("/admin/translations/overrides", json=body)
    assert response.status_code == 200, response.text
    assert sink.audit == [
        {
            "actor": ADMIN_ID,
            "action": "admin.translation.upsert",
            "entity_type": "translation_override",
            "entity_id": None,
            "before": None,
            "after": body,
        }
    ]


def test_translation_delete_writes_audit_row_with_removed_value(
    harness: tuple[TestClient, _Sink],
) -> None:
    client, sink = harness
    sink.deleted_rows = [
        {"locale": "fr", "namespace": "events", "message_key": "title", "value": "Billets"}
    ]
    response = client.delete(
        "/admin/translations/overrides",
        params={"locale": "fr", "namespace": "events", "message_key": "title"},
    )
    assert response.status_code == 204, response.text
    assert len(sink.audit) == 1
    row = sink.audit[0]
    assert row["actor"] == ADMIN_ID
    assert row["action"] == "admin.translation.delete"
    assert row["before"] == {
        "locale": "fr",
        "namespace": "events",
        "message_key": "title",
        "value": "Billets",
    }
    assert row["after"] is None


def test_admin_cod_confirm_is_attributed_to_the_administrator(
    harness: tuple[TestClient, _Sink], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, sink = harness
    calls: list[dict[str, Any]] = []

    def fake_confirm(**kwargs: Any) -> CodCollectionResult:
        calls.append(kwargs)
        return CodCollectionResult(
            order_id=ORDER_ID,
            collectable_ngwee=25_000,
            commission_ngwee=2_500,
            net_vendor_ngwee=22_500,
            transaction_ids=("t1", "t2", "t3"),
            created=True,
        )

    monkeypatch.setattr(cod_router, "confirm_cod_collection", fake_confirm)
    response = client.post(
        f"/admin/orders/{ORDER_ID}/cod/confirm-collection", json={"note": "cash counted"}
    )
    assert response.status_code == 200, response.text
    assert calls == [
        {
            "order_id": ORDER_ID,
            "actor_id": ADMIN_ID,
            "note": "cash counted",
            "actor_role": ActorRole.ADMIN,
        }
    ]
    assert len(sink.audit) == 1
    row = sink.audit[0]
    assert row["actor"] == ADMIN_ID
    assert row["action"] == "admin.cod.confirm_collection"
    assert row["entity_type"] == "order"
    assert row["entity_id"] == ORDER_ID
    after = row["after"]
    # Integer ngwee end to end; the three legs reconcile.
    assert after["collectable_ngwee"] == 25_000
    assert after["commission_ngwee"] + after["net_vendor_ngwee"] == after["collectable_ngwee"]
    assert all(isinstance(after[k], int) for k in ("commission_ngwee", "net_vendor_ngwee"))
    assert after["transaction_ids"] == ["t1", "t2", "t3"]
    assert after["note"] == "cash counted"


def test_admin_cod_refuse_is_attributed_to_the_administrator(
    harness: tuple[TestClient, _Sink], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, sink = harness
    monkeypatch.setattr(
        cod_router,
        "refuse_cod_collection",
        lambda **_k: CodRefusalResult(
            order_id=ORDER_ID,
            collectable_ngwee=25_000,
            reversal_transaction_id="rev-1",
            from_status="delivered",
            to_status="cancelled",
            created=True,
        ),
    )
    response = client.post(
        f"/admin/orders/{ORDER_ID}/cod/refuse-collection", json={"note": "customer refused"}
    )
    assert response.status_code == 200, response.text
    assert len(sink.audit) == 1
    row = sink.audit[0]
    assert (row["actor"], row["action"], row["entity_id"]) == (
        ADMIN_ID,
        "admin.cod.refuse_collection",
        ORDER_ID,
    )
    assert row["before"] == {"status": "delivered"}
    assert row["after"]["status"] == "cancelled"
    assert row["after"]["reversal_transaction_id"] == "rev-1"


def test_failed_cod_confirmation_writes_no_audit_row(
    harness: tuple[TestClient, _Sink], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure path: nothing was booked, so nothing may be recorded as done."""
    client, sink = harness

    def boom(**_k: Any) -> CodCollectionResult:
        raise CodError(code="cod_invalid_status", message="not collectable", http_status=409)

    monkeypatch.setattr(cod_router, "confirm_cod_collection", boom)
    response = client.post(f"/admin/orders/{ORDER_ID}/cod/confirm-collection", json={"note": "x"})
    assert response.status_code == 409, response.text
    assert sink.audit == []


@pytest.mark.parametrize("roles", [{"vendor"}, {"customer"}, {"moderator"}, {"rbac_finance"}])
def test_non_admin_cannot_confirm_cod_and_leaves_no_audit_row(
    harness: tuple[TestClient, _Sink], monkeypatch: pytest.MonkeyPatch, roles: set[str]
) -> None:
    client, sink = harness
    app = client.app
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(  # type: ignore[attr-defined]
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", roles=frozenset(roles), token="t"
    )
    monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: sink)
    called: list[int] = []
    monkeypatch.setattr(cod_router, "confirm_cod_collection", lambda **_k: called.append(1))
    response = client.post(f"/admin/orders/{ORDER_ID}/cod/confirm-collection", json={"note": "x"})
    assert response.status_code == 403, response.text
    # No action row. Operators (moderator, rbac_*) leave an `outcome = denied` row (S5);
    # customers and vendors leave nothing.
    assert called == []
    assert [row for row in sink.audit if row.get("outcome") != "denied"] == []
    denied = [row for row in sink.audit if row.get("outcome") == "denied"]
    operator = bool(roles & {"moderator"}) or any(r.startswith("rbac_") for r in roles)
    assert len(denied) == (1 if operator else 0)
