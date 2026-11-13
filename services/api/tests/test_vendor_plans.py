"""Vendor plans + shared canonical photos — API layer (no Postgres).

DB-level isolation and the admission trigger are proven in
tests/rls/test_vendor_plans_rls.py; this module covers the resolver, cap
integration, the vendor/admin endpoints (authz, validation, rate limit, audit),
the photo cap, sha256 dedup scoping and gallery merging.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.routers import admin_vendor_plans, vendor_plan
from app.routers.products import ProductImageResponse, _merge_canonical_gallery
from app.services.kyc import caps
from app.services.kyc.caps import VendorCapLimits, VendorQuota, enforce_listing_cap
from app.services.vendor_plans import canonical_photos
from app.services.vendor_plans.billing import SubscriptionCharge, get_subscription_gateway
from app.services.vendor_plans.canonical_photos import (
    find_duplicate,
    merge_listing_gallery,
    seed_canonical_images_from_listings,
)
from app.services.vendor_plans.resolver import (
    compose_effective_plan,
    plan_from_row,
    resolve_effective_plan,
)
from fastapi.testclient import TestClient

ADMIN_ID = "00000000-0000-0000-0000-0000000a0001"
MODERATOR_ID = "00000000-0000-0000-0000-0000000d0001"
VENDOR_USER_A = "11111111-1111-1111-1111-111111111111"
VENDOR_USER_B = "22222222-2222-2222-2222-222222222222"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
LISTING_A = "cccccccc-cccc-cccc-cccc-cccccccccccc"
LISTING_A2 = "cccccccc-cccc-cccc-cccc-ccccccccccc2"
LISTING_B = "dddddddd-dddd-dddd-dddd-dddddddddddd"
PRODUCT = "b0000000-0000-0000-0000-000000000001"
OTHER_PRODUCT = "b0000000-0000-0000-0000-000000000002"
SHA_1 = "a" * 64
SHA_2 = "b" * 64


# ---------------------------------------------------------------------------
# A small in-memory PostgREST-ish fake (eq / in_ / order / limit / upsert and
# one level of `table!inner(col)` join filtering via `table.col`).
# ---------------------------------------------------------------------------
class FakeQuery:
    def __init__(self, db: FakeDb, table: str) -> None:
        self.db = db
        self.table = table
        self.filters: list[tuple[str, str, Any]] = []
        self.op = "select"
        self.payload: Any = None
        self.on_conflict: str | None = None
        self.order_by: tuple[str, bool] | None = None
        self.limit_n: int | None = None
        self.single = False

    def select(self, _columns: str = "*", *, count: str | None = None) -> FakeQuery:
        _ = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: Any) -> FakeQuery:
        self.filters.append(("in", column, list(values)))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self.order_by = (column, desc)
        return self

    def limit(self, n: int) -> FakeQuery:
        self.limit_n = n
        return self

    def maybe_single(self) -> FakeQuery:
        self.single = True
        return self

    def insert(self, payload: Any) -> FakeQuery:
        self.op, self.payload = "insert", payload
        return self

    def upsert(self, payload: Any, *, on_conflict: str | None = None) -> FakeQuery:
        self.op, self.payload, self.on_conflict = "upsert", payload, on_conflict
        return self

    def update(self, payload: Any) -> FakeQuery:
        self.op, self.payload = "update", payload
        return self

    def delete(self) -> FakeQuery:
        self.op = "delete"
        return self

    def _value(self, row: dict[str, Any], column: str) -> Any:
        if "." in column:
            joined, col = column.split(".", 1)
            if joined == "vendor_listings" and self.table == "listing_images":
                listing = next(
                    (r for r in self.db.rows("vendor_listings") if r["id"] == row["listing_id"]),
                    None,
                )
                return listing.get(col) if listing else None
            return None
        return row.get(column)

    def _match(self, row: dict[str, Any]) -> bool:
        for op, column, value in self.filters:
            current = self._value(row, column)
            if op == "eq" and current != value:
                return False
            if op == "in" and current not in value:
                return False
        return True

    def execute(self) -> MagicMock:
        rows = self.db.rows(self.table)
        self.db.calls.append((self.table, self.op))
        if self.op in {"insert", "upsert"}:
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for item in items:
                new = dict(item)
                if self.op == "upsert" and self.on_conflict:
                    existing = next(
                        (r for r in rows if r.get(self.on_conflict) == new[self.on_conflict]),
                        None,
                    )
                    if existing is not None:
                        existing.update(new)
                        out.append(dict(existing))
                        continue
                new.setdefault("id", str(uuid4()))
                rows.append(new)
                out.append(dict(new))
            return MagicMock(data=out, count=len(out))
        matched = [row for row in rows if self._match(row)]
        if self.op == "update":
            for row in matched:
                row.update(self.payload)
            return MagicMock(data=[dict(r) for r in matched], count=len(matched))
        if self.op == "delete":
            self.db.tables[self.table] = [r for r in rows if not self._match(r)]
            return MagicMock(data=[dict(r) for r in matched], count=len(matched))
        if self.order_by:
            column, desc = self.order_by
            matched.sort(key=lambda r: (r.get(column) is None, r.get(column) or 0), reverse=desc)
        if self.limit_n is not None:
            matched = matched[: self.limit_n]
        data: Any = [dict(r) for r in matched]
        if self.single:
            data = data[0] if data else None
        return MagicMock(data=data, count=len(matched))


class FakeDb:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.calls: list[tuple[str, str]] = []

    def rows(self, table: str) -> list[dict[str, Any]]:
        return self.tables.setdefault(table, [])

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def rpc(self, *_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover - patched
        raise AssertionError("rpc not expected")


class FakeService:
    def __init__(self, db: FakeDb) -> None:
        self.client = db


PLAN_ROWS = [
    {"key": "free", "name": "Free", "price_ngwee": 0, "max_listings": 25,
     "max_images_per_listing": 3, "featured_slots": 0, "analytics_depth": "basic",
     "wholesale_tools": False, "is_default": True, "active": True, "position": 0},
    {"key": "starter", "name": "Starter", "price_ngwee": 4900, "max_listings": 150,
     "max_images_per_listing": 8, "featured_slots": 1, "analytics_depth": "standard",
     "wholesale_tools": False, "is_default": False, "active": True, "position": 1},
    {"key": "business", "name": "Business", "price_ngwee": 14900, "max_listings": 1000,
     "max_images_per_listing": 8, "featured_slots": 3, "analytics_depth": "advanced",
     "wholesale_tools": True, "is_default": False, "active": True, "position": 2},
    {"key": "pro", "name": "Pro", "price_ngwee": 34900, "max_listings": None,
     "max_images_per_listing": 8, "featured_slots": 10, "analytics_depth": "advanced",
     "wholesale_tools": True, "is_default": False, "active": True, "position": 3},
    {"key": "legacy", "name": "Legacy", "price_ngwee": 9900, "max_listings": 60,
     "max_images_per_listing": 8, "featured_slots": 0, "analytics_depth": "basic",
     "wholesale_tools": False, "is_default": False, "active": False, "position": 9},
]  # fmt: skip


def make_db(*, plans_on: bool = True, photos_on: bool = True) -> FakeDb:
    db = FakeDb()
    db.tables["feature_flags"] = [
        {"flag": "vendor_plans", "enabled": plans_on},
        {"flag": "shared_canonical_photos", "enabled": photos_on},
    ]
    db.tables["vendor_plans"] = [dict(row) for row in PLAN_ROWS]
    db.tables["vendors"] = [
        {"id": VENDOR_A, "owner_user_id": VENDOR_USER_A, "status": "active", "kyc_tier": 1},
        {"id": VENDOR_B, "owner_user_id": VENDOR_USER_B, "status": "active", "kyc_tier": 1},
    ]
    db.tables["vendor_listings"] = [
        {"id": LISTING_A, "vendor_id": VENDOR_A, "status": "draft", "product_id": PRODUCT,
         "created_at": "2026-11-01T00:00:00+00:00"},
        {"id": LISTING_A2, "vendor_id": VENDOR_A, "status": "draft", "product_id": None,
         "created_at": "2026-11-02T00:00:00+00:00"},
        {"id": LISTING_B, "vendor_id": VENDOR_B, "status": "draft", "product_id": PRODUCT,
         "created_at": "2026-11-03T00:00:00+00:00"},
    ]  # fmt: skip
    db.tables["products"] = [{"id": PRODUCT, "status": "active"}, {"id": OTHER_PRODUCT}]
    db.tables["user_roles"] = []
    return db


class Harness:
    def __init__(self, db: FakeDb, client: TestClient) -> None:
        self.db = db
        self.client = client
        self.user: CurrentUser = CurrentUser(id=ADMIN_ID, roles=frozenset({"admin"}), token="t")
        self.rate_allowed = True
        self.rate_calls: list[str] = []

    def as_role(self, user_id: str, *roles: str) -> Harness:
        self.user = CurrentUser(id=user_id, roles=frozenset(roles), token="t")
        return self


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Generator[Harness, None, None]:
    db = make_db()
    app = create_app()
    holder: dict[str, Harness] = {}

    async def current_user() -> CurrentUser:
        return holder["h"].user

    def service_dep() -> Generator[FakeService, None, None]:
        yield FakeService(holder["h"].db)

    def fake_bump(**kwargs: Any) -> tuple[bool, int]:
        holder["h"].rate_calls.append(kwargs["key"])
        return (holder["h"].rate_allowed, 0 if holder["h"].rate_allowed else 30)

    monkeypatch.setattr(admin_vendor_plans, "bump_rate_counter", fake_bump)
    # Admin audit_log writes go through the service client the recorder builds.
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


AUTH = {"Authorization": "Bearer t"}


def audit_rows(h: Harness) -> list[dict[str, Any]]:
    return h.db.rows("audit_log")


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------
def test_resolver_returns_none_when_flag_off() -> None:
    assert resolve_effective_plan(make_db(plans_on=False), VENDOR_A) is None


def test_resolver_fails_closed_when_flags_unreadable() -> None:
    broken = MagicMock()
    broken.table.side_effect = RuntimeError("db down")
    assert resolve_effective_plan(broken, VENDOR_A) is None


def test_resolver_uses_default_plan_then_assignment() -> None:
    db = make_db()
    plan = resolve_effective_plan(db, VENDOR_A)
    assert plan is not None and plan.plan.key == "free" and plan.max_listings == 25
    db.tables["vendor_plan_assignments"] = [{"vendor_id": VENDOR_A, "plan_key": "pro"}]
    plan = resolve_effective_plan(db, VENDOR_A)
    assert plan is not None and plan.plan.key == "pro" and plan.max_listings is None


def test_live_override_wins_and_expired_override_is_ignored() -> None:
    plan = plan_from_row(PLAN_ROWS[0])
    now = datetime(2026, 11, 13, tzinfo=UTC)
    live = {"unlimited_listings": True, "max_images_per_listing": 12,
            "expires_at": (now + timedelta(days=1)).isoformat()}  # fmt: skip
    effective = compose_effective_plan(plan, live, now=now)
    assert effective.max_listings is None
    assert effective.max_images_per_listing == 8  # clamped to the hard ≤8 rule
    assert effective.override_active
    expired = {"max_listings": 500, "expires_at": (now - timedelta(seconds=1)).isoformat()}
    effective = compose_effective_plan(plan, expired, now=now)
    assert effective.max_listings == 25 and not effective.override_active


# ---------------------------------------------------------------------------
# Cap integration (caps.py) — effective = min(KYC, plan)
# ---------------------------------------------------------------------------
def _limits(monkeypatch: pytest.MonkeyPatch, db: FakeDb, *, kyc_cap: int, listings: int) -> Any:
    monkeypatch.setattr(caps, "resolve_vendor_eligibility", lambda *_a, **_k: object())
    monkeypatch.setattr(caps, "cap_tier_for_quotas", lambda _e: 1)
    monkeypatch.setattr(
        caps,
        "load_vendor_quota",
        lambda _c, tier: VendorQuota(tier, kyc_cap, None, None, {}),
    )
    monkeypatch.setattr(caps, "_parse_config_int", lambda *_a: 50_000)
    monkeypatch.setattr(caps, "_count_vendor_listings", lambda *_a: listings)
    monkeypatch.setattr(caps, "_count_vendor_orders", lambda *_a: 0)
    return caps.load_vendor_cap_limits_by_id(FakeService(db), VENDOR_A, vendor_row={"id": VENDOR_A})


def test_plan_cap_binds_below_kyc_cap_with_upgrade_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    limits = _limits(monkeypatch, make_db(), kyc_cap=30, listings=25)
    assert limits.quota.max_listings == 25
    assert limits.kyc_max_listings == 30 and limits.limited_by_plan
    with pytest.raises(AppError) as excinfo:
        enforce_listing_cap(limits)
    details = excinfo.value.details or {}
    assert excinfo.value.code == "listing_cap_exceeded"
    assert details["message_key"] == "vendor.plans.limitReached"
    assert details["upgrade_available"] is True and details["plan_key"] == "free"


def test_kyc_cap_still_binds_for_bigger_plans(monkeypatch: pytest.MonkeyPatch) -> None:
    db = make_db()
    db.tables["vendor_plan_assignments"] = [{"vendor_id": VENDOR_A, "plan_key": "pro"}]
    limits = _limits(monkeypatch, db, kyc_cap=30, listings=30)
    assert limits.quota.max_listings == 30 and not limits.limited_by_plan
    with pytest.raises(AppError) as excinfo:
        enforce_listing_cap(limits)
    assert (excinfo.value.details or {})["message_key"] == "vendor.caps.listing_limit"


def test_flag_off_keeps_pre_plan_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    limits = _limits(monkeypatch, make_db(plans_on=False), kyc_cap=30, listings=29)
    assert limits.quota.max_listings == 30 and limits.plan is None
    enforce_listing_cap(limits)  # 29 < 30: no error


def test_enforce_listing_cap_allows_below_limit() -> None:
    limits = VendorCapLimits(
        vendor_id=VENDOR_A,
        kyc_tier=1,
        quota=VendorQuota(1, 25, None, None, {}),
        cod_cap_ngwee=50_000,
        listing_count=24,
        order_count=0,
    )
    enforce_listing_cap(limits)


# ---------------------------------------------------------------------------
# Vendor endpoint GET /vendor/plan
# ---------------------------------------------------------------------------
def test_vendor_plan_flag_off(harness: Harness) -> None:
    harness.db.tables["feature_flags"][0]["enabled"] = False
    harness.as_role(VENDOR_USER_A, "vendor")
    response = harness.client.get("/vendor/plan", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_vendor_plan_at_limit_offers_upgrades(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = harness.db

    def fake_limits(_svc: Any, vendor_id: str, **_k: Any) -> VendorCapLimits:
        plan = resolve_effective_plan(db, vendor_id)
        return VendorCapLimits(
            vendor_id=vendor_id,
            kyc_tier=1,
            quota=VendorQuota(1, 25, None, None, {}),
            cod_cap_ngwee=50_000,
            listing_count=27,  # e.g. after a downgrade: nothing is removed
            order_count=0,
            kyc_max_listings=30,
            plan=plan,
        )

    monkeypatch.setattr(vendor_plan, "load_vendor_cap_limits_by_id", fake_limits)
    harness.as_role(VENDOR_USER_A, "vendor")
    body = harness.client.get("/vendor/plan", headers=AUTH).json()
    assert body["enabled"] is True
    assert body["plan"]["key"] == "free" and body["plan"]["price_ngwee"] == 0
    assert body["effective_max_listings"] == 25 and body["listing_count"] == 27
    assert body["at_limit"] and body["over_limit"] and body["remaining_listings"] == 0
    assert body["limited_by"] == "plan"
    assert [p["key"] for p in body["upgrade_options"]] == ["starter", "business", "pro"]


def test_vendor_plan_requires_vendor_role(harness: Harness) -> None:
    harness.as_role(VENDOR_USER_A, "customer")
    assert harness.client.get("/vendor/plan", headers=AUTH).status_code == 403


# ---------------------------------------------------------------------------
# Admin plan CRUD
# ---------------------------------------------------------------------------
NEW_PLAN = {
    "key": "market_stall",
    "name": "Market stall",
    "price_ngwee": 2500,
    "max_listings": 40,
    "max_images_per_listing": 4,
    "featured_slots": 0,
    "analytics_depth": "basic",
    "wholesale_tools": False,
}


def test_admin_lists_plans_with_vendor_counts(harness: Harness) -> None:
    harness.db.tables["vendor_plan_assignments"] = [
        {"vendor_id": VENDOR_A, "plan_key": "starter"},
        {"vendor_id": VENDOR_B, "plan_key": "starter"},
    ]
    body = harness.client.get("/admin/vendor-plans", headers=AUTH).json()
    by_key = {row["key"]: row for row in body}
    assert by_key["starter"]["vendor_count"] == 2
    assert by_key["pro"]["max_listings"] is None


def test_admin_creates_plan_with_audit_and_rate_limit(harness: Harness) -> None:
    response = harness.client.post("/admin/vendor-plans", json=NEW_PLAN, headers=AUTH)
    assert response.status_code == 201, response.text
    assert response.json()["price_ngwee"] == 2500 and response.json()["is_default"] is False
    assert harness.rate_calls == [ADMIN_ID]
    audit = audit_rows(harness)
    assert len(audit) == 1 and audit[0]["action"] == "vendor_plans.create"
    assert audit[0]["actor"] == ADMIN_ID


@pytest.mark.parametrize(
    "patch",
    [
        {"price_ngwee": -1},
        {"price_ngwee": 49.5},
        {"price_ngwee": "K49"},
        {"max_images_per_listing": 9},
        {"max_listings": -5},
        {"key": "Bad Key"},
        {"name": "   "},
        {"analytics_depth": "everything"},
    ],
)
def test_admin_plan_validation(harness: Harness, patch: dict[str, Any]) -> None:
    response = harness.client.post("/admin/vendor-plans", json={**NEW_PLAN, **patch}, headers=AUTH)
    assert response.status_code == 422
    assert audit_rows(harness) == []


def test_admin_create_duplicate_key_conflicts(harness: Harness) -> None:
    response = harness.client.post(
        "/admin/vendor-plans", json={**NEW_PLAN, "key": "starter"}, headers=AUTH
    )
    assert response.status_code == 409


def test_admin_patch_unlimited_and_price(harness: Harness) -> None:
    response = harness.client.patch(
        "/admin/vendor-plans/business",
        json={"max_listings": None, "price_ngwee": 12900},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    assert response.json()["max_listings"] is None and response.json()["price_ngwee"] == 12900
    assert audit_rows(harness)[0]["before"]["max_listings"] == 1000


def test_admin_patch_rejects_empty_and_null_non_nullable(harness: Harness) -> None:
    assert (
        harness.client.patch("/admin/vendor-plans/free", json={}, headers=AUTH).status_code == 422
    )
    response = harness.client.patch(
        "/admin/vendor-plans/free", json={"price_ngwee": None}, headers=AUTH
    )
    assert response.status_code == 422


def test_admin_switches_default_plan(harness: Harness) -> None:
    response = harness.client.patch(
        "/admin/vendor-plans/starter", json={"is_default": True}, headers=AUTH
    )
    assert response.status_code == 200
    defaults = [r["key"] for r in harness.db.rows("vendor_plans") if r.get("is_default")]
    assert defaults == ["starter"]


def test_admin_cannot_deactivate_or_delete_default(harness: Harness) -> None:
    assert (
        harness.client.patch(
            "/admin/vendor-plans/free", json={"active": False}, headers=AUTH
        ).status_code
        == 409
    )
    assert harness.client.delete("/admin/vendor-plans/free", headers=AUTH).status_code == 409


def test_admin_cannot_delete_plan_in_use_but_can_delete_unused(harness: Harness) -> None:
    harness.db.tables["vendor_plan_assignments"] = [{"vendor_id": VENDOR_A, "plan_key": "legacy"}]
    assert harness.client.delete("/admin/vendor-plans/legacy", headers=AUTH).status_code == 409
    harness.db.tables["vendor_plan_assignments"] = []
    assert harness.client.delete("/admin/vendor-plans/legacy", headers=AUTH).status_code == 204
    assert all(r["key"] != "legacy" for r in harness.db.rows("vendor_plans"))
    assert audit_rows(harness)[-1]["action"] == "vendor_plans.delete"


def test_admin_write_rate_limited(harness: Harness) -> None:
    harness.rate_allowed = False
    response = harness.client.post("/admin/vendor-plans", json=NEW_PLAN, headers=AUTH)
    assert response.status_code == 429
    assert all(r["key"] != "market_stall" for r in harness.db.rows("vendor_plans"))


# ---------------------------------------------------------------------------
# Admin per-vendor assignment + override
# ---------------------------------------------------------------------------
def test_admin_assigns_plan_records_only(harness: Harness) -> None:
    response = harness.client.put(
        f"/admin/vendors/{VENDOR_A}/plan",
        json={"plan_key": "starter", "note": "pilot upgrade"},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assignment"]["plan_key"] == "starter"
    assert body["assignment"]["billing_status"] == "not_billed"
    assert body["effective_max_listings"] == 150
    rows = harness.db.rows("vendor_plan_assignments")
    assert len(rows) == 1 and rows[0]["assigned_by"] == ADMIN_ID
    assert audit_rows(harness)[0]["after"]["plan_key"] == "starter"
    # Re-assigning updates the same row (one current plan per vendor).
    harness.client.put(f"/admin/vendors/{VENDOR_A}/plan", json={"plan_key": "pro"}, headers=AUTH)
    assert [r["plan_key"] for r in harness.db.rows("vendor_plan_assignments")] == ["pro"]


def test_admin_cannot_assign_inactive_or_unknown_plan(harness: Harness) -> None:
    url = f"/admin/vendors/{VENDOR_A}/plan"
    assert harness.client.put(url, json={"plan_key": "legacy"}, headers=AUTH).status_code == 409
    assert harness.client.put(url, json={"plan_key": "nope"}, headers=AUTH).status_code == 404
    missing = f"/admin/vendors/{uuid4()}/plan"
    assert harness.client.put(missing, json={"plan_key": "pro"}, headers=AUTH).status_code == 404


def _future(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


@pytest.mark.parametrize(
    "body",
    [
        {"max_listings": 100, "expires_at": "2020-01-01T00:00:00+00:00", "reason": "x"},
        {"max_listings": 100, "unlimited_listings": True, "expires_at": "FUT", "reason": "x"},
        {"expires_at": "FUT", "reason": "nothing changes"},
        {"max_listings": 100, "expires_at": "FUT", "reason": "   "},
        {"max_images_per_listing": 9, "expires_at": "FUT", "reason": "x"},
        {"max_listings": 100, "expires_at": "2026-12-01T00:00:00", "reason": "naive"},
        {"max_listings": 100, "reason": "no expiry"},
        {"max_listings": 100, "expires_at": "FAR", "reason": "too long"},
    ],
)
def test_override_validation(harness: Harness, body: dict[str, Any]) -> None:
    if body.get("expires_at") == "FUT":
        body = {**body, "expires_at": _future()}
    if body.get("expires_at") == "FAR":
        body = {**body, "expires_at": _future(days=400)}
    response = harness.client.put(
        f"/admin/vendors/{VENDOR_A}/plan/override", json=body, headers=AUTH
    )
    assert response.status_code == 422, response.text
    assert harness.db.rows("vendor_plan_overrides") == []


def test_override_set_then_clear(harness: Harness) -> None:
    url = f"/admin/vendors/{VENDOR_A}/plan/override"
    response = harness.client.put(
        url,
        json={"unlimited_listings": True, "expires_at": _future(), "reason": "launch promo"},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["override"]["live"] and body["effective_max_listings"] is None
    cleared = harness.client.delete(url, headers=AUTH)
    assert cleared.status_code == 200 and cleared.json()["override"] is None
    assert [r["action"] for r in audit_rows(harness)] == [
        "vendor_plans.override.set",
        "vendor_plans.override.clear",
    ]
    assert harness.client.delete(url, headers=AUTH).status_code == 404


# ---------------------------------------------------------------------------
# Admin authz on the nested admin routes (the route matrix enumerates one router
# level, so these sub-routers are asserted here).
# ---------------------------------------------------------------------------
ADMIN_ROUTES = [
    ("get", "/admin/vendor-plans", None),
    ("post", "/admin/vendor-plans", NEW_PLAN),
    ("patch", "/admin/vendor-plans/free", {"price_ngwee": 1}),
    ("delete", "/admin/vendor-plans/legacy", None),
    ("get", f"/admin/vendors/{VENDOR_A}/plan", None),
    ("put", f"/admin/vendors/{VENDOR_A}/plan", {"plan_key": "pro"}),
    ("delete", f"/admin/vendors/{VENDOR_A}/plan/override", None),
]


@pytest.mark.parametrize(("method", "url", "body"), ADMIN_ROUTES)
@pytest.mark.parametrize(
    ("user_id", "roles"),
    [(VENDOR_USER_A, ("vendor",)), (VENDOR_USER_A, ("customer",)), (MODERATOR_ID, ("moderator",))],
)
def test_plan_admin_routes_deny_non_admins(
    harness: Harness, method: str, url: str, body: Any, user_id: str, roles: tuple[str, ...]
) -> None:
    harness.as_role(user_id, *roles)
    kwargs: dict[str, Any] = {"headers": AUTH}
    if body is not None:
        kwargs["json"] = body
    response = getattr(harness.client, method)(url, **kwargs)
    assert response.status_code == 403
    assert audit_rows(harness) == []


@pytest.mark.parametrize(("method", "url", "body"), ADMIN_ROUTES)
def test_plan_admin_routes_deny_anonymous(
    harness: Harness, method: str, url: str, body: Any
) -> None:
    harness.client.app.dependency_overrides.pop(get_current_user)  # type: ignore[attr-defined]
    kwargs: dict[str, Any] = {}
    if body is not None:
        kwargs["json"] = body
    response = getattr(harness.client, method)(url, **kwargs)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Canonical product photos (admin)
# ---------------------------------------------------------------------------
def test_admin_product_images_add_from_listing_and_by_id(harness: Harness) -> None:
    image_id = str(uuid4())
    harness.db.tables["listing_images"] = [
        {"id": image_id, "listing_id": LISTING_A, "cloudinary_public_id": "v/a1",
         "position": 1, "content_sha256": SHA_1},
    ]  # fmt: skip
    url = f"/admin/products/{PRODUCT}/images"
    response = harness.client.post(url, json={"listing_image_id": image_id}, headers=AUTH)
    assert response.status_code == 201, response.text
    assert response.json()["content_sha256"] == SHA_1 and response.json()["position"] == 1
    again = harness.client.post(url, json={"listing_image_id": image_id}, headers=AUTH)
    assert again.status_code == 409
    by_id = harness.client.post(url, json={"cloudinary_public_id": "catalog/p2"}, headers=AUTH)
    assert by_id.status_code == 201 and by_id.json()["position"] == 2
    listing = harness.client.get(url, headers=AUTH).json()
    assert listing["flag_enabled"] is True and len(listing["images"]) == 2
    removed = harness.client.delete(f"{url}/{by_id.json()['id']}", headers=AUTH)
    assert removed.status_code == 204


def test_admin_product_images_reject_foreign_listing_image(harness: Harness) -> None:
    image_id = str(uuid4())
    harness.db.tables["listing_images"] = [
        {"id": image_id, "listing_id": LISTING_A2, "cloudinary_public_id": "v/x", "position": 1}
    ]
    response = harness.client.post(
        f"/admin/products/{PRODUCT}/images", json={"listing_image_id": image_id}, headers=AUTH
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"listing_image_id": str(uuid4()), "cloudinary_public_id": "a/b"},
        {"cloudinary_public_id": "../etc"},
        {"cloudinary_public_id": "a/b", "content_sha256": "zz"},
    ],
)
def test_admin_product_images_validation(harness: Harness, body: dict[str, Any]) -> None:
    response = harness.client.post(f"/admin/products/{PRODUCT}/images", json=body, headers=AUTH)
    assert response.status_code == 422


def test_admin_product_images_cap_at_eight(harness: Harness) -> None:
    harness.db.tables["product_images"] = [
        {"id": str(uuid4()), "product_id": PRODUCT, "cloudinary_public_id": f"c/{n}",
         "position": n}
        for n in range(1, 9)
    ]  # fmt: skip
    response = harness.client.post(
        f"/admin/products/{PRODUCT}/images", json={"cloudinary_public_id": "c/9"}, headers=AUTH
    )
    assert response.status_code == 409


def test_moderator_can_manage_product_images_but_not_plans(harness: Harness) -> None:
    harness.as_role(MODERATOR_ID, "moderator")
    url = f"/admin/products/{PRODUCT}/images"
    assert harness.client.get(url, headers=AUTH).status_code == 200
    assert harness.client.get("/admin/vendor-plans", headers=AUTH).status_code == 403


# ---------------------------------------------------------------------------
# Vendor photos: plan cap, sha256 recording, dedup scoping
# ---------------------------------------------------------------------------
def _attach(h: Harness, listing: str, public_id: str, sha: str | None = None) -> Any:
    body: dict[str, Any] = {"cloudinary_public_id": public_id}
    if sha is not None:
        body["content_sha256"] = sha
    return h.client.post(f"/vendor/listings/{listing}/images", json=body, headers=AUTH)


def test_plan_photo_cap_prompts_upgrade(harness: Harness) -> None:
    harness.as_role(VENDOR_USER_A, "vendor")
    for n in range(3):
        assert _attach(harness, LISTING_A, f"v/a{n}").status_code == 200
    response = _attach(harness, LISTING_A, "v/a3")
    assert response.status_code == 400
    details = response.json()["error"]["details"]
    assert details["max_images"] == 3 and details["upgrade_available"] is True
    assert details["message_key"] == "vendor.plans.photoLimitReached"


def test_photo_cap_is_eight_when_plans_off(harness: Harness) -> None:
    harness.db.tables["feature_flags"][0]["enabled"] = False
    harness.as_role(VENDOR_USER_A, "vendor")
    for n in range(8):
        assert _attach(harness, LISTING_A, f"v/a{n}").status_code == 200
    response = _attach(harness, LISTING_A, "v/a8")
    assert response.status_code == 400
    assert response.json()["error"]["details"]["max_images"] == 8


def test_sha256_recorded_and_duplicate_refused(harness: Harness) -> None:
    harness.as_role(VENDOR_USER_A, "vendor")
    assert _attach(harness, LISTING_A, "v/a1", SHA_1.upper()).status_code == 200
    stored = harness.db.rows("listing_images")[0]
    assert stored["content_sha256"] == SHA_1  # normalised to lowercase
    duplicate = _attach(harness, LISTING_A, "v/a2", SHA_1)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_image"


def test_sha256_ignored_when_photos_flag_off(harness: Harness) -> None:
    harness.db.tables["feature_flags"][1]["enabled"] = False
    harness.as_role(VENDOR_USER_A, "vendor")
    assert _attach(harness, LISTING_A, "v/a1", SHA_1).status_code == 200
    assert "content_sha256" not in harness.db.rows("listing_images")[0]


def test_sha256_shape_validated(harness: Harness) -> None:
    harness.as_role(VENDOR_USER_A, "vendor")
    assert _attach(harness, LISTING_A, "v/a1", "g" * 64).status_code == 422


def _dedup(h: Harness, listing: str, sha: str) -> Any:
    return h.client.get(f"/vendor/listings/{listing}/images/dedup?sha256={sha}", headers=AUTH)


def test_dedup_flag_off(harness: Harness) -> None:
    harness.db.tables["feature_flags"][1]["enabled"] = False
    harness.as_role(VENDOR_USER_A, "vendor")
    assert _dedup(harness, LISTING_A, SHA_1).json() == {
        "enabled": False,
        "match": "none",
        "cloudinary_public_id": None,
    }


def test_dedup_scopes(harness: Harness) -> None:
    db = harness.db
    db.tables["listing_images"] = [
        {"id": str(uuid4()), "listing_id": LISTING_A2, "cloudinary_public_id": "v/own",
         "position": 1, "content_sha256": SHA_1},
        {"id": str(uuid4()), "listing_id": LISTING_B, "cloudinary_public_id": "v/b-secret",
         "position": 1, "content_sha256": SHA_2},
    ]  # fmt: skip
    harness.as_role(VENDOR_USER_A, "vendor")
    own = _dedup(harness, LISTING_A, SHA_1).json()
    assert own["match"] == "own" and own["cloudinary_public_id"] == "v/own"
    # Another vendor's photo with the same hash is never revealed.
    other = _dedup(harness, LISTING_A, SHA_2).json()
    assert other == {"enabled": True, "match": "none", "cloudinary_public_id": None}
    db.tables["product_images"] = [
        {"id": str(uuid4()), "product_id": PRODUCT, "cloudinary_public_id": "c/hero",
         "position": 1, "content_sha256": SHA_2},
    ]  # fmt: skip
    canonical = _dedup(harness, LISTING_A, SHA_2).json()
    assert canonical["match"] == "canonical" and canonical["cloudinary_public_id"] == "c/hero"
    # The standalone listing has no product, so the canonical photo does not apply.
    assert _dedup(harness, LISTING_A2, SHA_2).json()["match"] == "none"
    assert _dedup(harness, LISTING_A2, SHA_1).json()["match"] == "listing"


def test_dedup_on_another_vendors_listing_is_forbidden(harness: Harness) -> None:
    harness.as_role(VENDOR_USER_A, "vendor")
    assert _dedup(harness, LISTING_B, SHA_1).status_code == 403


def test_dedup_rejects_bad_hash(harness: Harness) -> None:
    harness.as_role(VENDOR_USER_A, "vendor")
    assert _dedup(harness, LISTING_A, "abc").status_code == 422


def test_find_duplicate_prefers_listing_then_canonical_then_own() -> None:
    db = make_db()
    db.tables["listing_images"] = [
        {"id": "1", "listing_id": LISTING_A, "cloudinary_public_id": "v/here",
         "content_sha256": SHA_1},
    ]  # fmt: skip
    db.tables["product_images"] = [
        {"product_id": PRODUCT, "cloudinary_public_id": "c/1", "content_sha256": SHA_1}
    ]
    result = find_duplicate(
        db, vendor_id=VENDOR_A, listing_id=LISTING_A, product_id=PRODUCT, sha256=SHA_1
    )
    assert result.match == "listing"


# ---------------------------------------------------------------------------
# Galleries + seeding
# ---------------------------------------------------------------------------
def test_merge_listing_gallery_keeps_own_photos_and_caps_at_eight() -> None:
    canonical = [f"c/{n}" for n in range(6)]
    own = [f"v/{n}" for n in range(5)]
    merged = merge_listing_gallery(own, canonical)
    assert len(merged) == 8
    assert [pid for pid, src in merged if src == "listing"] == own
    assert [pid for pid, _ in merged[:3]] == ["c/0", "c/1", "c/2"]
    assert merge_listing_gallery([], canonical) == [(pid, "canonical") for pid in canonical]
    full = [f"v/{n}" for n in range(8)]
    assert all(src == "listing" for _, src in merge_listing_gallery(full, canonical))
    assert merge_listing_gallery(["c/0"], ["c/0", "c/1"]) == [
        ("c/1", "canonical"),
        ("c/0", "listing"),
    ]


def test_pdp_gallery_leads_with_canonical_and_dedupes() -> None:
    listing_gallery = [
        ProductImageResponse(public_id="v/1", position=1, listing_id=LISTING_A),
        ProductImageResponse(public_id="c/1", position=2, listing_id=LISTING_A),
    ]
    merged = _merge_canonical_gallery(["c/1", "c/2"], listing_gallery, primary_listing_id=LISTING_A)
    assert [(i.public_id, i.source, i.position) for i in merged] == [
        ("c/1", "canonical", 1),
        ("c/2", "canonical", 2),
        ("v/1", "listing", 3),
    ]


def test_seed_canonical_images_is_idempotent_and_ordered() -> None:
    db = make_db()
    db.tables["listing_images"] = [
        {"id": "b1", "listing_id": LISTING_B, "cloudinary_public_id": "v/b1", "position": 1},
        {"id": "a2", "listing_id": LISTING_A, "cloudinary_public_id": "v/a2", "position": 2},
        {"id": "a1", "listing_id": LISTING_A, "cloudinary_public_id": "v/a1", "position": 1,
         "content_sha256": SHA_1},
        {"id": "dup", "listing_id": LISTING_B, "cloudinary_public_id": "v/a1", "position": 2},
    ]  # fmt: skip
    assert seed_canonical_images_from_listings(db, PRODUCT) == 3
    rows = db.rows("product_images")
    assert [(r["cloudinary_public_id"], r["position"]) for r in rows] == [
        ("v/a1", 1),
        ("v/a2", 2),
        ("v/b1", 3),
    ]
    assert rows[0]["content_sha256"] == SHA_1 and rows[0]["source_listing_image_id"] == "a1"
    assert seed_canonical_images_from_listings(db, PRODUCT) == 0


def test_seed_caps_at_six(monkeypatch: pytest.MonkeyPatch) -> None:
    db = make_db()
    db.tables["listing_images"] = [
        {"id": str(n), "listing_id": LISTING_A, "cloudinary_public_id": f"v/{n}", "position": n}
        for n in range(1, 9)
    ]
    assert seed_canonical_images_from_listings(db, PRODUCT) == 6
    assert canonical_photos.MAX_SEEDED_CANONICAL_IMAGES == 6


def test_catalog_card_falls_back_to_canonical_photo_only_when_flag_on() -> None:
    from app.routers.catalog import _fill_canonical_card_images

    db = make_db(photos_on=False)
    db.tables["product_images"] = [
        {"product_id": PRODUCT, "cloudinary_public_id": "c/hero", "position": 1}
    ]
    enriched: dict[str, dict[str, Any]] = {
        LISTING_A: {"image_public_id": None, "product": {"id": PRODUCT}},
        LISTING_B: {"image_public_id": "v/own", "product": {"id": PRODUCT}},
        LISTING_A2: {"image_public_id": None, "product": None},
    }
    _fill_canonical_card_images(db, enriched)
    assert enriched[LISTING_A]["image_public_id"] is None
    db.tables["feature_flags"][1]["enabled"] = True
    _fill_canonical_card_images(db, enriched)
    assert enriched[LISTING_A]["image_public_id"] == "c/hero"
    assert enriched[LISTING_B]["image_public_id"] == "v/own"
    assert enriched[LISTING_A2]["image_public_id"] is None


def test_catalog_card_fallback_makes_no_query_when_all_cards_have_photos() -> None:
    from app.routers.catalog import _fill_canonical_card_images

    db = make_db()
    _fill_canonical_card_images(db, {LISTING_A: {"image_public_id": "v/1", "product": {"id": "p"}}})
    assert db.calls == []


def test_billing_seam_refuses_to_charge() -> None:
    with pytest.raises(AppError) as excinfo:
        get_subscription_gateway().request_charge(
            SubscriptionCharge(VENDOR_A, "starter", 4900, "sub-x-202611")
        )
    assert excinfo.value.code == "billing_not_available"
