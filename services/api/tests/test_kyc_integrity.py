"""KYC integrity: auditable records, guarded admin review, capability freeze (MR-D02)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.services.kyc.eligibility import (
    build_eligibility_from_rows,
    resolve_vendor_eligibility,
)
from app.services.kyc.state_machine import (
    transition_approve,
    transition_revoke,
    transition_start_review,
    transition_submit,
    transition_suspend,
)
from fastapi.testclient import TestClient

ADMIN_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_OWNER_ID = "22222222-2222-2222-2222-222222222222"
OTHER_OWNER_ID = "33333333-3333-3333-3333-333333333333"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_VENDOR_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
KYC_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
OTHER_KYC_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
VALID_TOKEN = "valid.jwt.token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = columns, count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
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
            if "created_at" not in row:
                row["created_at"] = datetime.now(UTC).isoformat()
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if all(
                    row.get(column) == value
                    for op, column, value in self._filters
                    if op == "eq"
                ):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, 0) or 0, reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = rows
        for op, column, value in self._filters:
            if op == "eq":
                filtered = [row for row in filtered if row.get(column) == value]
            elif op == "in":
                allowed = set(value)
                filtered = [row for row in filtered if row.get(column) in allowed]
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
            "notification_outbox": FakeTable(),
            "kyc_orphaned_tier_report": FakeTable(),
            "vendor_quotas": FakeTable(),
            "platform_config": FakeTable(),
            "vendor_listings": FakeTable(),
            "orders": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable())


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    wrapper = MagicMock()
    wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.admin_kyc.get_supabase_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.kyc.get_supabase_client", lambda: wrapper)
    monkeypatch.setattr(
        "app.services.kyc.state_machine.get_supabase_service_client",
        lambda: wrapper,
    )
    return client


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


def _mock_verify(monkeypatch: pytest.MonkeyPatch, user_id: str) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )


def _mock_roles(monkeypatch: pytest.MonkeyPatch, roles_by_user: dict[str, frozenset[str]]) -> None:
    def fake_load(user_id: str, service_client: Any) -> frozenset[str]:
        _ = service_client
        return roles_by_user.get(user_id, frozenset())

    monkeypatch.setattr("app.core.auth._load_user_roles", fake_load)


def _mock_admin_audit(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    inserted: list[dict[str, Any]] = []

    class _Q:
        def __init__(self, row: dict[str, Any]) -> None:
            self._row = row

        def execute(self) -> MagicMock:
            inserted.append(self._row)
            return MagicMock(data=[{**self._row, "id": "audit-row"}])

    class _T:
        def insert(self, row: dict[str, Any]) -> _Q:
            return _Q(row)

    service = MagicMock()
    service.client.table.side_effect = lambda name: _T() if name == "audit_log" else MagicMock()
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: service)
    return inserted


def _seed_vendor(
    fake: FakeSupabaseClient,
    *,
    vendor_id: str = VENDOR_ID,
    owner_id: str = VENDOR_OWNER_ID,
    status: str = "draft",
    kyc_tier: int | None = None,
) -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": vendor_id,
            "owner_user_id": owner_id,
            "slug": f"slug-{vendor_id[:8]}",
            "display_name": f"Vendor {vendor_id[:8]}",
            "status": status,
            "kyc_tier": kyc_tier,
            "preferred_badge": False,
        }
    )


def _seed_kyc(
    fake: FakeSupabaseClient,
    *,
    kyc_id: str = KYC_ID,
    vendor_id: str = VENDOR_ID,
    tier: int = 2,
    status: str = "submitted",
) -> None:
    fake.tables["kyc_records"].rows.append(
        {
            "id": kyc_id,
            "vendor_id": vendor_id,
            "tier": tier,
            "status": status,
            "doc_storage_paths": [f"kyc/{vendor_id}/nrc.jpg"],
            "momo_name_match": {
                "phone": "+260971234567",
                "operator": "mtn",
                "resolved_name": "Ada Lovelace",
                "legal_name": "Ada Lovelace",
                "match_score": 0.99,
                "matched": True,
            },
            "reviewer_notes": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "decision_reason": None,
            "lifecycle_reason": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )


def test_orphaned_tier_does_not_unlock_wholesale() -> None:
    eligibility = build_eligibility_from_rows(
        vendor={
            "id": VENDOR_ID,
            "status": "active",
            "kyc_tier": 2,
            "preferred_badge": False,
        },
        approved_record=None,
    )
    assert eligibility.orphaned_tier is True
    assert eligibility.is_auditable_approved is False
    assert eligibility.effective_tier is None
    assert eligibility.can_wholesale is False
    assert eligibility.can_organise_events is False
    assert eligibility.is_directory_verified is False


def test_approved_record_unlocks_intended_capabilities() -> None:
    eligibility = build_eligibility_from_rows(
        vendor={
            "id": VENDOR_ID,
            "status": "active",
            "kyc_tier": 2,
            "preferred_badge": False,
        },
        approved_record={"id": KYC_ID, "tier": 2, "status": "approved"},
    )
    assert eligibility.is_auditable_approved is True
    assert eligibility.effective_tier == 2
    assert eligibility.can_wholesale is True
    assert eligibility.can_organise_events is True
    assert eligibility.is_directory_verified is True
    assert eligibility.orphaned_tier is False


def test_vendor_cannot_self_approve(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, VENDOR_OWNER_ID)
    _mock_roles(monkeypatch, {VENDOR_OWNER_ID: frozenset({"vendor"})})
    _seed_vendor(fake_client, status="pending_kyc")
    _seed_kyc(fake_client, status="submitted")

    response = api_client.post(
        f"/admin/kyc/{KYC_ID}/approve",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"reviewer_notes": "self approve"},
    )
    assert response.status_code == 403
    assert fake_client.tables["kyc_records"].rows[0]["status"] == "submitted"


def test_unauthorized_admin_cannot_review(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, OTHER_OWNER_ID)
    _mock_roles(monkeypatch, {OTHER_OWNER_ID: frozenset({"customer"})})
    _seed_vendor(fake_client, status="pending_kyc")
    _seed_kyc(fake_client, status="submitted")

    mutating = (
        (f"/admin/kyc/{KYC_ID}/start-review", {"lifecycle_reason": "attempt"}),
        (f"/admin/kyc/{KYC_ID}/approve", {"reviewer_notes": "attempt"}),
        (f"/admin/kyc/{KYC_ID}/suspend", {"reason": "attempt"}),
        (f"/admin/kyc/{KYC_ID}/revoke", {"reason": "attempt"}),
    )
    for path, body in mutating:
        response = api_client.post(
            path,
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json=body,
        )
        assert response.status_code == 403, path

    report = api_client.get(
        "/admin/kyc/orphaned-tiers",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert report.status_code == 403


def test_approve_records_immutable_decision_evidence_and_audit(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, ADMIN_ID)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    _mock_admin_audit(monkeypatch)
    _seed_vendor(fake_client, status="pending_kyc")
    _seed_kyc(fake_client, tier=2, status="submitted")

    start = api_client.post(
        f"/admin/kyc/{KYC_ID}/start-review",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"lifecycle_reason": "queue pickup"},
    )
    assert start.status_code == 200
    assert start.json()["kyc_record_status"] == "under_review"

    approve = api_client.post(
        f"/admin/kyc/{KYC_ID}/approve",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"reviewer_notes": "PACRA docs clear"},
    )
    assert approve.status_code == 200
    assert approve.json()["kyc_record_status"] == "approved"

    record = fake_client.tables["kyc_records"].rows[0]
    assert record["reviewed_by"] == ADMIN_ID
    assert record["reviewed_at"]
    assert record["decision_reason"] == "PACRA docs clear"
    assert record["tier"] == 2

    vendor = fake_client.tables["vendors"].rows[0]
    assert vendor["status"] == "active"
    assert vendor["kyc_tier"] == 2

    actions = {row["action"] for row in fake_client.tables["audit_log"].rows}
    assert "kyc.start_review" in actions
    assert "kyc.approve" in actions

    eligibility = resolve_vendor_eligibility(
        MagicMock(client=fake_client),
        VENDOR_ID,
    )
    assert eligibility.can_wholesale is True


def test_suspend_and_revoke_remove_capabilities_immediately(
    fake_client: FakeSupabaseClient,
) -> None:
    wrapper = MagicMock()
    wrapper.client = fake_client
    _seed_vendor(fake_client, status="active", kyc_tier=2)
    _seed_kyc(fake_client, tier=2, status="approved")
    fake_client.tables["kyc_records"].rows[0]["reviewed_by"] = ADMIN_ID
    fake_client.tables["kyc_records"].rows[0]["reviewed_at"] = "2026-07-01T00:00:00Z"
    fake_client.tables["kyc_records"].rows[0]["decision_reason"] = "ok"

    before = resolve_vendor_eligibility(wrapper, VENDOR_ID)
    assert before.can_wholesale is True

    suspended = transition_suspend(
        actor_id=ADMIN_ID,
        vendor_id=VENDOR_ID,
        kyc_record_id=KYC_ID,
        reason="Fraud signals",
        service_client=wrapper,
    )
    assert suspended["kyc_record"]["status"] == "suspended"
    assert suspended["vendor"]["status"] == "suspended"
    assert suspended["vendor"]["kyc_tier"] is None

    after_suspend = resolve_vendor_eligibility(wrapper, VENDOR_ID)
    assert after_suspend.can_wholesale is False
    assert after_suspend.can_organise_events is False
    assert after_suspend.is_auditable_approved is False

    # Decision evidence remains (immutable approval trail).
    record = fake_client.tables["kyc_records"].rows[0]
    assert record["reviewed_by"] == ADMIN_ID
    assert record["decision_reason"] == "ok"

    # Move back to approved for revoke path coverage via direct status reset.
    record["status"] = "approved"
    fake_client.tables["vendors"].rows[0]["status"] = "active"
    fake_client.tables["vendors"].rows[0]["kyc_tier"] = 2

    revoked = transition_revoke(
        actor_id=ADMIN_ID,
        vendor_id=VENDOR_ID,
        kyc_record_id=KYC_ID,
        reason="Revoked after appeal",
        service_client=wrapper,
    )
    assert revoked["kyc_record"]["status"] == "revoked"
    assert revoked["vendor"]["kyc_tier"] is None
    after_revoke = resolve_vendor_eligibility(wrapper, VENDOR_ID)
    assert after_revoke.can_wholesale is False


def test_cross_vendor_kyc_status_denied(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, OTHER_OWNER_ID)
    _mock_roles(monkeypatch, {OTHER_OWNER_ID: frozenset({"vendor"})})
    _seed_vendor(fake_client, vendor_id=VENDOR_ID, owner_id=VENDOR_OWNER_ID, status="active")
    _seed_kyc(fake_client, vendor_id=VENDOR_ID, status="approved", tier=2)
    _seed_vendor(
        fake_client,
        vendor_id=OTHER_VENDOR_ID,
        owner_id=OTHER_OWNER_ID,
        status="draft",
    )

    response = api_client.get(
        "/kyc/status",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    # Owner B only sees their own (draft) eligibility — not vendor A's approved tier.
    assert body["kyc_record_id"] is None or body["kyc_record_id"] != KYC_ID
    assert body["is_auditable_approved"] is False
    assert body["capabilities"]["wholesale"] is False


def test_vendor_status_reports_orphaned_tier_honestly(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, VENDOR_OWNER_ID)
    _mock_roles(monkeypatch, {VENDOR_OWNER_ID: frozenset({"vendor"})})
    _seed_vendor(fake_client, status="active", kyc_tier=2)

    response = api_client.get(
        "/kyc/status",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["orphaned_tier"] is True
    assert body["kyc_tier"] is None
    assert body["effective_tier"] is None
    assert body["is_auditable_approved"] is False
    assert body["capabilities"]["wholesale"] is False
    assert body["capabilities"]["directory_verified"] is False


def test_orphaned_tier_report_endpoint(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, ADMIN_ID)
    _mock_roles(monkeypatch, {ADMIN_ID: frozenset({"admin"})})
    fake_client.tables["kyc_orphaned_tier_report"].rows.append(
        {
            "vendor_id": VENDOR_ID,
            "slug": "orphan-shop",
            "display_name": "Orphan Shop",
            "vendor_status": "active",
            "stored_kyc_tier": 2,
            "vendor_updated_at": "2026-07-01T00:00:00Z",
            "kyc_record_count": 0,
            "approved_kyc_record_count": 0,
        }
    )

    response = api_client.get(
        "/admin/kyc/orphaned-tiers",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["stored_kyc_tier"] == 2
    assert payload[0]["approved_kyc_record_count"] == 0


def test_submit_creates_submitted_status_and_audit(
    fake_client: FakeSupabaseClient,
) -> None:
    wrapper = MagicMock()
    wrapper.client = fake_client
    _seed_vendor(fake_client, status="draft", kyc_tier=None)

    result = transition_submit(
        actor_id=VENDOR_OWNER_ID,
        vendor_id=VENDOR_ID,
        tier=1,
        doc_storage_paths=["kyc/nrc.jpg"],
        momo_name_match={"matched": True},
        service_client=wrapper,
    )
    assert result["kyc_record"]["status"] == "submitted"
    assert fake_client.tables["vendors"].rows[0]["status"] == "pending_kyc"
    assert any(
        row["action"] == "kyc.submit" for row in fake_client.tables["audit_log"].rows
    )


def test_start_review_idempotent_when_already_under_review(
    fake_client: FakeSupabaseClient,
) -> None:
    wrapper = MagicMock()
    wrapper.client = fake_client
    _seed_vendor(fake_client, status="pending_kyc")
    _seed_kyc(fake_client, status="under_review")

    result = transition_start_review(
        actor_id=ADMIN_ID,
        vendor_id=VENDOR_ID,
        kyc_record_id=KYC_ID,
        service_client=wrapper,
    )
    assert result["kyc_record"]["status"] == "under_review"


def test_approve_wrong_vendor_record_rejected(
    fake_client: FakeSupabaseClient,
) -> None:
    wrapper = MagicMock()
    wrapper.client = fake_client
    _seed_vendor(fake_client, vendor_id=VENDOR_ID, status="pending_kyc")
    _seed_vendor(
        fake_client,
        vendor_id=OTHER_VENDOR_ID,
        owner_id=OTHER_OWNER_ID,
        status="pending_kyc",
    )
    _seed_kyc(fake_client, kyc_id=OTHER_KYC_ID, vendor_id=OTHER_VENDOR_ID, status="submitted")

    with pytest.raises(Exception) as exc:
        transition_approve(
            actor_id=ADMIN_ID,
            vendor_id=VENDOR_ID,
            kyc_record_id=OTHER_KYC_ID,
            tier=2,
            service_client=wrapper,
        )
    assert getattr(exc.value, "http_status", None) in {404, 409} or "not found" in str(
        exc.value
    ).lower()
