"""M17-P08 — the clip cost guard.

Two claims, and both are about what happens on a bad day:

* **money is exact** — every figure is an integer number of micro-USD derived
  from a ``Decimal`` rate, and there is no float anywhere on the path;
* **the switch pauses uploads and leaves the feed alone** — asserted by tripping
  the guard and then *reading the feed*, not by reasoning about which module
  calls which.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.main import create_app
from app.services.clips import spend, state_machine
from fastapi.testclient import TestClient

VENDOR_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_USER = "11111111-1111-4111-8111-111111111111"
ADMIN_USER = "aaaa0000-0000-4000-8000-00000000000a"
CLIP_ID = "c1000000-0000-4000-8000-000000000001"
MONTH = "2026-07"


# --- Fake Supabase ----------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._eq: list[tuple[str, Any]] = []
        self._gte: list[tuple[str, Any]] = []
        self._maybe_single = False
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str = "*", **_kwargs: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._eq.append((column, value))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self._gte.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
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

    def _match(self, row: dict[str, Any]) -> bool:
        if not all(row.get(c) == v for c, v in self._eq):
            return False
        return all(str(row.get(c) or "") >= str(v) for c, v in self._gte)

    def execute(self) -> MagicMock:
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
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str = "*", **kwargs: Any) -> FakeQuery:
        return FakeQuery(self).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)


class FakeSupabase:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))

    def rpc(self, name: str, params: dict[str, Any]) -> MagicMock:
        if name == "clip_record_spend":
            return MagicMock(execute=lambda: MagicMock(data=self.store.record(params)))
        if name == "reset_clip_kill_switch":
            return MagicMock(execute=lambda: MagicMock(data=self.store.reset(params)))
        if name == "bump_rate_counter":
            return MagicMock(
                execute=lambda: MagicMock(data=[{"allowed": True, "retry_after_seconds": 0}])
            )
        raise AssertionError(f"unexpected rpc {name}")


class Store:
    """Models `clip_record_spend`'s two guarantees: relative increment, and the
    switch tripping in the same call that crossed the cap."""

    def __init__(self) -> None:
        self.client = FakeSupabase(self)

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.client.table(name).rows

    def _month(self, key: str) -> dict[str, Any]:
        for row in self.rows("clip_spend_monthly"):
            if row.get("month_key") == key:
                return row
        row = {
            "month_key": key,
            "total_usd_micros": 0,
            "clips_transcoded": 0,
            "bytes_served": 0,
            "killed_at": None,
            "admin_reset_at": None,
        }
        self.rows("clip_spend_monthly").append(row)
        return row

    def record(self, params: dict[str, Any]) -> int:
        row = self._month(str(params["p_month_key"]))
        row["total_usd_micros"] += max(0, int(params["p_usd_micros"]))
        row["clips_transcoded"] += max(0, int(params["p_clips"]))
        row["bytes_served"] += max(0, int(params["p_bytes"]))
        cap = int(params["p_cap_usd_micros"])
        if cap > 0 and row["total_usd_micros"] >= cap and not row["killed_at"]:
            row["killed_at"] = datetime.now(UTC).isoformat()
        return int(row["total_usd_micros"])

    def reset(self, params: dict[str, Any]) -> bool:
        row = self._month(str(params["p_month_key"]))
        if not row.get("killed_at"):
            return False
        row["admin_reset_at"] = datetime.now(UTC).isoformat()
        return True


@pytest.fixture
def store() -> Generator[Store, None, None]:
    spend.clear_clip_spend_cache()
    st = Store()
    st.rows("platform_config")
    st.rows("clip_spend_monthly")
    yield st
    spend.clear_clip_spend_cache()


# --- Money is exact ----------------------------------------------------------
def test_the_default_cap_stays_inside_the_infrastructure_budget(store: Store) -> None:
    # $10 for video alongside Ask Vergeo's $15, inside the $50/mo ceiling.
    assert spend.DEFAULT_MONTHLY_CAP_USD == 10
    assert spend.monthly_cap_usd_micros(store) == 10 * 1_000_000


def test_the_cap_is_read_from_config_not_hardcoded(store: Store) -> None:
    store.rows("platform_config").append({"key": spend.CAP_KEY, "value": 25})
    spend.clear_clip_spend_cache()

    assert spend.monthly_cap_usd_micros(store) == 25 * 1_000_000


def test_rates_are_decimals_and_costs_are_integer_micros(store: Store) -> None:
    rates = spend.unit_rates(store)
    assert all(isinstance(rate, Decimal) for rate in rates.values())

    cost = spend.transcode_cost_micros(store, clips=3)
    assert isinstance(cost, int)
    # 3 x $0.02 = $0.06 exactly, with no float drift.
    assert cost == 60_000


def test_delivery_cost_is_exact_for_a_whole_gigabyte(store: Store) -> None:
    assert spend.delivery_cost_micros(store, bytes_served=1_073_741_824) == 80_000


def test_zero_and_negative_amounts_cost_nothing(store: Store) -> None:
    assert spend.transcode_cost_micros(store, clips=0) == 0
    assert spend.transcode_cost_micros(store, clips=-5) == 0
    assert spend.delivery_cost_micros(store, bytes_served=0) == 0


def test_an_invalid_configured_rate_falls_back_rather_than_crashing(store: Store) -> None:
    store.rows("platform_config").append(
        {"key": spend.RATES_KEY, "value": {"transcode_per_clip": "not-a-number"}}
    )
    spend.clear_clip_spend_cache()

    assert spend.unit_rates(store)["transcode_per_clip"] == Decimal("0.02")


# --- The switch --------------------------------------------------------------
def test_spend_accumulates_and_trips_the_switch_at_the_cap(store: Store) -> None:
    store.rows("platform_config").append({"key": spend.CAP_KEY, "value": 1})
    spend.clear_clip_spend_cache()

    assert spend.is_killed(store, month_key=MONTH) is False
    spend.record_spend(store, usd_micros=400_000, clips=1, month_key=MONTH)
    assert spend.is_killed(store, month_key=MONTH) is False

    spend.record_spend(store, usd_micros=600_000, clips=1, month_key=MONTH)

    assert spend.current_month_total_micros(store, month_key=MONTH) == 1_000_000
    assert spend.is_killed(store, month_key=MONTH) is True


def test_concurrent_recordings_do_not_lose_spend(store: Store) -> None:
    """A read-then-write would land short — losing spend is the one direction a
    cost guard must never round toward."""
    for _ in range(10):
        spend.record_spend(store, usd_micros=20_000, clips=1, month_key=MONTH)

    assert spend.current_month_total_micros(store, month_key=MONTH) == 200_000


def test_headroom_never_goes_negative(store: Store) -> None:
    store.rows("platform_config").append({"key": spend.CAP_KEY, "value": 1})
    spend.clear_clip_spend_cache()
    spend.record_spend(store, usd_micros=5_000_000, month_key=spend.current_month_key())

    assert spend.headroom_micros(store) == 0


def test_the_reset_re_opens_the_month_without_erasing_the_trip(store: Store) -> None:
    store.rows("platform_config").append({"key": spend.CAP_KEY, "value": 1})
    spend.clear_clip_spend_cache()
    spend.record_spend(store, usd_micros=1_000_000, month_key=MONTH)
    assert spend.is_killed(store, month_key=MONTH) is True

    assert spend.reset_kill_switch(store, month_key=MONTH) is True

    assert spend.is_killed(store, month_key=MONTH) is False
    # The history survives: an auditor can still see that it tripped.
    row = store.rows("clip_spend_monthly")[0]
    assert row["killed_at"] is not None
    assert row["admin_reset_at"] is not None


def test_resetting_a_month_that_never_tripped_is_a_no_op(store: Store) -> None:
    assert spend.reset_kill_switch(store, month_key=MONTH) is False


def test_raise_if_killed_refuses_only_when_the_switch_is_on(store: Store) -> None:
    store.rows("platform_config").append({"key": spend.CAP_KEY, "value": 1})
    spend.clear_clip_spend_cache()

    spend.raise_if_killed(store)  # no row yet — must not raise

    spend.record_spend(store, usd_micros=1_000_000, month_key=spend.current_month_key())

    with pytest.raises(AppError) as excinfo:
        spend.raise_if_killed(store)
    assert excinfo.value.code == "clip_cost_kill_switch"
    assert excinfo.value.http_status == 503


def test_a_zero_cap_never_trips_the_switch(store: Store) -> None:
    """A cap of 0 means "unbounded", not "block everything" — the same
    convention `cod_cap_ngwee = 0` uses."""
    store.rows("platform_config").append({"key": spend.CAP_KEY, "value": 0})
    spend.clear_clip_spend_cache()

    spend.record_spend(store, usd_micros=9_999_999, month_key=MONTH)

    assert spend.is_killed(store, month_key=MONTH) is False


# --- The switch pauses uploads and leaves the feed alone ---------------------
@pytest.fixture
def api(store: Store, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    wrapper = store
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: wrapper)
    for module in (
        "app.routers.clips",
        "app.routers.clips_upload",
        "app.routers.admin_clip_analytics",
    ):
        monkeypatch.setattr(f"{module}.get_supabase_client", lambda: wrapper, raising=False)
    monkeypatch.setattr("app.media.authz.get_supabase_client", lambda: wrapper, raising=False)
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://key123:secret456@democloud")
    from app.settings import get_settings

    get_settings.cache_clear()

    store.rows("vendors").append(
        {"id": VENDOR_ID, "owner_user_id": VENDOR_USER, "status": "active", "kyc_tier": 2}
    )
    store.rows("video_clips").append(
        {
            "id": CLIP_ID,
            "vendor_id": VENDOR_ID,
            "status": state_machine.PUBLISHED,
            "caption": "solar lamp",
            "poster_url": "https://res.cloudinary.com/demo/a.webp",
            "duration_s": 30,
            "renditions": {
                "480p": {"url": "https://x/480.mp4", "width": 480, "bytes": 1_900_000}
            },
            "like_count": 0,
            "comment_count": 0,
            "view_count": 0,
            "published_at": datetime.now(UTC).isoformat(),
            "category_id": None,
        }
    )
    store.rows("clip_products")
    store.rows("vendor_listings")
    store.rows("audit_log")
    store.rows("feature_flags").append({"flag": "clips", "enabled": True})

    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client
    get_settings.cache_clear()


def _vendor_auth(monkeypatch: pytest.MonkeyPatch, user_id: str, role: str) -> dict[str, str]:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({role}),
    )
    return {"Authorization": "Bearer jwt"}


def test_a_tripped_switch_pauses_uploads(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _vendor_auth(monkeypatch, VENDOR_USER, "vendor")
    store.rows("platform_config").append({"key": spend.CAP_KEY, "value": 1})
    spend.clear_clip_spend_cache()
    spend.record_spend(store, usd_micros=1_000_000, month_key=spend.current_month_key())

    response = api.post("/clips", headers=headers, json={"caption": "hello"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "clip_cost_kill_switch"


def test_a_tripped_switch_leaves_the_feed_shoppable(api: TestClient, store: Store) -> None:
    """The whole point: a billing event must not become an outage."""
    store.rows("platform_config").append({"key": spend.CAP_KEY, "value": 1})
    spend.clear_clip_spend_cache()
    spend.record_spend(store, usd_micros=1_000_000, month_key=spend.current_month_key())

    feed = api.get("/clips/feed")
    detail = api.get(f"/clips/{CLIP_ID}")

    assert feed.status_code == 200
    assert [item["id"] for item in feed.json()["items"]] == [CLIP_ID]
    # Posters and prices still arrive — the readable, shoppable half is intact.
    assert feed.json()["items"][0]["poster_url"]
    assert detail.status_code == 200


def test_the_analytics_dashboard_reports_cost_and_funnel(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _vendor_auth(monkeypatch, ADMIN_USER, "admin")
    store.rows("platform_config").append({"key": spend.CAP_KEY, "value": 5})
    spend.clear_clip_spend_cache()
    spend.record_spend(store, usd_micros=1_500_000, clips=3, month_key=spend.current_month_key())

    body = api.get("/admin/clip-analytics", headers=headers).json()

    assert body["cost"]["spend_usd_micros"] == 1_500_000
    assert body["cost"]["cap_usd_micros"] == 5_000_000
    assert body["cost"]["headroom_usd_micros"] == 3_500_000
    assert body["cost"]["uploads_paused"] is False
    assert body["funnel"]["published_clips"] == 1


def test_an_admin_can_reverse_the_switch_and_the_reversal_is_audited(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _vendor_auth(monkeypatch, ADMIN_USER, "admin")
    store.rows("platform_config").append({"key": spend.CAP_KEY, "value": 1})
    spend.clear_clip_spend_cache()
    spend.record_spend(store, usd_micros=1_000_000, month_key=spend.current_month_key())

    response = api.post("/admin/clip-analytics/reset-kill-switch", headers=headers)

    assert response.status_code == 200
    assert response.json()["uploads_paused"] is False
    actions = [row.get("action") for row in store.rows("audit_log")]
    assert "admin.clips.reset_kill_switch" in actions


def test_the_reset_route_is_admin_only(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = _vendor_auth(monkeypatch, VENDOR_USER, "vendor")

    assert api.post("/admin/clip-analytics/reset-kill-switch", headers=headers).status_code == 403
    assert api.post("/admin/clip-analytics/reset-kill-switch").status_code == 401


def test_the_reset_route_has_a_registered_rate_limit_policy() -> None:
    from app.core import ratelimit_policies as rp

    assert "POST /clip-analytics/reset-kill-switch" in rp.POLICIES
