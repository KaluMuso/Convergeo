"""Customer listing-report API — authz, dedupe, validation, abuse ceilings."""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter
from app.deps import get_supabase_client
from app.main import create_app
from app.services.moderation.listing_reports import (
    create_listing_report,
    sanitize_report_detail,
)
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
LISTING_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_ID = "33333333-3333-3333-3333-333333333333"


class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
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

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            row.setdefault("id", str(uuid4()))
            row.setdefault("status", "open")
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        rows = self._parent.rows
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "flags": FakeTable(),
            "vendor_listings": FakeTable(),
            "audit_log": FakeTable(),
            "rate_limits": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    client.tables["vendor_listings"].rows.append(
        {
            "id": LISTING_ID,
            "vendor_id": VENDOR_ID,
            "status": "active",
        }
    )
    return client


@pytest.fixture
def report_client(
    fake_client: FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    app = create_app()

    class _Svc:
        def __init__(self, client: FakeSupabaseClient) -> None:
            self._client = client

        @property
        def client(self) -> FakeSupabaseClient:
            return self._client

    def _user() -> CurrentUser:
        return CurrentUser(id=USER_ID, roles=frozenset({"customer"}), token="t")

    app.dependency_overrides[get_supabase_client] = lambda: _Svc(fake_client)
    app.dependency_overrides[get_current_user] = _user

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()


def test_sanitize_report_detail_strips_controls_and_bounds() -> None:
    assert sanitize_report_detail(None) is None
    assert sanitize_report_detail("  \x00hi\x07  ") == "hi"
    assert sanitize_report_detail("x" * 600) == "x" * 500


def test_report_requires_auth(fake_client: FakeSupabaseClient) -> None:
    app = create_app()

    class _Svc:
        @property
        def client(self) -> FakeSupabaseClient:
            return fake_client

    app.dependency_overrides[get_supabase_client] = lambda: _Svc()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/flags/report",
            json={"listing_id": LISTING_ID, "reason": "scam"},
        )
    assert response.status_code == 401


def test_report_rejects_invalid_reason(report_client: TestClient) -> None:
    response = report_client.post(
        "/flags/report",
        json={"listing_id": LISTING_ID, "reason": "not-a-reason"},
    )
    assert response.status_code == 422


def test_report_creates_flag(
    report_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    with patch(
        "app.routers.flags_report.bump_rate_counter",
        return_value=(True, 0),
    ):
        response = report_client.post(
            "/flags/report",
            json={
                "listing_id": LISTING_ID,
                "reason": "counterfeit",
                "detail": "Looks fake",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["created"] is True
    assert body["deduped"] is False
    flags = fake_client.tables["flags"].rows
    assert len(flags) == 1
    assert flags[0]["entity_type"] == "listing"
    assert flags[0]["entity_id"] == LISTING_ID
    assert flags[0]["reporter_user_id"] == USER_ID
    assert flags[0]["reason"].startswith("counterfeit:")


def test_report_dedupes_open_flag(
    report_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    with patch(
        "app.routers.flags_report.bump_rate_counter",
        return_value=(True, 0),
    ):
        first = report_client.post(
            "/flags/report",
            json={"listing_id": LISTING_ID, "reason": "scam"},
        )
        second = report_client.post(
            "/flags/report",
            json={"listing_id": LISTING_ID, "reason": "misleading"},
        )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["created"] is True
    assert second.json()["deduped"] is True
    assert second.json()["flag_id"] == first.json()["flag_id"]
    assert len(fake_client.tables["flags"].rows) == 1


def test_report_unknown_listing_404(report_client: TestClient) -> None:
    with patch(
        "app.routers.flags_report.bump_rate_counter",
        return_value=(True, 0),
    ):
        response = report_client.post(
            "/flags/report",
            json={
                "listing_id": "99999999-9999-9999-9999-999999999999",
                "reason": "other",
            },
        )
    assert response.status_code == 404


def test_report_rate_limit_user(report_client: TestClient) -> None:
    calls = {"n": 0}

    def _bump(**kwargs: Any) -> tuple[bool, int]:
        scope = kwargs["scope"]
        if scope == "listing_report_user":
            calls["n"] += 1
            if calls["n"] > 10:
                return False, 30
        return True, 0

    with patch("app.routers.flags_report.bump_rate_counter", side_effect=_bump):
        last_status = 200
        for _ in range(11):
            response = report_client.post(
                "/flags/report",
                json={"listing_id": LISTING_ID, "reason": "other"},
            )
            last_status = response.status_code
    assert last_status == 429


def test_create_listing_report_service_dedupe(fake_client: FakeSupabaseClient) -> None:
    first, created = create_listing_report(
        fake_client,
        listing_id=LISTING_ID,
        reporter_user_id=USER_ID,
        reason="prohibited",
    )
    second, created_again = create_listing_report(
        fake_client,
        listing_id=LISTING_ID,
        reporter_user_id=USER_ID,
        reason="scam",
    )
    assert created is True
    assert created_again is False
    assert first["id"] == second["id"]


def test_bump_rate_counter_import_used() -> None:
    assert callable(bump_rate_counter)
    assert timedelta(minutes=1).total_seconds() == 60
