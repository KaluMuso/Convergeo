"""Restricted admin roles deny unlisted work and cannot grant themselves power."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from typing import Any

import pytest
from app.core.auth import CurrentUser, admin_permission_for_request, get_current_user
from app.main import create_app
from app.supabase_client import get_supabase_service_client
from fastapi.testclient import TestClient


class FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def select(self, *_args: Any) -> FakeQuery:
        return self

    def in_(self, *_args: Any) -> FakeQuery:
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
        return self

    def limit(self, *_args: Any) -> FakeQuery:
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.rows)


class FakeService:
    def __init__(self, permissions: list[str]) -> None:
        self.permissions = permissions
        self.calls: list[dict[str, Any]] = []
        self.client = self

    def table(self, name: str) -> FakeQuery:
        if name == "admin_roles":
            return FakeQuery([{"permissions": self.permissions}])
        if name == "services":
            return FakeQuery([{"id": "service-1", "title": "Test service"}])
        raise AssertionError(f"Unexpected table access: {name}")

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        assert name == "manage_admin_role"
        self.calls.append(params)
        return SimpleNamespace(execute=lambda: SimpleNamespace(data={"key": params["p_key"]}))


@pytest.fixture
def role_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, FakeService, Any], None, None]:
    service = FakeService(["finance.read"])
    app = create_app()
    user = CurrentUser(
        id="00000000-0000-0000-0000-000000000002", roles=frozenset({"rbac_finance"}), token="test"
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_supabase_service_client] = lambda: service
    monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: service)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, service, app


@pytest.mark.parametrize(
    "path,method,expected",
    [
        ("/admin/orders/search", "GET", "finance.read"),
        ("/admin/orders/{order_id}/cod/confirm-collection", "POST", None),
        ("/admin/refunds", "POST", None),
        ("/admin/events/high-value-queue", "GET", "events.manage"),
        ("/admin/products/merge", "POST", "products.manage"),
        ("/admin/roles", "GET", None),
        ("/admin/unknown", "GET", None),
    ],
)
def test_explicit_scope_map(path: str, method: str, expected: str | None) -> None:
    assert admin_permission_for_request(path, method) == expected


def test_finance_role_cannot_reach_other_or_money_routes(
    role_client: tuple[TestClient, FakeService, Any],
) -> None:
    client, service, _app = role_client
    for method, path in [
        ("GET", "/admin/events/high-value-queue"),
        ("GET", "/admin/products/duplicates"),
        ("POST", "/admin/echo"),
        ("POST", "/admin/orders/00000000-0000-0000-0000-000000000003/cod/confirm-collection"),
        ("GET", "/admin/roles"),
        ("POST", "/admin/roles"),
        ("PATCH", "/admin/roles/rbac_finance"),
        ("PUT", "/admin/roles/superadmin/users/00000000-0000-0000-0000-000000000002"),
    ]:
        response = client.request(method, path, json={} if method in {"POST", "PATCH"} else None)
        assert response.status_code == 403, (method, path, response.text)
    assert service.calls == []


def test_customer_cannot_read_admin_grants(
    role_client: tuple[TestClient, FakeService, Any],
) -> None:
    client, _service, app = role_client
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="00000000-0000-0000-0000-000000000003", roles=frozenset({"customer"}), token="test"
    )
    assert client.get("/admin/me/permissions").status_code == 403
    assert client.get("/admin/orders/search").status_code == 403


def test_finance_grants_are_read_only(
    role_client: tuple[TestClient, FakeService, Any],
) -> None:
    client, _service, _app = role_client
    response = client.get("/admin/me/permissions")
    assert response.status_code == 200
    assert response.json() == {
        "permissions": ["finance.read"],
        "can_manage_roles": False,
        "unrestricted": False,
    }


def test_service_role_can_view_services_but_not_inventory(
    role_client: tuple[TestClient, FakeService, Any],
) -> None:
    client, service, _app = role_client
    service.permissions = ["services.read"]
    visible = client.get("/admin/services")
    assert visible.status_code == 200, visible.text
    assert visible.json()["items"][0]["title"] == "Test service"
    assert client.get("/admin/inventory").status_code == 403


def test_superadmin_can_create_and_assign_only_known_permissions(
    role_client: tuple[TestClient, FakeService, Any],
) -> None:
    client, service, app = role_client
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="00000000-0000-0000-0000-000000000001",
        roles=frozenset({"superadmin"}),
        token="test",
    )
    invalid = client.post(
        "/admin/roles",
        json={
            "key": "rbac_payments",
            "name": "Payments",
            "permissions": ["payments.transfer"],
        },
    )
    assert invalid.status_code == 422
    assert service.calls == []
    created = client.post(
        "/admin/roles",
        json={
            "key": "rbac_finance",
            "name": "Finance",
            "permissions": ["finance.read"],
        },
    )
    assert created.status_code == 201, created.text
    assert service.calls[0]["p_actor"] == "00000000-0000-0000-0000-000000000001"
    assert service.calls[0]["p_permissions"] == ["finance.read"]
    assigned = client.put("/admin/roles/rbac_finance/users/00000000-0000-0000-0000-000000000002")
    assert assigned.status_code == 200, assigned.text
    assert service.calls[1]["p_action"] == "assign"
