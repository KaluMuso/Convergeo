"""M11-P02 — RFQ post-a-job tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.notifications.templates.whatsapp import (
    WHATSAPP_TEMPLATES,
    render_whatsapp_template,
)
from app.services.rfq import broadcast as broadcast_service
from fastapi import FastAPI
from fastapi.testclient import TestClient

CUSTOMER_A_ID = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_OWNER_A = "33333333-3333-3333-3333-333333333333"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
JOB_A_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
JOB_B_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
INTERNAL_TOKEN = "test-internal-job-jobs"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = list(filters)
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._in_filter: tuple[str, list[Any]] | None = None
        self._gt_filter: tuple[str, Any] | None = None
        self._lte_filter: tuple[str, Any] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def gt(self, column: str, value: Any) -> FakeQuery:
        self._gt_filter = (column, value)
        return self

    def lte(self, column: str, value: Any) -> FakeQuery:
        self._lte_filter = (column, value)
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in_filter = (column, values)
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

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload  # type: ignore[assignment]
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            rows: list[dict[str, Any]]
            if isinstance(self._payload, list):
                rows = []
                for item in self._payload:
                    row = dict(item)
                    if "id" not in row:
                        row["id"] = str(uuid4())
                    self._parent.rows.append(row)
                    rows.append(row)
            else:
                assert isinstance(self._payload, dict)
                row = dict(self._payload)
                if "id" not in row:
                    row["id"] = str(uuid4())
                if "created_at" not in row:
                    row["created_at"] = datetime.now(UTC).isoformat()
                if "updated_at" not in row:
                    row["updated_at"] = row["created_at"]
                self._parent.rows.append(row)
                rows = [row]
            return MagicMock(data=rows, count=None)

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            if self._maybe_single:
                return MagicMock(data=updated[0] if updated else None, count=len(updated))
            return MagicMock(data=updated, count=len(updated))

        rows = self._filtered_rows()
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
        if self._in_filter is not None:
            column, values = self._in_filter
            if row.get(column) not in values:
                return False
        if self._gt_filter is not None:
            column, value = self._gt_filter
            if not (str(row.get(column, "")) > str(value)):
                return False
        if self._lte_filter is not None:
            column, value = self._lte_filter
            if not (str(row.get(column, "")) <= str(value)):
                return False
        return True

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        if self._in_filter is not None:
            column, values = self._in_filter
            rows = [row for row in rows if row.get(column) in values]
        if self._gt_filter is not None:
            column, value = self._gt_filter
            rows = [row for row in rows if str(row.get(column, "")) > str(value)]
        if self._lte_filter is not None:
            column, value = self._lte_filter
            rows = [row for row in rows if str(row.get(column, "")) <= str(value)]
        return rows


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "jobs": FakeTable(),
            "services": FakeTable(),
            "vendors": FakeTable(),
            "orders": FakeTable(),
            "order_items": FakeTable(),
            "reviews": FakeTable(),
            "notification_outbox": FakeTable(),
            "flags": FakeTable(),
            "audit_log": FakeTable(),
            "platform_config": FakeTable(),
            "rate_counters": FakeTable(),
        }

    @property
    def client(self) -> FakeSupabaseClient:
        return self

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


def _seed_vendor(
    fake: FakeSupabaseClient,
    *,
    vendor_id: str,
    owner_user_id: str,
    display_name: str,
    preferred_badge: bool = False,
    status: str = "active",
) -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": vendor_id,
            "owner_user_id": owner_user_id,
            "display_name": display_name,
            "preferred_badge": preferred_badge,
            "status": status,
        }
    )


def _seed_service(
    fake: FakeSupabaseClient,
    *,
    service_id: str,
    vendor_id: str,
    category: str,
    service_area: str,
    status: str = "active",
) -> None:
    fake.tables["services"].rows.append(
        {
            "id": service_id,
            "vendor_id": vendor_id,
            "category": category,
            "service_area": service_area,
            "status": status,
        }
    )


def _make_client_app(fake: FakeSupabaseClient, user: CurrentUser) -> TestClient:
    app: FastAPI = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_JOB_JOBS_TOKEN", INTERNAL_TOKEN)


@pytest.fixture(autouse=True)
def _allow_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.jobs.bump_rate_counter",
        lambda **kwargs: (True, 0),
    )


class TestMatchProviders:
    def test_category_and_area_intersection_ranked_and_capped(self) -> None:
        fake = FakeSupabaseClient()
        fake.tables["platform_config"].rows.append(
            {"key": "rfq_broadcast_cap", "value": 2}
        )
        for index in range(5):
            vendor_id = f"vendor-{index:02d}"
            _seed_vendor(
                fake,
                vendor_id=vendor_id,
                owner_user_id=f"owner-{index:02d}",
                display_name=f"Vendor {index}",
                preferred_badge=index == 0,
            )
            _seed_service(
                fake,
                service_id=f"service-{index:02d}",
                vendor_id=vendor_id,
                category="home_services",
                service_area="Lusaka, Woodlands",
            )

        matches = broadcast_service.match_providers(
            fake,
            category="home_services",
            service_area="Lusaka, Woodlands",
        )
        assert len(matches) == 2
        assert matches[0].preferred_badge is True
        assert matches[0].vendor_id == "vendor-00"

    def test_no_match_returns_empty(self) -> None:
        fake = FakeSupabaseClient()
        _seed_vendor(
            fake,
            vendor_id=VENDOR_A_ID,
            owner_user_id=VENDOR_OWNER_A,
            display_name="Alpha Plumbing",
        )
        _seed_service(
            fake,
            service_id="service-a",
            vendor_id=VENDOR_A_ID,
            category="home_services",
            service_area="Ndola",
        )
        matches = broadcast_service.match_providers(
            fake,
            category="home_services",
            service_area="Lusaka",
        )
        assert matches == []


class TestBroadcastJob:
    def test_no_match_flags_admin_and_returns_ack(self) -> None:
        fake = FakeSupabaseClient()
        result = broadcast_service.broadcast_job(
            fake,
            job_id=JOB_A_ID,
            customer_id=CUSTOMER_A_ID,
            category="cleaning",
            service_area="Lusaka",
            description="Deep clean a 3-bedroom house",
        )
        assert result.no_match is True
        assert result.admin_flagged is True
        assert len(fake.tables["flags"].rows) == 1
        flag = fake.tables["flags"].rows[0]
        assert flag["entity_type"] == "job"
        assert flag["entity_id"] == JOB_A_ID
        assert flag["reason"] == broadcast_service.RFQ_NO_MATCH_FLAG_REASON

    def test_match_enqueues_outbox_rows(self) -> None:
        fake = FakeSupabaseClient()
        _seed_vendor(
            fake,
            vendor_id=VENDOR_A_ID,
            owner_user_id=VENDOR_OWNER_A,
            display_name="Alpha Plumbing",
            preferred_badge=True,
        )
        _seed_service(
            fake,
            service_id="service-a",
            vendor_id=VENDOR_A_ID,
            category="home_services",
            service_area="Lusaka",
        )
        result = broadcast_service.broadcast_job(
            fake,
            job_id=JOB_A_ID,
            customer_id=CUSTOMER_A_ID,
            category="home_services",
            service_area="Lusaka",
            description="Fix kitchen sink",
        )
        assert result.no_match is False
        assert result.matched_count == 1
        assert len(fake.tables["notification_outbox"].rows) == 1
        row = fake.tables["notification_outbox"].rows[0]
        # Regression guard: previously template=None (the WhatsApp adapter permanently
        # rejects templateless messages) and the payload used recipient_user_id, so the
        # dispatcher never resolved a `to`/locale — providers were never notified.
        assert row["template"] == broadcast_service.RFQ_MATCH_TEMPLATE
        assert row["channel"] == "whatsapp"
        assert row["payload"]["recipient_id"] == VENDOR_OWNER_A
        assert "recipient_user_id" not in row["payload"]

    def test_rfq_template_registered_and_renders(self) -> None:
        # The dispatcher renders each outbox row through the WhatsApp template registry;
        # an unregistered template raises TemplateRenderError. Prove rfq_job_broadcast is
        # registered and its variable mapper produces the expected body parameters (the
        # `to`/locale are injected by the dispatcher from recipient_id).
        assert broadcast_service.RFQ_MATCH_TEMPLATE in WHATSAPP_TEMPLATES
        rendered = render_whatsapp_template(
            broadcast_service.RFQ_MATCH_TEMPLATE,
            {
                "to": "+260970000000",
                "locale": "en",
                "category": "home_services",
                "service_area": "Lusaka",
                "description_preview": "Fix kitchen sink",
            },
        )
        assert rendered.meta_template_name == "rfq_job_broadcast"
        assert rendered.to_e164 == "+260970000000"
        assert rendered.body_parameters == ("home_services", "Lusaka", "Fix kitchen sink")


class TestJobsAuthz:
    def test_guest_cannot_post(self) -> None:
        fake = FakeSupabaseClient()
        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: fake
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/jobs",
            json={
                "category": "home_services",
                "description": "Need a plumber for a leaking tap",
                "service_area": "Lusaka",
                "budget_band": "flexible",
            },
        )
        assert response.status_code == 401

    def test_only_owner_can_read_pre_quote_job(self) -> None:
        fake = FakeSupabaseClient()
        fake.tables["jobs"].rows.append(
            {
                "id": JOB_A_ID,
                "customer_id": CUSTOMER_A_ID,
                "category": "home_services",
                "description": "Fix kitchen sink",
                "preferred_date": None,
                "budget_band_min_ngwee": None,
                "budget_band_max_ngwee": None,
                "status": "open",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        owner_client = _make_client_app(fake, CurrentUser(CUSTOMER_A_ID, frozenset(), "token-a"))
        other_client = _make_client_app(fake, CurrentUser(CUSTOMER_B_ID, frozenset(), "token-b"))

        owner_response = owner_client.get(f"/jobs/{JOB_A_ID}")
        other_response = other_client.get(f"/jobs/{JOB_A_ID}")

        assert owner_response.status_code == 200
        assert other_response.status_code == 403

    def test_create_job_broadcasts_and_returns_ack(self) -> None:
        fake = FakeSupabaseClient()
        _seed_vendor(
            fake,
            vendor_id=VENDOR_A_ID,
            owner_user_id=VENDOR_OWNER_A,
            display_name="Alpha Plumbing",
        )
        _seed_service(
            fake,
            service_id="service-a",
            vendor_id=VENDOR_A_ID,
            category="home_services",
            service_area="Lusaka, Woodlands",
        )
        client = _make_client_app(fake, CurrentUser(CUSTOMER_A_ID, frozenset(), "token-a"))
        response = client.post(
            "/jobs",
            json={
                "category": "home_services",
                "description": "Need a plumber for a leaking tap",
                "service_area": "Lusaka, Woodlands",
                "budget_band": "500_2000",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["job"]["status"] == "open"
        assert body["job"]["broadcast"]["matched_count"] == 1
        assert body["job"]["broadcast"]["message_key"] == "services.postJob.ack.sent"


class TestExpireTick:
    def test_stale_open_jobs_cancelled_with_notice_idempotent(self) -> None:
        fake = FakeSupabaseClient()
        stale_created = (datetime.now(UTC) - timedelta(days=8)).isoformat()
        fake.tables["jobs"].rows.extend(
            [
                {
                    "id": JOB_A_ID,
                    "customer_id": CUSTOMER_A_ID,
                    "category": "home_services",
                    "description": "Old open job",
                    "status": "open",
                    "created_at": stale_created,
                },
                {
                    "id": JOB_B_ID,
                    "customer_id": CUSTOMER_B_ID,
                    "category": "cleaning",
                    "description": "Recent open job",
                    "status": "open",
                    "created_at": datetime.now(UTC).isoformat(),
                },
            ]
        )
        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: fake
        client = TestClient(app, raise_server_exceptions=False)

        first = client.post(
            "/internal/jobs/expire-tick",
            headers={"X-Internal-Token": INTERNAL_TOKEN},
            json={"limit": 50},
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["expired"] == 1
        assert fake.tables["jobs"].rows[0]["status"] == "cancelled"
        audit_actions = [row["action"] for row in fake.tables["audit_log"].rows]
        assert "job.expired" in audit_actions
        expired_audit = next(
            row for row in fake.tables["audit_log"].rows if row["action"] == "job.expired"
        )
        assert expired_audit["after"]["resolve_snapshot"]["expired"] is True
        assert fake.tables["jobs"].rows[1]["status"] == "open"
        assert len(fake.tables["notification_outbox"].rows) == 1

        second = client.post(
            "/internal/jobs/expire-tick",
            headers={"X-Internal-Token": INTERNAL_TOKEN},
            json={"limit": 50},
        )
        assert second.status_code == 200
        assert second.json()["expired"] == 0

    def test_expire_tick_requires_token(self) -> None:
        fake = FakeSupabaseClient()
        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: fake
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/internal/jobs/expire-tick", json={"limit": 10})
        assert response.status_code == 401


class TestRankScore:
    def test_rank_prefers_badge_then_rating_then_proximity(self) -> None:
        score_badge = broadcast_service._rank_provider(
            preferred_badge=True,
            average_rating=3.0,
            proximity=0.0,
        )
        score_rating = broadcast_service._rank_provider(
            preferred_badge=False,
            average_rating=5.0,
            proximity=100.0,
        )
        assert score_badge > score_rating
