from __future__ import annotations

from collections.abc import Generator
from typing import Annotated, Any
from unittest.mock import MagicMock

import pytest
from app.core.admin_audit import AdminAuditedRoute, AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import require_role
from app.main import create_app
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
VALID_TOKEN = "valid.jwt.token"
ENTITY_ID = "33333333-3333-3333-3333-333333333333"


@pytest.fixture
def audit_app() -> FastAPI:
    return create_app()


@pytest.fixture
def audit_client(audit_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(audit_app, raise_server_exceptions=False) as test_client:
        yield test_client


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

    class FakeQuery:
        def __init__(self, row: dict[str, Any]) -> None:
            self._row = row

        def execute(self) -> MagicMock:
            inserted.append(self._row)
            return MagicMock(data=[{**self._row, "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}])

    class FakeTable:
        def insert(self, row: dict[str, Any]) -> FakeQuery:
            return FakeQuery(row)

    service_client = MagicMock()
    service_client.client.table.return_value = FakeTable()
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client",
        lambda: service_client,
    )
    return inserted


def test_admin_mutation_writes_exactly_one_audit_log_row(
    audit_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    inserted = _mock_audit_insert(monkeypatch)

    response = audit_client.post(
        "/admin/echo",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "entity_type": "config",
            "entity_id": ENTITY_ID,
            "before": {"value": 100},
            "after": {"value": 200},
        },
    )

    assert response.status_code == 200
    assert len(inserted) == 1
    row = inserted[0]
    assert row["actor"] == USER_ID
    assert row["action"] == "admin.echo"
    assert row["entity_type"] == "config"
    assert row["entity_id"] == ENTITY_ID
    assert row["before"] == {"value": 100}
    assert row["after"] == {"value": 200}


def test_admin_mutation_without_audit_record_fails(
    audit_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch)

    skip_app = create_app()

    skip_router = APIRouter(
        prefix="/admin",
        route_class=AdminAuditedRoute,
        dependencies=[Depends(require_role("admin"))],
    )

    @skip_router.post("/skip-audit")
    async def skip_audit(
        recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    ) -> dict[str, str]:
        _ = recorder
        return {"status": "skipped"}

    skip_app.include_router(skip_router)

    with TestClient(skip_app, raise_server_exceptions=False) as client:
        response = client.post(
            "/admin/skip-audit",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "audit_incomplete"


def test_non_admin_mutation_returns_403(
    audit_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch, user_id=OTHER_USER_ID)
    _mock_roles(monkeypatch, {OTHER_USER_ID: frozenset({"vendor"})})

    response = audit_client.post(
        "/admin/echo",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "entity_type": "config",
            "entity_id": ENTITY_ID,
            "before": {"value": 1},
            "after": {"value": 2},
        },
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "forbidden"


def test_admin_health_get_does_not_require_audit_row(
    audit_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})

    response = audit_client.get(
        "/admin/health",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
