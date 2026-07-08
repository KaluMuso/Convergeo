from __future__ import annotations

from collections.abc import Generator
from copy import deepcopy
from typing import Any
from uuid import uuid4

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"
TOKEN_A = "token.user-a"
TOKEN_B = "token.user-b"


class FakeSupabaseStore:
    def __init__(self) -> None:
        self.profiles: dict[str, dict[str, Any]] = {
            USER_A: {
                "id": USER_A,
                "phone": "+260971234567",
                "display_name": "Chisomo",
                "locale": "en",
                "notif_prefs": {"whatsapp": True, "sms": True, "email": False},
            },
            USER_B: {
                "id": USER_B,
                "phone": "+260979876543",
                "display_name": "Mwila",
                "locale": "bem",
                "notif_prefs": {},
            },
        }
        self.addresses: dict[str, dict[str, Any]] = {}

    def seed_address(self, *, user_id: str, landmark: str) -> str:
        address_id = str(uuid4())
        self.addresses[address_id] = {
            "id": address_id,
            "user_id": user_id,
            "label": "Home",
            "landmark": landmark,
            "lat": -15.3875,
            "lng": 28.3228,
            "phone": "+260971234567",
        }
        return address_id


class FakeResult:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, store: FakeSupabaseStore, table: str, user_id: str) -> None:
        self.store = store
        self.table = table
        self.user_id = user_id
        self._filters: list[tuple[str, Any]] = []
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._mode: str = "select"
        self._maybe_single = False
        self._columns = "*"

    def select(self, columns: str) -> FakeQuery:
        self._columns = columns
        self._mode = "select"
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._mode = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._mode = "update"
        self._payload = payload
        return self

    def delete(self) -> FakeQuery:
        self._mode = "delete"
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append((column, value))
        return self

    def order(self, _column: str) -> FakeQuery:
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> FakeResult:
        if self.table == "profiles":
            return self._execute_profiles()
        if self.table == "addresses":
            return self._execute_addresses()
        return FakeResult([] if not self._maybe_single else None)

    def _filter_value(self, column: str) -> Any:
        for key, value in self._filters:
            if key == column:
                return value
        return None

    def _execute_profiles(self) -> FakeResult:
        profile_id = self._filter_value("id")
        if profile_id is None or profile_id != self.user_id:
            return FakeResult(None if self._maybe_single else [])

        profile = self.store.profiles.get(str(profile_id))
        if profile is None:
            return FakeResult(None if self._maybe_single else [])

        if self._mode == "select":
            if self._maybe_single:
                return FakeResult(deepcopy(profile))
            return FakeResult([deepcopy(profile)])

        if self._mode == "update" and isinstance(self._payload, dict):
            profile.update(self._payload)
            if self._maybe_single:
                return FakeResult(deepcopy(profile))
            return FakeResult([deepcopy(profile)])

        return FakeResult(None if self._maybe_single else [])

    def _execute_addresses(self) -> FakeResult:
        if self._mode == "insert" and isinstance(self._payload, dict):
            address_id = str(uuid4())
            row = {**self._payload, "id": address_id}
            if row.get("user_id") != self.user_id:
                return FakeResult([])
            self.store.addresses[address_id] = row
            return FakeResult([deepcopy(row)])

        address_id = self._filter_value("id")
        user_filter = self._filter_value("user_id")

        if self._mode == "select":
            if address_id is not None:
                stored = self.store.addresses.get(str(address_id))
                if stored is None:
                    return FakeResult(None if self._maybe_single else [])
                stored_row: dict[str, Any] = stored
                if stored_row["user_id"] != self.user_id:
                    return FakeResult(None if self._maybe_single else [])
                if self._maybe_single:
                    return FakeResult(deepcopy(stored_row))
                return FakeResult([deepcopy(stored_row)])

            rows = [
                deepcopy(row)
                for row in self.store.addresses.values()
                if row["user_id"] == (user_filter or self.user_id)
            ]
            return FakeResult(rows)

        if address_id is None:
            return FakeResult(None if self._maybe_single else [])

        stored = self.store.addresses.get(str(address_id))
        if stored is None:
            return FakeResult(None if self._maybe_single else [])

        if self._mode == "update" and isinstance(self._payload, dict):
            if stored["user_id"] != self.user_id:
                return FakeResult(None if self._maybe_single else [])
            stored.update(self._payload)
            return FakeResult([deepcopy(stored)])

        if self._mode == "delete":
            if stored["user_id"] != self.user_id:
                return FakeResult(None if self._maybe_single else [])
            del self.store.addresses[str(address_id)]
            return FakeResult([])

        return FakeResult(None if self._maybe_single else [])


class FakeSupabaseClient:
    def __init__(self, store: FakeSupabaseStore, user_id: str) -> None:
        self.store = store
        self.user_id = user_id

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.store, name, self.user_id)


@pytest.fixture
def account_store() -> FakeSupabaseStore:
    return FakeSupabaseStore()


def _mock_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    token_to_user = {
        TOKEN_A: USER_A,
        TOKEN_B: USER_B,
    }

    def fake_verify(token: str, settings: Any) -> dict[str, Any]:
        _ = settings
        user_id = token_to_user.get(token)
        if user_id is None:
            from jwt.exceptions import InvalidTokenError

            raise InvalidTokenError("invalid token")
        return {"sub": user_id, "exp": 9_999_999_999}

    def fake_load_roles(user_id: str, service_client: Any) -> frozenset[str]:
        _ = service_client
        if user_id in token_to_user.values():
            return frozenset({"customer"})
        return frozenset()

    monkeypatch.setattr("app.core.auth.verify_supabase_jwt", fake_verify)
    monkeypatch.setattr("app.core.auth._load_user_roles", fake_load_roles)


@pytest.fixture
def account_client(
    account_store: FakeSupabaseStore,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    token_to_user = {
        TOKEN_A: USER_A,
        TOKEN_B: USER_B,
    }

    _mock_auth(monkeypatch)

    def fake_get_user_client(token: str, settings: Any = None) -> FakeSupabaseClient:
        _ = settings
        user_id = token_to_user[token]
        return FakeSupabaseClient(account_store, user_id)

    monkeypatch.setattr("app.routers.account.get_user_client", fake_get_user_client)

    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_get_profile(account_client: TestClient) -> None:
    response = account_client.get("/account/profile", headers=auth_header(TOKEN_A))
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Chisomo"
    assert body["locale"] == "en"


def test_patch_profile(account_client: TestClient) -> None:
    response = account_client.patch(
        "/account/profile",
        headers=auth_header(TOKEN_A),
        json={"display_name": "Updated Name", "locale": "nya"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Updated Name"
    assert body["locale"] == "nya"


def test_address_crud(account_client: TestClient) -> None:
    create_response = account_client.post(
        "/account/addresses",
        headers=auth_header(TOKEN_A),
        json={
            "label": "Office",
            "landmark": "Near Manda Hill",
            "lat": -15.4,
            "lng": 28.3,
            "phone": "+260971234567",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    address_id = created["id"]
    assert created["landmark"] == "Near Manda Hill"

    list_response = account_client.get("/account/addresses", headers=auth_header(TOKEN_A))
    assert list_response.status_code == 200
    assert any(item["id"] == address_id for item in list_response.json())

    patch_response = account_client.patch(
        f"/account/addresses/{address_id}",
        headers=auth_header(TOKEN_A),
        json={"landmark": "Manda Hill Mall entrance"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["landmark"] == "Manda Hill Mall entrance"

    delete_response = account_client.delete(
        f"/account/addresses/{address_id}",
        headers=auth_header(TOKEN_A),
    )
    assert delete_response.status_code == 204


def test_user_cannot_read_other_users_address(
    account_client: TestClient,
    account_store: FakeSupabaseStore,
) -> None:
    address_id = account_store.seed_address(user_id=USER_A, landmark="Kabulonga")

    response = account_client.get(
        f"/account/addresses/{address_id}",
        headers=auth_header(TOKEN_B),
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"


def test_user_cannot_edit_other_users_address(
    account_client: TestClient,
    account_store: FakeSupabaseStore,
) -> None:
    address_id = account_store.seed_address(user_id=USER_A, landmark="Woodlands")

    response = account_client.patch(
        f"/account/addresses/{address_id}",
        headers=auth_header(TOKEN_B),
        json={"landmark": "Hijacked"},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert account_store.addresses[address_id]["landmark"] == "Woodlands"


def test_preferences_persist(account_client: TestClient) -> None:
    get_response = account_client.get("/account/preferences", headers=auth_header(TOKEN_A))
    assert get_response.status_code == 200
    assert get_response.json()["notif_prefs"] == {
        "whatsapp": True,
        "sms": True,
        "email": False,
    }

    patch_response = account_client.patch(
        "/account/preferences",
        headers=auth_header(TOKEN_A),
        json={"email": True, "whatsapp": False},
    )
    assert patch_response.status_code == 200
    body = patch_response.json()
    assert body["notif_prefs"]["email"] is True
    assert body["notif_prefs"]["whatsapp"] is False
    assert body["notif_prefs"]["sms"] is True

    follow_up = account_client.get("/account/preferences", headers=auth_header(TOKEN_A))
    assert follow_up.json()["notif_prefs"]["email"] is True


def test_preferences_defaults_when_empty_json(account_client: TestClient) -> None:
    response = account_client.get("/account/preferences", headers=auth_header(TOKEN_B))
    assert response.status_code == 200
    assert response.json()["notif_prefs"] == {
        "whatsapp": True,
        "sms": True,
        "email": True,
    }


def test_account_requires_auth(account_client: TestClient) -> None:
    response = account_client.get("/account/profile")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
