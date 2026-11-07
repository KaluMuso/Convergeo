"""Restricted admin roles deny unlisted work and cannot grant themselves power."""

from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import product
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import jwt
import psycopg
import pytest
from app.core.admin_audit import get_admin_audit_recorder
from app.core.auth import CurrentUser, admin_permission_for_request, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.supabase_client import get_supabase_service_client
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from psycopg.rows import dict_row


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

    def eq(self, *_args: Any) -> FakeQuery:
        return self

    def neq(self, *_args: Any) -> FakeQuery:
        return self

    def or_(self, *_args: Any) -> FakeQuery:
        return self

    def maybe_single(self) -> FakeQuery:
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
        if name in {"products", "orders"}:
            return FakeQuery([])
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
    app.dependency_overrides[get_supabase_client] = lambda: service
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


def test_moderator_and_custom_role_permissions_are_combined(
    role_client: tuple[TestClient, FakeService, Any],
) -> None:
    client, service, app = role_client
    app.dependency_overrides[get_supabase_client] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="00000000-0000-0000-0000-000000000002",
        roles=frozenset({"moderator", "rbac_finance"}),
        token="test",
    )
    response = client.get("/admin/me/permissions")
    assert response.status_code == 200, response.text
    assert response.json()["permissions"] == [
        "finance.read",
        "products.manage",
        "vendors.manage",
    ]
    orders = client.get(
        "/admin/orders/search",
        params={"order_id": "00000000-0000-0000-0000-000000000003"},
    )
    assert orders.status_code == 200, orders.text
    assert orders.json() == []


def test_standalone_superadmin_inherits_admin_routes_and_finance_cannot_mutate(
    role_client: tuple[TestClient, FakeService, Any],
) -> None:
    client, service, app = role_client
    app.dependency_overrides[get_supabase_client] = lambda: service
    app.dependency_overrides[get_admin_audit_recorder] = lambda: object()
    superadmin = CurrentUser(
        id="00000000-0000-0000-0000-000000000001",
        roles=frozenset({"superadmin"}),
        token="test",
    )
    finance = CurrentUser(
        id="00000000-0000-0000-0000-000000000002",
        roles=frozenset({"rbac_finance"}),
        token="test",
    )
    app.dependency_overrides[get_current_user] = lambda: superadmin
    product = client.get("/admin/products/search", params={"q": "test"})
    assert product.status_code == 200, product.text
    assert product.json() == []
    # A missing order stops before the escrow operation; this proves the role
    # guard passed without performing any money mutation in the test.
    escrow_url = "/admin/orders/00000000-0000-0000-0000-000000000003/escrow"
    escrow_body = {
        "operation": "hold",
        "amount_ngwee": 100,
        "reason": "Authorization regression",
        "confirmation_phrase": "MANUAL ESCROW",
    }
    escrow = client.post(escrow_url, json=escrow_body)
    assert escrow.status_code == 404, escrow.text
    app.dependency_overrides[get_current_user] = lambda: finance
    assert client.get("/admin/products/search", params={"q": "test"}).status_code == 403
    assert client.post(escrow_url, json=escrow_body).status_code == 403


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
    revoked_legacy = client.delete("/admin/roles/admin/users/00000000-0000-0000-0000-000000000002")
    assert revoked_legacy.status_code == 200, revoked_legacy.text
    assert service.calls[2]["p_action"] == "revoke"
    assert service.calls[2]["p_key"] == "admin"


# These tests use real role rows and the management RPC in an explicitly
# selected disposable PG16 database. Resource reads remain synthetic, so no
# provider, ledger, payment or shared database operation can occur.
PERMISSION_ENDPOINTS = {
    "finance.read": ("/admin/orders/search", {"order_id": "00000000-0000-0000-0000-000000000003"}),
    "events.manage": ("/admin/events/high-value-queue", {}),
    "products.manage": ("/admin/products/search", {"q": "test"}),
    "services.read": ("/admin/services", {}),
    "vendors.manage": ("/admin/vendors", {}),
    "ads.manage": ("/admin/merch/hero-variants", {}),
    "analytics.read": ("/admin/search-insights/ask-cost", {}),
    "inventory.read": ("/admin/inventory", {}),
}
FORBIDDEN_MUTATIONS = (
    "/admin/orders/00000000-0000-0000-0000-000000000003/dispatch",
    "/admin/orders/00000000-0000-0000-0000-000000000003/intervene",
    "/admin/orders/00000000-0000-0000-0000-000000000003/escrow",
    "/admin/orders/00000000-0000-0000-0000-000000000003/cod/confirm-collection",
    "/admin/refunds/execute",
    "/admin/disputes/00000000-0000-0000-0000-000000000003/decide",
    "/admin/ai-spend/reset-kill-switch",
)


@pytest.fixture
def disposable_role_url() -> str:
    url = os.environ.get("CONVERGEO_RBAC_TEST_DB_URL")
    if not url:
        pytest.skip("RBAC acceptance requires an explicitly selected disposable PG16 database")
    parsed = urlparse(url)
    assert os.environ.get("CONVERGEO_DISPOSABLE_DB") == "1"
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert parsed.path == "/postgres"
    with psycopg.connect(url, connect_timeout=5, options="-c statement_timeout=15000") as db:
        row = db.execute("show server_version_num").fetchone()
        assert row is not None and int(row[0]) // 10000 == 16
    return url


class RoleDbQuery(FakeQuery):
    def __init__(self, db: psycopg.Connection[dict[str, Any]], table: str) -> None:
        super().__init__([])
        self.db = db
        self.table = table
        self.user_id: str | None = None
        self.keys: list[str] | None = None
        self.assignment_keys: list[str] | None = None

    def eq(self, column: str, value: Any) -> RoleDbQuery:
        if self.table == "user_roles" and column == "user_id":
            self.user_id = str(value)
        return self

    def in_(self, column: str, values: list[str]) -> RoleDbQuery:
        if self.table == "admin_roles" and column == "key":
            self.keys = values
        elif self.table == "user_roles" and column == "role":
            self.assignment_keys = values
        return self

    def is_(self, *_args: Any) -> RoleDbQuery:
        return self

    def ilike(self, *_args: Any) -> RoleDbQuery:
        return self

    def execute(self) -> SimpleNamespace:
        if self.table == "user_roles":
            if self.user_id is not None:
                rows = self.db.execute(
                    "select role from public.user_roles where user_id = %s", (self.user_id,)
                ).fetchall()
            else:
                assert self.assignment_keys is not None
                rows = self.db.execute(
                    "select user_id, role from public.user_roles where role = any(%s)",
                    (self.assignment_keys,),
                ).fetchall()
        elif self.table == "admin_roles":
            rows = self.db.execute(
                "select key, name, permissions from public.admin_roles "
                "where (%s::text[] is null or key = any(%s))",
                (self.keys, self.keys),
            ).fetchall()
        else:
            rows = []
        return SimpleNamespace(data=rows)


class RoleDbService(FakeService):
    def __init__(self, db: psycopg.Connection[dict[str, Any]]) -> None:
        super().__init__([])
        self.db = db
        self.resource_reads: list[str] = []

    def table(self, name: str) -> RoleDbQuery:
        if name not in {"user_roles", "admin_roles"}:
            self.resource_reads.append(name)
        return RoleDbQuery(self.db, name)

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        assert name == "manage_admin_role", "No provider or money RPC is permitted in this fixture"
        self.calls.append(params)

        def execute() -> SimpleNamespace:
            try:
                with self.db.transaction():
                    self.db.execute("set local role service_role")
                    row = self.db.execute(
                        "select public.manage_admin_role(%s,%s,%s,%s,%s,%s) as result",
                        (
                            params["p_actor"],
                            params["p_action"],
                            params["p_key"],
                            params["p_name"],
                            params["p_permissions"],
                            params["p_target"],
                        ),
                    ).fetchone()
                    assert row is not None
                    return SimpleNamespace(data=row["result"])
            except psycopg.Error as exc:
                raise APIError(
                    {
                        "code": exc.sqlstate,
                        "message": exc.diag.message_primary,
                        "details": None,
                        "hint": None,
                    }
                ) from exc

        return SimpleNamespace(execute=execute)


@dataclass
class RoleApiHarness:
    client: TestClient
    service: RoleDbService
    subjects: dict[str, str]
    tokens: dict[str, str]
    verified_tokens: list[str]

    def headers(self, persona: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[persona]}"}

    def create(self, key: str, permissions: list[str]) -> None:
        response = self.client.post(
            "/admin/roles",
            headers=self.headers("superadmin"),
            json={"key": key, "name": "Scoped test role", "permissions": permissions},
        )
        assert response.status_code == 201, response.text

    def assign(self, key: str, persona: str = "operator") -> None:
        response = self.client.put(
            f"/admin/roles/{key}/users/{self.subjects[persona]}",
            headers=self.headers("superadmin"),
        )
        assert response.status_code == 200, response.text

    def grants(self, persona: str = "operator") -> dict[str, Any]:
        response = self.client.get("/admin/me/permissions", headers=self.headers(persona))
        assert response.status_code == 200, response.text
        return dict(response.json())


@pytest.fixture
def role_api(
    disposable_role_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[RoleApiHarness, None, None]:
    subjects = {
        name: str(uuid4())
        for name in (
            "superadmin",
            "operator",
            "other_operator",
            "customer",
            "vendor",
            "vendor_staff",
        )
    }
    with psycopg.connect(
        disposable_role_url,
        row_factory=dict_row,
        connect_timeout=5,
        options="-c statement_timeout=15000",
    ) as db:
        for persona, user_id in subjects.items():
            db.execute("insert into auth.users(id) values (%s)", (user_id,))
            db.execute(
                "insert into public.profiles(id) values (%s) on conflict do nothing", (user_id,)
            )
            role = (
                "superadmin"
                if persona == "superadmin"
                else ("vendor" if persona in {"vendor", "vendor_staff"} else "customer")
            )
            db.execute(
                "insert into public.user_roles(user_id,role) values (%s,%s) "
                "on conflict (user_id,role) do nothing",
                (user_id, role),
            )
        service = RoleDbService(db)
        verified_tokens: list[str] = []
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        tokens = {
            persona: jwt.encode(
                {
                    "sub": user_id,
                    "exp": datetime.now(UTC) + timedelta(minutes=10),
                    "aud": "authenticated",
                    "iss": "https://example.supabase.co/auth/v1",
                    "app_metadata": {"roles": ["admin"]},
                    "user_metadata": {"roles": ["superadmin"], "vendor_staff": True},
                },
                private_key,
                algorithm="RS256",
            )
            for persona, user_id in subjects.items()
        }

        def signing_key(token: str) -> SimpleNamespace:
            verified_tokens.append(token)
            return SimpleNamespace(key=private_key.public_key())

        # Only JWKS retrieval is isolated; the production signature, issuer,
        # audience and expiry verifier runs on real locally signed JWTs.
        monkeypatch.setattr(
            "app.core.auth._jwks_client",
            lambda _url: SimpleNamespace(get_signing_key_from_jwt=signing_key),
        )
        monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: service)
        monkeypatch.setattr("app.routers.admin_events.load_high_value_gmv_ngwee", lambda: 1000)
        monkeypatch.setattr("app.routers.admin_search_insights.ask_cost_by_day", lambda **_kw: [])
        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: service
        with TestClient(app, raise_server_exceptions=False) as client:
            yield RoleApiHarness(client, service, subjects, tokens, verified_tokens)
        db.rollback()  # Includes synthetic first-superadmin and every role/audit fixture row.


@pytest.mark.parametrize(
    "granted,requested",
    list(product(PERMISSION_ENDPOINTS, repeat=2)),
)
def test_disposable_api_permission_domains(
    role_api: RoleApiHarness,
    granted: str,
    requested: str,
) -> None:
    role_api.create("rbac_limited", [granted])
    role_api.assign("rbac_limited")
    path, params = PERMISSION_ENDPOINTS[requested]
    reads = len(role_api.service.resource_reads)
    response = role_api.client.get(path, params=params, headers=role_api.headers("operator"))
    assert response.status_code == (200 if granted == requested else 403), response.text
    if granted != requested:
        assert len(role_api.service.resource_reads) == reads


@pytest.mark.parametrize(
    "persona,permission",
    list(
        product(
            ("customer", "vendor", "vendor_staff"),
            PERMISSION_ENDPOINTS,
        )
    ),
)
def test_disposable_non_admins_cannot_enter_platform(
    role_api: RoleApiHarness,
    persona: str,
    permission: str,
) -> None:
    path, params = PERMISSION_ENDPOINTS[permission]
    response = role_api.client.get(path, params=params, headers=role_api.headers(persona))
    assert response.status_code == 403, response.text
    assert role_api.service.resource_reads == []
    assert role_api.service.calls == []


@pytest.mark.parametrize(
    "permission,path",
    list(
        product(
            PERMISSION_ENDPOINTS,
            FORBIDDEN_MUTATIONS,
        )
    ),
)
def test_disposable_custom_roles_cannot_mutate_money_or_controls(
    role_api: RoleApiHarness,
    permission: str,
    path: str,
) -> None:
    role_api.create("rbac_limited", [permission])
    role_api.assign("rbac_limited")
    before_calls = len(role_api.service.calls)
    response = role_api.client.post(path, headers=role_api.headers("operator"), json={})
    assert response.status_code == 403, response.text
    assert len(role_api.service.calls) == before_calls
    assert role_api.service.resource_reads == []


def test_disposable_distinct_roles_and_role_union(role_api: RoleApiHarness) -> None:
    role_api.create("rbac_finance", ["finance.read"])
    role_api.create("rbac_services", ["services.read"])
    role_api.assign("rbac_finance")
    role_api.assign("rbac_services", "other_operator")
    assert role_api.grants()["permissions"] == ["finance.read"]
    assert role_api.grants("other_operator")["permissions"] == ["services.read"]
    role_api.assign("rbac_services")
    grants = role_api.grants()
    assert grants == {
        "permissions": ["finance.read", "services.read"],
        "can_manage_roles": False,
        "unrestricted": False,
    }
    for permission in ("finance.read", "services.read"):
        path, params = PERMISSION_ENDPOINTS[permission]
        assert (
            role_api.client.get(
                path, params=params, headers=role_api.headers("operator")
            ).status_code
            == 200
        )
    assert (
        role_api.client.get("/admin/inventory", headers=role_api.headers("operator")).status_code
        == 403
    )


def test_disposable_revocation_and_update_use_unchanged_jwt(role_api: RoleApiHarness) -> None:
    role_api.create("rbac_limited", ["finance.read"])
    role_api.assign("rbac_limited")
    assert role_api.grants()["permissions"] == ["finance.read"]
    response = role_api.client.patch(
        "/admin/roles/rbac_limited",
        headers=role_api.headers("superadmin"),
        json={"name": "Inventory only", "permissions": ["inventory.read"]},
    )
    assert response.status_code == 200, response.text
    assert role_api.grants()["permissions"] == ["inventory.read"]
    path, params = PERMISSION_ENDPOINTS["finance.read"]
    assert (
        role_api.client.get(path, params=params, headers=role_api.headers("operator")).status_code
        == 403
    )
    assert (
        role_api.client.get("/admin/inventory", headers=role_api.headers("operator")).status_code
        == 200
    )
    response = role_api.client.delete(
        f"/admin/roles/rbac_limited/users/{role_api.subjects['operator']}",
        headers=role_api.headers("superadmin"),
    )
    assert response.status_code == 200, response.text
    assert (
        role_api.client.get("/admin/inventory", headers=role_api.headers("operator")).status_code
        == 403
    )
    assert (
        role_api.client.get(
            "/admin/me/permissions", headers=role_api.headers("operator")
        ).status_code
        == 403
    )
    assert role_api.verified_tokens.count(role_api.tokens["operator"]) >= 6


def test_disposable_legacy_admin_cannot_be_newly_assigned(role_api: RoleApiHarness) -> None:
    response = role_api.client.put(
        f"/admin/roles/admin/users/{role_api.subjects['operator']}",
        headers=role_api.headers("superadmin"),
    )
    assert response.status_code == 422, response.text
    assert (
        role_api.client.get(
            "/admin/me/permissions", headers=role_api.headers("operator")
        ).status_code
        == 403
    )


def test_disposable_vendor_queue_contract_stays_bounded(role_api: RoleApiHarness) -> None:
    role_api.create("rbac_vendors", ["vendors.manage"])
    role_api.assign("rbac_vendors")
    response = role_api.client.get(
        "/admin/vendors", params={"status": "active"}, headers=role_api.headers("operator")
    )
    assert response.status_code == 422, response.text
    assert role_api.service.resource_reads == []


@pytest.mark.parametrize(
    "persona,operation",
    list(
        product(
            ("customer", "vendor"),
            ("definitions", "management_rpc"),
        )
    ),
)
def test_disposable_browser_identities_cannot_bypass_api(
    role_api: RoleApiHarness,
    persona: str,
    operation: str,
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as rejected:
        with role_api.service.db.transaction():
            role_api.service.db.execute("set local role authenticated")
            role_api.service.db.execute(
                "select set_config('request.jwt.claim.sub', %s, true)",
                (role_api.subjects[persona],),
            )
            if operation == "definitions":
                role_api.service.db.execute("select * from public.admin_roles")
            else:
                # Even impersonating a valid superadmin argument cannot bypass
                # the service-only EXECUTE boundary from a browser DB role.
                role_api.service.db.execute(
                    "select public.manage_admin_role(%s,'create','rbac_bypass',"
                    "'Must not exist',array['finance.read'],null)",
                    (role_api.subjects["superadmin"],),
                )
    assert rejected.value.sqlstate == "42501"
    assert role_api.service.db.execute(
        "select count(*) as n from public.admin_roles where key='rbac_bypass'"
    ).fetchone() == {"n": 0}


def test_disposable_all_thirteen_sql_contracts(disposable_role_url: str) -> None:
    script = Path(__file__).resolve().parents[3] / (
        "supabase/tests/20261009100000_configurable_admin_roles.test.sql"
    )
    tap: list[str] = []
    with psycopg.connect(
        disposable_role_url,
        autocommit=True,
        connect_timeout=5,
        options="-c statement_timeout=15000",
    ) as db:
        cursor = db.execute(script.read_text())
        while True:
            if cursor.description:
                for row in cursor.fetchall():
                    if isinstance(row[0], str):
                        tap.extend(row[0].splitlines())
            if not cursor.nextset():
                break
    assert "1..13" in tap, tap
    results = [line for line in tap if line.startswith(("ok ", "not ok "))]
    assert len(results) == 13, tap
    assert all(line.startswith("ok ") and "# SKIP" not in line.upper() for line in results), tap
