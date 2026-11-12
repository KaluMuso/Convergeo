"""Convergeo Intelligence 1B-01: rollup tick endpoint and day selection (DB-free).

Exact rollup values, idempotency and the 30-minute session rule are asserted against a
live database in ``tests/rls/test_analytics_v2_rollup_db.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.routers import internal_analytics as mod
from app.services.analytics import flags as analytics_flags
from app.services.analytics import rollup
from app.services.analytics.rollup import RollupDayResult, RollupTickResult
from app.services.db import SqlResult
from fastapi.testclient import TestClient

TOKEN = {"X-Internal-Token": "dev-internal-analytics"}
WORKFLOW = Path(__file__).resolve().parents[3] / "infra" / "n8n" / "analytics-rollup.json"
NOW = datetime(2026, 11, 20, 2, 15, tzinfo=UTC)


def test_rollup_tick_requires_token(client: TestClient) -> None:
    assert client.post("/internal/analytics/rollup-tick").status_code == 401


def test_rollup_tick_is_noop_when_flag_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, False)
    tick = MagicMock(side_effect=AssertionError("must not roll up with the flag off"))
    monkeypatch.setattr(mod, "run_rollup_tick", tick)
    resp = client.post("/internal/analytics/rollup-tick", headers=TOKEN)
    assert resp.status_code == 200 and resp.json() == {"skipped": "flag_off"}


def test_rollup_tick_runs_when_flag_on(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, True)
    result = RollupTickResult(
        days=[
            RollupDayResult(day=date(2026, 11, 18), ok=True, rows=40),
            RollupDayResult(day=date(2026, 11, 19), ok=False, error="canceling statement"),
        ]
    )
    calls: list[date | None] = []

    def fake_tick(*, day: date | None = None) -> RollupTickResult:
        calls.append(day)
        return result

    monkeypatch.setattr(mod, "run_rollup_tick", fake_tick)
    resp = client.post("/internal/analytics/rollup-tick?day=2026-11-18", headers=TOKEN)
    assert resp.status_code == 200
    assert calls == [date(2026, 11, 18)]
    assert resp.json() == {
        "days": [
            {"day": "2026-11-18", "ok": True, "rows": 40},
            {"day": "2026-11-19", "ok": False, "rows": 0, "error": "canceling statement"},
        ],
        "ok": False,
    }


def test_rollup_tick_rejects_future_day(client: TestClient) -> None:
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, True)
    resp = client.post("/internal/analytics/rollup-tick?day=2999-01-01", headers=TOKEN)
    assert resp.status_code == 422


def test_days_to_roll_catches_up_missing_days_and_always_redoes_yesterday(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    done = ["2026-11-13", "2026-11-14", "2026-11-16", "2026-11-19"]
    monkeypatch.setattr(rollup, "run_sql_script", lambda _s: SqlResult(ok=True, rows=done))
    assert rollup.days_to_roll(NOW) == [
        date(2026, 11, 15),
        date(2026, 11, 17),
        date(2026, 11, 18),
        date(2026, 11, 19),
    ]


def test_rollup_day_runs_under_statement_timeout_and_records_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripts: list[str] = []

    def fake_sql(script: str) -> SqlResult:
        scripts.append(script)
        if "analytics_rollup_day" in script:
            return SqlResult(ok=False, rows=[], error="canceling statement due to timeout")
        return SqlResult(ok=True, rows=[])

    monkeypatch.setattr(rollup, "run_sql_script", fake_sql)
    out = rollup.rollup_day(date(2026, 11, 19))
    assert out.ok is False and out.error and "timeout" in out.error
    assert "SET LOCAL statement_timeout = '60s'" in scripts[0]
    assert "SET LOCAL lock_timeout" in scripts[0]
    assert "analytics_rollup_day('2026-11-19'::date, 30)" in scripts[0]
    assert "'error'" in scripts[1] and "analytics_rollup_runs" in scripts[1]


def test_tick_is_single_flight(monkeypatch: pytest.MonkeyPatch) -> None:
    assert rollup._tick_lock.acquire(blocking=False)
    try:
        assert rollup.run_rollup_tick(now=NOW).as_dict() == {"skipped": "busy"}
    finally:
        rollup._tick_lock.release()


def test_n8n_rollup_workflow_targets_tick_daily_utc() -> None:
    workflow = json.loads(WORKFLOW.read_text())
    assert workflow["settings"]["timezone"] == "UTC"
    assert workflow["active"] is False
    urls = [n["parameters"].get("url", "") for n in workflow["nodes"]]
    assert any(u.endswith("/internal/analytics/rollup-tick") for u in urls)
    trigger = workflow["nodes"][0]["parameters"]["rule"]["interval"][0]
    assert trigger["triggerAtHour"] == 2 and trigger["triggerAtMinute"] == 15
