"""Multi-branch businesses — API layer (no Postgres).

The database rules (limits, dedup, state machine, RLS) are proven in
tests/rls/test_multi_branch_rls.py. This module covers what the API adds on top:
the acting-branch scope, flag gating, ownership (another owner's ids -> 404),
validation, the friendly sibling-distance pre-check, DB-refusal mapping, the
evidence path pin, admin decisions (audit + refusals), rate limits, and the
customer storefront's business summary.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from typing import Any

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.routers import admin_branches, directory, vendor_branches
from app.services.branches import context
from app.services.branches.rules import map_db_error, shop_allowance
from fastapi.testclient import TestClient
from tests.test_vendor_plans import FakeDb, FakeQuery, FakeService

ADMIN_ID = "00000000-0000-0000-0000-0000000a0001"
OWNER_A = "11111111-1111-1111-1111-111111111111"
OWNER_B = "22222222-2222-2222-2222-222222222222"
BIZ_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BIZ_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
BRANCH_A2 = "aaaaaaaa-0000-0000-0000-0000000000a2"
FLAG_ID = "ffffffff-0000-0000-0000-0000000000f1"
AUTH = {"Authorization": "Bearer t"}


class BranchQuery(FakeQuery):
    def neq(self, column: str, value: Any) -> BranchQuery:
        self.filters.append(("neq", column, value))
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        plain = [f for f in self.filters if f[0] != "neq"]
        for _op, column, value in (f for f in self.filters if f[0] == "neq"):
            if row.get(column) == value:
                return False
        saved, self.filters = self.filters, plain
        try:
            return super()._match(row)
        finally:
            self.filters = saved


class BranchDb(FakeDb):
    def __init__(self) -> None:
        super().__init__()
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_error: Exception | None = None
        self.rpc_result: Any = None

    def table(self, name: str) -> BranchQuery:
        return BranchQuery(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        self.rpc_calls.append((name, params))
        db = self

        class _Call:
            def execute(self) -> Any:
                if db.rpc_error is not None:
                    raise db.rpc_error
                from unittest.mock import MagicMock

                return MagicMock(data=db.rpc_result)

        return _Call()


class DbRefusal(Exception):
    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.details = details


def make_db(*, flag_on: bool = True) -> BranchDb:
    db = BranchDb()
    db.tables["feature_flags"] = [{"flag": "multi_branch", "enabled": flag_on}]
    db.tables["platform_config"] = [{"key": "branch_min_sibling_distance_m", "value": 50}]
    db.tables["vendor_businesses"] = [
        {"id": BIZ_A, "owner_user_id": OWNER_A, "legal_name": "Lusaka Electronics Ltd",
         "registration_type": "company", "pacra_number": "120190012345",
         "pacra_cert_path": f"businesses/{BIZ_A}/pacra-1.jpg", "status": "active",
         "created_at": "2026-11-01"},
        {"id": BIZ_B, "owner_user_id": OWNER_B, "legal_name": "Zed Fashion",
         "registration_type": "unspecified", "pacra_number": None, "status": "active",
         "created_at": "2026-11-01"},
    ]  # fmt: skip
    db.tables["vendors"] = [
        {"id": BIZ_A, "business_id": BIZ_A, "owner_user_id": OWNER_A, "slug": "lusaka-electronics",
         "display_name": "Lusaka Electronics", "status": "active", "branch_status": "approved",
         "branch_kind": "physical", "is_primary_branch": True, "created_at": "2026-11-01",
         "vendor_locations": [{"lat": -15.4167, "lng": 28.2833, "landmark": "East Park"}]},
        {"id": BRANCH_A2, "business_id": BIZ_A, "owner_user_id": OWNER_A, "slug": "le-manda-hill",
         "display_name": "LE Manda Hill", "status": "draft", "branch_status": "draft",
         "branch_kind": "physical", "is_primary_branch": False, "created_at": "2026-11-10",
         "vendor_locations": [{"lat": -15.3990, "lng": 28.3060, "landmark": "Manda Hill"}]},
        {"id": BIZ_B, "business_id": BIZ_B, "owner_user_id": OWNER_B, "slug": "zed-fashion",
         "display_name": "Zed Fashion", "status": "active", "branch_status": "approved",
         "branch_kind": "physical", "is_primary_branch": True, "created_at": "2026-11-01"},
    ]  # fmt: skip
    db.tables["vendor_plans"] = [
        {"key": "free", "name": "Free", "is_default": True, "included_shops": 1,
         "extra_shop_price_ngwee": None, "staff_seats": 0},
        {"key": "business", "name": "Business", "is_default": False, "included_shops": 1,
         "extra_shop_price_ngwee": 8900, "staff_seats": 5},
    ]  # fmt: skip
    db.tables["vendor_plan_assignments"] = [{"vendor_id": BIZ_A, "plan_key": "business"}]
    db.tables["kyc_records"] = [{"id": "k1", "vendor_id": BIZ_A, "status": "approved"}]
    db.tables["vendor_branch_flags"] = []
    db.tables["vendor_branch_events"] = []
    db.tables["vendor_branch_evidence"] = []
    db.tables["vendor_business_staff"] = []
    db.tables["user_roles"] = []
    return db


class Harness:
    def __init__(self, db: BranchDb, client: TestClient) -> None:
        self.db = db
        self.client = client
        self.user = CurrentUser(id=OWNER_A, roles=frozenset({"vendor"}), token="t")
        self.rate_allowed = True
        self.rate_calls: list[str] = []

    def as_user(self, user_id: str, *roles: str) -> Harness:
        self.user = CurrentUser(id=user_id, roles=frozenset(roles), token="t")
        return self


@pytest.fixture
def h(monkeypatch: pytest.MonkeyPatch) -> Generator[Harness, None, None]:
    app = create_app()
    holder: dict[str, Harness] = {}

    async def current_user() -> CurrentUser:
        return holder["h"].user

    def service_dep() -> Generator[FakeService, None, None]:
        yield FakeService(holder["h"].db)

    def fake_bump(**kwargs: Any) -> tuple[bool, int]:
        holder["h"].rate_calls.append(kwargs["key"])
        return (holder["h"].rate_allowed, 0 if holder["h"].rate_allowed else 30)

    monkeypatch.setattr(vendor_branches, "bump_rate_counter", fake_bump)
    monkeypatch.setattr(admin_branches, "bump_rate_counter", fake_bump)
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client", lambda: FakeService(holder["h"].db)
    )
    monkeypatch.setattr(
        "app.core.auth.get_supabase_service_client", lambda: FakeService(holder["h"].db)
    )
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_supabase_client] = service_dep
    with TestClient(app, raise_server_exceptions=False) as client:
        holder["h"] = Harness(make_db(), client)
        yield holder["h"]
    app.dependency_overrides.clear()


def _branch_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "display_name": "LE Cairo Road",
        "branch_kind": "physical",
        "location": {"lat": -15.4200, "lng": 28.2800, "landmark": "Cairo Road, near Findeco"},
        "contact_phone": "0971234567",
        "payout_msisdn": "0961234567",
        "payout_rail": "mtn",
        "hours": {"mon": {"open": "08:00", "close": "18:00"}},
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Acting-branch scope
# ---------------------------------------------------------------------------
def test_branch_header_parsing_rejects_garbage() -> None:
    assert context.parse_branch_header(None) is None
    assert context.parse_branch_header("not-a-uuid") is None
    assert context.parse_branch_header("'; drop table vendors;--") is None
    assert context.parse_branch_header(BRANCH_A2.upper()) == BRANCH_A2
    assert context.parse_branch_header(" Primary ") == context.PRIMARY


def test_primary_header_narrows_to_the_primary_shop() -> None:
    db = make_db()
    token = context.set_acting_branch_id("primary")
    try:
        scoped = context.scope_owner_vendor_query(
            db.table("vendors").select("id").eq("owner_user_id", OWNER_A)
        )
        assert [row["id"] for row in scoped.execute().data] == [BIZ_A]
    finally:
        context.reset_acting_branch_id(token)


def test_scope_only_narrows_when_header_present() -> None:
    db = make_db()
    query = db.table("vendors").select("id").eq("owner_user_id", OWNER_A)
    assert context.scope_owner_vendor_query(query).filters == [("eq", "owner_user_id", OWNER_A)]
    token = context.set_acting_branch_id(BRANCH_A2)
    try:
        scoped = context.scope_owner_vendor_query(
            db.table("vendors").select("id").eq("owner_user_id", OWNER_A)
        )
        # Narrowing keeps the owner filter: another owner's branch id can never match.
        assert scoped.filters == [("eq", "owner_user_id", OWNER_A), ("eq", "id", BRANCH_A2)]
        cross = context.scope_owner_vendor_query(
            db.table("vendors").select("id").eq("owner_user_id", OWNER_B)
        )
        assert cross.execute().data == []
    finally:
        context.reset_acting_branch_id(token)


def test_middleware_sets_and_resets_acting_branch() -> None:
    seen: list[str | None] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        seen.append(context.acting_branch_id())

    middleware = context.ActingBranchMiddleware(app)
    headers = [(b"x-vendor-branch", BRANCH_A2.encode())]
    noop: Any = None  # the test app never calls receive/send
    asyncio.run(middleware({"type": "http", "headers": headers}, noop, noop))
    asyncio.run(
        middleware({"type": "http", "headers": [(b"x-vendor-branch", b"nope")]}, noop, noop)
    )
    assert seen == [BRANCH_A2, None]
    assert context.acting_branch_id() is None


# ---------------------------------------------------------------------------
# Shop allowance mirror + error mapping
# ---------------------------------------------------------------------------
def test_shop_allowance_matrix() -> None:
    free = {"key": "free", "included_shops": 1, "extra_shop_price_ngwee": None}
    business = {"key": "business", "included_shops": 1, "extra_shop_price_ngwee": 8900}
    chain = {"key": "chain", "included_shops": 5, "extra_shop_price_ngwee": 15000}
    unlimited = {"key": "enterprise_plus", "included_shops": None, "extra_shop_price_ngwee": None}
    no_pacra = shop_allowance(pacra_number=None, plan=chain, used=1)
    assert not no_pacra.can_add and no_pacra.blocked_reason == "unregistered"
    assert shop_allowance(pacra_number="X1", plan=free, used=1).blocked_reason == "plan"
    addon = shop_allowance(pacra_number="X1", plan=business, used=1)
    assert addon.can_add and addon.next_billing_role == "addon" and addon.next_price_ngwee == 8900
    included = shop_allowance(pacra_number="X1", plan=chain, used=4)
    assert included.next_billing_role == "included" and included.next_price_ngwee == 0
    assert shop_allowance(pacra_number="X1", plan=chain, used=5).next_price_ngwee == 15000
    assert shop_allowance(pacra_number="X1", plan=unlimited, used=400).limit is None


@pytest.mark.parametrize(
    ("message", "status", "key"),
    [
        ("branch_limit_unregistered", 409, "vendor.branches.errors.unregisteredLimit"),
        ("payout_msisdn_other_owner", 409, "vendor.branches.errors.payoutTaken"),
        ("branch_too_close_to_sibling", 422, "vendor.branches.errors.tooClose"),
        ("branch_open_flags", 409, "admin.branches.errors.openFlags"),
        (
            'duplicate key value violates unique constraint "vendor_businesses_pacra_number_key"',
            409,
            "vendor.branches.errors.pacraTaken",
        ),
    ],
)
def test_db_refusals_map_to_stable_errors(message: str, status: int, key: str) -> None:
    mapped = map_db_error(DbRefusal(message))
    assert mapped is not None
    assert mapped.http_status == status
    assert mapped.details["message_key"] == key


def test_unknown_db_error_is_not_swallowed() -> None:
    assert map_db_error(DbRefusal("connection reset")) is None


# ---------------------------------------------------------------------------
# Vendor endpoints
# ---------------------------------------------------------------------------
def test_list_flag_off_hides_switcher(h: Harness) -> None:
    h.db = make_db(flag_on=False)
    response = h.client.get("/vendor/businesses", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "businesses": []}


def test_list_returns_only_my_businesses_with_allowance(h: Harness) -> None:
    response = h.client.get("/vendor/businesses", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert [b["id"] for b in body["businesses"]] == [BIZ_A]
    business = body["businesses"][0]
    assert [b["id"] for b in business["branches"]] == [BIZ_A, BRANCH_A2]
    assert business["allowance"]["next_billing_role"] == "addon"
    assert business["allowance"]["next_price_ngwee"] == 8900
    assert business["owner_kyc_approved"] is True


def test_list_reads_plan_kyc_and_notes_concurrently(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reads that only need the branch rows must not queue behind each other."""
    import threading
    import time as _time

    import app.routers.vendor_branches as module

    threads: dict[str, str] = {}
    real_plan, real_notes = module._business_plan, module._latest_notes

    def slow_plan(client: Any, branches: list[dict[str, Any]]) -> Any:
        threads["plan"] = threading.current_thread().name
        _time.sleep(0.05)
        return real_plan(client, branches)

    def slow_notes(client: Any, ids: list[str]) -> Any:
        threads["notes"] = threading.current_thread().name
        _time.sleep(0.05)
        return real_notes(client, ids)

    monkeypatch.setattr(module, "_business_plan", slow_plan)
    monkeypatch.setattr(module, "_latest_notes", slow_notes)

    response = h.client.get("/vendor/businesses", headers=AUTH)

    assert response.status_code == 200
    assert threads["plan"] != threads["notes"]
    business = response.json()["businesses"][0]
    assert business["allowance"]["next_price_ngwee"] == 8900
    assert business["owner_kyc_approved"] is True


def test_customer_role_cannot_list_businesses(h: Harness) -> None:
    h.as_user(OWNER_A, "customer")
    assert h.client.get("/vendor/businesses", headers=AUTH).status_code == 403


def test_other_owners_business_is_not_found(h: Harness) -> None:
    h.db.rpc_result = {"id": BRANCH_A2}
    response = h.client.post(
        f"/vendor/businesses/{BIZ_B}/branches", json=_branch_body(), headers=AUTH
    )
    assert response.status_code == 404
    assert h.db.rpc_calls == []
    staff = h.client.get(f"/vendor/businesses/{BIZ_B}/staff", headers=AUTH)
    assert staff.status_code == 404


def test_other_owners_branch_is_not_found_for_evidence(h: Harness) -> None:
    h.as_user(OWNER_B, "vendor")
    response = h.client.put(
        f"/vendor/businesses/{BIZ_A}/branches/{BRANCH_A2}/evidence",
        json={
            "kind": "storefront_photo",
            "storage_path": f"branches/{BIZ_A}/{BRANCH_A2}/storefront_photo-1.jpg",
        },
        headers=AUTH,
    )
    assert response.status_code == 404


def test_create_branch_flag_off_is_404(h: Harness) -> None:
    h.db.tables["feature_flags"][0]["enabled"] = False
    response = h.client.post(
        f"/vendor/businesses/{BIZ_A}/branches", json=_branch_body(), headers=AUTH
    )
    assert response.status_code == 404
    assert response.json()["error"]["details"]["message_key"] == "vendor.branches.errors.disabled"


@pytest.mark.parametrize(
    "overrides",
    [
        {"payout_msisdn": "+44 7700 900123"},  # not a Zambian mobile
        {"contact_phone": "12"},
        {"location": None},  # physical shop without a location
        {"location": {"lat": 51.5, "lng": -0.12, "landmark": "London"}},  # outside Zambia
        {"payout_rail": "paypal"},
        {"hours": {"mon": {"open": "25:00"}}},
        {"unexpected": True},  # strict model
    ],
)
def test_create_branch_validation(h: Harness, overrides: dict[str, Any]) -> None:
    response = h.client.post(
        f"/vendor/businesses/{BIZ_A}/branches", json=_branch_body(**overrides), headers=AUTH
    )
    assert response.status_code == 422
    assert h.db.rpc_calls == []


def test_create_branch_too_close_to_sibling_precheck(h: Harness) -> None:
    near = {"lat": -15.41672, "lng": 28.28332, "landmark": "East Park, next door"}
    response = h.client.post(
        f"/vendor/businesses/{BIZ_A}/branches", json=_branch_body(location=near), headers=AUTH
    )
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert details["message_key"] == "vendor.branches.errors.tooClose"
    assert details["min_m"] == 50 and details["nearest_m"] < 50
    assert h.db.rpc_calls == []


def test_create_branch_maps_db_refusal(h: Harness) -> None:
    h.db.rpc_error = DbRefusal("payout_msisdn_other_owner")
    response = h.client.post(
        f"/vendor/businesses/{BIZ_A}/branches", json=_branch_body(), headers=AUTH
    )
    assert response.status_code == 409
    assert (
        response.json()["error"]["details"]["message_key"] == "vendor.branches.errors.payoutTaken"
    )


def test_create_branch_success_normalises_and_rate_limits(h: Harness) -> None:
    h.db.rpc_result = {
        "id": BRANCH_A2, "plan_key": "business", "branch_billing_role": "addon",
        "addon_price_ngwee": 8900, "flags_opened": 1,
    }  # fmt: skip
    response = h.client.post(
        f"/vendor/businesses/{BIZ_A}/branches", json=_branch_body(), headers=AUTH
    )
    assert response.status_code == 201, response.text
    assert response.json()["addon_price_ngwee"] == 8900
    name, params = h.db.rpc_calls[0]
    assert name == "create_vendor_branch"
    assert params["p_owner"] == OWNER_A
    assert params["p_payload"]["payout_msisdn"] == "260961234567"
    assert params["p_payload"]["slug"] == "le-cairo-road"
    assert h.rate_calls == [f"branches:{OWNER_A}"]


def test_create_branch_rate_limited(h: Harness) -> None:
    h.rate_allowed = False
    response = h.client.post(
        f"/vendor/businesses/{BIZ_A}/branches", json=_branch_body(), headers=AUTH
    )
    assert response.status_code == 429
    assert h.db.rpc_calls == []


def test_evidence_path_is_pinned_to_the_branch_folder(h: Harness) -> None:
    response = h.client.put(
        f"/vendor/businesses/{BIZ_A}/branches/{BRANCH_A2}/evidence",
        json={
            "kind": "storefront_photo",
            "storage_path": f"branches/{BIZ_B}/{BIZ_B}/storefront_photo-1.jpg",
        },
        headers=AUTH,
    )
    assert response.status_code == 422
    assert (
        response.json()["error"]["details"]["message_key"] == "vendor.branches.errors.evidencePath"
    )


def test_premises_proof_needs_proof_type(h: Harness) -> None:
    response = h.client.put(
        f"/vendor/businesses/{BIZ_A}/branches/{BRANCH_A2}/evidence",
        json={
            "kind": "premises_proof",
            "storage_path": f"branches/{BIZ_A}/{BRANCH_A2}/premises_proof-1.jpg",
        },
        headers=AUTH,
    )
    assert response.status_code == 422


def test_evidence_recorded_and_rescanned(h: Harness) -> None:
    h.db.rpc_result = 2
    response = h.client.put(
        f"/vendor/businesses/{BIZ_A}/branches/{BRANCH_A2}/evidence",
        json={
            "kind": "premises_proof",
            "proof_type": "council_permit",
            "storage_path": f"branches/{BIZ_A}/{BRANCH_A2}/premises_proof-1.jpg",
            "content_sha256": "a" * 64,
        },
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    assert response.json()["duplicate_flags"] == 2
    assert h.db.rows("vendor_branch_evidence")[0]["proof_type"] == "council_permit"
    assert h.db.rpc_calls == [("vendor_branch_dedup_scan", {"p_vendor_id": BRANCH_A2})]


def test_submit_maps_missing_evidence(h: Harness) -> None:
    h.db.rpc_error = DbRefusal("branch_evidence_required")
    response = h.client.post(
        f"/vendor/businesses/{BIZ_A}/branches/{BRANCH_A2}/submit", headers=AUTH
    )
    assert response.status_code == 409


def test_registered_business_needs_pacra_and_certificate(h: Harness) -> None:
    h.as_user(OWNER_B, "vendor")
    response = h.client.patch(
        f"/vendor/businesses/{BIZ_B}", json={"registration_type": "company"}, headers=AUTH
    )
    assert response.status_code == 422
    assert (
        response.json()["error"]["details"]["message_key"] == "vendor.branches.errors.pacraRequired"
    )
    bad_path = h.client.patch(
        f"/vendor/businesses/{BIZ_B}",
        json={"registration_type": "company", "pacra_number": "1201 9001 9999",
              "pacra_cert_path": f"businesses/{BIZ_A}/pacra-1.jpg"},
        headers=AUTH,
    )  # fmt: skip
    assert bad_path.status_code == 422


def test_unregistered_with_pacra_number_is_invalid(h: Harness) -> None:
    response = h.client.patch(
        f"/vendor/businesses/{BIZ_A}",
        json={"registration_type": "unregistered", "pacra_number": "120190012345"},
        headers=AUTH,
    )
    assert response.status_code == 422


def test_cannot_downgrade_to_unregistered_with_two_shops(h: Harness) -> None:
    response = h.client.patch(
        f"/vendor/businesses/{BIZ_A}", json={"registration_type": "unregistered"}, headers=AUTH
    )
    assert response.status_code == 409
    assert (
        response.json()["error"]["details"]["message_key"]
        == "vendor.branches.errors.unregisteredLimit"
    )


def test_staff_invite_maps_seat_limit(h: Harness) -> None:
    original = BranchQuery.execute

    def refuse(self: BranchQuery) -> Any:
        if self.table == "vendor_business_staff" and self.op == "insert":
            raise DbRefusal("staff_seat_limit")
        return original(self)

    BranchQuery.execute = refuse  # type: ignore[method-assign,assignment]
    try:
        response = h.client.post(
            f"/vendor/businesses/{BIZ_A}/staff",
            json={"display_name": "Mutale", "invite_msisdn": "0971112233"},
            headers=AUTH,
        )
    finally:
        BranchQuery.execute = original  # type: ignore[method-assign]
    assert response.status_code == 409
    assert (
        response.json()["error"]["details"]["message_key"]
        == "vendor.branches.errors.staffSeatLimit"
    )


def test_staff_branch_scope_must_be_own_branches(h: Harness) -> None:
    response = h.client.post(
        f"/vendor/businesses/{BIZ_A}/staff",
        json={"display_name": "Mutale", "invite_msisdn": "0971112233", "branch_ids": [BIZ_B]},
        headers=AUTH,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------
def _pending(h: Harness) -> None:
    h.db.tables["vendors"][1]["branch_status"] = "pending_review"


def test_vendor_cannot_reach_admin_queue(h: Harness) -> None:
    assert h.client.get("/admin/branches", headers=AUTH).status_code == 403
    response = h.client.post(f"/admin/branches/{BRANCH_A2}/approve", json={}, headers=AUTH)
    assert response.status_code == 403


def test_admin_queue_lists_pending_non_primary(h: Harness) -> None:
    _pending(h)
    h.as_user(ADMIN_ID, "admin")
    response = h.client.get("/admin/branches", headers=AUTH)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [BRANCH_A2]


def test_admin_approve_records_audit(h: Harness) -> None:
    _pending(h)
    h.as_user(ADMIN_ID, "admin")
    h.db.rpc_result = {"id": BRANCH_A2, "to": "approved"}
    response = h.client.post(
        f"/admin/branches/{BRANCH_A2}/approve", json={"note": "ok"}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    assert h.db.rpc_calls[0][0] == "transition_vendor_branch"
    assert h.db.rpc_calls[0][1]["p_to"] == "approved"
    audits = h.db.rows("audit_log")
    assert len(audits) == 1 and audits[0]["action"] == "branches.approved"
    assert h.rate_calls == [ADMIN_ID]


def test_admin_approve_blocked_by_open_flags(h: Harness) -> None:
    _pending(h)
    h.as_user(ADMIN_ID, "admin")
    h.db.rpc_error = DbRefusal("branch_open_flags")
    response = h.client.post(f"/admin/branches/{BRANCH_A2}/approve", json={}, headers=AUTH)
    assert response.status_code == 409
    assert h.db.rows("audit_log") == []


@pytest.mark.parametrize("path", ["request-info", "reject"])
def test_admin_info_and_reject_need_a_note(h: Harness, path: str) -> None:
    h.as_user(ADMIN_ID, "admin")
    response = h.client.post(
        f"/admin/branches/{BRANCH_A2}/{path}", json={"note": "  "}, headers=AUTH
    )
    assert response.status_code == 422
    assert h.db.rpc_calls == []


def _flag(kind: str) -> dict[str, Any]:
    return {
        "id": FLAG_ID, "vendor_id": BRANCH_A2, "kind": kind, "matched_vendor_id": BIZ_A,
        "score": 1, "details": {}, "status": "open", "created_at": "2026-11-15",
    }  # fmt: skip


def test_cross_owner_payout_flag_can_never_be_cleared(h: Harness) -> None:
    h.as_user(ADMIN_ID, "admin")
    h.db.tables["vendor_branch_flags"] = [_flag("payout_other_owner")]
    response = h.client.post(
        f"/admin/branches/flags/{FLAG_ID}/resolve",
        json={"resolution": "cleared", "note": "looks fine"},
        headers=AUTH,
    )
    assert response.status_code == 409
    assert h.db.rows("vendor_branch_flags")[0]["status"] == "open"


def test_clearing_same_owner_payout_flag_lifts_hold(h: Harness) -> None:
    h.as_user(ADMIN_ID, "admin")
    h.db.tables["vendor_branch_flags"] = [_flag("payout_shared_same_owner")]
    h.db.tables["vendors"][1]["payout_hold_until"] = "2036-11-15T00:00:00+00:00"
    response = h.client.post(
        f"/admin/branches/flags/{FLAG_ID}/resolve",
        json={"resolution": "cleared", "note": "same owner, one till"},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    assert h.db.tables["vendors"][1]["payout_hold_until"] is None
    audit = h.db.rows("audit_log")[0]
    assert audit["action"] == "branches.flag.cleared"
    assert audit["after"]["payout_hold_lifted"] is True


def test_resolving_twice_conflicts(h: Harness) -> None:
    h.as_user(ADMIN_ID, "admin")
    flag = _flag("name_similar")
    flag["status"] = "cleared"
    h.db.tables["vendor_branch_flags"] = [flag]
    response = h.client.post(
        f"/admin/branches/flags/{FLAG_ID}/resolve",
        json={"resolution": "confirmed", "note": "dup"},
        headers=AUTH,
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Customer storefront: parent business + other branches
# ---------------------------------------------------------------------------
def test_business_summary_lists_live_siblings_only() -> None:
    db = make_db()
    db.tables["vendors"][1].update({"status": "active", "branch_status": "approved"})
    summary = directory._business_summary(db, {"id": BIZ_A, "business_id": BIZ_A})
    assert summary is not None
    assert summary.name == "Lusaka Electronics Ltd"
    assert [b.slug for b in summary.other_branches] == ["le-manda-hill"]
    assert summary.other_branches[0].landmark == "Manda Hill"


def test_business_summary_absent_when_flag_off_or_single_shop() -> None:
    db = make_db(flag_on=False)
    db.tables["vendors"][1].update({"status": "active", "branch_status": "approved"})
    assert directory._business_summary(db, {"id": BIZ_A, "business_id": BIZ_A}) is None
    single = make_db()  # sibling still a draft
    assert directory._business_summary(single, {"id": BIZ_A, "business_id": BIZ_A}) is None
    assert directory._business_summary(single, {"id": BIZ_A}) is None
