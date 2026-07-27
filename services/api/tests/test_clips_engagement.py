"""M17-P03 — likes, comments, reports and views.

The whole point of this pebble is that **the constraint does the deduping, not the
code**. So the fake Supabase here enforces the real unique keys from migration
``0076`` and serialises writes behind a lock — which is what lets the concurrency
tests actually mean something. A fake that accepted every insert would let a
read-then-write implementation pass, and a read-then-write implementation is
exactly the bug these tests exist to catch.

Counters move only through the ``SECURITY DEFINER`` RPC, so the fake exposes
``clip_bump_counter`` as an RPC and **nothing else can touch those columns** —
a direct UPDATE on ``like_count`` in the fake would be a test failure, not a
silent pass.
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.services.clips import state_machine
from fastapi.testclient import TestClient

VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
CLIP_ID = "c1000000-0000-4000-8000-000000000001"
JWT = "valid.jwt.token"

TODAY = datetime.now(UTC).date().isoformat()


class UniqueViolation(Exception):
    """Stands in for Postgres 23505 — the constraint, not an application check."""


# --- Fake Supabase ----------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._eq: list[tuple[str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str = "*", **_kwargs: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._eq.append((column, value))
        return self

    def order(self, column: str, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "update"
        self._payload = payload
        return self

    def delete(self) -> FakeQuery:
        self._op = "delete"
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        return all(row.get(c) == v for c, v in self._eq)

    def execute(self) -> MagicMock:
        store = self._parent.store
        with store.lock:
            if self._op == "insert":
                assert self._payload is not None
                row = dict(self._payload)
                self._parent.apply_defaults(row)
                self._parent.enforce_unique(row)
                row.setdefault("id", f"{self._parent.name}-{len(self._parent.rows)}")
                row.setdefault("created_at", datetime.now(UTC).isoformat())
                self._parent.rows.append(row)
                return MagicMock(data=[dict(row)])

            if self._op == "update":
                assert self._payload is not None
                # A direct write to a counter column is the thing this pebble
                # promises never happens — make it loud rather than silent.
                for column in ("like_count", "comment_count", "view_count"):
                    assert column not in self._payload, (
                        f"{column} was written directly instead of via clip_bump_counter"
                    )
                updated = []
                for row in self._parent.rows:
                    if self._match(row):
                        row.update(self._payload)
                        updated.append(dict(row))
                return MagicMock(data=updated)

            if self._op == "delete":
                removed = [dict(r) for r in self._parent.rows if self._match(r)]
                self._parent.rows[:] = [r for r in self._parent.rows if not self._match(r)]
                return MagicMock(data=removed)

            rows = [dict(row) for row in self._parent.rows if self._match(row)]
            if self._order:
                column, desc = self._order
                rows.sort(key=lambda r: str(r.get(column) or ""), reverse=desc)
            if self._limit is not None:
                rows = rows[: self._limit]
            if self._maybe_single:
                return MagicMock(data=rows[0] if rows else None)
            return MagicMock(data=rows)


class FakeTable:
    #: The real unique keys from migration 0076.
    UNIQUE_KEYS: dict[str, tuple[str, ...]] = {
        "clip_likes": ("clip_id", "user_id"),
        "clip_reports": ("clip_id", "reporter_id"),
        "clip_views": ("clip_id", "user_id", "viewed_on"),
    }
    #: Column defaults the database would supply.
    DEFAULTS: dict[str, dict[str, Any]] = {
        "clip_views": {"viewed_on": TODAY},
    }

    def __init__(self, name: str, store: Store) -> None:
        self.name = name
        self.store = store
        self.rows: list[dict[str, Any]] = []

    def apply_defaults(self, row: dict[str, Any]) -> None:
        for column, value in self.DEFAULTS.get(self.name, {}).items():
            row.setdefault(column, value)

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

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)

    def delete(self) -> FakeQuery:
        return FakeQuery(self).delete()


class FakeSupabase:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name, self.store))

    def rpc(self, name: str, params: dict[str, Any]) -> MagicMock:
        if name == "clip_bump_counter":
            return MagicMock(execute=lambda: MagicMock(data=self._bump(params)))
        if name == "bump_rate_counter":
            return MagicMock(execute=lambda: MagicMock(data=[self.store.rate_verdict()]))
        raise AssertionError(f"unexpected rpc {name}")

    def _bump(self, params: dict[str, Any]) -> int:
        column = str(params["p_column"])
        assert column in {"like_count", "comment_count", "view_count"}
        with self.store.lock:
            for row in self.table("video_clips").rows:
                if row.get("id") == params["p_clip_id"]:
                    value = max(0, int(row.get(column) or 0) + int(params["p_delta"]))
                    row[column] = value
                    return value
        raise AssertionError("clip_bump_counter: clip not found")


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

    def counter(self, column: str) -> int:
        return int(self.rows("video_clips")[0].get(column) or 0)


# --- Fixtures ---------------------------------------------------------------
@pytest.fixture
def store() -> Store:
    st = Store()
    st.rows("video_clips").append(
        {
            "id": CLIP_ID,
            "vendor_id": VENDOR_A,
            "status": state_machine.PUBLISHED,
            "caption": "solar lamp demo",
            "like_count": 0,
            "comment_count": 0,
            "view_count": 0,
            "published_at": datetime.now(UTC).isoformat(),
        }
    )
    st.rows("feature_flags").append({"flag": "clips_comments", "enabled": True})
    for name in ("clip_likes", "clip_comments", "clip_reports", "clip_views", "audit_log"):
        st.rows(name)
    return st


@pytest.fixture
def api(store: Store, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    wrapper = store
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr(
        "app.routers.clips_engagement.get_supabase_client", lambda: wrapper, raising=False
    )
    # Analytics writes go through psql in production; they are fire-and-forget
    # here so an emit can never be what makes an engagement test pass or fail.
    monkeypatch.setattr(
        "app.services.analytics.events.record_event",
        lambda **kwargs: None,
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def headers(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": USER_A, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"customer"}),
    )
    return {"Authorization": f"Bearer {JWT}"}


def _multi_user_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve the caller from the bearer token so several users can act."""
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": token, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"customer"}),
    )


# --- Likes ------------------------------------------------------------------
def test_a_like_creates_one_row_and_moves_the_counter_once(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    body = api.post(f"/clips/{CLIP_ID}/like", headers=headers).json()

    assert body["liked"] is True
    assert body["like_count"] == 1
    assert len(store.rows("clip_likes")) == 1
    assert store.counter("like_count") == 1


def test_liking_twice_leaves_one_row_and_one_count(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    first = api.post(f"/clips/{CLIP_ID}/like", headers=headers).json()
    second = api.post(f"/clips/{CLIP_ID}/like", headers=headers).json()

    assert first["like_count"] == second["like_count"] == 1
    assert len(store.rows("clip_likes")) == 1
    assert store.counter("like_count") == 1


def test_concurrent_likes_from_the_same_user_produce_one_row(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    """The PK decides, not the request ordering."""
    barrier = threading.Barrier(8)

    def like() -> None:
        barrier.wait()
        api.post(f"/clips/{CLIP_ID}/like", headers=headers)

    threads = [threading.Thread(target=like) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(store.rows("clip_likes")) == 1
    assert store.counter("like_count") == 1


def test_concurrent_likes_from_different_users_lose_no_updates(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read-then-write counter would land short of 12 here."""
    _multi_user_auth(monkeypatch)
    users = [f"{index:08d}-0000-4000-8000-000000000000" for index in range(12)]
    barrier = threading.Barrier(len(users))

    def like(user_id: str) -> None:
        barrier.wait()
        api.post(f"/clips/{CLIP_ID}/like", headers={"Authorization": f"Bearer {user_id}"})

    threads = [threading.Thread(target=like, args=(user,)) for user in users]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(store.rows("clip_likes")) == len(users)
    assert store.counter("like_count") == len(users)


def test_unliking_removes_the_row_and_decrements_once(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    api.post(f"/clips/{CLIP_ID}/like", headers=headers)

    body = api.request("DELETE", f"/clips/{CLIP_ID}/like", headers=headers).json()

    assert body["liked"] is False
    assert body["like_count"] == 0
    assert store.rows("clip_likes") == []


def test_unliking_twice_is_idempotent(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    api.post(f"/clips/{CLIP_ID}/like", headers=headers)
    api.request("DELETE", f"/clips/{CLIP_ID}/like", headers=headers)
    second = api.request("DELETE", f"/clips/{CLIP_ID}/like", headers=headers)

    assert second.status_code == 200
    assert second.json()["like_count"] == 0
    assert store.counter("like_count") == 0


def test_unliking_something_never_liked_does_not_go_negative(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    response = api.request("DELETE", f"/clips/{CLIP_ID}/like", headers=headers)

    assert response.json()["like_count"] == 0
    assert store.counter("like_count") == 0


def test_liking_requires_authentication(api: TestClient) -> None:
    assert api.post(f"/clips/{CLIP_ID}/like").status_code == 401


def test_liking_an_unpublished_clip_is_404(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    store.rows("video_clips")[0]["status"] = "pending_review"

    assert api.post(f"/clips/{CLIP_ID}/like", headers=headers).status_code == 404


# --- No client-writable counters -------------------------------------------
@pytest.mark.parametrize("counter", ["like_count", "comment_count", "view_count"])
def test_a_request_that_tries_to_set_a_counter_is_rejected(
    api: TestClient, store: Store, headers: dict[str, str], counter: str
) -> None:
    response = api.post(
        f"/clips/{CLIP_ID}/view",
        headers=headers,
        json={"watched_ms": 5000, counter: 9999},
    )

    assert response.status_code == 422
    assert store.counter(counter) == 0


def test_the_counter_rpc_refuses_an_unknown_column(store: Store) -> None:
    from app.errors import AppError

    with pytest.raises(AppError) as excinfo:
        state_machine.bump_counter(
            store, clip_id=CLIP_ID, column="published_at", delta=1
        )
    assert excinfo.value.code == "clip_invalid_counter"


# --- Comments ---------------------------------------------------------------
def test_a_comment_is_stored_and_counted(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    response = api.post(
        f"/clips/{CLIP_ID}/comments", headers=headers, json={"body": "Nice lamp"}
    )

    assert response.status_code == 201
    assert response.json()["body"] == "Nice lamp"
    assert len(store.rows("clip_comments")) == 1
    assert store.counter("comment_count") == 1


def test_comments_are_invisible_when_the_flag_is_off(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    """F-V2: built, but shipped OFF. The flag is the whole switch."""
    store.rows("feature_flags")[0]["enabled"] = False

    posted = api.post(
        f"/clips/{CLIP_ID}/comments", headers=headers, json={"body": "Nice lamp"}
    )
    listed = api.get(f"/clips/{CLIP_ID}/comments")

    assert posted.status_code == 404
    assert listed.status_code == 404
    assert store.rows("clip_comments") == []


def test_a_missing_flag_row_means_comments_are_off(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    """Fail closed: no row is not the same as 'assume on'."""
    store.rows("feature_flags").clear()

    assert (
        api.post(
            f"/clips/{CLIP_ID}/comments", headers=headers, json={"body": "hi"}
        ).status_code
        == 404
    )


def test_a_prohibited_comment_is_never_persisted(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    from app.services.moderation.prohibited import PROHIBITED_KEYWORDS

    banned = sorted(PROHIBITED_KEYWORDS)[0]

    response = api.post(
        f"/clips/{CLIP_ID}/comments", headers=headers, json={"body": f"buy my {banned}"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "prohibited_comment"
    assert store.rows("clip_comments") == []
    assert store.counter("comment_count") == 0


def test_commenting_requires_authentication(api: TestClient) -> None:
    assert api.post(f"/clips/{CLIP_ID}/comments", json={"body": "hi"}).status_code == 401


def test_the_comment_rate_limit_is_enforced(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    store.rate_limit_allows = False

    response = api.post(
        f"/clips/{CLIP_ID}/comments", headers=headers, json={"body": "hi"}
    )

    assert response.status_code == 429
    assert store.rows("clip_comments") == []


def test_every_engagement_write_passes_through_the_rate_limiter(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    store.rate_limit_allows = False

    assert api.post(f"/clips/{CLIP_ID}/like", headers=headers).status_code == 429
    assert (
        api.request("DELETE", f"/clips/{CLIP_ID}/like", headers=headers).status_code == 429
    )
    assert (
        api.post(
            f"/clips/{CLIP_ID}/report", headers=headers, json={"reason": "spam"}
        ).status_code
        == 429
    )
    assert (
        api.post(
            f"/clips/{CLIP_ID}/view", headers=headers, json={"watched_ms": 5000}
        ).status_code
        == 429
    )


def test_an_over_long_comment_is_refused_by_the_schema(
    api: TestClient, headers: dict[str, str]
) -> None:
    response = api.post(
        f"/clips/{CLIP_ID}/comments", headers=headers, json={"body": "x" * 501}
    )
    assert response.status_code == 422


def test_hidden_comments_are_not_listed(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    api.post(f"/clips/{CLIP_ID}/comments", headers=headers, json={"body": "visible one"})
    store.rows("clip_comments")[0]["status"] = "hidden"

    assert api.get(f"/clips/{CLIP_ID}/comments").json()["items"] == []


# --- Reports ----------------------------------------------------------------
def test_a_report_is_recorded_once_per_reporter(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    first = api.post(f"/clips/{CLIP_ID}/report", headers=headers, json={"reason": "spam"})
    second = api.post(
        f"/clips/{CLIP_ID}/report", headers=headers, json={"reason": "spam again"}
    )

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(store.rows("clip_reports")) == 1


def test_different_reporters_each_get_a_row(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _multi_user_auth(monkeypatch)
    for user in (USER_A, USER_B):
        api.post(
            f"/clips/{CLIP_ID}/report",
            headers={"Authorization": f"Bearer {user}"},
            json={"reason": "spam"},
        )

    assert len(store.rows("clip_reports")) == 2


def test_reporting_requires_authentication(api: TestClient) -> None:
    assert api.post(f"/clips/{CLIP_ID}/report", json={"reason": "spam"}).status_code == 401


# --- Views ------------------------------------------------------------------
def test_a_view_under_three_seconds_is_not_counted(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    response = api.post(
        f"/clips/{CLIP_ID}/view", headers=headers, json={"watched_ms": 2999}
    )

    assert response.status_code == 202
    assert response.json()["counted"] is False
    assert store.rows("clip_views") == []
    assert store.counter("view_count") == 0


def test_a_view_at_three_seconds_is_counted(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    body = api.post(
        f"/clips/{CLIP_ID}/view", headers=headers, json={"watched_ms": 3000}
    ).json()

    assert body["counted"] is True
    assert body["view_count"] == 1
    assert len(store.rows("clip_views")) == 1


def test_the_same_user_watching_twice_the_same_day_counts_once(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    api.post(f"/clips/{CLIP_ID}/view", headers=headers, json={"watched_ms": 9000})
    second = api.post(
        f"/clips/{CLIP_ID}/view", headers=headers, json={"watched_ms": 9000}
    ).json()

    assert second["counted"] is False
    assert len(store.rows("clip_views")) == 1
    assert store.counter("view_count") == 1


def test_a_client_claiming_three_seconds_a_hundred_times_still_counts_once(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    """The dedupe is the constraint, not the client's honesty."""
    for _ in range(100):
        api.post(f"/clips/{CLIP_ID}/view", headers=headers, json={"watched_ms": 3000})

    assert len(store.rows("clip_views")) == 1
    assert store.counter("view_count") == 1


def test_the_same_user_on_a_different_day_counts_again(
    api: TestClient, store: Store, headers: dict[str, str]
) -> None:
    api.post(f"/clips/{CLIP_ID}/view", headers=headers, json={"watched_ms": 4000})
    # Yesterday's row, as the date-keyed unique constraint would have stored it.
    store.rows("clip_views")[0]["viewed_on"] = "2026-07-26"

    second = api.post(
        f"/clips/{CLIP_ID}/view", headers=headers, json={"watched_ms": 4000}
    ).json()

    assert second["counted"] is True
    assert len(store.rows("clip_views")) == 2
    assert store.counter("view_count") == 2


def test_the_view_date_is_never_taken_from_the_request(
    api: TestClient, headers: dict[str, str]
) -> None:
    """Picking the date would let a client earn a second view whenever it liked."""
    response = api.post(
        f"/clips/{CLIP_ID}/view",
        headers=headers,
        json={"watched_ms": 4000, "viewed_on": "2020-01-01"},
    )
    assert response.status_code == 422


def test_different_users_each_count(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _multi_user_auth(monkeypatch)
    for user in (USER_A, USER_B):
        api.post(
            f"/clips/{CLIP_ID}/view",
            headers={"Authorization": f"Bearer {user}"},
            json={"watched_ms": 5000},
        )

    assert len(store.rows("clip_views")) == 2
    assert store.counter("view_count") == 2


def test_anonymous_views_are_not_counted(api: TestClient, store: Store) -> None:
    """A client-supplied 'stable key' would be a counter the client controls."""
    assert (
        api.post(f"/clips/{CLIP_ID}/view", json={"watched_ms": 9000}).status_code == 401
    )
    assert store.rows("clip_views") == []


def test_a_negative_watch_time_is_refused(
    api: TestClient, headers: dict[str, str]
) -> None:
    response = api.post(
        f"/clips/{CLIP_ID}/view", headers=headers, json={"watched_ms": -1}
    )
    assert response.status_code == 422


# --- Registry ---------------------------------------------------------------
def test_every_engagement_route_has_a_registered_rate_limit_policy() -> None:
    from app.core import ratelimit_policies as rp

    for route_id in (
        "POST /clips/{clip_id}/like",
        "DELETE /clips/{clip_id}/like",
        "POST /clips/{clip_id}/comments",
        "POST /clips/{clip_id}/report",
        "POST /clips/{clip_id}/view",
    ):
        assert route_id in rp.POLICIES
        assert route_id not in rp.EXEMPT_ROUTE_IDS
