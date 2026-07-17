"""Admin translation overrides — CRUD + admin authz.

Isolation-clean: the Supabase client is a tiny in-memory fake, so no Postgres is
needed. RLS (admin-only) is proven separately by tests/rls/test_matrix.py.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from fastapi.testclient import TestClient

ADMIN_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ADMIN_TOKEN = "admin-token"
VENDOR_TOKEN = "vendor-token"


class _FakeQuery:
    def __init__(self, store: list[dict[str, Any]]) -> None:
        self._store = store
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._on_conflict: list[str] = []
        self._filters: list[tuple[str, Any]] = []

    def select(self, _columns: str) -> _FakeQuery:
        return self

    def order(self, _column: str) -> _FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._filters.append((column, value))
        return self

    def upsert(self, payload: dict[str, Any], *, on_conflict: str) -> _FakeQuery:
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = [c.strip() for c in on_conflict.split(",")]
        return self

    def delete(self) -> _FakeQuery:
        self._op = "delete"
        return self

    def execute(self) -> MagicMock:
        if self._op == "upsert":
            assert self._payload is not None
            row = dict(self._payload)
            match = next(
                (
                    existing
                    for existing in self._store
                    if all(existing.get(k) == row.get(k) for k in self._on_conflict)
                ),
                None,
            )
            if match is not None:
                match.update(row)
                out = dict(match)
            else:
                row.setdefault("id", "11111111-1111-1111-1111-111111111111")
                row.setdefault("updated_at", "2026-07-17T00:00:00+00:00")
                self._store.append(row)
                out = dict(row)
            return MagicMock(data=[out])
        if self._op == "delete":
            kept = [r for r in self._store if not all(r.get(c) == v for c, v in self._filters)]
            deleted = len(self._store) - len(kept)
            self._store[:] = kept
            return MagicMock(data=[], count=deleted)
        rows = [r for r in self._store if all(r.get(c) == v for c, v in self._filters)]
        return MagicMock(data=[dict(r) for r in rows])


class _FakeClient:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def table(self, _name: str) -> _FakeQuery:
        return _FakeQuery(self.rows)


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    app = create_app()
    wrapper = MagicMock()
    wrapper.client = _FakeClient()
    app.dependency_overrides[get_supabase_client] = lambda: wrapper

    with patch(
        "app.core.auth.verify_supabase_jwt",
        side_effect=lambda token, settings: {
            ADMIN_TOKEN: {"sub": ADMIN_ID, "exp": 9_999_999_999},
            VENDOR_TOKEN: {"sub": VENDOR_ID, "exp": 9_999_999_999},
        }[token],
    ), patch(
        "app.core.auth._load_user_roles",
        side_effect=lambda user_id, service_client: (
            frozenset({"admin"}) if user_id == ADMIN_ID else frozenset({"vendor"})
        ),
    ), patch(
        "app.deps.get_supabase_service_client",
        return_value=wrapper,
    ), patch(
        "app.supabase_client.get_supabase_service_client",
        return_value=wrapper,
    ):
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_upsert_then_list(api_client: TestClient) -> None:
    put = api_client.put(
        "/admin/translations/overrides",
        headers=_auth(ADMIN_TOKEN),
        json={"locale": "fr", "namespace": "events", "message_key": "title", "value": "Événements"},
    )
    assert put.status_code == 200
    assert put.json()["value"] == "Événements"

    listed = api_client.get("/admin/translations/overrides", headers=_auth(ADMIN_TOKEN))
    assert listed.status_code == 200
    overrides = listed.json()["overrides"]
    assert len(overrides) == 1
    assert overrides[0]["locale"] == "fr"
    assert overrides[0]["value"] == "Événements"


def test_upsert_updates_in_place(api_client: TestClient) -> None:
    body = {"locale": "zh", "namespace": "events", "message_key": "title"}
    api_client.put(
        "/admin/translations/overrides", headers=_auth(ADMIN_TOKEN), json={**body, "value": "活动"}
    )
    api_client.put(
        "/admin/translations/overrides", headers=_auth(ADMIN_TOKEN), json={**body, "value": "活動"}
    )
    overrides = api_client.get(
        "/admin/translations/overrides", headers=_auth(ADMIN_TOKEN)
    ).json()["overrides"]
    assert len(overrides) == 1  # updated in place, not duplicated
    assert overrides[0]["value"] == "活動"


def test_delete_reverts(api_client: TestClient) -> None:
    body = {"locale": "fr", "namespace": "events", "message_key": "title", "value": "X"}
    api_client.put("/admin/translations/overrides", headers=_auth(ADMIN_TOKEN), json=body)
    resp = api_client.delete(
        "/admin/translations/overrides",
        headers=_auth(ADMIN_TOKEN),
        params={"locale": "fr", "namespace": "events", "message_key": "title"},
    )
    assert resp.status_code == 204
    overrides = api_client.get(
        "/admin/translations/overrides", headers=_auth(ADMIN_TOKEN)
    ).json()["overrides"]
    assert overrides == []


def test_non_admin_forbidden(api_client: TestClient) -> None:
    resp = api_client.get("/admin/translations/overrides", headers=_auth(VENDOR_TOKEN))
    assert resp.status_code == 403


def test_anon_unauthorized(api_client: TestClient) -> None:
    resp = api_client.get("/admin/translations/overrides")
    assert resp.status_code == 401
