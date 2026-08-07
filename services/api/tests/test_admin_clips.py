"""M17-P07 — admin review, takedown and report triage.

The claims this file exists to hold:

* **approve is the only path to `published`** — asserted structurally against the
  state machine, not by reading the routers;
* **an admin cannot publish broken media** — missing rendition, missing poster or
  an over-cap duration refuses, because approval judges content and the machine
  still owns validity;
* **takedown is instant** — the very next feed read must not return the clip, and
  the test asks the feed rather than trusting RLS timing;
* **three upheld takedowns suspend the vendor**, and suspension takes that
  vendor's other published clips down with it;
* **every action is idempotent and concurrency-safe**: a replay is a no-op, and a
  second concurrent action loses with a 409.
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.services.clips import state_machine
from fastapi.testclient import TestClient

ADMIN_USER = "aaaa0000-0000-4000-8000-00000000000a"
VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_OWNER = "11111111-1111-4111-8111-111111111111"
CLIP_ID = "c1000000-0000-4000-8000-000000000001"
JWT = "admin.jwt"

GOOD_RENDITIONS: dict[str, Any] = {
    "480p": {"url": "https://res.cloudinary.com/demo/a_480.mp4", "width": 480, "bytes": 1_900_000},
    "720p": {"url": "https://res.cloudinary.com/demo/a_720.mp4", "width": 720, "bytes": 4_100_000},
}


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

    def lt(self, column: str, value: Any) -> FakeQuery:
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
        with self._parent.store.lock:
            if self._op == "insert":
                assert self._payload is not None
                row = dict(self._payload)
                row.setdefault("id", f"{self._parent.name}-{len(self._parent.rows)}")
                row.setdefault("created_at", datetime.now(UTC).isoformat())
                self._parent.rows.append(row)
                return MagicMock(data=[dict(row)])

            if self._op == "update":
                assert self._payload is not None
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
    def __init__(self, name: str, store: Store) -> None:
        self.name = name
        self.store = store
        self.rows: list[dict[str, Any]] = []

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
        if name == "bump_rate_counter":
            return MagicMock(
                execute=lambda: MagicMock(data=[{"allowed": True, "retry_after_seconds": 0}])
            )
        raise AssertionError(f"unexpected rpc {name}")


class Store:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.client = FakeSupabase(self)

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.client.table(name).rows

    def clip(self, clip_id: str = CLIP_ID) -> dict[str, Any]:
        return next(row for row in self.rows("video_clips") if row["id"] == clip_id)


def _clip(
    clip_id: str,
    *,
    status: str = state_machine.PENDING_REVIEW,
    renditions: dict[str, Any] | None = None,
    poster: str | None = "https://res.cloudinary.com/demo/a.webp",
    duration: int | None = 30,
    age_hours: float = 1.0,
) -> dict[str, Any]:
    created = (datetime.now(UTC) - timedelta(hours=age_hours)).isoformat()
    return {
        "id": clip_id,
        "vendor_id": VENDOR_A,
        "status": status,
        "caption": "solar lamp demo",
        "category_id": None,
        "poster_url": poster,
        "duration_s": duration,
        "renditions": GOOD_RENDITIONS if renditions is None else renditions,
        "like_count": 0,
        "comment_count": 0,
        "view_count": 0,
        "published_at": None,
        "taken_down_at": None,
        "rejection_reason": None,
        "created_at": created,
    }


@pytest.fixture
def store() -> Store:
    st = Store()
    st.rows("vendors").append(
        {
            "id": VENDOR_A,
            "display_name": "Alpha Traders",
            "status": "active",
            "kyc_tier": 2,
            "owner_user_id": VENDOR_OWNER,
        }
    )
    st.rows("video_clips").append(_clip(CLIP_ID))
    st.rows("user_roles").append({"user_id": ADMIN_USER, "role": "admin"})
    for name in (
        "clip_reports",
        "clip_products",
        "vendor_listings",
        "audit_log",
        "notification_outbox",
        "orders",
        "payouts",
        "feature_flags",
    ):
        st.rows(name)
    st.rows("feature_flags").append({"flag": "clips", "enabled": True})
    return st


@pytest.fixture
def api(store: Store, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    wrapper = store
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: wrapper)
    for module in ("app.routers.admin_clips", "app.routers.clips"):
        monkeypatch.setattr(f"{module}.get_supabase_client", lambda: wrapper, raising=False)
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": ADMIN_USER, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"admin"}),
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {JWT}"}


# --- Structural: only approve can publish ------------------------------------
def test_published_is_reachable_only_from_pending_review() -> None:
    sources = [
        state
        for state, targets in state_machine.ALLOWED_TRANSITIONS.items()
        if state_machine.PUBLISHED in targets
    ]
    assert sources == [state_machine.PENDING_REVIEW]


def test_no_module_outside_admin_clips_calls_publish() -> None:
    """The only publish call site in the app is the admin approve route."""
    from pathlib import Path

    import app as app_package

    root = Path(app_package.__file__).parent
    callers = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if "state_machine.publish(" in path.read_text(encoding="utf-8")
    }
    assert callers == {"routers/admin_clips.py"}


# --- RBAC --------------------------------------------------------------------
def test_an_unauthenticated_caller_is_refused(api: TestClient) -> None:
    assert api.get("/admin/clips").status_code == 401


def test_a_non_admin_is_refused(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"vendor"}),
    )
    assert api.get("/admin/clips", headers=_h()).status_code == 403


# --- Queue -------------------------------------------------------------------
def test_the_queue_is_oldest_first_with_an_sla_badge(api: TestClient, store: Store) -> None:
    store.rows("video_clips").append(_clip("newer", age_hours=0.5))
    store.rows("video_clips").append(_clip("stale", age_hours=40))

    items = api.get("/admin/clips", headers=_h()).json()["items"]

    assert [item["clip_id"] for item in items] == ["stale", CLIP_ID, "newer"]
    assert items[0]["sla_breached"] is True
    assert items[1]["sla_breached"] is False


def test_the_queue_shows_only_pending_review(api: TestClient, store: Store) -> None:
    store.rows("video_clips").append(_clip("draft-one", status=state_machine.DRAFT))
    store.rows("video_clips").append(_clip("live-one", status=state_machine.PUBLISHED))

    items = api.get("/admin/clips", headers=_h()).json()["items"]

    assert [item["clip_id"] for item in items] == [CLIP_ID]


def test_the_detail_view_serves_short_lived_preview_urls(api: TestClient) -> None:
    body = api.get(f"/admin/clips/{CLIP_ID}", headers=_h()).json()

    assert set(body["preview_urls"]) == {"480p", "720p"}
    assert body["preview_expires_in_s"] <= 300
    assert body["media_ready"] is True
    assert body["screen_verdict"] == "passed"


# --- Approve -----------------------------------------------------------------
def test_approving_publishes_and_audits(api: TestClient, store: Store) -> None:
    response = api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())

    assert response.status_code == 200
    assert response.json()["status"] == state_machine.PUBLISHED
    assert store.clip()["status"] == state_machine.PUBLISHED
    actions = [row["action"] for row in store.rows("audit_log")]
    assert "admin.clips.approve" in actions


def test_approving_twice_is_a_no_op(api: TestClient, store: Store) -> None:
    api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())
    before = len(store.rows("audit_log"))

    second = api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())

    assert second.status_code == 200
    assert second.json()["status"] == state_machine.PUBLISHED
    assert len(store.rows("audit_log")) == before


@pytest.mark.parametrize(
    ("kwargs", "problem"),
    [
        ({"renditions": {"480p": GOOD_RENDITIONS["480p"]}}, "missing_rendition_720p"),
        ({"poster": None}, "missing_poster"),
        ({"duration": 90}, "duration_exceeded"),
        ({"duration": None}, "missing_duration"),
    ],
)
def test_an_admin_cannot_publish_malformed_media(
    api: TestClient, store: Store, kwargs: dict[str, Any], problem: str
) -> None:
    store.rows("video_clips")[:] = [_clip(CLIP_ID, **kwargs)]

    response = api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "clip_media_not_ready"
    assert problem in response.json()["error"]["details"]["problems"]
    assert store.clip()["status"] == state_machine.PENDING_REVIEW


def test_a_draft_cannot_be_approved(api: TestClient, store: Store) -> None:
    store.rows("video_clips")[0]["status"] = state_machine.DRAFT

    response = api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "clip_invalid_transition"


def test_two_concurrent_approvals_produce_exactly_one_winner(
    api: TestClient, store: Store
) -> None:
    barrier = threading.Barrier(4)
    results: list[int] = []

    def approve() -> None:
        barrier.wait()
        results.append(api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h()).status_code)

    threads = [threading.Thread(target=approve) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert store.clip()["status"] == state_machine.PUBLISHED
    # Losers are told (409) or see the already-published replay (200) — never a
    # silent overwrite, and never more than one publish transition.
    assert all(code in (200, 409) for code in results)
    transitions = [
        row
        for row in store.rows("audit_log")
        if row.get("action") == "clip.transition"
        and (row.get("after") or {}).get("status") == state_machine.PUBLISHED
    ]
    assert len(transitions) == 1


# --- Reject ------------------------------------------------------------------
def test_rejecting_requires_a_reason(api: TestClient) -> None:
    assert api.post(f"/admin/clips/{CLIP_ID}/reject", headers=_h(), json={}).status_code == 422
    assert (
        api.post(
            f"/admin/clips/{CLIP_ID}/reject", headers=_h(), json={"reason": ""}
        ).status_code
        == 422
    )


def test_rejecting_records_the_reason_for_the_vendor(api: TestClient, store: Store) -> None:
    response = api.post(
        f"/admin/clips/{CLIP_ID}/reject", headers=_h(), json={"reason": "blurry footage"}
    )

    assert response.status_code == 200
    assert store.clip()["status"] == state_machine.REJECTED
    assert store.clip()["rejection_reason"] == "blurry footage"


def test_rejecting_twice_is_a_no_op(api: TestClient, store: Store) -> None:
    api.post(f"/admin/clips/{CLIP_ID}/reject", headers=_h(), json={"reason": "no"})
    before = len(store.rows("audit_log"))

    second = api.post(f"/admin/clips/{CLIP_ID}/reject", headers=_h(), json={"reason": "no"})

    assert second.status_code == 200
    assert len(store.rows("audit_log")) == before


# --- Takedown ----------------------------------------------------------------
def test_a_taken_down_clip_disappears_from_the_public_feed_immediately(
    api: TestClient, store: Store
) -> None:
    api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())
    assert [c["id"] for c in api.get("/clips/feed").json()["items"]] == [CLIP_ID]

    api.post(f"/admin/clips/{CLIP_ID}/takedown", headers=_h(), json={"reason": "unsafe"})

    # Asked, not assumed: the very next read must not return it.
    assert api.get("/clips/feed").json()["items"] == []
    assert api.get(f"/clips/{CLIP_ID}").status_code == 404


def test_takedown_is_idempotent(api: TestClient, store: Store) -> None:
    api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())
    api.post(f"/admin/clips/{CLIP_ID}/takedown", headers=_h(), json={"reason": "unsafe"})

    second = api.post(
        f"/admin/clips/{CLIP_ID}/takedown", headers=_h(), json={"reason": "unsafe"}
    )

    assert second.status_code == 200
    assert second.json()["status"] == state_machine.TAKEN_DOWN


# --- Reports -----------------------------------------------------------------
def _seed_report(store: Store, *, report_id: str = "r1", age_hours: float = 1.0) -> None:
    store.rows("clip_reports").append(
        {
            "id": report_id,
            "clip_id": CLIP_ID,
            "reporter_id": "22222222-2222-4222-8222-222222222222",
            "reason": "misleading",
            "created_at": (datetime.now(UTC) - timedelta(hours=age_hours)).isoformat(),
        }
    )


def test_the_report_queue_flags_the_24h_slo(api: TestClient, store: Store) -> None:
    _seed_report(store, report_id="fresh", age_hours=2)
    _seed_report(store, report_id="stale", age_hours=30)

    items = api.get("/admin/clips/reports", headers=_h()).json()["items"]

    by_id = {item["report_id"]: item for item in items}
    assert by_id["stale"]["sla_breached"] is True
    assert by_id["fresh"]["sla_breached"] is False


def test_dismissing_a_report_leaves_the_clip_alone(api: TestClient, store: Store) -> None:
    api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())
    _seed_report(store)

    response = api.post("/admin/clips/reports/r1/dismiss", headers=_h(), json={})

    assert response.json()["outcome"] == "dismissed"
    assert store.clip()["status"] == state_machine.PUBLISHED
    assert store.rows("clip_reports") == []


def test_upholding_a_report_takes_the_clip_down(api: TestClient, store: Store) -> None:
    api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())
    _seed_report(store)

    response = api.post("/admin/clips/reports/r1/uphold", headers=_h(), json={"note": "unsafe"})

    assert response.json()["outcome"] == "upheld"
    assert store.clip()["status"] == state_machine.TAKEN_DOWN
    assert api.get("/clips/feed").json()["items"] == []


# --- Strike escalation -------------------------------------------------------
def test_three_takedowns_inside_the_window_suspend_the_vendor(
    api: TestClient, store: Store
) -> None:
    from app.routers.admin_clips import STRIKE_THRESHOLD

    # Two prior strikes already on the record.
    for index in range(STRIKE_THRESHOLD - 1):
        store.rows("video_clips").append(
            _clip(
                f"struck-{index}",
                status=state_machine.TAKEN_DOWN,
            )
            | {"taken_down_at": datetime.now(UTC).isoformat()}
        )
    # Another published clip that must disappear with the suspension.
    store.rows("video_clips").append(_clip("still-live", status=state_machine.PUBLISHED))

    api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())
    response = api.post(
        f"/admin/clips/{CLIP_ID}/takedown", headers=_h(), json={"reason": "third strike"}
    )

    assert response.json()["vendor_suspended"] is True
    assert store.rows("vendors")[0]["status"] == "suspended"
    # Suspension hides the vendor's remaining published clips too.
    still_live = next(row for row in store.rows("video_clips") if row["id"] == "still-live")
    assert still_live["status"] == state_machine.TAKEN_DOWN
    assert api.get("/clips/feed").json()["items"] == []


def test_two_takedowns_do_not_suspend(api: TestClient, store: Store) -> None:
    store.rows("video_clips").append(
        _clip("struck-0", status=state_machine.TAKEN_DOWN)
        | {"taken_down_at": datetime.now(UTC).isoformat()}
    )

    api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())
    response = api.post(
        f"/admin/clips/{CLIP_ID}/takedown", headers=_h(), json={"reason": "second"}
    )

    assert response.json()["vendor_suspended"] is False
    assert store.rows("vendors")[0]["status"] == "active"


def test_strikes_outside_the_window_do_not_count(api: TestClient, store: Store) -> None:
    from app.routers.admin_clips import STRIKE_WINDOW

    old = (datetime.now(UTC) - STRIKE_WINDOW - timedelta(days=1)).isoformat()
    for index in range(3):
        store.rows("video_clips").append(
            _clip(f"ancient-{index}", status=state_machine.TAKEN_DOWN) | {"taken_down_at": old}
        )

    api.post(f"/admin/clips/{CLIP_ID}/approve", headers=_h())
    response = api.post(
        f"/admin/clips/{CLIP_ID}/takedown", headers=_h(), json={"reason": "first recent"}
    )

    assert response.json()["vendor_suspended"] is False


# --- Registry ----------------------------------------------------------------
def test_every_admin_clip_action_has_a_rate_limit_policy() -> None:
    from app.core import ratelimit_policies as rp

    for route_id in (
        "POST /clips/{clip_id}/approve",
        "POST /clips/{clip_id}/reject",
        "POST /clips/{clip_id}/takedown",
        "POST /clips/reports/{report_id}/dismiss",
        "POST /clips/reports/{report_id}/uphold",
    ):
        assert route_id in rp.POLICIES
