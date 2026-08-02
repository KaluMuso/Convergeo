"""R02-P14b — vendor follows API.

The fake Supabase here enforces the real ``(user_id, vendor_id)`` primary key
from migration 0083, so the idempotency tests mean something: a router that
relied on read-then-write instead of the constraint would still pass a fake
that accepts every insert, and read-then-write is exactly the bug the PK
exists to prevent.

No live DB — MagicMock/fake-client conventions per tests/test_cart.py and
tests/test_clips_engagement.py.
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
OWNER_USER = "33333333-3333-4333-8333-333333333333"

VENDOR_ACTIVE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_SUSPENDED = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
VENDOR_NONEXISTENT = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


class UniqueViolation(Exception):
    """Stands in for Postgres 23505 — the constraint, not an application check."""

    code = "23505"


# --- Fake Supabase ------------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._eq: list[tuple[str, Any]] = []
        self._in: list[tuple[str, list[Any]]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._offset: int = 0
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str = "*", **_kwargs: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._eq.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in.append((column, list(values)))
        return self

    def order(self, column: str, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def offset(self, count: int) -> FakeQuery:
        self._offset = count
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "insert"
        self._payload = payload
        return self

    def delete(self) -> FakeQuery:
        self._op = "delete"
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        if not all(row.get(c) == v for c, v in self._eq):
            return False
        return all(row.get(c) in values for c, values in self._in)

    def execute(self) -> MagicMock:
        store = self._parent.store
        with store.lock:
            if self._op == "insert":
                assert self._payload is not None
                row = dict(self._payload)
                self._parent.enforce_unique(row)
                row.setdefault("created_at", datetime.now(UTC).isoformat())
                self._parent.rows.append(row)
                return MagicMock(data=[dict(row)])

            if self._op == "delete":
                removed = [dict(r) for r in self._parent.rows if self._match(r)]
                self._parent.rows[:] = [r for r in self._parent.rows if not self._match(r)]
                return MagicMock(data=removed)

            rows = [dict(row) for row in self._parent.rows if self._match(row)]
            if self._order:
                column, desc = self._order
                rows.sort(key=lambda r: str(r.get(column) or ""), reverse=desc)
            if self._offset:
                rows = rows[self._offset :]
            if self._limit is not None:
                rows = rows[: self._limit]
            return MagicMock(data=rows)


class FakeTable:
    #: The real PK from migration 0083 — the thing that makes PUT idempotent.
    UNIQUE_KEYS: dict[str, tuple[str, ...]] = {
        "vendor_follows": ("user_id", "vendor_id"),
        "vendors": ("id",),
    }

    def __init__(self, name: str, store: Store) -> None:
        self.name = name
        self.store = store
        self.rows: list[dict[str, Any]] = []

    def enforce_unique(self, row: dict[str, Any]) -> None:
        columns = self.UNIQUE_KEYS.get(self.name)
        if not columns:
            return
        key = tuple(row.get(c) for c in columns)
        for existing in self.rows:
            if tuple(existing.get(c) for c in columns) == key:
                raise UniqueViolation(f"{self.name} {columns} exists")

    def select(self, columns: str = "*", **kwargs: Any) -> FakeQuery:
        return FakeQuery(self).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def delete(self) -> FakeQuery:
        return FakeQuery(self).delete()


class FakeSupabase:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name, self.store))

    def rpc(self, name: str, params: dict[str, Any]) -> MagicMock:
        if name == "bump_rate_counter":
            return MagicMock(execute=lambda: MagicMock(data=[self.store.rate_verdict()]))
        if name == "vendor_follower_count":
            vendor_id = params["p_vendor_id"]
            with self.store.lock:
                count = sum(
                    1
                    for row in self.table("vendor_follows").rows
                    if row.get("vendor_id") == vendor_id
                )
            return MagicMock(execute=lambda: MagicMock(data=count))
        raise AssertionError(f"unexpected rpc {name}")


class Store:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.client = FakeSupabase(self)
        self.rate_limit_allows = True
        self.rate_calls = 0

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.client.table(name).rows

    def rate_verdict(self) -> dict[str, Any]:
        with self.lock:
            self.rate_calls += 1
        return {"allowed": self.rate_limit_allows, "retry_after_seconds": 30}


# --- Fixtures -------------------------------------------------------------------
@pytest.fixture
def store() -> Store:
    st = Store()
    st.rows("vendors").extend(
        [
            {
                "id": VENDOR_ACTIVE,
                "owner_user_id": OWNER_USER,
                "slug": "kabwata-crafts",
                "display_name": "Kabwata Crafts",
                "status": "active",
            },
            {
                "id": VENDOR_SUSPENDED,
                "owner_user_id": USER_B,
                "slug": "suspended-shop",
                "display_name": "Suspended Shop",
                "status": "suspended",
            },
        ]
    )
    st.rows("vendor_follows")
    return st


@pytest.fixture
def api(store: Store, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    wrapper = store
    # Service-role dependency (PUT/DELETE/GET /me/follows).
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    # User-token client (GET /vendor/followers/count) — same fake store, since
    # the fake does not model RLS; the router-level authz is what's under test.
    monkeypatch.setattr(
        "app.routers.follows.get_user_client",
        lambda token, settings=None: wrapper.client,
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve the caller from the bearer token so several users can act."""
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": token, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"customer"}),
    )


def _headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


# --- Guests: 401 on everything ----------------------------------------------------
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PUT", f"/vendors/{VENDOR_ACTIVE}/follow"),
        ("DELETE", f"/vendors/{VENDOR_ACTIVE}/follow"),
        ("GET", "/me/follows"),
        ("GET", "/vendor/followers/count"),
    ],
)
def test_guest_gets_401_on_every_endpoint(api: TestClient, method: str, path: str) -> None:
    response = api.request(method, path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# --- Follow: idempotent by primary key ---------------------------------------------
def test_follow_returns_204_and_creates_one_row(api: TestClient, store: Store, auth: None) -> None:
    response = api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))
    assert response.status_code == 204
    assert store.rows("vendor_follows") == [
        {
            "user_id": USER_A,
            "vendor_id": VENDOR_ACTIVE,
            "created_at": store.rows("vendor_follows")[0]["created_at"],
        }
    ]


def test_follow_twice_is_204_both_times_and_still_one_row(
    api: TestClient, store: Store, auth: None
) -> None:
    """Idempotency asserted, not just 'no crash': second 204 AND no second row."""
    first = api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))
    second = api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))

    assert first.status_code == 204
    assert second.status_code == 204
    assert len(store.rows("vendor_follows")) == 1


def test_two_users_following_produce_two_rows(api: TestClient, store: Store, auth: None) -> None:
    assert api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A)).status_code == 204
    assert api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_B)).status_code == 204
    assert len(store.rows("vendor_follows")) == 2


def test_follow_suspended_vendor_is_404_identical_to_nonexistent(
    api: TestClient, store: Store, auth: None
) -> None:
    """No existence oracle for suspended vendors: code+status+message+details
    must all be equal, not merely 'both 404'."""
    suspended = api.put(f"/vendors/{VENDOR_SUSPENDED}/follow", headers=_headers(USER_A))
    absent = api.put(f"/vendors/{VENDOR_NONEXISTENT}/follow", headers=_headers(USER_A))

    assert suspended.status_code == 404
    assert suspended.status_code == absent.status_code

    suspended_error = suspended.json()["error"]
    absent_error = absent.json()["error"]
    assert suspended_error["code"] == absent_error["code"]
    assert suspended_error["message"] == absent_error["message"]
    assert suspended_error["details"] == absent_error["details"]

    assert store.rows("vendor_follows") == []


def test_follow_is_rate_limited(api: TestClient, store: Store, auth: None) -> None:
    store.rate_limit_allows = False
    response = api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert store.rows("vendor_follows") == []


# --- Unfollow: idempotent ------------------------------------------------------------
def test_unfollow_never_followed_is_still_204(api: TestClient, store: Store, auth: None) -> None:
    response = api.delete(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))
    assert response.status_code == 204
    assert store.rows("vendor_follows") == []


def test_unfollow_removes_the_row_and_repeats_are_204(
    api: TestClient, store: Store, auth: None
) -> None:
    api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))
    assert len(store.rows("vendor_follows")) == 1

    first = api.delete(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))
    second = api.delete(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))

    assert first.status_code == 204
    assert second.status_code == 204
    assert store.rows("vendor_follows") == []


def test_unfollow_only_removes_the_callers_row(api: TestClient, store: Store, auth: None) -> None:
    api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))
    api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_B))

    api.delete(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))

    remaining = store.rows("vendor_follows")
    assert len(remaining) == 1
    assert remaining[0]["user_id"] == USER_B


# --- GET /me/follows ---------------------------------------------------------------
def test_me_follows_lists_followed_vendors_with_name_and_slug(
    api: TestClient, store: Store, auth: None
) -> None:
    api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))

    body = api.get("/me/follows", headers=_headers(USER_A)).json()

    assert body["limit"] == 20
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["vendor_id"] == VENDOR_ACTIVE
    assert item["name"] == "Kabwata Crafts"
    assert item["slug"] == "kabwata-crafts"
    assert item["followed_at"] is not None


def test_me_follows_is_scoped_to_the_caller(api: TestClient, store: Store, auth: None) -> None:
    api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_B))

    body = api.get("/me/follows", headers=_headers(USER_A)).json()
    assert body["items"] == []


def test_me_follows_omits_a_vendor_suspended_after_the_follow(
    api: TestClient, store: Store, auth: None
) -> None:
    """No 'suspended' label — the entry simply drops out (same no-oracle rule)."""
    # Seed the row directly: it was legitimately created while the vendor was
    # active; the PUT would (correctly) refuse it now.
    store.rows("vendor_follows").append(
        {
            "user_id": USER_A,
            "vendor_id": VENDOR_SUSPENDED,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))

    body = api.get("/me/follows", headers=_headers(USER_A)).json()
    assert [item["vendor_id"] for item in body["items"]] == [VENDOR_ACTIVE]


def test_me_follows_rejects_limit_above_50(api: TestClient, auth: None) -> None:
    response = api.get("/me/follows?limit=51", headers=_headers(USER_A))
    assert response.status_code == 422

    response = api.get("/me/follows?limit=0", headers=_headers(USER_A))
    assert response.status_code == 422


# --- GET /vendor/followers/count ------------------------------------------------------
def test_follower_count_as_non_vendor_is_404(api: TestClient, auth: None) -> None:
    response = api.get("/vendor/followers/count", headers=_headers(USER_A))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_follower_count_as_owner_returns_the_count(
    api: TestClient, store: Store, auth: None
) -> None:
    api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_A))
    api.put(f"/vendors/{VENDOR_ACTIVE}/follow", headers=_headers(USER_B))

    response = api.get("/vendor/followers/count", headers=_headers(OWNER_USER))
    assert response.status_code == 200
    assert response.json() == {"count": 2}


def test_follower_count_is_zero_for_a_vendor_nobody_follows(
    api: TestClient, store: Store, auth: None
) -> None:
    response = api.get("/vendor/followers/count", headers=_headers(OWNER_USER))
    assert response.status_code == 200
    assert response.json() == {"count": 0}


# --- Rate-limit registry ------------------------------------------------------------
def test_follow_routes_are_declared_in_the_policy_registry(api: TestClient) -> None:
    """The startup coverage gate requires every mutating route to be declared;
    follows.py registers its own entries at import time (it owns only itself)."""
    from app.core.ratelimit_policies import policy_for

    put_policy = policy_for("PUT", "/vendors/{vendor_id}/follow")
    delete_policy = policy_for("DELETE", "/vendors/{vendor_id}/follow")
    assert put_policy is not None
    assert delete_policy is not None
    assert put_policy.limit == 60
