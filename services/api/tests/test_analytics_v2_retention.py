"""Convergeo Intelligence 1A-07: v2 retention tick + storage endpoint (DB-free).

The live-DB behaviour of the sweep is in ``tests/rls/test_analytics_v2_retention_db.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.routers import internal_analytics as mod
from app.services.analytics import flags as analytics_flags
from app.services.analytics.retention import RetentionSweepResult, V2RetentionResult
from fastapi.testclient import TestClient

TOKEN = {"X-Internal-Token": "dev-internal-analytics"}
WORKFLOW = Path(__file__).resolve().parents[3] / "infra" / "n8n" / "analytics-retention.json"


def test_tick_requires_token(client: TestClient) -> None:
    assert client.post("/internal/analytics/v2-retention-tick").status_code == 401
    assert client.get("/internal/analytics/storage").status_code == 401


def test_tick_is_noop_when_rollups_flag_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sweep = MagicMock(side_effect=AssertionError("must not sweep with the flag off"))
    monkeypatch.setattr(mod, "sweep_v2_retention", sweep)
    resp = client.post("/internal/analytics/v2-retention-tick", headers=TOKEN)
    assert resp.status_code == 200 and resp.json() == {"skipped": "flag_off"}


def test_tick_runs_when_rollups_flag_on(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, True)
    monkeypatch.setattr(
        mod,
        "sweep_v2_retention",
        MagicMock(return_value=V2RetentionResult(5, 7, 1, complete=True, search_daily_purged=4)),
    )
    resp = client.post("/internal/analytics/v2-retention-tick", headers=TOKEN)
    assert resp.json() == {
        "event_log_deleted": 5,
        "listing_dedup_purged": 7,
        "search_terms_scrubbed": 1,
        "search_daily_purged": 4,
        "complete": True,
    }


def test_v1_retention_tick_shape_unchanged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mod,
        "sweep_analytics_retention",
        MagicMock(return_value=RetentionSweepResult(1, 2, 3)),
    )
    resp = client.post("/internal/analytics/retention-tick", headers=TOKEN)
    assert resp.json() == {"search_query_log": 1, "funnel_events": 2, "analytics_events": 3}


def test_storage_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    report = {"database_bytes": 10, "analytics_total_bytes": 4, "tables": {}}
    monkeypatch.setattr(mod, "analytics_storage_report", MagicMock(return_value=report))
    assert client.get("/internal/analytics/storage", headers=TOKEN).json() == report
    monkeypatch.setattr(
        mod, "analytics_storage_report", MagicMock(side_effect=RuntimeError("db down"))
    )
    assert client.get("/internal/analytics/storage", headers=TOKEN).status_code == 503


def test_n8n_workflow_chains_v2_tick_in_utc() -> None:
    workflow = json.loads(WORKFLOW.read_text())
    assert workflow["settings"]["timezone"] == "UTC"
    urls = [n["parameters"].get("url", "") for n in workflow["nodes"]]
    assert any(u.endswith("/internal/analytics/retention-tick") for u in urls)
    assert any(u.endswith("/internal/analytics/v2-retention-tick") for u in urls)
    assert workflow["connections"]["Sweep Analytics PII"]["main"][0][0]["node"] == (
        "Sweep Analytics v2 (flag-gated)"
    )


def test_storage_report_flags_70_percent_of_free_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """FC-1: Supabase Free 500 MB quota; alert at 70% (350 MB)."""
    from app.services.analytics import retention
    from app.services.db import SqlResult

    mb = 1024 * 1024
    for size, alert in ((22 * mb, False), (350 * mb - 1, False), (350 * mb, True)):
        monkeypatch.setattr(
            retention,
            "run_sql_script",
            lambda _s, size=size: SqlResult(ok=True, rows=[f"database|{size}|0"]),
        )
        report = retention.analytics_storage_report()
        assert report["quota_bytes"] == 500 * mb
        assert report["alert_threshold_bytes"] == 350 * mb
        assert report["alert"] is alert
