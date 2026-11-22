"""Notification center API — caller-scoped list / count / mark seen / mark read.

The fake Supabase models only the PostgREST verbs this router uses. RLS itself
is proven against real Postgres in ``tests/test_in_app_notifications_db.py``;
here the router-level authz (own id, audience role) is under test.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.routers.notifications import decode_cursor, encode_cursor
from fastapi.testclient import TestClient

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
VENDOR_USER = "33333333-3333-4333-8333-333333333333"
ADMIN_ROLE_USERS = {
    "44444444-4444-4444-8444-444444444441": "admin",
    "44444444-4444-4444-8444-444444444442": "superadmin",
    "44444444-4444-4444-8444-444444444443": "moderator",
    "44444444-4444-4444-8444-444444444444": "rbac_finance",
}

_OR_RE = re.compile(
    r'^created_at\.lt\."(?P<ts>[^"]+)",and\(created_at\.eq\."(?P=ts)",id\.lt\.(?P<id>[0-9a-f-]+)\)$'
)


class FakeQuery:
    def __init__(self, table: FakeTable) -> None:
        self.table = table
        self.filters: list[Any] = []
        self.orders: list[tuple[str, bool]] = []
        self.limit_n: int | None = None
        self.op = "select"
        self.payload: dict[str, Any] = {}
        self.head = False
        self.count: str | None = None

    def select(
        self, _columns: str = "*", count: str | None = None, head: bool = False
    ) -> FakeQuery:
        self.count, self.head = count, head
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def is_(self, column: str, value: str) -> FakeQuery:
        assert value == "null"
        self.filters.append(lambda r: r.get(column) is None)
        return self

    def lte(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(lambda r: str(r.get(column)) <= str(value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self.filters.append(lambda r: r.get(column) in values)
        return self

    def or_(self, expression: str) -> FakeQuery:
        match = _OR_RE.match(expression)
        assert match, expression
        ts, row_id = match["ts"], match["id"]
        self.filters.append(
            lambda r: r["created_at"] < ts or (r["created_at"] == ts and r["id"] < row_id)
        )
        return self

    def order(self, column: str, desc: bool = False) -> FakeQuery:
        self.orders.append((column, desc))
        return self

    def limit(self, n: int) -> FakeQuery:
        self.limit_n = n
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self.op, self.payload = "update", payload
        return self

    def delete(self) -> FakeQuery:
        self.op = "delete"
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self.op, self.payload = "insert", payload
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        return all(f(row) for f in self.filters)

    def execute(self) -> MagicMock:
        rows = self.table.rows
        if self.op == "insert":
            rows.append(dict(self.payload))
            return MagicMock(data=[dict(self.payload)])
        if self.op == "delete":
            gone = [r for r in rows if self._matches(r)]
            rows[:] = [r for r in rows if not self._matches(r)]
            return MagicMock(data=gone)
        if self.op == "update":
            hit = [r for r in rows if self._matches(r)]
            for r in hit:
                r.update(self.payload)
            return MagicMock(data=[dict(r) for r in hit])
        out = [dict(r) for r in rows if self._matches(r)]
        for column, desc in reversed(self.orders):

            def sort_key(r: dict[str, Any], c: str = column) -> str:
                return str(r.get(c))

            out.sort(key=sort_key, reverse=desc)
        if self.limit_n is not None:
            out = out[: self.limit_n]
        return MagicMock(data=[] if self.head else out, count=len(out))


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, *args: Any, **kwargs: Any) -> FakeQuery:
        return FakeQuery(self).select(*args, **kwargs)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)

    def delete(self) -> FakeQuery:
        return FakeQuery(self).delete()

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)


class Store:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.tables: dict[str, FakeTable] = {}
        self.allow = True
        self.client = self

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable())

    def rpc(self, name: str, _params: dict[str, Any]) -> MagicMock:
        assert name == "bump_rate_counter"
        return MagicMock(
            execute=lambda: MagicMock(data=[{"allowed": self.allow, "retry_after_seconds": 9}])
        )


def _row(n: int, user: str, audience: str = "customer", **extra: Any) -> dict[str, Any]:
    return {
        "id": f"00000000-0000-4000-8000-{n:012d}",
        "recipient_user_id": user,
        "audience": audience,
        "type": "order_shipped",
        "i18n_key": "notifications.inApp.customer.order_shipped",
        "params": {"ref": f"REF{n}", "nested": {"x": 1}},
        "link_path": f"/account/orders/{n}",
        "created_at": f"2026-11-13T10:{n:02d}:00+00:00",
        "seen_at": None,
        "read_at": None,
        **extra,
    }


@pytest.fixture
def store() -> Store:
    st = Store()
    st.table("in_app_notifications").rows.extend(
        [_row(n, USER_A) for n in range(1, 6)]
        + [_row(10, USER_B), _row(11, VENDOR_USER, "vendor"), _row(12, USER_A, "vendor")]
    )
    return st


@pytest.fixture
def api(store: Store, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: store)
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": token, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset(
            {"customer", "vendor"}
            if user_id == VENDOR_USER
            else {"customer", ADMIN_ROLE_USERS[user_id]}
            if user_id in ADMIN_ROLE_USERS
            else {"customer"}
        ),
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


def _h(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user}"}


def _rows(store: Store) -> list[dict[str, Any]]:
    return store.table("in_app_notifications").rows


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/me/notifications"),
        ("GET", "/me/notifications/unseen-count"),
        ("POST", "/me/notifications/seen"),
        ("POST", "/me/notifications/read-all"),
        ("POST", "/me/notifications/00000000-0000-4000-8000-000000000001/read"),
    ],
)
def test_guest_gets_401(api: TestClient, method: str, path: str) -> None:
    assert api.request(method, path, json={}).status_code == 401


def test_list_returns_only_callers_rows_newest_first(api: TestClient) -> None:
    body = api.get("/me/notifications", headers=_h(USER_A)).json()
    refs = [item["params"]["ref"] for item in body["items"]]
    assert refs == ["REF5", "REF4", "REF3", "REF2", "REF1"]
    # Non-scalar params never leak through the strict response model.
    assert "nested" not in body["items"][0]["params"]
    assert body["next_cursor"] is None


def test_cursor_pagination_walks_all_pages_without_overlap(api: TestClient) -> None:
    seen: list[str] = []
    cursor = None
    for _ in range(5):
        url = "/me/notifications?limit=2" + (f"&cursor={cursor}" if cursor else "")
        body = api.get(url, headers=_h(USER_A)).json()
        seen += [item["params"]["ref"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == ["REF5", "REF4", "REF3", "REF2", "REF1"]


def test_cursor_round_trip_and_tampered_cursor_rejected(api: TestClient) -> None:
    ts, row_id = "2026-11-13T10:00:00+00:00", "00000000-0000-4000-8000-000000000001"
    assert decode_cursor(encode_cursor(ts, row_id)) == (ts, row_id)
    evil = encode_cursor('x",id.gt.0', row_id)
    response = api.get(f"/me/notifications?cursor={evil}", headers=_h(USER_A))
    assert response.status_code == 422


def test_vendor_feed_requires_vendor_role(api: TestClient) -> None:
    assert api.get("/me/notifications?audience=vendor", headers=_h(USER_A)).status_code == 403
    assert (
        api.get(
            "/me/notifications/unseen-count?audience=admin", headers=_h(VENDOR_USER)
        ).status_code
        == 403
    )
    body = api.get("/me/notifications?audience=vendor", headers=_h(VENDOR_USER)).json()
    assert [item["params"]["ref"] for item in body["items"]] == ["REF11"]


def test_unseen_count_and_mark_all_seen(api: TestClient, store: Store) -> None:
    assert api.get("/me/notifications/unseen-count", headers=_h(USER_A)).json() == {"unseen": 5}
    result = api.post("/me/notifications/seen", json={}, headers=_h(USER_A)).json()
    assert result == {"updated": 5}
    assert api.get("/me/notifications/unseen-count", headers=_h(USER_A)).json() == {"unseen": 0}
    # B's row and A's vendor-audience row are untouched.
    untouched = [r for r in _rows(store) if r["seen_at"] is None]
    assert {r["params"]["ref"] for r in untouched} == {"REF10", "REF11", "REF12"}


def test_mark_specific_ids_seen_ignores_other_users_ids(api: TestClient, store: Store) -> None:
    ids = [_row(1, USER_A)["id"], _row(10, USER_B)["id"]]
    result = api.post("/me/notifications/seen", json={"ids": ids}, headers=_h(USER_A)).json()
    assert result == {"updated": 1}
    b_row = next(r for r in _rows(store) if r["recipient_user_id"] == USER_B)
    assert b_row["seen_at"] is None


def test_mark_seen_rejects_non_uuid_ids(api: TestClient) -> None:
    response = api.post("/me/notifications/seen", json={"ids": ["1 or 1=1"]}, headers=_h(USER_A))
    assert response.status_code == 422


def test_mark_read_own_row_sets_seen_and_read(api: TestClient, store: Store) -> None:
    row_id = _row(2, USER_A)["id"]
    assert api.post(f"/me/notifications/{row_id}/read", headers=_h(USER_A)).json() == {"updated": 1}
    row = next(r for r in _rows(store) if r["id"] == row_id)
    assert row["read_at"] is not None and row["seen_at"] is not None
    # Idempotent second tap.
    assert api.post(f"/me/notifications/{row_id}/read", headers=_h(USER_A)).json() == {"updated": 0}


def test_mark_read_other_users_row_is_404(api: TestClient, store: Store) -> None:
    row_id = _row(10, USER_B)["id"]
    response = api.post(f"/me/notifications/{row_id}/read", headers=_h(USER_A))
    assert response.status_code == 404
    assert next(r for r in _rows(store) if r["id"] == row_id)["read_at"] is None


def test_read_all_only_touches_callers_audience(api: TestClient, store: Store) -> None:
    assert api.post("/me/notifications/read-all", headers=_h(USER_A)).json() == {"updated": 5}
    unread = {r["params"]["ref"] for r in _rows(store) if r["read_at"] is None}
    assert unread == {"REF10", "REF11", "REF12"}


def test_rate_limited_returns_429(api: TestClient, store: Store) -> None:
    store.allow = False
    response = api.get("/me/notifications/unseen-count", headers=_h(USER_A))
    assert response.status_code == 429


def test_push_subscribe_is_disabled_by_default(api: TestClient, store: Store) -> None:
    store.table("feature_flags").rows.append({"flag": "web_push", "enabled": False})
    config = api.get("/me/web-push", headers=_h(USER_A)).json()
    assert config == {"enabled": False, "vapid_public_key": None}
    response = api.put(
        "/me/push-subscriptions",
        json={
            "audience": "customer",
            "endpoint": "https://push.example.test/abc",
            "keys": {"p256dh": "p" * 20, "auth": "a" * 12},
        },
        headers=_h(USER_A),
    )
    assert response.status_code == 409
    assert store.table("web_push_subscriptions").rows == []


ENDPOINT = "https://fcm.googleapis.com/fcm/send/fake-endpoint-for-tests"
KEYS_A = {"p256dh": "p" * 20, "auth": "a" * 12}
KEYS_OTHER = {"p256dh": "q" * 20, "auth": "b" * 12}


def _enable_push(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_PUSH_VAPID_PUBLIC_KEY", "public-placeholder")
    monkeypatch.setenv("WEB_PUSH_VAPID_PRIVATE_KEY", "private-placeholder")
    monkeypatch.setenv("WEB_PUSH_VAPID_SUBJECT", "mailto:ops@example.test")
    store.table("feature_flags").rows.append({"flag": "web_push", "enabled": True})


def _sub_body(keys: dict[str, str], audience: str = "customer") -> dict[str, Any]:
    return {"audience": audience, "endpoint": ENDPOINT, "keys": keys}


def test_push_config_fails_closed_without_all_three_vapid_vars(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.table("feature_flags").rows.append({"flag": "web_push", "enabled": True})
    monkeypatch.setenv("WEB_PUSH_VAPID_PUBLIC_KEY", "public-placeholder")
    monkeypatch.delenv("WEB_PUSH_VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("WEB_PUSH_VAPID_SUBJECT", raising=False)
    assert api.get("/me/web-push", headers=_h(USER_A)).json() == {
        "enabled": False,
        "vapid_public_key": None,
    }
    assert (
        api.put("/me/push-subscriptions", json=_sub_body(KEYS_A), headers=_h(USER_A)).status_code
        == 409
    )


def test_push_subscribe_stores_and_refreshes_own_row(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_push(store, monkeypatch)
    subs = store.table("web_push_subscriptions").rows
    assert (
        api.put("/me/push-subscriptions", json=_sub_body(KEYS_A), headers=_h(USER_A)).status_code
        == 204
    )
    assert [(s["user_id"], s["p256dh"]) for s in subs] == [(USER_A, KEYS_A["p256dh"])]
    subs[0]["id"] = "sub-1"
    # Same user re-subscribing (rotated keys) updates in place, no duplicate.
    assert (
        api.put(
            "/me/push-subscriptions", json=_sub_body(KEYS_OTHER), headers=_h(USER_A)
        ).status_code
        == 204
    )
    assert [(s["user_id"], s["p256dh"]) for s in subs] == [(USER_A, KEYS_OTHER["p256dh"])]


def test_push_subscribe_never_deletes_another_users_endpoint(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Knowing B's endpoint URL is not enough to take it over or delete it."""
    _enable_push(store, monkeypatch)
    subs = store.table("web_push_subscriptions").rows
    subs.append(
        {
            "id": "sub-b",
            "user_id": USER_B,
            "audience": "customer",
            "endpoint": ENDPOINT,
            "p256dh": KEYS_OTHER["p256dh"],
            "auth_secret": KEYS_OTHER["auth"],
        }
    )
    response = api.put("/me/push-subscriptions", json=_sub_body(KEYS_A), headers=_h(USER_A))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "push_endpoint_conflict"
    assert [s["user_id"] for s in subs] == [USER_B]
    # Unsubscribe is scoped to the caller too.
    removed = api.post(
        "/me/push-subscriptions/remove", json={"endpoint": ENDPOINT}, headers=_h(USER_A)
    )
    assert removed.status_code == 204
    assert [s["user_id"] for s in subs] == [USER_B]


def test_push_subscribe_transfers_only_with_the_browsers_own_keys(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shared phone: A signs in where B was; the browser re-presents the same keys."""
    _enable_push(store, monkeypatch)
    subs = store.table("web_push_subscriptions").rows
    subs.append(
        {
            "id": "sub-b",
            "user_id": USER_B,
            "audience": "customer",
            "endpoint": ENDPOINT,
            "p256dh": KEYS_A["p256dh"],
            "auth_secret": KEYS_A["auth"],
        }
    )
    queue = store.table("web_push_deliveries").rows
    queue.extend(
        [
            {"id": "d1", "subscription_id": "sub-b", "status": "pending"},
            {"id": "d2", "subscription_id": "sub-b", "status": "sent"},
        ]
    )
    assert (
        api.put("/me/push-subscriptions", json=_sub_body(KEYS_A), headers=_h(USER_A)).status_code
        == 204
    )
    assert [(s["id"], s["user_id"]) for s in subs] == [("sub-b", USER_A)]
    # B's still-queued alert must never reach A's phone.
    assert [d["id"] for d in queue] == ["d2"]


def test_push_subscribe_rejects_non_push_service_endpoints(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_push(store, monkeypatch)
    for endpoint in (
        "https://push.example.test/abc",
        "https://169.254.169.254/latest/meta-data",
        "https://fcm.googleapis.com.evil.test/x",
    ):
        body = {"audience": "customer", "endpoint": endpoint, "keys": KEYS_A}
        assert api.put("/me/push-subscriptions", json=body, headers=_h(USER_A)).status_code == 422
    assert store.table("web_push_subscriptions").rows == []


def test_push_subscribe_vendor_audience_needs_vendor_role(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_push(store, monkeypatch)
    body = _sub_body(KEYS_A, audience="vendor")
    assert api.put("/me/push-subscriptions", json=body, headers=_h(USER_A)).status_code == 403
    assert api.put("/me/push-subscriptions", json=body, headers=_h(VENDOR_USER)).status_code == 204


@pytest.mark.parametrize("admin_user", sorted(ADMIN_ROLE_USERS))
def test_every_admin_panel_role_can_read_the_admin_feed(api: TestClient, admin_user: str) -> None:
    """superadmin / moderator / restricted rbac_* accounts no longer 403 (bell stays visible)."""
    for path in (
        "/me/notifications?audience=admin",
        "/me/notifications/unseen-count?audience=admin",
    ):
        assert api.get(path, headers=_h(admin_user)).status_code == 200
    assert (
        api.post(
            "/me/notifications/seen?audience=admin", json={}, headers=_h(admin_user)
        ).status_code
        == 200
    )


def test_admin_feed_still_rejects_non_admin_roles(api: TestClient) -> None:
    assert api.get("/me/notifications?audience=admin", headers=_h(USER_A)).status_code == 403
    assert api.get("/me/notifications?audience=admin", headers=_h(VENDOR_USER)).status_code == 403
