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


PRODUCT_1 = "33333333-3333-3333-3333-333333333333"
PRODUCT_2 = "44444444-4444-4444-4444-444444444444"


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
        self.products: dict[str, dict[str, Any]] = {
            PRODUCT_1: {
                "id": PRODUCT_1,
                "slug": "tecno-spark",
                "name": "Tecno Spark",
            },
            PRODUCT_2: {
                "id": PRODUCT_2,
                "slug": "itel-a70",
                "name": "Itel A70",
            },
        }
        self.user_wishlist: list[dict[str, Any]] = []
        self.user_recently_viewed: list[dict[str, Any]] = []

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

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> FakeQuery:
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

    def order(self, _column: str, desc: bool = False) -> FakeQuery:
        _ = desc
        return self

    def limit(self, _count: int) -> FakeQuery:
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append((f"in:{column}", list(values)))
        return self

    def upsert(self, payload: dict[str, Any], on_conflict: str | None = None) -> FakeQuery:
        _ = on_conflict
        self._mode = "upsert"
        self._payload = payload
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> FakeResult:
        if self.table == "profiles":
            return self._execute_profiles()
        if self.table == "addresses":
            return self._execute_addresses()
        if self.table == "products":
            return self._execute_products()
        if self.table == "user_wishlist":
            return self._execute_wishlist()
        if self.table == "user_recently_viewed":
            return self._execute_recent()
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

    def _execute_products(self) -> FakeResult:
        in_ids = self._filter_value("in:id")
        if self._mode == "select" and isinstance(in_ids, list):
            rows = [
                deepcopy(self.store.products[str(pid)])
                for pid in in_ids
                if str(pid) in self.store.products
            ]
            return FakeResult(rows)
        return FakeResult([])

    def _execute_wishlist(self) -> FakeResult:
        user_filter = self._filter_value("user_id") or self.user_id
        if self._mode == "delete":
            self.store.user_wishlist = [
                row for row in self.store.user_wishlist if row["user_id"] != user_filter
            ]
            return FakeResult([])
        if self._mode == "insert":
            payload = self._payload
            rows = payload if isinstance(payload, list) else [payload]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                self.store.user_wishlist.append(deepcopy(row))
            return FakeResult(deepcopy(rows) if isinstance(rows, list) else [])
        if self._mode == "select":
            out: list[dict[str, Any]] = []
            for row in self.store.user_wishlist:
                if row["user_id"] != user_filter:
                    continue
                product = self.store.products.get(str(row["product_id"]), {})
                out.append(
                    {
                        "product_id": row["product_id"],
                        "created_at": row.get("created_at", "2026-07-20T00:00:00+00:00"),
                        "products": product,
                    }
                )
            return FakeResult(out)
        return FakeResult([])

    def _execute_recent(self) -> FakeResult:
        user_filter = self._filter_value("user_id") or self.user_id
        if self._mode == "upsert" and isinstance(self._payload, dict):
            pid = str(self._payload["product_id"])
            self.store.user_recently_viewed = [
                row
                for row in self.store.user_recently_viewed
                if not (row["user_id"] == user_filter and row["product_id"] == pid)
            ]
            self.store.user_recently_viewed.append(deepcopy(self._payload))
            return FakeResult([deepcopy(self._payload)])
        if self._mode == "delete":
            in_ids = self._filter_value("in:product_id")
            if isinstance(in_ids, list):
                drop = {str(x) for x in in_ids}
                self.store.user_recently_viewed = [
                    row
                    for row in self.store.user_recently_viewed
                    if not (row["user_id"] == user_filter and row["product_id"] in drop)
                ]
            return FakeResult([])
        if self._mode == "select":
            out: list[dict[str, Any]] = []
            for row in self.store.user_recently_viewed:
                if row["user_id"] != user_filter:
                    continue
                product = self.store.products.get(str(row["product_id"]), {})
                out.append(
                    {
                        "product_id": row["product_id"],
                        "viewed_at": row.get("viewed_at", "2026-07-20T00:00:00+00:00"),
                        "products": product,
                    }
                )
            return FakeResult(out)
        return FakeResult([])


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
    body = response.json()
    assert body["notif_prefs"] == {
        "whatsapp": True,
        "sms": True,
        "email": True,
    }
    assert body["onboarding"] == {"interests": [], "completed_at": None}


def test_onboarding_complete_persists_interests(account_client: TestClient) -> None:
    response = account_client.patch(
        "/account/onboarding",
        headers=auth_header(TOKEN_A),
        json={
            "interests": ["electronics", "events", "electronics"],
            "locale": "bem",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["onboarding"]["interests"] == ["electronics", "events"]
    assert body["onboarding"]["completed_at"] is not None

    follow_up = account_client.get("/account/preferences", headers=auth_header(TOKEN_A))
    assert follow_up.json()["onboarding"]["interests"] == ["electronics", "events"]


def test_preferences_patch_preserves_onboarding(account_client: TestClient) -> None:
    account_client.patch(
        "/account/onboarding",
        headers=auth_header(TOKEN_A),
        json={"interests": ["fashion"]},
    )
    patch_response = account_client.patch(
        "/account/preferences",
        headers=auth_header(TOKEN_A),
        json={"email": False},
    )
    assert patch_response.status_code == 200
    body = patch_response.json()
    assert body["notif_prefs"]["email"] is False
    assert body["onboarding"]["interests"] == ["fashion"]
    assert body["onboarding"]["completed_at"] is not None


def test_onboarding_rejects_unknown_interest(account_client: TestClient) -> None:
    response = account_client.patch(
        "/account/onboarding",
        headers=auth_header(TOKEN_A),
        json={"interests": ["widgets"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_account_requires_auth(account_client: TestClient) -> None:
    response = account_client.get("/account/profile")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"


def test_wishlist_put_and_get(account_client: TestClient) -> None:
    put = account_client.put(
        "/account/wishlist",
        headers=auth_header(TOKEN_A),
        json={"product_ids": [PRODUCT_1, PRODUCT_2, PRODUCT_1]},
    )
    assert put.status_code == 200
    items = put.json()["items"]
    assert len(items) == 2
    assert {item["slug"] for item in items} == {"tecno-spark", "itel-a70"}

    get = account_client.get("/account/wishlist", headers=auth_header(TOKEN_A))
    assert get.status_code == 200
    assert len(get.json()["items"]) == 2


def test_recently_viewed_post_and_get(account_client: TestClient) -> None:
    post = account_client.post(
        "/account/recently-viewed",
        headers=auth_header(TOKEN_A),
        json={"product_id": PRODUCT_1},
    )
    assert post.status_code == 200
    items = post.json()["items"]
    assert len(items) == 1
    assert items[0]["slug"] == "tecno-spark"

    get = account_client.get("/account/recently-viewed", headers=auth_header(TOKEN_A))
    assert get.status_code == 200
    assert get.json()["items"][0]["product_id"] == PRODUCT_1
