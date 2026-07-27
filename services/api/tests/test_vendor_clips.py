"""M17-P06 — the vendor studio's server side.

The claims worth defending are all about *whose data this is*:

* an unverified caller — no vendor row — is refused, with a reason;
* vendor A cannot read, stat, or link on vendor B's clip;
* a clip cannot link a listing that belongs to someone else, and the API says so
  rather than letting the database raise;
* the ≤3 link cap is enforced server-side, not just in the picker;
* the weekly allowance comes from ``platform_config``, not from a constant — the
  test proves it by *changing the config* and watching the limit move.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.services.clips import quota, state_machine
from fastapi.testclient import TestClient

VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
USER_NO_VENDOR = "33333333-3333-4333-8333-333333333333"

CLIP_A = "c1000000-0000-4000-8000-000000000001"
CLIP_B = "c1000000-0000-4000-8000-000000000002"
LISTING_A1 = "b1000000-0000-4000-8000-000000000001"
LISTING_A2 = "b1000000-0000-4000-8000-000000000002"
LISTING_A3 = "b1000000-0000-4000-8000-000000000003"
LISTING_A4 = "b1000000-0000-4000-8000-000000000004"
LISTING_B1 = "b2000000-0000-4000-8000-000000000001"

JWT_A = "jwt-a"
JWT_B = "jwt-b"
JWT_NONE = "jwt-none"


class UniqueViolation(Exception):
    pass


# --- Fake Supabase ----------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._eq: list[tuple[str, Any]] = []
        self._in: list[tuple[str, list[Any]]] = []
        self._gte: list[tuple[str, Any]] = []
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

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in.append((column, list(values)))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self._gte.append((column, value))
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
        if not all(row.get(c) == v for c, v in self._eq):
            return False
        if not all(row.get(c) in values for c, values in self._in):
            return False
        return all(str(row.get(c) or "") >= str(v) for c, v in self._gte)

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            self._parent.enforce_unique(row)
            row.setdefault("id", f"{self._parent.name}-{len(self._parent.rows)}")
            row.setdefault("created_at", datetime.now(UTC).isoformat())
            self._parent.rows.append(row)
            return MagicMock(data=[dict(row)])

        if self._op == "delete":
            removed = [dict(r) for r in self._parent.rows if self._match(r)]
            self._parent.rows[:] = [r for r in self._parent.rows if not self._match(r)]
            return MagicMock(data=removed)

        if self._op == "update":
            assert self._payload is not None
            updated = []
            for row in self._parent.rows:
                if self._match(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

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
    UNIQUE_KEYS: dict[str, tuple[str, ...]] = {
        "clip_products": ("clip_id", "listing_id"),
    }

    def __init__(self, name: str) -> None:
        self.name = name
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

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)

    def delete(self) -> FakeQuery:
        return FakeQuery(self).delete()


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))

    def rpc(self, name: str, params: dict[str, Any]) -> MagicMock:
        if name == "bump_rate_counter":
            return MagicMock(
                execute=lambda: MagicMock(data=[{"allowed": True, "retry_after_seconds": 0}])
            )
        raise AssertionError(f"unexpected rpc {name}")


class Store:
    def __init__(self) -> None:
        self.client = FakeSupabase()

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.client.table(name).rows


def _clip(
    clip_id: str, vendor_id: str, *, status: str = state_machine.DRAFT, **extra: Any
) -> dict[str, Any]:
    return {
        "id": clip_id,
        "vendor_id": vendor_id,
        "status": status,
        "caption": "solar lamp",
        "category_id": None,
        "poster_url": None,
        "duration_s": 30,
        "renditions": {},
        "like_count": 0,
        "comment_count": 0,
        "view_count": 0,
        "rejection_reason": None,
        "published_at": None,
        "taken_down_at": None,
        "created_at": datetime.now(UTC).isoformat(),
        **extra,
    }


def _listing(listing_id: str, vendor_id: str, *, status: str = "active") -> dict[str, Any]:
    return {
        "id": listing_id,
        "vendor_id": vendor_id,
        "title_override": f"Listing {listing_id[-1]}",
        "price_ngwee": 45_000,
        "status": status,
    }


@pytest.fixture
def store() -> Store:
    st = Store()
    st.rows("vendors").extend(
        [
            {"id": VENDOR_A, "owner_user_id": USER_A, "status": "active", "kyc_tier": 1},
            {"id": VENDOR_B, "owner_user_id": USER_B, "status": "active", "kyc_tier": 1},
        ]
    )
    st.rows("vendor_listings").extend(
        [
            _listing(LISTING_A1, VENDOR_A),
            _listing(LISTING_A2, VENDOR_A),
            _listing(LISTING_A3, VENDOR_A),
            _listing(LISTING_A4, VENDOR_A),
            _listing(LISTING_B1, VENDOR_B),
        ]
    )
    st.rows("video_clips").extend([_clip(CLIP_A, VENDOR_A), _clip(CLIP_B, VENDOR_B)])
    for name in ("clip_products", "analytics_events", "platform_config"):
        st.rows(name)
    return st


@pytest.fixture
def api(store: Store, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    wrapper = store
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr(
        "app.routers.vendor_clips.get_supabase_client", lambda: wrapper, raising=False
    )
    monkeypatch.setattr("app.media.authz.get_supabase_client", lambda: wrapper, raising=False)

    users = {JWT_A: USER_A, JWT_B: USER_B, JWT_NONE: USER_NO_VENDOR}
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": users[token], "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"vendor"}),
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


def _h(token: str = JWT_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- D-V7: vendors only -----------------------------------------------------
def test_a_caller_without_a_vendor_row_is_refused_with_a_reason(api: TestClient) -> None:
    response = api.get("/vendor/clips", headers=_h(JWT_NONE))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_an_unauthenticated_caller_is_401(api: TestClient) -> None:
    assert api.get("/vendor/clips").status_code == 401


# --- Ownership ---------------------------------------------------------------
def test_a_vendor_sees_only_their_own_clips(api: TestClient) -> None:
    body = api.get("/vendor/clips", headers=_h(JWT_A)).json()

    assert [item["id"] for item in body["items"]] == [CLIP_A]


def test_vendor_a_cannot_read_vendor_bs_clip(api: TestClient) -> None:
    assert api.get(f"/vendor/clips/{CLIP_B}", headers=_h(JWT_A)).status_code == 404


def test_vendor_a_cannot_stat_vendor_bs_clip(api: TestClient) -> None:
    assert api.get(f"/vendor/clips/{CLIP_B}/stats", headers=_h(JWT_A)).status_code == 404


def test_vendor_a_cannot_link_on_vendor_bs_clip(api: TestClient, store: Store) -> None:
    response = api.post(
        f"/vendor/clips/{CLIP_B}/listings", headers=_h(JWT_A), json={"listing_id": LISTING_A1}
    )

    assert response.status_code == 404
    assert store.rows("clip_products") == []


# --- Cross-vendor linking ----------------------------------------------------
def test_linking_another_vendors_listing_is_refused_by_the_api(
    api: TestClient, store: Store
) -> None:
    """The DB trigger is the backstop; this is the answer a human can act on."""
    response = api.post(
        f"/vendor/clips/{CLIP_A}/listings", headers=_h(JWT_A), json={"listing_id": LISTING_B1}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "listing_not_owned"
    assert store.rows("clip_products") == []


def test_a_nonexistent_listing_answers_the_same_as_someone_elses(api: TestClient) -> None:
    missing = api.post(
        f"/vendor/clips/{CLIP_A}/listings",
        headers=_h(JWT_A),
        json={"listing_id": "b9000000-0000-4000-8000-000000000009"},
    )
    theirs = api.post(
        f"/vendor/clips/{CLIP_A}/listings", headers=_h(JWT_A), json={"listing_id": LISTING_B1}
    )

    assert missing.status_code == theirs.status_code == 403
    assert missing.json()["error"]["code"] == theirs.json()["error"]["code"]


def test_a_paused_listing_cannot_be_linked(api: TestClient, store: Store) -> None:
    store.rows("vendor_listings")[0]["status"] = "paused"

    response = api.post(
        f"/vendor/clips/{CLIP_A}/listings", headers=_h(JWT_A), json={"listing_id": LISTING_A1}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "listing_not_active"


# --- The three-link cap ------------------------------------------------------
def test_three_links_are_allowed_and_the_fourth_is_refused(
    api: TestClient, store: Store
) -> None:
    for index, listing_id in enumerate((LISTING_A1, LISTING_A2, LISTING_A3)):
        response = api.post(
            f"/vendor/clips/{CLIP_A}/listings",
            headers=_h(JWT_A),
            json={"listing_id": listing_id, "sort_order": index},
        )
        assert response.status_code == 200

    fourth = api.post(
        f"/vendor/clips/{CLIP_A}/listings", headers=_h(JWT_A), json={"listing_id": LISTING_A4}
    )

    assert fourth.status_code == 422
    assert fourth.json()["error"]["code"] == "clip_link_limit"
    assert len(store.rows("clip_products")) == 3


def test_linking_the_same_listing_twice_is_idempotent(api: TestClient, store: Store) -> None:
    api.post(f"/vendor/clips/{CLIP_A}/listings", headers=_h(JWT_A), json={"listing_id": LISTING_A1})
    second = api.post(
        f"/vendor/clips/{CLIP_A}/listings", headers=_h(JWT_A), json={"listing_id": LISTING_A1}
    )

    assert second.status_code == 200
    assert len(store.rows("clip_products")) == 1


def test_unlinking_frees_a_slot(api: TestClient, store: Store) -> None:
    for listing_id in (LISTING_A1, LISTING_A2, LISTING_A3):
        api.post(
            f"/vendor/clips/{CLIP_A}/listings", headers=_h(JWT_A), json={"listing_id": listing_id}
        )

    api.delete(f"/vendor/clips/{CLIP_A}/listings/{LISTING_A1}", headers=_h(JWT_A))
    fourth = api.post(
        f"/vendor/clips/{CLIP_A}/listings", headers=_h(JWT_A), json={"listing_id": LISTING_A4}
    )

    assert fourth.status_code == 200
    assert len(store.rows("clip_products")) == 3


def test_a_sort_order_outside_the_cap_is_refused_by_the_schema(api: TestClient) -> None:
    response = api.post(
        f"/vendor/clips/{CLIP_A}/listings",
        headers=_h(JWT_A),
        json={"listing_id": LISTING_A1, "sort_order": 3},
    )
    assert response.status_code == 422


# --- Weekly allowance --------------------------------------------------------
def test_the_weekly_cap_is_read_from_config_not_hardcoded(store: Store) -> None:
    store.rows("platform_config").append(
        {"key": quota.WEEKLY_CAP_KEY, "value": {"1": 7, "2": 20}}
    )

    assert quota.weekly_cap_for_tier(store, 1) == 7
    assert quota.weekly_cap_for_tier(store, 2) == 20


def test_a_missing_config_row_falls_back_to_the_documented_default(store: Store) -> None:
    assert quota.weekly_cap_for_tier(store, 1) == quota.DEFAULT_WEEKLY_CAPS["1"]


def test_an_unknown_tier_gets_the_most_restrictive_allowance(store: Store) -> None:
    store.rows("platform_config").append(
        {"key": quota.WEEKLY_CAP_KEY, "value": {"1": 3, "2": 10}}
    )

    assert quota.weekly_cap_for_tier(store, 9) == 3


def test_the_quota_window_is_trailing_not_calendar(store: Store) -> None:
    """Three clips six days ago must still count today."""
    now = datetime.now(UTC)
    for index in range(3):
        store.rows("video_clips").append(
            _clip(
                f"old-{index}",
                VENDOR_A,
                created_at=(now - timedelta(days=6)).isoformat(),
            )
        )

    used = quota.count_clips_in_window(store, vendor_id=VENDOR_A, now=now)
    assert used == 4  # the three backdated plus the fixture's CLIP_A


def test_a_clip_older_than_the_window_no_longer_counts(store: Store) -> None:
    now = datetime.now(UTC)
    store.rows("video_clips").append(
        _clip("ancient", VENDOR_A, created_at=(now - timedelta(days=8)).isoformat())
    )

    assert quota.count_clips_in_window(store, vendor_id=VENDOR_A, now=now) == 1


def test_a_rejected_clip_still_counts_against_the_allowance(store: Store) -> None:
    """It spent a transcode credit, which is the cost the cap bounds."""
    store.rows("video_clips").append(
        _clip("rejected-one", VENDOR_A, status=state_machine.REJECTED)
    )

    assert quota.count_clips_in_window(store, vendor_id=VENDOR_A) == 2


def test_an_over_quota_vendor_is_refused_with_the_cap_in_the_error(store: Store) -> None:
    from app.errors import AppError

    store.rows("platform_config").append({"key": quota.WEEKLY_CAP_KEY, "value": {"1": 1}})

    with pytest.raises(AppError) as excinfo:
        quota.enforce_clip_weekly_cap(store, vendor_id=VENDOR_A, tier=1)

    assert excinfo.value.code == "clip_cap_exceeded"
    assert excinfo.value.http_status == 403
    assert excinfo.value.details["weekly_cap"] == 1
    assert excinfo.value.details["window_days"] == 7


def test_the_list_response_reports_the_live_quota(api: TestClient, store: Store) -> None:
    store.rows("platform_config").append({"key": quota.WEEKLY_CAP_KEY, "value": {"1": 5}})

    body = api.get("/vendor/clips", headers=_h(JWT_A)).json()

    assert body["weekly_cap"] == 5
    assert body["remaining_this_week"] == 4
    assert body["window_days"] == 7


# --- Stats -------------------------------------------------------------------
def test_stats_are_scoped_to_the_caller(api: TestClient, store: Store) -> None:
    store.rows("video_clips")[0].update({"view_count": 12, "like_count": 4})
    store.rows("analytics_events").append(
        {
            "id": "e1",
            "entity_type": "video_clip",
            "entity_id": CLIP_A,
            "event_type": "clip_add_to_cart",
        }
    )

    body = api.get(f"/vendor/clips/{CLIP_A}/stats", headers=_h(JWT_A)).json()

    assert body["view_count"] == 12
    assert body["like_count"] == 4
    assert body["orders_attributed"] == 1


def test_a_pending_review_clip_reports_its_real_status(api: TestClient, store: Store) -> None:
    """The studio must be able to say "awaiting review" — never "live"."""
    store.rows("video_clips")[0]["status"] = state_machine.PENDING_REVIEW

    body = api.get(f"/vendor/clips/{CLIP_A}", headers=_h(JWT_A)).json()

    assert body["status"] == state_machine.PENDING_REVIEW
    assert body["published_at"] is None


def test_a_rejection_reason_reaches_the_vendor(api: TestClient, store: Store) -> None:
    store.rows("video_clips")[0].update(
        {"status": state_machine.REJECTED, "rejection_reason": "prohibited_keyword"}
    )

    body = api.get(f"/vendor/clips/{CLIP_A}", headers=_h(JWT_A)).json()

    assert body["rejection_reason"] == "prohibited_keyword"
