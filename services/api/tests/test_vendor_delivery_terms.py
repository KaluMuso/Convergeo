from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from fastapi.testclient import TestClient

USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TOKEN = "vendor-token"


class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._filters: list[tuple[str, Any]] = []
        self._single = False
        self._op: str | None = None
        self._payload: dict[str, Any] = {}

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = (columns, count)
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append((column, value))
        return self

    def maybe_single(self) -> FakeQuery:
        self._single = True
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._op, self._payload = "update", payload
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._op, self._payload = "insert", payload
        return self

    def _match(self) -> list[dict[str, Any]]:
        return [r for r in self._parent.rows if all(r.get(c) == v for c, v in self._filters)]

    def execute(self) -> MagicMock:
        if self._op == "insert":
            self._parent.rows.append(dict(self._payload))
            return MagicMock(data=[dict(self._payload)])
        if self._op == "update":
            hit = self._match()
            for row in hit:
                row.update(self._payload)
            return MagicMock(data=[dict(r) for r in hit])
        rows = self._match()
        if self._single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns, count=count)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)


class FakeClient:
    def __init__(self) -> None:
        self.tables = {"vendors": FakeTable(), "audit_log": FakeTable()}
        self.tables["vendors"].rows.extend(
            [
                {
                    "id": VENDOR_A_ID,
                    "owner_user_id": USER_A_ID,
                    "free_delivery_all": False,
                    "free_delivery_method": "platform_courier",
                },
                {
                    "id": VENDOR_B_ID,
                    "owner_user_id": USER_B_ID,
                    "free_delivery_all": False,
                    "free_delivery_method": "platform_courier",
                },
            ]
        )

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _patch_auth(monkeypatch: pytest.MonkeyPatch, roles: frozenset[str]) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": USER_A_ID, "exp": 9_999_999_999},
    )
    monkeypatch.setattr("app.core.auth._load_user_roles", lambda uid, sc: roles)


@pytest.fixture
def fake() -> FakeClient:
    return FakeClient()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake: FakeClient) -> Generator[TestClient, None, None]:
    _patch_auth(monkeypatch, frozenset({"vendor"}))
    monkeypatch.setattr("app.routers.vendor_delivery.bump_rate_counter", lambda **kw: (True, 0))
    wrapper = MagicMock()
    wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: wrapper)
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: wrapper
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_get_returns_current_terms(client: TestClient) -> None:
    response = client.get("/vendor/delivery-terms", headers=_h())
    assert response.status_code == 200
    assert response.json() == {
        "free_delivery_all": False,
        "free_delivery_method": "platform_courier",
    }


def test_patch_updates_only_own_shop(client: TestClient, fake: FakeClient) -> None:
    response = client.patch(
        "/vendor/delivery-terms",
        headers=_h(),
        json={"free_delivery_all": True, "free_delivery_method": "self_delivery"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "free_delivery_all": True,
        "free_delivery_method": "self_delivery",
    }
    rows = {r["id"]: r for r in fake.tables["vendors"].rows}
    assert rows[VENDOR_A_ID]["free_delivery_all"] is True
    assert rows[VENDOR_B_ID]["free_delivery_all"] is False
    assert rows[VENDOR_B_ID]["free_delivery_method"] == "platform_courier"


def test_patch_with_no_change_returns_current_terms(client: TestClient, fake: FakeClient) -> None:
    response = client.patch(
        "/vendor/delivery-terms", headers=_h(), json={"free_delivery_all": False}
    )
    assert response.status_code == 200
    assert response.json()["free_delivery_all"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"free_delivery_method": "drone"},
        {"free_delivery_all": "yes"},
        {"delivery_funding": "vendor"},
        {"free_delivery_all": True, "extra": 1},
    ],
)
def test_patch_rejects_bad_or_unknown_fields(
    client: TestClient, fake: FakeClient, payload: dict[str, Any]
) -> None:
    response = client.patch("/vendor/delivery-terms", headers=_h(), json=payload)
    assert response.status_code == 422
    assert fake.tables["vendors"].rows[0]["free_delivery_all"] is False


def test_patch_is_rate_limited(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, fake: FakeClient
) -> None:
    monkeypatch.setattr("app.routers.vendor_delivery.bump_rate_counter", lambda **kw: (False, 30))
    response = client.patch(
        "/vendor/delivery-terms", headers=_h(), json={"free_delivery_all": True}
    )
    assert response.status_code == 429
    assert fake.tables["vendors"].rows[0]["free_delivery_all"] is False


def test_non_vendor_is_refused(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, fake: FakeClient
) -> None:
    _patch_auth(monkeypatch, frozenset({"customer"}))
    for method, kwargs in (("get", {}), ("patch", {"json": {"free_delivery_all": True}})):
        response = getattr(client, method)("/vendor/delivery-terms", headers=_h(), **kwargs)
        assert response.status_code == 403
    assert fake.tables["vendors"].rows[0]["free_delivery_all"] is False


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/vendor/delivery-terms").status_code == 401
    assert (
        client.patch("/vendor/delivery-terms", json={"free_delivery_all": True}).status_code == 401
    )
