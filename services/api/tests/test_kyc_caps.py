from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.errors import AppError
from app.main import create_app
from app.services.kyc.badge import (
    PreferredBadgeJob,
    apply_preferred_badge_for_vendor,
    evaluate_preferred_badge,
)
from app.services.kyc.caps import (
    OrderCapChecker,
    VendorCapLimits,
    VendorQuota,
    clear_vendor_cap_cache,
    enforce_first_order_cap,
    enforce_listing_cap,
    enforce_payout_velocity,
    load_vendor_quota,
)
from app.services.kyc.name_match import MomoNameMatchResult, score_name_match
from app.services.kyc.state_machine import (
    KycApplicationStatus,
    KycStateMachine,
    KycTransitionError,
    ServiceRoleClient,
    transition_approve,
    transition_reject,
    transition_submit,
    write_kyc_audit_log,
)
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
KYC_RECORD_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
VALID_TOKEN = "valid.jwt.token"
COD_CAP_NGWEE = 50_000


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._count_exact = False
        self._selected_columns = "*"

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        self._selected_columns = columns
        if count == "exact":
            self._count_exact = True
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("gte", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = f"{len(self._parent.rows):08x}-fake-fake-fake-fakefakefake"
            self._parent.rows.append(row)
            return MagicMock(data=[row], count=None)

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for _index, row in enumerate(self._parent.rows):
                if all(
                    row.get(column) == value
                    for op, column, value in self._filters
                    if op == "eq"
                ):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated, count=len(updated))

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        count = len(rows) if self._count_exact else None
        return MagicMock(data=rows, count=count)

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = rows
        for op, column, value in self._filters:
            if op == "eq":
                filtered = [row for row in filtered if row.get(column) == value]
            elif op == "in":
                allowed = set(value)
                filtered = [row for row in filtered if row.get(column) in allowed]
            elif op == "gte":
                filtered = [
                    row for row in filtered if str(row.get(column, "")) >= str(value)
                ]
        return filtered


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "kyc_records": FakeTable(),
            "audit_log": FakeTable(),
            "vendor_quotas": FakeTable(),
            "platform_config": FakeTable(),
            "vendor_listings": FakeTable(),
            "orders": FakeTable(),
            "payouts": FakeTable(),
            "disputes": FakeTable(),
            "reviews": FakeTable(),
            "order_items": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _seed_t1_vendor(fake: FakeSupabaseClient, *, kyc_tier: int = 1, status: str = "draft") -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": USER_ID,
            "status": status,
            "kyc_tier": kyc_tier,
            "preferred_badge": False,
        }
    )
    if kyc_tier is not None and status == "active":
        fake.tables["kyc_records"].rows.append(
            {
                "id": f"kyc-{VENDOR_ID}-{kyc_tier}",
                "vendor_id": VENDOR_ID,
                "tier": kyc_tier,
                "status": "approved",
                "doc_storage_paths": ["kyc/seed.jpg"],
                "momo_name_match": {"matched": True},
                "reviewed_by": USER_ID,
                "reviewed_at": "2026-07-01T00:00:00Z",
                "decision_reason": "seed",
            }
        )
    fake.tables["vendor_quotas"].rows.extend(
        [
            {
                "tier": 1,
                "max_listings": 30,
                "first_orders_cap_ngwee": COD_CAP_NGWEE,
                "first_orders_count": 5,
                "payout_velocity": {"max_payouts_per_day": 1, "max_amount_ngwee_per_day": 100_000},
            },
            {
                "tier": 2,
                "max_listings": 9999,
                "first_orders_cap_ngwee": None,
                "first_orders_count": None,
                "payout_velocity": {"note": "T2 Verified Business — caps lifted"},
            },
            {
                "tier": 3,
                "max_listings": 9999,
                "first_orders_cap_ngwee": None,
                "first_orders_count": None,
                "payout_velocity": {"note": "T3 Premium — caps lifted"},
            },
        ]
    )
    fake.tables["platform_config"].rows.append(
        {"key": "cod_cap_ngwee", "value": COD_CAP_NGWEE}
    )


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    clear_vendor_cap_cache()
    return FakeSupabaseClient()


@pytest.fixture
def service_client(fake_client: FakeSupabaseClient) -> ServiceRoleClient:
    wrapper = MagicMock()
    wrapper.client = fake_client
    return wrapper


@pytest.fixture
def kyc_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": USER_ID, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"vendor"}),
    )
    service_wrapper = MagicMock()
    service_wrapper.client = fake_client
    monkeypatch.setattr(
        "app.deps.get_supabase_service_client",
        lambda: service_wrapper,
    )
    monkeypatch.setattr(
        "app.deps.get_supabase_client",
        lambda: iter([service_wrapper]),
    )

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _mock_verify(monkeypatch: pytest.MonkeyPatch, user_id: str = USER_ID) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )


def _mock_roles(monkeypatch: pytest.MonkeyPatch, roles: frozenset[str]) -> None:
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: roles,
    )


def _t1_limits(
    *,
    listing_count: int = 0,
    order_count: int = 0,
    kyc_tier: int = 1,
) -> VendorCapLimits:
    quota = VendorQuota(
        tier=kyc_tier,
        max_listings=30 if kyc_tier == 1 else 9999,
        first_orders_cap_ngwee=COD_CAP_NGWEE if kyc_tier == 1 else None,
        first_orders_count=5 if kyc_tier == 1 else None,
        payout_velocity={"max_payouts_per_day": 1, "max_amount_ngwee_per_day": 100_000},
    )
    return VendorCapLimits(
        vendor_id=VENDOR_ID,
        kyc_tier=kyc_tier,
        quota=quota,
        cod_cap_ngwee=COD_CAP_NGWEE,
        listing_count=listing_count,
        order_count=order_count,
    )


def test_listing_cap_blocks_31st_t1_listing() -> None:
    limits = _t1_limits(listing_count=30)
    with pytest.raises(AppError) as exc:
        enforce_listing_cap(limits)
    assert exc.value.http_status == 403
    assert exc.value.details["message_key"] == "vendor.caps.listing_limit"


def test_listing_cap_allows_30th_t1_listing() -> None:
    enforce_listing_cap(_t1_limits(listing_count=29))


def test_t2_lifts_listing_cap() -> None:
    limits = _t1_limits(listing_count=500, kyc_tier=2)
    enforce_listing_cap(limits)


def test_first_order_cap_blocks_k500_plus_one_ngwee() -> None:
    limits = _t1_limits(order_count=0)
    with pytest.raises(AppError) as exc:
        enforce_first_order_cap(limits, COD_CAP_NGWEE + 1)
    assert exc.value.http_status == 403
    assert exc.value.details["message_key"] == "vendor.caps.first_order_amount"


def test_first_order_cap_allows_exact_k500() -> None:
    enforce_first_order_cap(_t1_limits(order_count=0), COD_CAP_NGWEE)


def test_sixth_order_unrestricted_even_above_cap() -> None:
    enforce_first_order_cap(_t1_limits(order_count=5), COD_CAP_NGWEE + 1)


def test_t2_lifts_first_order_cap() -> None:
    enforce_first_order_cap(_t1_limits(order_count=0, kyc_tier=2), COD_CAP_NGWEE + 1)


def test_payout_velocity_blocks_second_payout(
    fake_client: FakeSupabaseClient,
    service_client: ServiceRoleClient,
) -> None:
    fake_client.tables["payouts"].rows.append(
        {
            "vendor_id": VENDOR_ID,
            "amount_ngwee": 10_000,
            "status": "paid",
            "created_at": "2099-01-01T00:00:00+00:00",
        }
    )
    limits = _t1_limits()
    with pytest.raises(AppError) as exc:
        enforce_payout_velocity(limits, 5_000, service_client)
    assert exc.value.details["message_key"] == "vendor.caps.payout_velocity"


def test_order_cap_checker_dependency_blocks_over_cap() -> None:
    checker = OrderCapChecker(limits=_t1_limits(order_count=2))
    with pytest.raises(AppError):
        checker.ensure_can_accept(COD_CAP_NGWEE + 1)


def test_state_machine_illegal_submit_from_submitted(
    fake_client: FakeSupabaseClient,
    service_client: ServiceRoleClient,
) -> None:
    _seed_t1_vendor(fake_client, status="pending_kyc")
    fake_client.tables["kyc_records"].rows.append(
        {
            "id": KYC_RECORD_ID,
            "vendor_id": VENDOR_ID,
            "tier": 1,
            "status": "submitted",
            "doc_storage_paths": ["private/kyc/nrc.jpg"],
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    with pytest.raises(KycTransitionError):
        transition_submit(
            actor_id=USER_ID,
            vendor_id=VENDOR_ID,
            tier=1,
            doc_storage_paths=["private/kyc/nrc.jpg"],
            momo_name_match={"matched": True},
            service_client=service_client,
        )


def test_state_machine_submit_and_audit(
    fake_client: FakeSupabaseClient,
    service_client: ServiceRoleClient,
) -> None:
    _seed_t1_vendor(fake_client)
    transition_submit(
        actor_id=USER_ID,
        vendor_id=VENDOR_ID,
        tier=1,
        doc_storage_paths=["private/kyc/nrc.jpg"],
        momo_name_match={"matched": True, "match_score": 0.95},
        service_client=service_client,
    )
    assert fake_client.tables["vendors"].rows[0]["status"] == "pending_kyc"
    assert fake_client.tables["kyc_records"].rows[-1]["status"] == "submitted"
    assert len(fake_client.tables["audit_log"].rows) == 1
    assert fake_client.tables["audit_log"].rows[0]["action"] == "kyc.submit"


def test_state_machine_approve_rejects_name_match_mismatch(
    fake_client: FakeSupabaseClient,
    service_client: ServiceRoleClient,
) -> None:
    _seed_t1_vendor(fake_client, status="pending_kyc")
    fake_client.tables["kyc_records"].rows.append(
        {
            "id": KYC_RECORD_ID,
            "vendor_id": VENDOR_ID,
            "tier": 1,
            "status": "submitted",
            "doc_storage_paths": ["private/kyc/nrc.jpg"],
            "momo_name_match": {"matched": False, "match_score": 0.2},
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    with pytest.raises(AppError) as exc:
        transition_approve(
            actor_id="admin-user",
            vendor_id=VENDOR_ID,
            kyc_record_id=KYC_RECORD_ID,
            tier=1,
            service_client=service_client,
        )
    assert exc.value.code == "kyc_name_match_required"


def test_state_machine_approve_audited(
    fake_client: FakeSupabaseClient,
    service_client: ServiceRoleClient,
) -> None:
    _seed_t1_vendor(fake_client, status="pending_kyc")
    fake_client.tables["kyc_records"].rows.append(
        {
            "id": KYC_RECORD_ID,
            "vendor_id": VENDOR_ID,
            "tier": 1,
            "status": "submitted",
            "doc_storage_paths": ["private/kyc/nrc.jpg"],
            "momo_name_match": {"matched": True, "match_score": 0.95},
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    transition_approve(
        actor_id="admin-user",
        vendor_id=VENDOR_ID,
        kyc_record_id=KYC_RECORD_ID,
        tier=1,
        service_client=service_client,
    )
    assert fake_client.tables["vendors"].rows[0]["status"] == "active"
    assert fake_client.tables["kyc_records"].rows[0]["status"] == "approved"
    assert any(row["action"] == "kyc.approve" for row in fake_client.tables["audit_log"].rows)


def test_state_machine_reject_audited(
    fake_client: FakeSupabaseClient,
    service_client: ServiceRoleClient,
) -> None:
    _seed_t1_vendor(fake_client, status="pending_kyc")
    fake_client.tables["kyc_records"].rows.append(
        {
            "id": KYC_RECORD_ID,
            "vendor_id": VENDOR_ID,
            "tier": 1,
            "status": "submitted",
            "doc_storage_paths": ["private/kyc/nrc.jpg"],
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    transition_reject(
        actor_id="admin-user",
        vendor_id=VENDOR_ID,
        kyc_record_id=KYC_RECORD_ID,
        reviewer_notes="Blurry NRC photo",
        service_client=service_client,
    )
    assert fake_client.tables["kyc_records"].rows[0]["status"] == "rejected"
    assert any(row["action"] == "kyc.reject" for row in fake_client.tables["audit_log"].rows)


def test_name_match_mismatch_score() -> None:
    score, matched = score_name_match("John Banda", "Jane Phiri")
    assert matched is False
    assert score < 0.85


def test_name_match_strong_match() -> None:
    score, matched = score_name_match("John Banda", "John Banda")
    assert matched is True
    assert score == 1.0


@pytest.mark.asyncio
async def test_name_match_recorded_not_auto_approved(
    kyc_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_t1_vendor(fake_client)
    monkeypatch.setenv("LENCO_API_TOKEN", "test-token")
    monkeypatch.setattr(
        "app.routers.kyc.resolve_and_score_momo_name",
        AsyncMock(
            return_value=MomoNameMatchResult(
                phone="0961111111",
                operator="mtn",
                resolved_name="Different Person",
                legal_name="Jane Phiri",
                match_score=0.1,
                matched=False,
                recorded_at="2026-07-08T00:00:00+00:00",
                raw={"accountName": "Different Person"},
            )
        ),
    )

    response = kyc_client.post(
        "/kyc/submit",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "tier": 1,
            "doc_storage_paths": ["private/kyc/nrc.jpg"],
            "momo_phone": "0961111111",
            "legal_name": "Jane Phiri",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["momo_name_match"]["matched"] is False
    assert fake_client.tables["kyc_records"].rows[-1]["momo_name_match"]["matched"] is False
    assert fake_client.tables["kyc_records"].rows[-1]["status"] == "submitted"


def test_badge_grant_idempotent(
    fake_client: FakeSupabaseClient,
    service_client: ServiceRoleClient,
) -> None:
    _seed_t1_vendor(fake_client, status="active", kyc_tier=2)
    fake_client.tables["vendors"].rows[0]["preferred_badge"] = False
    for index in range(20):
        order_id = f"order-{index:02d}"
        fake_client.tables["orders"].rows.append(
            {"id": order_id, "vendor_id": VENDOR_ID, "status": "completed"}
        )
        item_id = f"item-{index:02d}"
        fake_client.tables["order_items"].rows.append(
            {"id": item_id, "order_id": order_id}
        )
        fake_client.tables["reviews"].rows.append(
            {"order_item_id": item_id, "rating": 5, "status": "published"}
        )

    first = apply_preferred_badge_for_vendor(service_client, VENDOR_ID)
    second = apply_preferred_badge_for_vendor(service_client, VENDOR_ID)
    assert first is not None
    assert first.current is True
    assert second is None
    assert fake_client.tables["vendors"].rows[0]["preferred_badge"] is True


def test_badge_revoke_idempotent(
    fake_client: FakeSupabaseClient,
    service_client: ServiceRoleClient,
) -> None:
    _seed_t1_vendor(fake_client, status="active", kyc_tier=2)
    fake_client.tables["vendors"].rows[0]["preferred_badge"] = True
    fake_client.tables["orders"].rows.append(
        {"id": "order-01", "vendor_id": VENDOR_ID, "status": "completed"}
    )

    evaluation = evaluate_preferred_badge(service_client, VENDOR_ID)
    assert evaluation.qualifies is False

    first = apply_preferred_badge_for_vendor(service_client, VENDOR_ID)
    second = apply_preferred_badge_for_vendor(service_client, VENDOR_ID)
    assert first is not None
    assert first.current is False
    assert second is None


def test_preferred_badge_job_runs_active_vendors_only(
    fake_client: FakeSupabaseClient,
    service_client: ServiceRoleClient,
) -> None:
    _seed_t1_vendor(fake_client, status="active", kyc_tier=2)
    fake_client.tables["vendors"].rows.append(
        {
            "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "owner_user_id": "other-user",
            "status": "draft",
            "kyc_tier": 1,
            "preferred_badge": False,
        }
    )
    for index in range(20):
        order_id = f"order-{index:02d}"
        fake_client.tables["orders"].rows.append(
            {"id": order_id, "vendor_id": VENDOR_ID, "status": "completed"}
        )
        item_id = f"item-{index:02d}"
        fake_client.tables["order_items"].rows.append(
            {"id": item_id, "order_id": order_id}
        )
        fake_client.tables["reviews"].rows.append(
            {"order_item_id": item_id, "rating": 5, "status": "published"}
        )

    job = PreferredBadgeJob(service_client)
    changes = job.run()
    assert len(changes) == 1
    assert changes[0].vendor_id == VENDOR_ID


def test_load_vendor_quota_from_db(
    fake_client: FakeSupabaseClient,
    service_client: ServiceRoleClient,
) -> None:
    _seed_t1_vendor(fake_client)
    quota = load_vendor_quota(service_client, 1)
    assert quota.max_listings == 30
    assert quota.first_orders_cap_ngwee == COD_CAP_NGWEE


def test_kyc_status_endpoint(kyc_client: TestClient, fake_client: FakeSupabaseClient) -> None:
    _seed_t1_vendor(fake_client)
    response = kyc_client.get(
        "/kyc/status",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["application_status"] == "draft"


def test_kyc_resubmit_only_after_rejection(
    kyc_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_t1_vendor(fake_client, status="pending_kyc")
    fake_client.tables["kyc_records"].rows.append(
        {
            "id": KYC_RECORD_ID,
            "vendor_id": VENDOR_ID,
            "tier": 1,
            "status": "submitted",
            "doc_storage_paths": ["private/kyc/nrc.jpg"],
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    monkeypatch.setenv("LENCO_API_TOKEN", "test-token")
    monkeypatch.setattr(
        "app.routers.kyc.resolve_and_score_momo_name",
        AsyncMock(
            return_value=MomoNameMatchResult(
                phone="0961111111",
                operator="mtn",
                resolved_name="Jane Phiri",
                legal_name="Jane Phiri",
                match_score=1.0,
                matched=True,
                recorded_at="2026-07-08T00:00:00+00:00",
                raw={"accountName": "Jane Phiri"},
            )
        ),
    )

    response = kyc_client.post(
        "/kyc/resubmit",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "tier": 1,
            "doc_storage_paths": ["private/kyc/nrc.jpg"],
            "momo_phone": "0961111111",
            "legal_name": "Jane Phiri",
        },
    )
    assert response.status_code == 409


def test_require_listing_cap_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.kyc.caps import get_vendor_cap_limits, require_listing_cap

    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, frozenset({"vendor"}))

    async def over_limit_limits() -> VendorCapLimits:
        return _t1_limits(listing_count=30)

    app = create_app()
    app.dependency_overrides[get_vendor_cap_limits] = over_limit_limits
    cap_router = APIRouter()

    @cap_router.post("/test/listing-cap", dependencies=[Depends(require_listing_cap)])
    async def listing_cap_probe() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(cap_router)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/test/listing-cap",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
    app.dependency_overrides.clear()
    assert response.status_code == 403
    assert response.json()["error"]["details"]["message_key"] == "vendor.caps.listing_limit"


def test_write_kyc_audit_log(
    service_client: ServiceRoleClient,
    fake_client: FakeSupabaseClient,
) -> None:
    row = write_kyc_audit_log(
        service_client,
        actor_id=USER_ID,
        action="kyc.test",
        entity_type="vendor",
        entity_id=VENDOR_ID,
        before={"status": "draft"},
        after={"status": "pending_kyc"},
    )
    assert row["action"] == "kyc.test"
    assert len(fake_client.tables["audit_log"].rows) == 1


def test_kyc_state_machine_status_derivation(
    fake_client: FakeSupabaseClient,
    service_client: ServiceRoleClient,
) -> None:
    _seed_t1_vendor(fake_client, status="pending_kyc")
    fake_client.tables["kyc_records"].rows.append(
        {
            "id": KYC_RECORD_ID,
            "vendor_id": VENDOR_ID,
            "tier": 1,
            "status": "rejected",
            "doc_storage_paths": [],
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    machine = KycStateMachine(service_client)
    status, record = machine.get_status(VENDOR_ID)
    assert status == KycApplicationStatus.REJECTED
    assert record is not None
    assert record.status == "rejected"


def test_cod_cap_zero_is_honored_not_replaced_by_default() -> None:
    """Regression: a configured cod_cap_ngwee of 0 (COD disabled) must be read back
    as 0, not silently replaced by the hardcoded default."""
    import app.services.kyc.caps as caps_module

    caps_module._cod_cap_cache = None
    fake = FakeSupabaseClient()
    fake.tables["platform_config"].rows.append({"key": "cod_cap_ngwee", "value": 0})

    parsed = caps_module._parse_config_int(fake, "cod_cap_ngwee", 50_000)
    assert parsed == 0

    caps_module._cod_cap_cache = None
    fake2 = FakeSupabaseClient()
    fake2.tables["platform_config"].rows.append({"key": "cod_cap_ngwee", "value": 25_000})
    assert caps_module._parse_config_int(fake2, "cod_cap_ngwee", 50_000) == 25_000

    caps_module._cod_cap_cache = None
    fake3 = FakeSupabaseClient()  # no row → falls back to the supplied default
    assert caps_module._parse_config_int(fake3, "cod_cap_ngwee", 50_000) == 50_000
    caps_module._cod_cap_cache = None
