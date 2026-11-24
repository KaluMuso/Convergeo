"""Clips pilot allowlist — uploads and viewing limited to allowlisted vendors.

What must hold while ``clips`` is ON and the pilot gate is enforced:

* a vendor outside the allowlist cannot mint an upload slot (no draft row, no
  signature, so no transcode credit);
* the public feed, clip detail, ranking explain and engagement serve only
  allowlisted vendors' published clips;
* comments stay off even if ``clips_comments`` is flipped;
* the gate fails closed: missing config, malformed config and an unreadable
  allowlist all mean "enforced, nobody allowlisted";
* the weekly cap and the cost guard keep working, and a tripped guard still
  leaves the (pilot) feed shoppable;
* the admin control is admin-only, validated, idempotent and audited.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.main import create_app
from app.services.clips import pilot, quota, spend, state_machine
from fastapi.testclient import TestClient

PILOT_VENDOR = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PILOT_OWNER = "11111111-1111-4111-8111-111111111111"
OTHER_VENDOR = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OTHER_OWNER = "22222222-2222-4222-8222-222222222222"
ADMIN_USER = "aaaa0000-0000-4000-8000-00000000000a"
PILOT_CLIP = "c1000000-0000-4000-8000-000000000001"
OTHER_CLIP = "c2000000-0000-4000-8000-000000000002"


# --- Fake Supabase ----------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._eq: list[tuple[str, Any]] = []
        self._in: list[tuple[str, set[str]]] = []
        self._gte: list[tuple[str, Any]] = []
        self._maybe_single = False
        self._limit: int | None = None
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, *_a: Any, **_k: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._eq.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in.append((column, {str(v) for v in values}))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self._gte.append((column, value))
        return self

    def lt(self, *_a: Any) -> FakeQuery:
        return self

    def order(self, *_a: Any, **_k: Any) -> FakeQuery:
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._op, self._payload = "update", payload
        return self

    def delete(self) -> FakeQuery:
        self._op = "delete"
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        if not all(row.get(c) == v for c, v in self._eq):
            return False
        if not all(str(row.get(c)) in vs for c, vs in self._in):
            return False
        return all(str(row.get(c) or "") >= str(v) for c, v in self._gte)

    def execute(self) -> MagicMock:
        table = self._parent
        if table.broken:
            raise RuntimeError(f"{table.name} unreadable")
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            row.setdefault("id", f"{table.name}-{len(table.rows)}")
            row.setdefault("created_at", datetime.now(UTC).isoformat())
            table.rows.append(row)
            return MagicMock(data=[dict(row)])
        if self._op == "update":
            assert self._payload is not None
            out = []
            for row in table.rows:
                if self._match(row):
                    row.update(self._payload)
                    out.append(dict(row))
            return MagicMock(data=out)
        if self._op == "delete":
            gone = [r for r in table.rows if self._match(r)]
            table.rows[:] = [r for r in table.rows if not self._match(r)]
            return MagicMock(data=gone)
        rows = [dict(r) for r in table.rows if self._match(r)]
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []
        self.broken = False

    def select(self, *a: Any, **k: Any) -> FakeQuery:
        return FakeQuery(self).select(*a, **k)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)

    def delete(self) -> FakeQuery:
        return FakeQuery(self).delete()


class Store:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}
        self.client = self

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.table(name).rows

    def rpc(self, name: str, params: dict[str, Any]) -> MagicMock:
        if name == "clip_record_spend":
            row = next(
                (
                    r
                    for r in self.rows("clip_spend_monthly")
                    if r["month_key"] == params["p_month_key"]
                ),
                None,
            )
            if row is None:
                row = {
                    "month_key": params["p_month_key"],
                    "total_usd_micros": 0,
                    "killed_at": None,
                    "admin_reset_at": None,
                }
                self.rows("clip_spend_monthly").append(row)
            row["total_usd_micros"] += int(params["p_usd_micros"])
            cap = int(params["p_cap_usd_micros"])
            if cap > 0 and row["total_usd_micros"] >= cap and not row["killed_at"]:
                row["killed_at"] = datetime.now(UTC).isoformat()
            total = row["total_usd_micros"]
            return MagicMock(execute=lambda: MagicMock(data=total))
        if name == "bump_rate_counter":
            return MagicMock(
                execute=lambda: MagicMock(data=[{"allowed": True, "retry_after_seconds": 0}])
            )
        if name == "clip_bump_counter":
            return MagicMock(execute=lambda: MagicMock(data=1))
        raise AssertionError(f"unexpected rpc {name}")


def _clip(clip_id: str, vendor_id: str) -> dict[str, Any]:
    return {
        "id": clip_id,
        "vendor_id": vendor_id,
        "status": state_machine.PUBLISHED,
        "caption": "solar lamp",
        "poster_url": "https://res.cloudinary.com/demo/a.webp",
        "duration_s": 30,
        "renditions": {"480p": {"url": "https://x/480.mp4", "width": 480, "bytes": 1_900_000}},
        "like_count": 0,
        "comment_count": 0,
        "view_count": 0,
        "published_at": datetime.now(UTC).isoformat(),
        "created_at": datetime.now(UTC).isoformat(),
        "category_id": None,
    }


@pytest.fixture
def store() -> Generator[Store, None, None]:
    spend.clear_clip_spend_cache()
    st = Store()
    st.rows("vendors").extend(
        [
            {
                "id": PILOT_VENDOR,
                "owner_user_id": PILOT_OWNER,
                "status": "active",
                "kyc_tier": 1,
                "display_name": "Pilot Shop",
            },
            {
                "id": OTHER_VENDOR,
                "owner_user_id": OTHER_OWNER,
                "status": "active",
                "kyc_tier": 1,
                "display_name": "Other Shop",
            },
        ]
    )
    st.rows("video_clips").extend(
        [_clip(PILOT_CLIP, PILOT_VENDOR), _clip(OTHER_CLIP, OTHER_VENDOR)]
    )
    st.rows("feature_flags").append({"flag": "clips", "enabled": True})
    # The pilot as it would be configured: enforced row present, one vendor in.
    st.rows("platform_config").append({"key": pilot.ENFORCED_KEY, "value": True})
    st.rows("clip_pilot_vendors").append(
        {"vendor_id": PILOT_VENDOR, "note": "anchor", "added_by": ADMIN_USER}
    )
    for name in (
        "clip_products",
        "vendor_listings",
        "audit_log",
        "clip_likes",
        "clip_views",
        "clip_reports",
        "clip_comments",
        "clip_spend_monthly",
    ):
        st.rows(name)
    yield st
    spend.clear_clip_spend_cache()


@pytest.fixture
def api(store: Store, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: store)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: store)
    for module in (
        "app.routers.clips",
        "app.routers.clips_upload",
        "app.routers.clips_engagement",
        "app.routers.admin_clip_pilot",
    ):
        monkeypatch.setattr(f"{module}.get_supabase_client", lambda: store, raising=False)
    monkeypatch.setattr("app.media.authz.get_supabase_client", lambda: store, raising=False)
    monkeypatch.setattr("app.services.analytics.events.record_event", lambda **kwargs: None)
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://key123:secret456@democloud")
    from app.settings import get_settings

    get_settings.cache_clear()
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client
    get_settings.cache_clear()


def _auth(monkeypatch: pytest.MonkeyPatch, user_id: str, role: str) -> dict[str, str]:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles", lambda user_id, service_client: frozenset({role})
    )
    return {"Authorization": "Bearer jwt"}


# --- Fail-closed gate --------------------------------------------------------
def test_a_missing_enforcement_row_means_enforced(store: Store) -> None:
    store.rows("platform_config").clear()
    assert pilot.allowlist_enforced(store) is True


@pytest.mark.parametrize("value", ["false", 0, None, "no", {"enabled": False}, "garbage{"])
def test_only_a_json_false_ends_the_pilot(store: Store, value: Any) -> None:
    store.rows("platform_config")[0]["value"] = value
    expected = value == "false"  # a JSON-encoded string "false" decodes to False
    assert pilot.allowlist_enforced(store) is (not expected)


def test_an_explicit_false_ends_the_pilot(store: Store) -> None:
    store.rows("platform_config")[0]["value"] = False
    assert pilot.allowlist_enforced(store) is False
    assert pilot.vendor_in_pilot(store, OTHER_VENDOR) is True


def test_an_unreadable_config_means_enforced(store: Store) -> None:
    store.table("platform_config").broken = True
    assert pilot.allowlist_enforced(store) is True


def test_an_unreadable_allowlist_means_nobody(store: Store) -> None:
    store.table("clip_pilot_vendors").broken = True
    assert pilot.vendor_in_pilot(store, PILOT_VENDOR) is False


def test_an_empty_vendor_id_is_never_in_the_pilot(store: Store) -> None:
    assert pilot.vendor_in_pilot(store, "") is False


# --- Uploads -----------------------------------------------------------------
def test_a_pilot_vendor_gets_an_upload_slot(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(monkeypatch, PILOT_OWNER, "vendor")
    response = api.post("/clips", headers=headers, json={"caption": "new lamp"})
    assert response.status_code == 200, response.text
    assert response.json()["signature"]


def test_a_non_pilot_vendor_is_refused_before_anything_is_created(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(monkeypatch, OTHER_OWNER, "vendor")
    before = len(store.rows("video_clips"))

    response = api.post("/clips", headers=headers, json={"caption": "new lamp"})

    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "clip_pilot_not_allowlisted"
    assert body["details"]["message_key"] == "vendor.clips.errors.notInPilot"
    assert len(store.rows("video_clips")) == before


def test_an_unreadable_allowlist_refuses_uploads(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(monkeypatch, PILOT_OWNER, "vendor")
    store.table("clip_pilot_vendors").broken = True
    assert api.post("/clips", headers=headers, json={"caption": "x"}).status_code == 403


def test_the_flag_still_comes_first(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(monkeypatch, PILOT_OWNER, "vendor")
    store.rows("feature_flags")[0]["enabled"] = False
    assert api.post("/clips", headers=headers, json={"caption": "x"}).status_code == 404
    assert api.get("/clips/feed").status_code == 404


def test_the_weekly_cap_still_applies_to_pilot_vendors(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(monkeypatch, PILOT_OWNER, "vendor")
    store.rows("platform_config").append(
        {"key": quota.WEEKLY_CAP_KEY, "value": {"1": 1, "2": 1, "3": 1}}
    )
    # PILOT_CLIP was created "now", so tier 1's allowance of 1 is already used.
    response = api.post("/clips", headers=headers, json={"caption": "x"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "clip_cap_exceeded"


def test_zero_weekly_caps_pause_uploads_without_touching_the_feed(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deploy-free emergency upload pause documented in the enablement doc."""
    headers = _auth(monkeypatch, PILOT_OWNER, "vendor")
    store.rows("platform_config").append(
        {"key": quota.WEEKLY_CAP_KEY, "value": {"1": 0, "2": 0, "3": 0}}
    )
    store.rows("video_clips")[:] = [
        {
            **c,
            "published_at": "2026-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        for c in store.rows("video_clips")
    ]
    assert api.post("/clips", headers=headers, json={"caption": "x"}).status_code == 403
    assert [i["id"] for i in api.get("/clips/feed").json()["items"]] == [PILOT_CLIP]


def test_an_unreadable_clip_count_refuses_the_upload(store: Store) -> None:
    """The weekly cap fails closed: if usage cannot be counted, no slot."""
    store.table("video_clips").broken = True
    with pytest.raises(RuntimeError):
        quota.enforce_clip_weekly_cap(store, vendor_id=PILOT_VENDOR, tier=1)


def test_a_tripped_cost_guard_pauses_pilot_uploads_and_keeps_the_feed(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(monkeypatch, PILOT_OWNER, "vendor")
    store.rows("platform_config").append({"key": spend.CAP_KEY, "value": 1})
    spend.clear_clip_spend_cache()
    spend.record_spend(store, usd_micros=1_000_000, month_key=spend.current_month_key())

    upload = api.post("/clips", headers=headers, json={"caption": "x"})
    feed = api.get("/clips/feed")

    assert upload.status_code == 503
    assert upload.json()["error"]["code"] == "clip_cost_kill_switch"
    assert feed.status_code == 200
    assert [i["id"] for i in feed.json()["items"]] == [PILOT_CLIP]
    assert feed.json()["items"][0]["poster_url"]


# --- Viewing -----------------------------------------------------------------
def test_the_feed_serves_only_pilot_vendors(api: TestClient) -> None:
    items = api.get("/clips/feed").json()["items"]
    assert [i["id"] for i in items] == [PILOT_CLIP]


def test_a_non_pilot_clip_is_404_on_detail_ranking_and_engagement(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert api.get(f"/clips/{OTHER_CLIP}").status_code == 404
    assert api.get(f"/clips/{OTHER_CLIP}/ranking").status_code == 404
    headers = _auth(monkeypatch, PILOT_OWNER, "customer")
    assert api.post(f"/clips/{OTHER_CLIP}/like", headers=headers).status_code == 404
    assert api.get(f"/clips/{PILOT_CLIP}").status_code == 200


def test_removing_a_vendor_hides_their_clips_immediately(api: TestClient, store: Store) -> None:
    store.rows("clip_pilot_vendors").clear()
    assert api.get("/clips/feed").json()["items"] == []
    assert api.get(f"/clips/{PILOT_CLIP}").status_code == 404
    # Nothing was unpublished — re-adding restores the clip as it was.
    assert store.rows("video_clips")[0]["status"] == state_machine.PUBLISHED


def test_ending_the_pilot_shows_every_active_vendor(api: TestClient, store: Store) -> None:
    store.rows("platform_config")[0]["value"] = False
    ids = sorted(i["id"] for i in api.get("/clips/feed").json()["items"])
    assert ids == sorted([PILOT_CLIP, OTHER_CLIP])


def test_comments_stay_off_during_the_pilot_even_if_flagged_on(
    api: TestClient, store: Store
) -> None:
    store.rows("feature_flags").append({"flag": "clips_comments", "enabled": True})
    assert api.get(f"/clips/{PILOT_CLIP}/comments").status_code == 404
    assert pilot.comments_allowed(store, True) is False
    store.rows("platform_config")[0]["value"] = False
    assert pilot.comments_allowed(store, True) is True
    assert pilot.comments_allowed(store, False) is False


# --- Admin control -----------------------------------------------------------
def test_admin_sees_the_gate_and_the_allowlist(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(monkeypatch, ADMIN_USER, "admin")
    body = api.get("/admin/clip-pilot", headers=headers).json()
    assert body["clips_enabled"] is True
    assert body["comments_flag_enabled"] is False
    assert body["allowlist_enforced"] is True
    assert [v["vendor_id"] for v in body["vendors"]] == [PILOT_VENDOR]
    assert body["vendors"][0]["vendor_name"] == "Pilot Shop"


def test_admin_add_is_audited_and_idempotent(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(monkeypatch, ADMIN_USER, "admin")

    first = api.post(
        "/admin/clip-pilot/vendors", headers=headers, json={"vendor_id": OTHER_VENDOR, "note": "x"}
    )
    second = api.post(
        "/admin/clip-pilot/vendors", headers=headers, json={"vendor_id": OTHER_VENDOR}
    )

    assert first.status_code == 200 and first.json()["changed"] is True
    assert second.status_code == 200 and second.json()["changed"] is False
    assert len([r for r in store.rows("clip_pilot_vendors") if r["vendor_id"] == OTHER_VENDOR]) == 1
    added = [r for r in store.rows("audit_log") if r.get("action") == "admin.clips.pilot_add"]
    assert len(added) == 1
    assert added[0].get("actor") == ADMIN_USER
    # And the new vendor is now live in the feed.
    assert len(api.get("/clips/feed").json()["items"]) == 2


def test_admin_remove_is_audited_and_idempotent(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(monkeypatch, ADMIN_USER, "admin")
    first = api.delete(f"/admin/clip-pilot/vendors/{PILOT_VENDOR}", headers=headers)
    second = api.delete(f"/admin/clip-pilot/vendors/{PILOT_VENDOR}", headers=headers)
    assert first.json()["changed"] is True
    assert second.json()["changed"] is False
    assert store.rows("clip_pilot_vendors") == []
    removed = [r for r in store.rows("audit_log") if r.get("action") == "admin.clips.pilot_remove"]
    assert len(removed) == 1


def test_admin_add_validates_the_vendor(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(monkeypatch, ADMIN_USER, "admin")
    missing = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    assert (
        api.post(
            "/admin/clip-pilot/vendors", headers=headers, json={"vendor_id": missing}
        ).status_code
        == 404
    )
    assert (
        api.post(
            "/admin/clip-pilot/vendors", headers=headers, json={"vendor_id": "not-a-uuid" * 4}
        ).status_code
        == 422
    )
    store.rows("vendors")[1]["status"] = "suspended"
    refused = api.post(
        "/admin/clip-pilot/vendors", headers=headers, json={"vendor_id": OTHER_VENDOR}
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "vendor_not_active"
    assert store.rows("audit_log") == []


def test_the_pilot_routes_are_admin_only(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert api.get("/admin/clip-pilot").status_code == 401
    headers = _auth(monkeypatch, PILOT_OWNER, "vendor")
    assert api.get("/admin/clip-pilot", headers=headers).status_code == 403
    assert (
        api.post(
            "/admin/clip-pilot/vendors", headers=headers, json={"vendor_id": OTHER_VENDOR}
        ).status_code
        == 403
    )
    assert (
        api.delete(f"/admin/clip-pilot/vendors/{PILOT_VENDOR}", headers=headers).status_code == 403
    )


def test_the_pilot_write_routes_have_rate_limit_policies() -> None:
    from app.core import ratelimit_policies as rp

    assert "POST /clip-pilot/vendors" in rp.POLICIES
    assert "DELETE /clip-pilot/vendors/{vendor_id}" in rp.POLICIES


def test_the_require_helper_raises_an_actionable_error(store: Store) -> None:
    with pytest.raises(AppError) as excinfo:
        pilot.require_vendor_in_pilot(store, OTHER_VENDOR)
    assert excinfo.value.http_status == 403
    pilot.require_vendor_in_pilot(store, PILOT_VENDOR)
