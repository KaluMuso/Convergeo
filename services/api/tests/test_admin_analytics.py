"""Convergeo Intelligence 1B-04: admin analytics API — authz, flag gate, windows, cache.

Exact values (k-threshold, commercial reconciliation) are asserted on a live DB in
``tests/rls/test_admin_analytics_db.py``.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta
from typing import Any

import pytest
from app.main import create_app
from app.routers import admin_analytics as mod
from app.services.analytics import flags as analytics_flags
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
TOKEN = {"Authorization": "Bearer valid.jwt.token"}
ROUTES = ["overview", "search-demand", "products-funnel", "insights"]


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    mod.clear_analytics_cache()
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": USER_ID, "exp": 9_999_999_999},
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client
    mod.clear_analytics_cache()


def _roles(monkeypatch: pytest.MonkeyPatch, *roles: str) -> None:
    monkeypatch.setattr(
        "app.core.auth._load_user_roles", lambda user_id, service_client: frozenset(roles)
    )


@pytest.mark.parametrize("role", ["customer", "vendor", "moderator"])
@pytest.mark.parametrize("route", [*ROUTES, "status"])
def test_non_admin_gets_403(
    api: TestClient, monkeypatch: pytest.MonkeyPatch, role: str, route: str
) -> None:
    _roles(monkeypatch, role)
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, True)
    assert api.get(f"/admin/analytics/{route}", headers=TOKEN).status_code == 403


@pytest.mark.parametrize("route", ROUTES)
def test_flag_off_routes_are_404_and_read_nothing(
    api: TestClient, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    _roles(monkeypatch, "admin")
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, False)

    def boom(_script: str) -> Any:
        raise AssertionError("no DB read with the flag off")

    monkeypatch.setattr(mod, "run_sql_script", boom)
    resp = api.get(f"/admin/analytics/{route}", headers=TOKEN)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "analytics_disabled"


def test_status_reports_disabled_when_flag_off(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _roles(monkeypatch, "admin")
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, False)
    resp = api.get("/admin/analytics/status", headers=TOKEN)
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False, "data_through": None}


@pytest.mark.parametrize(
    "query",
    ["from=2026-11-10&to=2026-11-01", "from=2026-01-01&to=2026-11-01", "to=2999-01-01"],
)
def test_invalid_windows_are_422(
    api: TestClient, monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    _roles(monkeypatch, "admin")
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, True)
    assert api.get(f"/admin/analytics/overview?{query}", headers=TOKEN).status_code == 422


def test_responses_are_cached_per_window(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _roles(monkeypatch, "admin")
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, True)
    calls: list[tuple[date, date]] = []

    def fake_builder(start: date, end: date) -> dict[str, Any]:
        calls.append((start, end))
        return {"range": {"from": start.isoformat(), "to": end.isoformat()}}

    monkeypatch.setattr(mod, "build_overview", fake_builder)
    for _ in range(3):
        resp = api.get("/admin/analytics/overview", headers=TOKEN)
        assert resp.status_code == 200
    assert len(calls) == 1
    start, end = calls[0]
    assert (end - start).days == 6 and end == mod._today() - timedelta(days=1)


def test_backend_failure_is_503_not_500(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _roles(monkeypatch, "admin")
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, True)

    def failing(_start: date, _end: date) -> dict[str, Any]:
        raise RuntimeError("statement timeout")

    monkeypatch.setattr(mod, "build_search_demand", failing)
    resp = api.get("/admin/analytics/search-demand", headers=TOKEN)
    assert resp.status_code == 503


def test_rate_bps_respects_minimum_sample() -> None:
    assert mod.rate_bps(5, 19, 20) is None
    assert mod.rate_bps(5, 20, 20) == 2500
    assert mod.rate_bps(1, 3, 1) == 3333
    assert mod.rate_bps(2, 3, 1) == 6667
    assert mod.rate_bps(0, 0, 1) is None


def test_k_threshold_never_below_five(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.db import SqlResult

    monkeypatch.setattr(
        mod,
        "run_sql_script",
        lambda _s: SqlResult(ok=True, rows=["analytics_term_k_min|2", "analytics_min_sample_n|50"]),
    )
    assert mod._thresholds() == (5, 50)
