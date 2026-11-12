from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.main import create_app
from app.routers.admin_dashboards import (
    DASHBOARD_CACHE_TTL_SECONDS,
    build_dashboard,
    clear_dashboard_cache,
    compute_payout_liabilities,
)
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
REPORT_ID = "77777777-7777-7777-7777-777777777777"
VALID_TOKEN = "valid.jwt.token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: list[tuple[str, bool]] = []
        self._limit: int | None = None
        self._maybe_single = False
        self._count: str | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        self._count = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def lte(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("lte", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order.append((column, desc))
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> MagicMock:
        rows = [row for row in self._parent.rows if self._row_matches(row)]
        for column, desc in reversed(self._order):
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        total = len(rows)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=total)
        if self._count == "exact":
            return MagicMock(data=rows, count=total)
        return MagicMock(data=rows, count=total)

    def _row_matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "lte" and row.get(column, "") > value:
                return False
        return True


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "orders": FakeTable(),
            "order_items": FakeTable(),
            "checkout_groups": FakeTable(),
            "vendors": FakeTable(),
            "vendor_listings": FakeTable(),
            "products": FakeTable(),
            "reconciliation_reports": FakeTable(),
            "platform_config": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


def _mock_verify(monkeypatch: pytest.MonkeyPatch, user_id: str = USER_ID) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )


def _mock_roles(monkeypatch: pytest.MonkeyPatch, roles: dict[str, frozenset[str]]) -> None:
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: roles.get(user_id, frozenset()),
    )


def _seed_dashboard_fixtures(fake: FakeSupabaseClient) -> None:
    fake.tables["orders"].rows.extend(
        [
            {"id": "o1", "status": "placed", "delivery_fee_ngwee": 1_000},
            {"id": "o2", "status": "completed", "delivery_fee_ngwee": 2_000},
            {"id": "o3", "status": "cancelled", "delivery_fee_ngwee": 0},
        ]
    )
    fake.tables["order_items"].rows.extend(
        [
            {"order_id": "o1", "qty": 2, "unit_price_ngwee": 10_000},
            {"order_id": "o2", "qty": 1, "unit_price_ngwee": 50_000},
            {"order_id": "o3", "qty": 1, "unit_price_ngwee": 99_999},
        ]
    )
    fake.tables["checkout_groups"].rows.extend(
        [
            {"status": "pending"},
            {"status": "completed"},
            {"status": "abandoned"},
        ]
    )
    fake.tables["vendors"].rows.extend([{"id": "v1"}, {"id": "v2"}])
    fake.tables["vendor_listings"].rows.extend([{"id": "l1"}, {"id": "l2"}, {"id": "l3"}])
    fake.tables["products"].rows.append({"id": "p1"})
    fake.tables["platform_config"].rows.append({"key": "ai_monthly_cap_usd", "value": 15})
    fake.tables["reconciliation_reports"].rows.append(
        {
            "id": REPORT_ID,
            "report_date": "2026-07-09",
            "summary": {"clean": True},
            "discrepancies": {"balance_diff_ngwee": 0, "orphaned_lenco": [], "ledger_only": []},
        }
    )


@pytest.fixture
def dashboard_app() -> Any:
    return create_app()


@pytest.fixture
def dashboard_client(dashboard_app: Any) -> Generator[TestClient, None, None]:
    clear_dashboard_cache()
    with TestClient(dashboard_app, raise_server_exceptions=False) as test_client:
        yield test_client
    clear_dashboard_cache()


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "configured-account")
    client = FakeSupabaseClient()
    service_wrapper = MagicMock()
    service_wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr(
        "app.routers.admin_dashboards.get_supabase_client",
        lambda: service_wrapper,
    )
    return client


def test_aggregate_correctness_vs_fixtures(
    dashboard_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _seed_dashboard_fixtures(fake_client)

    with (
        patch(
            "app.routers.admin_dashboards.platform_escrow_held_ngwee",
            return_value=300_000,
        ),
        patch(
            "app.routers.admin_dashboards.platform_released_unpaid_ngwee",
            return_value=125_000,
        ),
        patch(
            "app.routers.admin_dashboards.compute_gmv_ngwee",
            return_value=72_000,
        ),
    ):
        response = dashboard_client.get(
            "/admin/dashboard",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["gmv_ngwee"] == 72_000
    assert body["orders_by_status"]["placed"] == 1
    assert body["orders_by_status"]["completed"] == 1
    assert body["orders_by_status"]["cancelled"] == 1
    assert body["payout_liabilities"]["escrow_held_ngwee"] == 300_000
    assert body["payout_liabilities"]["released_unpaid_ngwee"] == 125_000
    assert body["payout_liabilities"]["total_ngwee"] == 425_000
    assert body["counts"]["vendors"] == 2
    assert body["counts"]["listings"] == 3
    assert body["counts"]["products"] == 1
    assert body["funnel"]["checkout_started"] == 3
    assert body["funnel"]["checkout_completed"] == 1
    assert body["funnel"]["orders_placed"] == 2
    assert body["funnel"]["orders_completed"] == 1
    # AI tile now reads real Ask spend from ask_spend_monthly (0 here — no spend rows
    # seeded), no kill-switch trip.
    assert body["ai_usage"]["data_available"] is True
    assert body["ai_usage"]["flagged"] is False
    assert body["ai_usage"]["killed"] is False
    assert body["ai_usage"]["spend_usd"] == 0.0
    assert body["ai_usage"]["cap_usd"] == 15


def test_payout_liabilities_sum_matches_ledger_seams() -> None:
    with (
        patch(
            "app.routers.admin_dashboards.platform_escrow_held_ngwee",
            return_value=200_000,
        ),
        patch(
            "app.routers.admin_dashboards.platform_released_unpaid_ngwee",
            return_value=80_000,
        ),
    ):
        liabilities = compute_payout_liabilities()

    assert liabilities.escrow_held_ngwee == 200_000
    assert liabilities.released_unpaid_ngwee == 80_000
    assert liabilities.total_ngwee == 280_000


def test_injected_reconciliation_mismatch_flags_red(
    dashboard_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _seed_dashboard_fixtures(fake_client)
    fake_client.tables["reconciliation_reports"].rows[0]["discrepancies"] = {
        "balance_diff_ngwee": 5_000,
        "orphaned_lenco": [{"reference": "ord-bad"}],
        "ledger_only": [],
    }

    with (
        patch("app.routers.admin_dashboards.platform_escrow_held_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.platform_released_unpaid_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.compute_gmv_ngwee", return_value=0),
    ):
        response = dashboard_client.get(
            "/admin/dashboard",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

    assert response.status_code == 200
    reconciliation = response.json()["reconciliation"]
    assert reconciliation["status"] == "red"
    assert reconciliation["has_mismatch"] is True
    assert reconciliation["report_id"] == REPORT_ID


def test_cache_behavior_5min(
    dashboard_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _seed_dashboard_fixtures(fake_client)

    build_calls = {"count": 0}
    original_build = build_dashboard

    def counting_build(service_client: Any) -> Any:
        build_calls["count"] += 1
        return original_build(service_client)

    monkeypatch.setattr("app.routers.admin_dashboards.build_dashboard", counting_build)

    with (
        patch("app.routers.admin_dashboards.platform_escrow_held_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.platform_released_unpaid_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.compute_gmv_ngwee", return_value=0),
    ):
        first = dashboard_client.get(
            "/admin/dashboard",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        second = dashboard_client.get(
            "/admin/dashboard",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cached_at"] == second.json()["cached_at"]
    assert build_calls["count"] == 1

    clear_dashboard_cache()
    with (
        patch("app.routers.admin_dashboards.platform_escrow_held_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.platform_released_unpaid_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.compute_gmv_ngwee", return_value=0),
    ):
        third = dashboard_client.get(
            "/admin/dashboard",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
    assert third.status_code == 200
    assert third.json()["cached_at"] != first.json()["cached_at"]
    assert build_calls["count"] == 2
    assert DASHBOARD_CACHE_TTL_SECONDS == 300.0


def test_cache_expires_after_ttl(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    clear_dashboard_cache()
    service_wrapper = MagicMock()
    service_wrapper.client = fake_client
    _seed_dashboard_fixtures(fake_client)

    build_calls = {"count": 0}
    original_build = build_dashboard

    def counting_build(service_client: Any) -> Any:
        build_calls["count"] += 1
        return original_build(service_client)

    monkeypatch.setattr("app.routers.admin_dashboards.build_dashboard", counting_build)
    monotonic_values = iter([100.0, 100.0, 500.0])
    monkeypatch.setattr(
        "app.routers.admin_dashboards.time.monotonic",
        lambda: next(monotonic_values, 500.0),
    )

    with (
        patch("app.routers.admin_dashboards.platform_escrow_held_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.platform_released_unpaid_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.compute_gmv_ngwee", return_value=0),
    ):
        from app.routers.admin_dashboards import _get_cached_dashboard

        first = _get_cached_dashboard(service_wrapper)
        second = _get_cached_dashboard(service_wrapper)
        third = _get_cached_dashboard(service_wrapper)

    assert first.cached_at == second.cached_at
    assert build_calls["count"] == 2
    assert third.cached_at != first.cached_at


def test_non_admin_gets_403(
    dashboard_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch, OTHER_USER_ID)
    _mock_roles(monkeypatch, {OTHER_USER_ID: frozenset({"customer"})})
    _seed_dashboard_fixtures(fake_client)

    response = dashboard_client.get(
        "/admin/dashboard",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 403


def test_build_dashboard_legacy_clean_is_unknown(
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_dashboard_fixtures(fake_client)
    service_wrapper = MagicMock()
    service_wrapper.client = fake_client
    with (
        patch("app.routers.admin_dashboards.platform_escrow_held_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.platform_released_unpaid_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.compute_gmv_ngwee", return_value=0),
    ):
        payload = build_dashboard(service_wrapper)

    assert payload.reconciliation.status == "unknown"
    assert payload.reconciliation.provenance == "LEGACY_UNVERSIONED_ACCOUNT_UNBOUND"
    assert payload.reconciliation.has_mismatch is False
    assert payload.reconciliation.report_date == date(2026, 7, 9)
    assert payload.cached_at <= datetime.now(UTC)


def _versioned_report(number: int, **changes: Any) -> dict[str, Any]:
    from datetime import timedelta

    return {
        "id": f"version-{number}",
        "provider_account_id": "configured-account",
        "currency": "ZMW",
        "report_date": (datetime.now(UTC).date() - timedelta(days=1)).isoformat(),
        "version_number": number,
        "input_fingerprint": str(number).zfill(64),
        "source_version": "a" * 40,
        "summary": {"certifiable": False},
        "discrepancies": {},
        **changes,
    }


def test_current_versioned_discrepancy_beats_absent_or_clean_legacy(
    fake_client: FakeSupabaseClient,
) -> None:
    from app.routers.admin_dashboards import _latest_reconciliation

    wrapper = MagicMock(client=fake_client)
    _seed_dashboard_fixtures(fake_client)
    table = fake_client.table("reconciliation_report_versions")
    table.rows.extend(
        [
            _versioned_report(1),
            _versioned_report(2, discrepancies={"provider_unmatched": [{"identity": "unmatched"}]}),
            _versioned_report(99, provider_account_id="other-account"),
            _versioned_report(100, currency="USD"),
        ]
    )
    for legacy in (True, False):
        if not legacy:
            fake_client.tables["reconciliation_reports"].rows.clear()
        tile = _latest_reconciliation(wrapper)
        assert tile.status == "red"
        assert tile.report_id == "version-2"
        assert tile.version_number == 2
        assert tile.evidence_state == "unresolved"
        assert tile.provenance == "VERSIONED_ACCOUNT_BOUND"
        assert tile.provider_account_id == "configured-account"
        assert tile.discrepancies["provider_unmatched"]


@pytest.mark.parametrize("case", ["missing", "stale", "noncertifying", "unconfigured"])
def test_unqualified_reconciliation_evidence_never_green(
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    from app.routers.admin_dashboards import _latest_reconciliation

    if case == "unconfigured":
        monkeypatch.delenv("LENCO_ACCOUNT_ID")
    elif case != "missing":
        row = _versioned_report(1)
        if case == "stale":
            row["report_date"] = "2020-01-01"
        fake_client.table("reconciliation_report_versions").rows.append(row)
    tile = _latest_reconciliation(MagicMock(client=fake_client))
    assert tile.status == "unknown"
    assert tile.evidence_state == ("account_unconfigured" if case == "unconfigured" else case)


def test_version_selection_is_by_number_not_creation_or_exact_replay(
    fake_client: FakeSupabaseClient,
) -> None:
    from app.routers.admin_dashboards import _latest_reconciliation

    fake_client.table("reconciliation_report_versions").rows.extend(
        [
            _versioned_report(10, created_at="2020-01-01"),
            _versioned_report(9, created_at="2030-01-01"),
        ]
    )
    tile = _latest_reconciliation(MagicMock(client=fake_client))
    assert tile.version_number == 10
    assert tile.report_id == "version-10"
    assert tile.certifiable is False
    assert tile.status == "unknown"


def test_protected_admin_dashboard_returns_immutable_identity_and_discrepancy(
    dashboard_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _seed_dashboard_fixtures(fake_client)
    fake_client.table("reconciliation_report_versions").rows.append(
        _versioned_report(3, discrepancies={"provider_unmatched": [{"identity": "movement-api"}]})
    )
    with (
        patch("app.routers.admin_dashboards.platform_escrow_held_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.platform_released_unpaid_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.compute_gmv_ngwee", return_value=0),
    ):
        response = dashboard_client.get(
            "/admin/dashboard",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
    assert response.status_code == 200
    tile = response.json()["reconciliation"]
    assert tile["report_id"] == "version-3"
    assert tile["version_number"] == 3
    assert tile["status"] == "red"
    assert tile["provenance"] == "VERSIONED_ACCOUNT_BOUND"
    assert tile["discrepancies"]["provider_unmatched"][0]["identity"] == "movement-api"


@pytest.mark.parametrize("change", ["append", "rollover"])
def test_cached_dashboard_refreshes_reconciliation(
    dashboard_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    from datetime import timedelta

    from app.routers import admin_dashboards

    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _seed_dashboard_fixtures(fake_client)

    class Clock(datetime):
        current: Clock

        @classmethod
        def now(cls, tz: Any = None) -> Clock:
            return cls.current

    Clock.current = Clock(2026, 10, 1, 23, 59, tzinfo=UTC)
    monkeypatch.setattr(admin_dashboards, "datetime", Clock)
    monkeypatch.setattr("app.routers.admin_dashboards.time.monotonic", lambda: 100.0)
    table = fake_client.table("reconciliation_report_versions")
    table.rows.append(_versioned_report(1, report_date="2026-09-30"))
    with (
        patch("app.routers.admin_dashboards.platform_escrow_held_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.platform_released_unpaid_ngwee", return_value=0),
        patch("app.routers.admin_dashboards.compute_gmv_ngwee", return_value=72_000) as gmv,
    ):
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        first = dashboard_client.get("/admin/dashboard", headers=headers)
        assert first.status_code == 200
        original = first.json()
        assert original["reconciliation"]["evidence_state"] == "noncertifying"
        assert original["reconciliation"]["status"] == "unknown"
        if change == "append":
            table.rows.append(
                _versioned_report(
                    2, report_date="2026-09-30", discrepancies={"balance_diff_ngwee": 123}
                )
            )
        else:
            Clock.current += timedelta(minutes=2)
        second = dashboard_client.get("/admin/dashboard", headers=headers)
        assert second.status_code == 200
        body = second.json()
        assert gmv.call_count == 1  # Aggregate cache remains effective.
    assert {k: v for k, v in body.items() if k != "reconciliation"} == {
        k: v for k, v in original.items() if k != "reconciliation"
    }
    tile = body["reconciliation"]
    assert tile["certifiable"] is False
    if change == "append":
        assert tile["report_id"] == "version-2"
        assert tile["status"] == "red"
        assert tile["evidence_state"] == "unresolved"
    else:
        assert tile["expected_report_date"] == "2026-10-01"
        assert tile["status"] == "unknown"
        assert tile["evidence_state"] == "stale"


@pytest.mark.parametrize(
    "failed_table", ["reconciliation_report_versions", "reconciliation_reports"]
)
@pytest.mark.parametrize("warm_cache", [False, True])
def test_dashboard_isolates_reconciliation_query_failure(
    dashboard_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
    failed_table: str,
    warm_cache: bool,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _seed_dashboard_fixtures(fake_client)
    failing = fake_client.table(failed_table)
    execute = FakeQuery.execute

    def fail_query(query: FakeQuery) -> MagicMock:
        if query._parent is failing:
            raise RuntimeError("injected reconciliation query failure")
        return execute(query)

    with (
        patch("app.routers.admin_dashboards.platform_escrow_held_ngwee", return_value=300),
        patch("app.routers.admin_dashboards.platform_released_unpaid_ngwee", return_value=125),
        patch("app.routers.admin_dashboards.compute_gmv_ngwee", return_value=72_000),
    ):
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        if warm_cache:
            assert dashboard_client.get("/admin/dashboard", headers=headers).status_code == 200
        monkeypatch.setattr(FakeQuery, "execute", fail_query)
        response = dashboard_client.get("/admin/dashboard", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["gmv_ngwee"] == 72_000
    assert body["counts"]["vendors"] == 2
    assert body["orders_by_status"]["placed"] == 1
    assert body["payout_liabilities"]["total_ngwee"] == 425
    tile = body["reconciliation"]
    assert tile["status"] == "unknown"
    assert tile["evidence_state"] == "error"
    assert tile["certifiable"] is False
    assert tile["report_id"] is None
    assert tile["provider_account_id"] == "configured-account"
    assert tile["currency"] == "ZMW"
