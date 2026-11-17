"""Event collaboration API: authz, checklist validation, guarded state machine."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.events.collaboration import (
    Checklist,
    EventDraft,
    assert_transition_allowed,
    readiness_pct,
    submit_field_errors,
)
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

PROPOSER_USER = "11111111-1111-1111-1111-111111111111"
ORGANISER_USER = "22222222-2222-2222-2222-222222222222"
OTHER_USER = "33333333-3333-3333-3333-333333333333"
PROPOSER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORGANISER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
OTHER = "cccccccc-cccc-cccc-cccc-cccccccccccc"
TOKENS = {"tp": PROPOSER_USER, "to": ORGANISER_USER, "tx": OTHER_USER}
BASE = "/vendor/event-collaboration"


class FakeQuery:
    def __init__(self, table: list[dict[str, Any]]) -> None:
        self.table = table
        self.filters: list[tuple[str, str, Any]] = []
        self.op = "select"
        self.payload: dict[str, Any] = {}
        self.single = False
        self.order_by: tuple[str, bool] | None = None
        self.max_rows: int | None = None

    def select(self, _c: str, **_k: Any) -> FakeQuery:
        return self

    def eq(self, c: str, v: Any) -> FakeQuery:
        self.filters.append(("eq", c, v))
        return self

    def in_(self, c: str, v: list[Any]) -> FakeQuery:
        self.filters.append(("in", c, v))
        return self

    def order(self, c: str, *, desc: bool = False) -> FakeQuery:
        self.order_by = (c, desc)
        return self

    def limit(self, n: int) -> FakeQuery:
        self.max_rows = n
        return self

    def maybe_single(self) -> FakeQuery:
        self.single = True
        return self

    def insert(self, p: dict[str, Any]) -> FakeQuery:
        self.op, self.payload = "insert", p
        return self

    def update(self, p: dict[str, Any]) -> FakeQuery:
        self.op, self.payload = "update", p
        return self

    def upsert(self, p: dict[str, Any], **_k: Any) -> FakeQuery:
        self.op, self.payload = "upsert", p
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for op, c, v in self.filters:
            if op == "eq" and row.get(c) != v:
                return False
            if op == "in" and row.get(c) not in v:
                return False
        return True

    def execute(self) -> MagicMock:
        if self.op == "insert":
            row = {"id": f"e0000000-0000-0000-0000-{len(self.table):012d}", **self.payload}
            row.setdefault("status", "draft")
            row.setdefault("organiser_note", None)
            self.table.append(row)
            return MagicMock(data=[dict(row)])
        if self.op == "upsert":
            for row in self.table:
                if row.get("vendor_id") == self.payload.get("vendor_id"):
                    row.update(self.payload)
                    return MagicMock(data=[dict(row)])
            self.table.append(dict(self.payload))
            return MagicMock(data=[dict(self.payload)])
        if self.op == "update":
            hit = [r for r in self.table if self._match(r)]
            for row in hit:
                row.update(self.payload)
            return MagicMock(data=[dict(r) for r in hit])
        rows = [dict(r) for r in self.table if self._match(r)]
        if self.order_by:
            col, desc = self.order_by
            rows.sort(key=lambda r: str(r.get(col, "")), reverse=desc)
        if self.max_rows is not None:
            rows = rows[: self.max_rows]
        if self.single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeClient:
    """Fake Supabase client; ``rpc`` independently emulates the SQL state machine."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.tables.setdefault(name, []))

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        client = self

        class _Call:
            def execute(self) -> MagicMock:
                return client._rpc(name, params)

        return _Call()

    def _err(self, code: str, msg: str) -> APIError:
        return APIError({"message": msg, "code": code, "hint": None, "details": None})

    def _rpc(self, name: str, p: dict[str, Any]) -> MagicMock:
        if name == "event_collab_record_create":
            self.tables.setdefault("event_collab_audit", []).append(
                {
                    "request_id": p["p_request_id"],
                    "action": "create",
                    "actor_role": "proposer",
                    "from_status": None,
                    "to_status": "draft",
                    "reason": None,
                    "created_at": "t",
                }
            )
            return MagicMock(data=None)
        assert name == "event_collab_transition"
        req = next(r for r in self.tables["event_collab_requests"] if r["id"] == p["p_request_id"])
        owners = {v["id"]: v["owner_user_id"] for v in self.tables["vendors"]}
        actor = p["p_actor_user_id"]
        if actor == owners[req["organiser_vendor_id"]]:
            role = "organiser"
        elif actor == owners[req["proposer_vendor_id"]]:
            role = "proposer"
        else:
            raise self._err("42501", "not a party")
        action = p["p_action"]
        table = {
            "submit": ("proposer", {"draft", "changes_requested"}, "submitted"),
            "approve": ("organiser", {"submitted"}, "approved"),
            "decline": ("organiser", {"submitted"}, "declined"),
            "request_changes": ("organiser", {"submitted"}, "changes_requested"),
            "publish": ("organiser", {"approved"}, "published"),
        }[action]
        if role != table[0]:
            raise self._err("42501", "wrong role")
        if req["status"] not in table[1]:
            raise self._err("55000", "bad state")
        if action in ("decline", "request_changes") and len(p.get("p_reason") or "") < 3:
            raise self._err("22023", "reason")
        frm = req["status"]
        req["status"] = table[2]
        if action == "publish":
            event = {
                "id": f"ev-{len(self.tables.setdefault('events', []))}",
                "organiser_vendor_id": req["organiser_vendor_id"],
                "slug": p["p_event_slug"],
                "title": req["event_draft"]["title"],
                "status": "published",
            }
            self.tables["events"].append(event)
            req["event_id"] = event["id"]
        if p.get("p_reason"):
            req["organiser_note"] = p["p_reason"]
        self.tables.setdefault("event_collab_audit", []).append(
            {
                "request_id": req["id"],
                "action": action,
                "actor_role": role,
                "from_status": frm,
                "to_status": req["status"],
                "reason": p.get("p_reason"),
                "created_at": "t",
            }
        )
        return MagicMock(data=[dict(req)])


def _future(hours: int = 72) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def full_checklist(**over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "venue": {"name": "Hall", "landmark": "Near the mall", "lat": -15.4, "lng": 28.3},
        "schedule": {"starts_at": _future(), "ends_at": _future(76)},
        "capacity": {"capacity": 200},
        "equipment": {
            "sound": "ready",
            "stage": "needed",
            "power": "ready",
            "seating": "not_needed",
            "security": "ready",
        },
        "permits": {"status": "pending"},
        "tiers": [{"name": "General", "price_ngwee": 5000, "qty_cap": 150}],
    }
    data.update(over)
    return data


DRAFT = {"title": "Collab night", "category": "music", "city": "Lusaka"}


@pytest.fixture
def fake() -> FakeClient:
    c = FakeClient()
    c.tables["vendors"] = [
        {
            "id": PROPOSER,
            "owner_user_id": PROPOSER_USER,
            "status": "active",
            "kyc_tier": None,
            "slug": "prop",
            "display_name": "Proposer Shop",
            "preferred_badge": False,
        },
        {
            "id": ORGANISER,
            "owner_user_id": ORGANISER_USER,
            "status": "active",
            "kyc_tier": 2,
            "slug": "org",
            "display_name": "Big Events",
            "preferred_badge": False,
        },
        {
            "id": OTHER,
            "owner_user_id": OTHER_USER,
            "status": "active",
            "kyc_tier": None,
            "slug": "other",
            "display_name": "Other Shop",
            "preferred_badge": False,
        },
    ]
    c.tables["kyc_records"] = [
        {"id": "k1", "vendor_id": ORGANISER, "tier": 2, "status": "approved"}
    ]
    c.tables["feature_flags"] = [{"flag": "events_collaboration", "enabled": True}]
    c.tables["event_collab_organiser_prefs"] = [
        {"vendor_id": ORGANISER, "accepts_requests": True, "blurb": "We do concerts"}
    ]
    return c


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch, fake: FakeClient) -> Generator[TestClient, None, None]:
    def verify(token: str, settings: Any) -> dict[str, Any]:
        _ = settings
        if token in TOKENS:
            return {"sub": TOKENS[token], "exp": 9_999_999_999}
        raise ValueError("bad token")

    monkeypatch.setattr("app.core.auth.verify_supabase_jwt", verify)
    monkeypatch.setattr("app.core.auth._load_user_roles", lambda _u, _c: frozenset({"vendor"}))
    wrapper = MagicMock()
    wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.event_collaboration.bump_rate_counter", lambda **_k: (True, 0))
    monkeypatch.setattr(
        "app.services.events.high_value.run_sql_script", lambda _s: MagicMock(ok=False, rows=[])
    )
    monkeypatch.setattr("app.services.events.high_value.count_upheld_event_disputes", lambda _v: 0)
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: wrapper
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create(api: TestClient, **over: Any) -> dict[str, Any]:
    body = {
        "organiser_vendor_id": ORGANISER,
        "event_draft": DRAFT,
        "checklist": full_checklist(),
        "revenue_share_bps": 2500,
    }
    body.update(over)
    r = api.post(f"{BASE}/requests", headers=h("tp"), json=body)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


# --- flag / opt-in / organiser list -------------------------------------------------
def test_flag_off_hides_everything(api: TestClient, fake: FakeClient) -> None:
    fake.tables["feature_flags"][0]["enabled"] = False
    status = api.get(f"{BASE}/status", headers=h("tp"))
    assert status.json() == {"enabled": False, "can_organise": False, "accepts_requests": False}
    assert api.get(f"{BASE}/organisers", headers=h("tp")).status_code == 404
    r = api.post(f"{BASE}/requests", headers=h("tp"), json={"organiser_vendor_id": ORGANISER})
    assert r.status_code == 404


def test_only_verified_opted_in_organisers_listed(api: TestClient, fake: FakeClient) -> None:
    # OTHER opted in but has no approved KYC; PROPOSER (caller) opted in too.
    fake.tables["event_collab_organiser_prefs"] += [
        {"vendor_id": OTHER, "accepts_requests": True, "blurb": None},
        {"vendor_id": PROPOSER, "accepts_requests": True, "blurb": None},
    ]
    items = api.get(f"{BASE}/organisers", headers=h("tp")).json()["items"]
    assert [i["vendor_id"] for i in items] == [ORGANISER]
    assert api.get(f"{BASE}/organisers?q=zzz", headers=h("tp")).json()["items"] == []
    assert len(api.get(f"{BASE}/organisers?q=big", headers=h("tp")).json()["items"]) == 1


def test_opt_in_requires_verified_organiser(api: TestClient) -> None:
    denied = api.put(f"{BASE}/organiser-settings", headers=h("tp"), json={"accepts_requests": True})
    assert denied.status_code == 403
    ok = api.put(f"{BASE}/organiser-settings", headers=h("to"), json={"accepts_requests": False})
    assert ok.status_code == 200 and ok.json()["accepts_requests"] is False


def test_cannot_choose_unlisted_organiser_or_self(api: TestClient, fake: FakeClient) -> None:
    fake.tables["event_collab_organiser_prefs"][0]["accepts_requests"] = False
    body = {"organiser_vendor_id": ORGANISER, "event_draft": DRAFT}
    assert api.post(f"{BASE}/requests", headers=h("tp"), json=body).status_code == 422
    body["organiser_vendor_id"] = PROPOSER
    assert api.post(f"{BASE}/requests", headers=h("tp"), json=body).status_code == 422


# --- authz -----------------------------------------------------------------------
def test_vendor_cannot_see_or_touch_other_vendors_requests(api: TestClient) -> None:
    rid = create(api)["id"]
    assert api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp")).status_code == 200
    for method, path, kw in (
        ("get", f"/requests/{rid}", {}),
        ("patch", f"/requests/{rid}", {"json": {"revenue_share_bps": 100}}),
        ("post", f"/requests/{rid}/approve", {}),
        ("post", f"/requests/{rid}/publish", {}),
        ("post", f"/requests/{rid}/decline", {"json": {"reason": "nope nope"}}),
    ):
        r = getattr(api, method)(f"{BASE}{path}", headers=h("tx"), **kw)
        assert r.status_code == 404, (path, r.text)
    assert api.get(f"{BASE}/requests?role=proposer", headers=h("tx")).json()["items"] == []
    assert api.get(f"{BASE}/requests?role=organiser", headers=h("tx")).json()["items"] == []


def test_organiser_inbox_hides_drafts(api: TestClient) -> None:
    rid = create(api)["id"]
    assert api.get(f"{BASE}/requests?role=organiser", headers=h("to")).json()["items"] == []
    assert api.get(f"{BASE}/requests/{rid}", headers=h("to")).status_code == 404
    api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp"))
    items = api.get(f"{BASE}/requests?role=organiser", headers=h("to")).json()["items"]
    assert [i["id"] for i in items] == [rid]


# --- state machine failure paths ---------------------------------------------------
def test_full_happy_path_publishes_under_organiser(api: TestClient, fake: FakeClient) -> None:
    rid = create(api)["id"]
    assert (
        api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp")).json()["status"] == "submitted"
    )
    assert (
        api.post(f"{BASE}/requests/{rid}/approve", headers=h("to")).json()["status"] == "approved"
    )
    done = api.post(f"{BASE}/requests/{rid}/publish", headers=h("to")).json()
    assert done["status"] == "published" and done["event_id"]
    event = fake.tables["events"][0]
    assert event["organiser_vendor_id"] == ORGANISER and event["status"] == "published"
    assert [a["action"] for a in done["audit"]] == ["create", "submit", "approve", "publish"]


def test_approving_twice_is_rejected(api: TestClient) -> None:
    rid = create(api)["id"]
    api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp"))
    assert api.post(f"{BASE}/requests/{rid}/approve", headers=h("to")).status_code == 200
    again = api.post(f"{BASE}/requests/{rid}/approve", headers=h("to"))
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_transition"


def test_non_organiser_cannot_approve_or_publish(api: TestClient) -> None:
    rid = create(api)["id"]
    api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp"))
    r = api.post(f"{BASE}/requests/{rid}/approve", headers=h("tp"))
    assert r.status_code == 403
    api.post(f"{BASE}/requests/{rid}/approve", headers=h("to"))
    assert api.post(f"{BASE}/requests/{rid}/publish", headers=h("tp")).status_code == 403


def test_publish_before_approval_is_rejected(api: TestClient, fake: FakeClient) -> None:
    rid = create(api)["id"]
    api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp"))
    r = api.post(f"{BASE}/requests/{rid}/publish", headers=h("to"))
    assert r.status_code == 409
    assert fake.tables.get("events", []) == []


def test_decline_and_changes_need_reasons_then_resubmit(api: TestClient) -> None:
    rid = create(api)["id"]
    api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp"))
    assert api.post(f"{BASE}/requests/{rid}/decline", headers=h("to"), json={}).status_code == 422
    assert (
        api.post(
            f"{BASE}/requests/{rid}/request-changes", headers=h("to"), json={"reason": "x"}
        ).status_code
        == 422
    )
    ch = api.post(
        f"{BASE}/requests/{rid}/request-changes",
        headers=h("to"),
        json={"reason": "Confirm the generator"},
    ).json()
    assert ch["status"] == "changes_requested" and ch["organiser_note"] == "Confirm the generator"
    edited = api.patch(f"{BASE}/requests/{rid}", headers=h("tp"), json={"revenue_share_bps": 2000})
    assert edited.status_code == 200 and edited.json()["revenue_share_bps"] == 2000
    assert (
        api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp")).json()["status"] == "submitted"
    )
    declined = api.post(
        f"{BASE}/requests/{rid}/decline", headers=h("to"), json={"reason": "Dates clash"}
    )
    assert declined.json()["status"] == "declined"
    assert api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp")).status_code == 409


def test_submitted_request_is_frozen_and_only_proposer_edits(api: TestClient) -> None:
    rid = create(api)["id"]
    assert api.patch(f"{BASE}/requests/{rid}", headers=h("to"), json={}).status_code == 404
    api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp"))
    assert (
        api.patch(
            f"{BASE}/requests/{rid}", headers=h("tp"), json={"revenue_share_bps": 1}
        ).status_code
        == 409
    )
    assert api.patch(f"{BASE}/requests/{rid}", headers=h("to"), json={}).status_code == 403


def test_publish_blocked_when_start_is_now_past(api: TestClient, fake: FakeClient) -> None:
    rid = create(api)["id"]
    api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp"))
    api.post(f"{BASE}/requests/{rid}/approve", headers=h("to"))
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    fake.tables["event_collab_requests"][0]["checklist"]["schedule"]["starts_at"] = past
    r = api.post(f"{BASE}/requests/{rid}/publish", headers=h("to"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "past_instance"


# --- checklist validation --------------------------------------------------------------
def test_submit_reports_every_missing_field(api: TestClient) -> None:
    rid = create(api, checklist={}, event_draft={"title": "Only a title"}, revenue_share_bps=None)[
        "id"
    ]
    r = api.post(f"{BASE}/requests/{rid}/submit", headers=h("tp"))
    assert r.status_code == 422
    fields = {f["field"] for f in r.json()["error"]["details"]["fields"]}
    assert {
        "event_draft.category",
        "checklist.venue.name",
        "checklist.venue.landmark",
        "checklist.venue.gps",
        "checklist.schedule.starts_at",
        "checklist.capacity.capacity",
        "checklist.equipment.sound",
        "checklist.permits.status",
        "checklist.tiers",
        "revenue_share_bps",
    } <= fields


def test_checklist_rules() -> None:
    draft = EventDraft.model_validate(DRAFT)
    past = full_checklist(schedule={"starts_at": _future(-5), "ends_at": _future(-1)})
    codes = {
        (e["field"], e["code"])
        for e in submit_field_errors(draft, Checklist.model_validate(past), 100)
    }
    assert ("checklist.schedule.starts_at", "must_be_future") in codes
    backwards = full_checklist(schedule={"starts_at": _future(10), "ends_at": _future(5)})
    codes = {
        (e["field"], e["code"])
        for e in submit_field_errors(draft, Checklist.model_validate(backwards), 100)
    }
    assert ("checklist.schedule.ends_at", "must_be_after_start") in codes
    big = full_checklist(tiers=[{"name": "VIP", "price_ngwee": 1, "qty_cap": 999}])
    codes = {
        (e["field"], e["code"])
        for e in submit_field_errors(draft, Checklist.model_validate(big), 100)
    }
    assert ("checklist.tiers.0.qty_cap", "exceeds_capacity") in codes
    assert submit_field_errors(draft, Checklist.model_validate(full_checklist()), 0) == []


def test_pydantic_strict_rejects_bad_shapes(api: TestClient) -> None:
    base = {"organiser_vendor_id": ORGANISER}
    bad_bodies = [
        {**base, "revenue_share_bps": 10_001},
        {**base, "revenue_share_bps": -1},
        {**base, "revenue_share_bps": 25.5},
        {**base, "revenue_share_bps": "2500"},
        {**base, "checklist": {"tiers": [{"name": "A", "price_ngwee": 12.5}]}},
        {**base, "checklist": {"equipment": {"sound": "maybe"}}},
        {**base, "checklist": {"venue": {"lat": 200}}},
        {**base, "unknown": 1},
        {"organiser_vendor_id": "not-a-uuid"},
    ]
    for body in bad_bodies:
        assert api.post(f"{BASE}/requests", headers=h("tp"), json=body).status_code == 422, body


def test_readiness_percentage() -> None:
    assert readiness_pct(Checklist(), None) == 0
    full = Checklist.model_validate(
        full_checklist(
            equipment={k: "ready" for k in ("sound", "stage", "power", "seating", "security")},
            permits={"status": "obtained"},
        )
    )
    assert readiness_pct(full, 2500) == 100
    mixed = Checklist.model_validate(full_checklist())  # stage needed + permits pending
    assert readiness_pct(mixed, 2500) == round(100 * 9 / 11)
    created = readiness_pct(mixed, None)
    assert created == round(100 * 8 / 11)


def test_python_transition_mirror() -> None:
    assert assert_transition_allowed("submit", role="proposer", status="draft") == "submitted"
    with pytest.raises(Exception) as exc:
        assert_transition_allowed("publish", role="organiser", status="submitted")
    assert getattr(exc.value, "code", "") == "invalid_transition"
    with pytest.raises(Exception) as exc2:
        assert_transition_allowed("approve", role="proposer", status="submitted")
    assert getattr(exc2.value, "code", "") == "forbidden"


def test_rate_limited(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.event_collaboration.bump_rate_counter", lambda **_k: (False, 7)
    )
    r = api.post(f"{BASE}/requests", headers=h("tp"), json={"organiser_vendor_id": ORGANISER})
    assert r.status_code == 429
