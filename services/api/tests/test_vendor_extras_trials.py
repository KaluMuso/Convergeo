"""Paid extras (vendor + admin), seller free trials, annual price, branch cards.

API-level: authz, strict validation, rate limits, audit rows and error mapping.
The DB state machine / guards are proven against Postgres in
tests/rls/test_plan_limits_extras_rls.py.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.routers import admin_config, admin_extras, directory, vendor_extras
from app.services.vendor_plans.billing import (
    SubscriptionCharge,
    add_months,
    annual_price_ngwee,
    get_subscription_gateway,
    in_trial,
    plan_fee_due_ngwee,
    trial_end_for_signup,
)
from fastapi.testclient import TestClient
from tests.test_vendor_plans import (
    ADMIN_ID,
    AUTH,
    MODERATOR_ID,
    VENDOR_A,
    VENDOR_B,
    VENDOR_USER_A,
    VENDOR_USER_B,
    FakeDb,
    FakeService,
    Harness,
    make_db,
)

REQ_A = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee1"
BUSINESS_A = VENDOR_A


def extras_db() -> FakeDb:
    db = make_db()
    db.tables["vendor_extras"] = [
        {"key": "store_design", "name": "Store design", "description": "d", "pricing": "range",
         "price_ngwee": 50000, "price_max_ngwee": 500000, "unit": "one_off",
         "price_is_placeholder": False, "active": True, "position": 2},
        {"key": "custom_domain", "name": "Custom domain", "description": "", "pricing": "fixed",
         "price_ngwee": 7500, "price_max_ngwee": None, "unit": "per_month",
         "price_is_placeholder": True, "active": True, "position": 11},
        {"key": "retired", "name": "Retired", "description": "", "pricing": "fixed",
         "price_ngwee": 100, "price_max_ngwee": None, "unit": "one_off",
         "price_is_placeholder": False, "active": False, "position": 20},
    ]  # fmt: skip
    db.tables["vendor_extras_requests"] = []
    db.tables["vendor_businesses"] = [
        {"id": BUSINESS_A, "legal_name": "Mwila Traders",
         "trial_ends_at": (datetime.now(UTC) + timedelta(days=30)).isoformat()},
    ]  # fmt: skip
    for vendor in db.tables["vendors"]:
        vendor["business_id"] = vendor["id"]
    return db


@pytest.fixture
def h(monkeypatch: pytest.MonkeyPatch) -> Generator[Harness, None, None]:
    db = extras_db()
    app = create_app()
    holder: dict[str, Harness] = {}

    async def current_user() -> CurrentUser:
        return holder["h"].user

    def service_dep() -> Generator[FakeService, None, None]:
        yield FakeService(holder["h"].db)

    def fake_bump(**kwargs: Any) -> tuple[bool, int]:
        holder["h"].rate_calls.append(kwargs["key"])
        return (holder["h"].rate_allowed, 0 if holder["h"].rate_allowed else 30)

    monkeypatch.setattr(vendor_extras, "bump_rate_counter", fake_bump)
    monkeypatch.setattr(admin_extras, "bump_rate_counter", fake_bump)
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client", lambda: FakeService(holder["h"].db)
    )
    monkeypatch.setattr(
        "app.core.auth.get_supabase_service_client", lambda: FakeService(holder["h"].db)
    )
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_supabase_client] = service_dep
    with TestClient(app, raise_server_exceptions=False) as client:
        holder["h"] = Harness(db, client)
        yield holder["h"]
    app.dependency_overrides.clear()


class DbError(Exception):
    def __init__(self, message: str, code: str = "22023") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def fake_transition(db: FakeDb) -> list[dict[str, Any]]:
    """Mirror of transition_vendor_extras_request (allowed edges only)."""
    calls: list[dict[str, Any]] = []
    admin_edges = {
        "requested": {"quoted", "approved", "cancelled"},
        "quoted": {"quoted", "approved", "cancelled"},
        "approved": {"fulfilled", "cancelled"},
    }
    vendor_edges = {"quoted": {"approved", "cancelled"}, "requested": {"cancelled"}}

    def rpc(name: str, params: dict[str, Any]) -> Any:
        assert name == "transition_vendor_extras_request"
        calls.append(params)
        row = next(
            r for r in db.rows("vendor_extras_requests") if r["id"] == params["p_request_id"]
        )
        edges = admin_edges if params["p_actor_role"] == "admin" else vendor_edges
        if params["p_to"] not in edges.get(row["status"], set()):
            raise DbError("extras_invalid_transition")
        row["status"] = params["p_to"]
        if params["p_quoted_price_ngwee"] is not None:
            row["quoted_price_ngwee"] = params["p_quoted_price_ngwee"]
        return MagicMock(execute=lambda: MagicMock(data={"to": params["p_to"]}))

    db.rpc = rpc  # type: ignore[method-assign]
    return calls


def seed_request(db: FakeDb, *, status: str = "requested", vendor_id: str = VENDOR_A) -> None:
    db.tables["vendor_extras_requests"].append(
        {"id": REQ_A, "vendor_id": vendor_id, "extra_key": "store_design", "quantity": 1,
         "note": None, "status": status, "quoted_price_ngwee": None, "admin_note": None,
         "created_at": "2026-11-15T10:00:00+00:00"}
    )  # fmt: skip


# ---------------------------------------------------------------------------
# Money / trial math (pure)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("monthly", "pct", "annual"),
    [
        (0, 15, 0),
        (4900, 15, 49980),  # 12 x 4900 = 58800 x 0.85 = 49980
        (24900, 15, 253980),
        (150000, 15, 1530000),
        (333, 15, 3396),  # 3396.6 -> rounded down
        (4900, 0, 58800),
    ],
)
def test_annual_price_integer_rounded_down(monthly: int, pct: int, annual: int) -> None:
    assert annual_price_ngwee(monthly, pct) == annual


@pytest.mark.parametrize(("monthly", "pct"), [(-1, 15), (100, -1), (100, 91)])
def test_annual_price_rejects_bad_input(monthly: int, pct: int) -> None:
    with pytest.raises(ValueError):
        annual_price_ngwee(monthly, pct)


def test_trial_is_signup_plus_one_calendar_month() -> None:
    signup = datetime(2026, 11, 15, 9, 30, tzinfo=UTC)
    assert trial_end_for_signup(signup) == datetime(2026, 12, 15, 9, 30, tzinfo=UTC)
    # Day clamps like Postgres interval arithmetic (Jan 31 -> Feb 28).
    assert trial_end_for_signup(datetime(2027, 1, 31, tzinfo=UTC)) == datetime(
        2027, 2, 28, tzinfo=UTC
    )
    assert trial_end_for_signup(datetime(2028, 1, 31, tzinfo=UTC)) == datetime(
        2028, 2, 29, tzinfo=UTC
    )
    assert add_months(datetime(2026, 12, 31, tzinfo=UTC), 2) == datetime(2027, 2, 28, tzinfo=UTC)


def test_no_plan_fee_during_trial_and_full_fee_after() -> None:
    end = datetime(2027, 1, 15, tzinfo=UTC)
    assert in_trial(end, at=end - timedelta(seconds=1))
    assert not in_trial(end, at=end)  # the boundary instant is no longer free
    assert plan_fee_due_ngwee(24900, end, at=end - timedelta(days=1)) == 0
    assert plan_fee_due_ngwee(24900, end, at=end) == 24900
    assert plan_fee_due_ngwee(24900, None) == 24900  # no trial recorded


def test_billing_seam_refuses_charges_during_trial() -> None:
    charge = SubscriptionCharge(VENDOR_A, "starter", 4900, "sub-x-202611")
    with pytest.raises(AppError) as excinfo:
        get_subscription_gateway(datetime.now(UTC) + timedelta(days=1)).request_charge(charge)
    assert excinfo.value.code == "plan_in_trial"
    with pytest.raises(AppError) as after:
        get_subscription_gateway(datetime.now(UTC) - timedelta(days=1)).request_charge(charge)
    assert after.value.code == "billing_not_available"


def test_annual_discount_is_an_admin_editable_platform_key() -> None:
    assert admin_config.AI_DAILY_QUOTA_BOUNDS["plan_annual_discount_pct"] == (0, 90)
    assert "plan_annual_discount_pct" in admin_config.EDITABLE_PLATFORM_KEYS


def test_vendor_plan_reports_trial(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import vendor_plan
    from app.services.kyc.caps import VendorCapLimits, VendorQuota
    from app.services.vendor_plans.resolver import resolve_effective_plan

    def fake_limits(_svc: Any, vendor_id: str, **_k: Any) -> VendorCapLimits:
        return VendorCapLimits(
            vendor_id=vendor_id, kyc_tier=1, quota=VendorQuota(1, 30, None, None, {}),
            cod_cap_ngwee=50_000, listing_count=3, order_count=0, kyc_max_listings=30,
            plan=resolve_effective_plan(h.db, vendor_id), active_listing_count=2,
        )  # fmt: skip

    monkeypatch.setattr(vendor_plan, "load_vendor_cap_limits_by_id", fake_limits)
    h.as_role(VENDOR_USER_A, "vendor")
    body = h.client.get("/vendor/plan", headers=AUTH).json()
    assert body["in_trial"] is True and body["trial_ends_at"]
    h.db.tables["feature_flags"][0]["enabled"] = False  # trial shows with plans off too
    off = h.client.get("/vendor/plan", headers=AUTH).json()
    assert off["enabled"] is False and off["in_trial"] is True


# ---------------------------------------------------------------------------
# Vendor extras
# ---------------------------------------------------------------------------
def test_vendor_lists_active_extras_and_own_requests(h: Harness) -> None:
    seed_request(h.db, vendor_id=VENDOR_B)
    h.as_role(VENDOR_USER_A, "vendor")
    body = h.client.get("/vendor/extras", headers=AUTH).json()
    assert [e["key"] for e in body["extras"]] == ["store_design", "custom_domain"]
    assert body["extras"][1]["price_is_placeholder"] is True
    assert body["requests"] == []  # vendor B's request is not visible


def test_vendor_requests_extra_once(h: Harness) -> None:
    h.as_role(VENDOR_USER_A, "vendor")
    first = h.client.post(
        "/vendor/extras/requests",
        json={"extra_key": "store_design", "note": " logo too "},
        headers=AUTH,
    )
    assert first.status_code == 201, first.text
    row = h.db.rows("vendor_extras_requests")[0]
    assert row["vendor_id"] == VENDOR_A and row["requested_by"] == VENDOR_USER_A
    assert row["note"] == "logo too" and "status" not in row  # DB default = requested
    assert h.rate_calls == [f"extras:{VENDOR_USER_A}"]
    row["status"] = "requested"
    again = h.client.post(
        "/vendor/extras/requests", json={"extra_key": "store_design"}, headers=AUTH
    )
    assert again.status_code == 409
    assert (
        again.json()["error"]["details"]["message_key"] == "vendor.extras.errors.alreadyRequested"
    )


@pytest.mark.parametrize(
    "body",
    [
        {"extra_key": "BAD KEY"},
        {"extra_key": "store_design", "quantity": 0},
        {"extra_key": "store_design", "quantity": 10_001},
        {"extra_key": "store_design", "note": "x" * 501},
        {"extra_key": "store_design", "price_ngwee": 1},
    ],
)
def test_vendor_request_validation(h: Harness, body: dict[str, Any]) -> None:
    h.as_role(VENDOR_USER_A, "vendor")
    assert h.client.post("/vendor/extras/requests", json=body, headers=AUTH).status_code == 422


def test_vendor_cannot_request_inactive_or_unknown_extra(h: Harness) -> None:
    h.as_role(VENDOR_USER_A, "vendor")
    for key in ("retired", "no_such_extra"):
        r = h.client.post("/vendor/extras/requests", json={"extra_key": key}, headers=AUTH)
        assert r.status_code == 404


def test_vendor_request_rate_limited(h: Harness) -> None:
    h.as_role(VENDOR_USER_A, "vendor")
    h.rate_allowed = False
    r = h.client.post("/vendor/extras/requests", json={"extra_key": "store_design"}, headers=AUTH)
    assert r.status_code == 429
    assert h.db.rows("vendor_extras_requests") == []


def test_extras_routes_require_vendor_role(h: Harness) -> None:
    h.as_role(VENDOR_USER_A, "customer")
    assert h.client.get("/vendor/extras", headers=AUTH).status_code == 403
    r = h.client.post("/vendor/extras/requests", json={"extra_key": "store_design"}, headers=AUTH)
    assert r.status_code == 403


def test_vendor_cancels_own_request_but_not_another_shops(h: Harness) -> None:
    calls = fake_transition(h.db)
    seed_request(h.db, vendor_id=VENDOR_B)
    h.as_role(VENDOR_USER_A, "vendor")
    foreign = h.client.post(f"/vendor/extras/requests/{REQ_A}/cancel", headers=AUTH)
    assert foreign.status_code == 404 and calls == []
    h.as_role(VENDOR_USER_B, "vendor")
    ok = h.client.post(f"/vendor/extras/requests/{REQ_A}/cancel", headers=AUTH)
    assert ok.status_code == 200 and ok.json()["status"] == "cancelled"
    assert calls[0]["p_actor_role"] == "vendor" and calls[0]["p_actor"] == VENDOR_USER_B


def test_vendor_cannot_accept_unquoted_request(h: Harness) -> None:
    fake_transition(h.db)
    seed_request(h.db)
    h.as_role(VENDOR_USER_A, "vendor")
    r = h.client.post(f"/vendor/extras/requests/{REQ_A}/accept", headers=AUTH)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "extras_invalid_transition"


# ---------------------------------------------------------------------------
# Admin queue + catalogue
# ---------------------------------------------------------------------------
def test_admin_quote_then_approve_then_fulfil_with_audit(h: Harness) -> None:
    calls = fake_transition(h.db)
    seed_request(h.db)
    h.as_role(ADMIN_ID, "admin")
    queue = h.client.get("/admin/extras/requests?status=requested", headers=AUTH).json()
    assert queue[0]["extra_name"] == "Store design"
    quoted = h.client.post(
        f"/admin/extras/requests/{REQ_A}/transition",
        json={"to": "quoted", "quoted_price_ngwee": 120000, "note": "Logo + cover"},
        headers=AUTH,
    )
    assert quoted.status_code == 200, quoted.text
    assert quoted.json()["quoted_price_ngwee"] == 120000
    for to in ("approved", "fulfilled"):
        r = h.client.post(
            f"/admin/extras/requests/{REQ_A}/transition", json={"to": to}, headers=AUTH
        )
        assert r.status_code == 200 and r.json()["status"] == to
    assert [c["p_to"] for c in calls] == ["quoted", "approved", "fulfilled"]
    actions = [row["action"] for row in h.db.rows("audit_log")]
    assert actions == [
        "extras.request.quoted",
        "extras.request.approved",
        "extras.request.fulfilled",
    ]


def test_admin_cannot_reopen_fulfilled_request(h: Harness) -> None:
    fake_transition(h.db)
    seed_request(h.db, status="fulfilled")
    h.as_role(ADMIN_ID, "admin")
    r = h.client.post(
        f"/admin/extras/requests/{REQ_A}/transition", json={"to": "cancelled"}, headers=AUTH
    )
    assert r.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"to": "quoted"},  # a quote needs a price
        {"to": "approved", "quoted_price_ngwee": 100},
        {"to": "quoted", "quoted_price_ngwee": -1},
        {"to": "quoted", "quoted_price_ngwee": 1.5},
        {"to": "requested"},
    ],
)
def test_admin_transition_validation(h: Harness, body: dict[str, Any]) -> None:
    seed_request(h.db)
    h.as_role(ADMIN_ID, "admin")
    r = h.client.post(f"/admin/extras/requests/{REQ_A}/transition", json=body, headers=AUTH)
    assert r.status_code == 422


def test_extras_admin_routes_deny_vendor_and_moderator_catalogue(h: Harness) -> None:
    h.as_role(VENDOR_USER_A, "vendor")
    assert h.client.get("/admin/extras/requests", headers=AUTH).status_code == 403
    h.as_role(MODERATOR_ID, "moderator")
    # Moderators triage the queue (vendors.manage) but never edit catalogue prices.
    assert h.client.get("/admin/extras/requests", headers=AUTH).status_code == 200
    r = h.client.patch("/admin/extras/custom_domain", json={"price_ngwee": 1}, headers=AUTH)
    assert r.status_code == 403


def test_admin_edits_price_clears_placeholder_and_audits(h: Harness) -> None:
    h.as_role(ADMIN_ID, "admin")
    r = h.client.patch(
        "/admin/extras/custom_domain", json={"price_ngwee": 9900, "active": True}, headers=AUTH
    )
    assert r.status_code == 200, r.text
    assert r.json()["price_ngwee"] == 9900 and r.json()["price_is_placeholder"] is False
    assert h.db.rows("audit_log")[-1]["action"] == "extras.update"


@pytest.mark.parametrize(
    "patch",
    [
        {"pricing": "range"},  # range needs a max above the price
        {"price_max_ngwee": 10},  # fixed must not have a max
        {"price_ngwee": 2.5},
        {"unit": "per_year"},
        {"name": "  "},
        {},
    ],
)
def test_admin_extra_validation(h: Harness, patch: dict[str, Any]) -> None:
    h.as_role(ADMIN_ID, "admin")
    assert (
        h.client.patch("/admin/extras/custom_domain", json=patch, headers=AUTH).status_code == 422
    )


def test_admin_creates_extra(h: Harness) -> None:
    h.as_role(ADMIN_ID, "admin")
    body = {"key": "logo_pack", "name": "Logo pack", "pricing": "fixed", "price_ngwee": 20000,
            "unit": "one_off"}  # fmt: skip
    assert h.client.post("/admin/extras", json=body, headers=AUTH).status_code == 201
    assert h.client.post("/admin/extras", json=body, headers=AUTH).status_code == 409


# ---------------------------------------------------------------------------
# Admin trials
# ---------------------------------------------------------------------------
def test_admin_lists_and_extends_trial_with_audit(h: Harness) -> None:
    h.as_role(ADMIN_ID, "admin")
    listed = h.client.get("/admin/trials", headers=AUTH).json()
    assert listed[0]["business_id"] == BUSINESS_A and listed[0]["in_trial"] is True
    new_end = (datetime.now(UTC) + timedelta(days=90)).isoformat()
    r = h.client.post(
        f"/admin/trials/{BUSINESS_A}",
        json={"action": "extend", "ends_at": new_end, "reason": "pilot anchor seller"},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    audit = h.db.rows("audit_log")[-1]
    assert audit["action"] == "trials.extend" and audit["after"]["reason"] == "pilot anchor seller"


def test_admin_cannot_shorten_via_extend_and_can_end_once(h: Harness) -> None:
    h.as_role(ADMIN_ID, "admin")
    earlier = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    shorter = h.client.post(
        f"/admin/trials/{BUSINESS_A}",
        json={"action": "extend", "ends_at": earlier, "reason": "oops"},
        headers=AUTH,
    )
    assert shorter.status_code == 422
    ended = h.client.post(
        f"/admin/trials/{BUSINESS_A}",
        json={"action": "end", "reason": "asked to start paying"},
        headers=AUTH,
    )
    assert ended.status_code == 200 and ended.json()["in_trial"] is False
    again = h.client.post(
        f"/admin/trials/{BUSINESS_A}", json={"action": "end", "reason": "again"}, headers=AUTH
    )
    assert again.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"action": "extend", "reason": "no date"},
        {"action": "extend", "ends_at": "2027-01-01T00:00:00", "reason": "naive"},
        {"action": "extend", "ends_at": "2099-01-01T00:00:00+00:00", "reason": "too far"},
        {"action": "end", "ends_at": "2027-01-01T00:00:00+00:00", "reason": "end with date"},
        {"action": "end", "reason": "x"},
        {"action": "pause", "reason": "nope"},
    ],
)
def test_admin_trial_validation(h: Harness, body: dict[str, Any]) -> None:
    h.as_role(ADMIN_ID, "admin")
    assert h.client.post(f"/admin/trials/{BUSINESS_A}", json=body, headers=AUTH).status_code == 422


def test_trial_routes_are_admin_only(h: Harness) -> None:
    h.as_role(MODERATOR_ID, "moderator")
    assert h.client.get("/admin/trials", headers=AUTH).status_code == 403
    h.as_role(VENDOR_USER_A, "vendor")
    r = h.client.post(
        f"/admin/trials/{BUSINESS_A}", json={"action": "end", "reason": "mine"}, headers=AUTH
    )
    assert r.status_code == 403


def test_trial_change_rate_limited(h: Harness) -> None:
    h.as_role(ADMIN_ID, "admin")
    h.rate_allowed = False
    r = h.client.post(
        f"/admin/trials/{BUSINESS_A}", json={"action": "end", "reason": "limit"}, headers=AUTH
    )
    assert r.status_code == 429


# ---------------------------------------------------------------------------
# Other branches (directory card data)
# ---------------------------------------------------------------------------
def test_branch_card_fields() -> None:
    now = datetime(2026, 11, 16, 10, 0, tzinfo=directory.LUSAKA_TZ)  # a Monday, 10:00
    link = directory._branch_link(
        {
            "slug": "mwila-kabwata",
            "display_name": "Mwila Kabwata",
            "contact_phone": "260971234567",
            "whatsapp_msisdn": "260955000000",
            "vendor_locations": [
                {"landmark": "Opposite Kabwata market", "lat": -15.44, "lng": 28.3,
                 "hours": {"mon": "08:00-18:00"}, "address": "Plot 1", "map_url": None}
            ],
        },
        now=now,
    )  # fmt: skip
    assert link is not None
    assert link.phone == "260971234567"  # contact phone wins over WhatsApp
    assert link.map_url == "https://www.google.com/maps/search/?api=1&query=-15.44,28.3"
    assert link.lat == -15.44 and link.landmark == "Opposite Kabwata market"


def test_branch_card_without_hours_or_gps() -> None:
    link = directory._branch_link(
        {"slug": "x", "display_name": "X", "vendor_locations": [
            {"landmark": "Town", "map_url": "http://insecure"}]}
    )  # fmt: skip
    assert link is not None
    assert link.open_now is None and link.map_url is None and link.phone is None
    assert directory._branch_link({"display_name": "no slug"}) is None
