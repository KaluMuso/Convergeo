"""Founder analytics dashboards: windows (Lusaka days), permissions, CSV export and audit.

Exact aggregates are asserted against seeded data in
``tests/rls/test_analytics_dashboards_db.py``; these tests replace the SQL builders.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Generator
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from app.main import create_app
from app.routers import admin_analytics
from app.routers import admin_analytics_dashboards as mod
from app.services.analytics import dashboards
from app.services.analytics import flags as analytics_flags
from app.services.analytics.reporting_day import reporting_today
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
TOKEN = {"Authorization": "Bearer valid.jwt.token"}
REPORTS = ["users", "growth", "vendors", "services-events"]
TODAY = date(2026, 11, 13)


# ---------------------------------------------------------------------------
# Windows and the Lusaka reporting day
# ---------------------------------------------------------------------------


def test_reporting_day_turns_at_22_00_utc() -> None:
    assert reporting_today(datetime(2026, 11, 12, 21, 59, 59, tzinfo=UTC)) == date(2026, 11, 12)
    assert reporting_today(datetime(2026, 11, 12, 22, 0, 0, tzinfo=UTC)) == date(2026, 11, 13)


@pytest.mark.parametrize(
    ("period", "start", "end"),
    [
        ("today", TODAY, TODAY),
        ("7d", date(2026, 11, 7), TODAY),
        ("30d", date(2026, 10, 15), TODAY),
        (None, date(2026, 11, 7), TODAY),
    ],
)
def test_preset_periods_end_today(period: str | None, start: date, end: date) -> None:
    window = dashboards.resolve_window(period, today=TODAY)
    assert (window.start, window.end) == (start, end)


def test_custom_period_is_inclusive_and_validated() -> None:
    window = dashboards.resolve_window("custom", date(2026, 1, 1), date(2026, 1, 31), today=TODAY)
    assert window.days == 31
    for start, end in (
        (date(2026, 2, 1), date(2026, 1, 1)),  # reversed
        (date(2026, 11, 1), date(2026, 11, 14)),  # future
        (date(2025, 1, 1), date(2026, 11, 1)),  # > 366 days
        (None, date(2026, 11, 1)),  # missing from
    ):
        with pytest.raises(dashboards.RangeError):
            dashboards.resolve_window("custom", start, end, today=TODAY)
    with pytest.raises(dashboards.RangeError):
        dashboards.resolve_window("90d", today=TODAY)


def test_sql_bounds_are_lusaka_midnights() -> None:
    lower = dashboards.lower_bound(date(2026, 11, 13))
    upper = dashboards.upper_bound(date(2026, 11, 13))
    assert lower == "('2026-11-13'::date::timestamp AT TIME ZONE 'Africa/Lusaka')"
    assert upper == "(('2026-11-13'::date + 1)::timestamp AT TIME ZONE 'Africa/Lusaka')"


def test_rate_bps_half_up_and_empty() -> None:
    assert dashboards.rate_bps(2, 3) == 6_667
    assert dashboards.rate_bps(1, 8) == 1_250
    assert dashboards.rate_bps(5, 0) is None


# ---------------------------------------------------------------------------
# API: permissions, finance gate, export audit
# ---------------------------------------------------------------------------


class _AuditSink:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.client = SimpleNamespace(table=self._table)

    def _table(self, name: str) -> Any:
        sink = self

        class _Query:
            def insert(self, row: dict[str, Any]) -> Any:
                assert name == "audit_log"
                sink.rows.append(row)
                return SimpleNamespace(execute=lambda: SimpleNamespace(data=[row]))

        return _Query()


FAKE_PAYLOAD: dict[str, dict[str, Any]] = {
    "users": {
        "range": {},
        "totals": {"customers": 3},
        "daily": [{"day": "2026-11-13", "customers": 1, "vendors": 0}],
        "activity": {"enabled": False},
        "cohorts": [{"cohort": "2026-11", "size": 1, "retained": [1, None]}],
    },
    "growth": {"range": {}, "totals": {"orders_paid": 2}, "daily": []},
    "vendors": {
        "range": {},
        "top": [{"vendor_id": "v1", "name": "=HYPERLINK(1)", "paid_orders": 1}],
    },
    "services-events": {"range": {}, "events": {"tickets_sold": 4}, "daily": []},
    "revenue": {"range": {}, "platform_revenue": {"total_ngwee": 3_000}, "daily": []},
}


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[TestClient, _AuditSink], None, None]:
    mod.clear_dashboards_cache()
    sink = _AuditSink()
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": USER_ID, "exp": 9_999_999_999},
    )
    for target in (
        "app.core.auth.get_supabase_service_client",
        "app.core.admin_audit.get_supabase_service_client",
        "app.routers.admin_analytics_dashboards.get_supabase_service_client",
    ):
        monkeypatch.setattr(target, lambda: sink)
    monkeypatch.setattr(
        dashboards, "build_users", lambda window, activity_enabled: FAKE_PAYLOAD["users"]
    )
    monkeypatch.setattr(dashboards, "build_growth", lambda window: FAKE_PAYLOAD["growth"])
    monkeypatch.setattr(
        dashboards,
        "build_vendors",
        lambda window, include_money: {**FAKE_PAYLOAD["vendors"], "finance_visible": include_money},
    )
    monkeypatch.setattr(
        dashboards, "build_services_events", lambda window: FAKE_PAYLOAD["services-events"]
    )
    monkeypatch.setattr(dashboards, "build_revenue", lambda window: FAKE_PAYLOAD["revenue"])
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, False)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client, sink
    mod.clear_dashboards_cache()


def _as(monkeypatch: pytest.MonkeyPatch, roles: set[str], permissions: set[str]) -> None:
    monkeypatch.setattr(
        "app.core.auth._load_user_roles", lambda user_id, service_client: frozenset(roles)
    )
    granted = lambda user, client: frozenset(permissions)  # noqa: E731
    monkeypatch.setattr("app.core.auth.load_admin_permissions", granted)
    monkeypatch.setattr(mod, "load_admin_permissions", granted)


@pytest.mark.parametrize("role", ["customer", "vendor", "moderator"])
@pytest.mark.parametrize("route", [*REPORTS, "revenue", "export?report=users"])
def test_non_operators_are_refused(
    api: tuple[TestClient, _AuditSink], monkeypatch: pytest.MonkeyPatch, role: str, route: str
) -> None:
    client, _ = api
    _as(monkeypatch, {role}, set())
    assert client.get(f"/admin/analytics/{route}", headers=TOKEN).status_code == 403


@pytest.mark.parametrize("route", REPORTS)
def test_analytics_read_reaches_operational_reports_not_revenue(
    api: tuple[TestClient, _AuditSink], monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    client, _ = api
    _as(monkeypatch, {"rbac_analyst"}, {"analytics.read"})
    assert client.get(f"/admin/analytics/{route}?period=7d", headers=TOKEN).status_code == 200
    assert client.get("/admin/analytics/revenue", headers=TOKEN).status_code == 403


def test_finance_read_reaches_revenue_but_not_operational_reports(
    api: tuple[TestClient, _AuditSink], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api
    _as(monkeypatch, {"rbac_finance"}, {"finance.read"})
    resp = client.get("/admin/analytics/revenue?period=30d", headers=TOKEN)
    assert resp.status_code == 200
    assert resp.json()["platform_revenue"]["total_ngwee"] == 3_000
    for route in REPORTS:
        assert client.get(f"/admin/analytics/{route}", headers=TOKEN).status_code == 403


def test_vendor_sales_value_needs_finance(
    api: tuple[TestClient, _AuditSink], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api
    _as(monkeypatch, {"rbac_analyst"}, {"analytics.read"})
    assert client.get("/admin/analytics/vendors", headers=TOKEN).json()["finance_visible"] is False
    mod.clear_dashboards_cache()
    _as(monkeypatch, {"rbac_both"}, {"analytics.read", "finance.read"})
    assert client.get("/admin/analytics/vendors", headers=TOKEN).json()["finance_visible"] is True


def test_invalid_window_is_422(
    api: tuple[TestClient, _AuditSink], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api
    _as(monkeypatch, {"admin"}, {"analytics.read"})
    assert client.get("/admin/analytics/users?period=custom", headers=TOKEN).status_code == 422
    assert client.get("/admin/analytics/users?period=year", headers=TOKEN).status_code == 422
    resp = client.get(
        "/admin/analytics/users?period=custom&from=2026-11-10&to=2026-11-01", headers=TOKEN
    )
    assert resp.status_code == 422


def test_export_writes_csv_and_an_audit_row(
    api: tuple[TestClient, _AuditSink], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, sink = api
    _as(monkeypatch, {"rbac_analyst"}, {"analytics.read"})
    resp = client.get("/admin/analytics/export?report=vendors&period=7d", headers=TOKEN)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment;" in resp.headers["content-disposition"]
    assert resp.headers["cache-control"] == "no-store"
    lines = list(csv.reader(io.StringIO(resp.text)))
    assert lines[1] == list(mod.CSV_HEADER)
    # The vendor name that looks like a formula is neutralised.
    assert ["vendors", "top", "", "v1 =HYPERLINK(1)", "paid_orders", "1"] in lines
    assert all(not cell.startswith("=") for line in lines[2:] for cell in line)
    (row,) = sink.rows
    assert row["action"] == "analytics.export"
    assert row["entity_type"] == "analytics_report"
    assert row["actor"] == USER_ID
    assert row["after"]["report"] == "vendors"
    assert row["after"]["period"] == "7d"
    assert row["after"]["finance_visible"] is False
    assert row["after"]["rows"] == len(lines) - 2


def test_export_of_revenue_without_finance_is_refused_and_audited(
    api: tuple[TestClient, _AuditSink], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, sink = api
    _as(monkeypatch, {"rbac_analyst"}, {"analytics.read"})
    resp = client.get("/admin/analytics/export?report=revenue&period=7d", headers=TOKEN)
    assert resp.status_code == 403
    (row,) = sink.rows
    assert row["action"] == "admin.access.denied"
    assert row["outcome"] == "denied"
    assert row["after"]["route"] == "/admin/analytics/export"


def test_export_of_revenue_with_finance(
    api: tuple[TestClient, _AuditSink], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, sink = api
    _as(monkeypatch, {"rbac_finance"}, {"finance.read"})
    resp = client.get("/admin/analytics/export?report=revenue&period=today", headers=TOKEN)
    assert resp.status_code == 200
    assert "platform_revenue,,,total_ngwee,3000" in resp.text
    assert sink.rows[0]["after"]["report"] == "revenue"
    assert sink.rows[0]["after"]["finance_visible"] is True
    # Operational exports stay with analytics.read.
    denied = client.get("/admin/analytics/export?report=users", headers=TOKEN)
    assert denied.status_code == 403


def test_users_activity_follows_the_rollups_flag(
    api: tuple[TestClient, _AuditSink], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api
    seen: list[bool] = []

    def build_users(window: dashboards.Window, activity_enabled: bool) -> dict[str, Any]:
        seen.append(activity_enabled)
        return FAKE_PAYLOAD["users"]

    monkeypatch.setattr(dashboards, "build_users", build_users)
    _as(monkeypatch, {"admin"}, {"analytics.read"})
    client.get("/admin/analytics/users", headers=TOKEN)
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, True)
    client.get("/admin/analytics/users", headers=TOKEN)
    assert seen == [False, True]


def test_csv_cells_neutralise_formulas() -> None:
    assert mod._cell("=1+1") == "'=1+1"
    assert mod._cell("@cmd") == "'@cmd"
    assert mod._cell(-500) == "-500"  # numbers stay numbers
    assert mod._cell(None) == ""
    assert mod._cell(True) == "true"


# ---------------------------------------------------------------------------
# v2 overview: money withheld without finance (D3)
# ---------------------------------------------------------------------------


def test_v2_overview_without_finance_withholds_money() -> None:
    commercial = {
        "orders_paid": 3,
        "gmv_paid_ngwee": 24_500,
        "aov_ngwee": 8_167,
        "payments_reconciled": False,
        "payment_mismatch_days": ["2026-11-10"],
    }
    payload: dict[str, Any] = {
        "commercial": commercial,
        "previous_commercial": commercial,
        "daily": [{"day": "2026-11-10", "orders_paid": 3, "gmv_paid_ngwee": 24_500}],
    }
    out = admin_analytics.without_finance(payload)
    assert out["commercial"]["orders_paid"] == 3
    assert out["commercial"]["gmv_paid_ngwee"] is None
    assert out["commercial"]["aov_ngwee"] is None
    assert out["commercial"]["payments_reconciled"] is None
    assert out["commercial"]["payment_mismatch_days"] == []
    assert out["daily"][0]["gmv_paid_ngwee"] is None
    assert out["finance_visible"] is False
    assert payload["commercial"]["gmv_paid_ngwee"] == 24_500  # cached payload untouched
