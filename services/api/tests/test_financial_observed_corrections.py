"""Bounded source controls only; the PostgreSQL cases remain mandatory."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from app.services.db import SqlResult
from tests import financial_observed_sql as diagnostics

ROOT = Path(__file__).resolve().parents[3]


def test_completion_forward_preserves_all_authority_except_record_name() -> None:
    migrations = ROOT / "supabase/migrations"
    original = (migrations / "20260929120002_funded_service_completion.sql").read_text()
    forward = (migrations / "20260930203000_service_completion_variable_disambiguation.sql")
    expected = original[original.index("create function public.confirm_funded_service("):]
    expected = expected.replace("create function", "create or replace function", 1)
    expected = expected.replace("; ob record;", "; balance_obligation record;")
    expected = expected.replace("for ob in select", "for balance_obligation in select")
    expected = expected.replace("1,ob.amount_ngwee);", "1,balance_obligation.amount_ngwee);")
    actual = forward.read_text()
    assert actual[actual.index("create or replace function"):].strip() == expected.strip()


def test_fixture_diagnostics_preserve_error_result_without_disclosure_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = SqlResult(ok=False, rows=[], error="invalid service obligation")
    monkeypatch.setattr(diagnostics, "run_sql_script", lambda script: result)
    monkeypatch.setenv("LANE_D_POSTGREST_URL", "http://127.0.0.1:3006")
    request: Any = SimpleNamespace(node=SimpleNamespace(user_properties=[]))
    assert diagnostics.capture_native_sql(request, label="rfq_accept")("BEGIN;") is result
    evidence = json.loads(request.node.user_properties[0][1])
    assert evidence["error"] == "invalid service obligation"
    assert evidence["rows"] == [] and evidence["affected_rows"] == 0
