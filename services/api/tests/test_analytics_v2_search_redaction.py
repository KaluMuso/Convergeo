"""Convergeo Intelligence 1A-06: search-term redaction (plan §R-E), collect-flag gated."""

from __future__ import annotations

import logging
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from app.services import search as search_service
from app.services.analytics import flags as analytics_flags
from app.services.analytics import search_log
from app.services.analytics import writer as writer_mod
from app.services.analytics.search_log import redact_term
from app.services.analytics.writer import AnalyticsWriter
from app.services.db import SqlResult


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("samsung a54", "samsung a54"),
        ("phones under 500", "phones under 500"),
        ("iphone 15 pro 256gb", "iphone 15 pro 256gb"),
        ("call 0977 123 456 for tv", "call # for tv"),
        ("+260971234567 fridge", "# fridge"),
        ("nrc 123456/78/1", "nrc #"),
        ("mail me jane.doe+x@example.co.zm", "mail me @"),
        ("x" * 300, "x" * 120),
    ],
)
def test_redact_term(raw: str, expected: str) -> None:
    assert redact_term(raw) == expected


@pytest.fixture
def writer() -> Generator[AnalyticsWriter, None, None]:
    w = AnalyticsWriter(
        executor=MagicMock(return_value=SqlResult(ok=True, rows=[])), autostart=False
    )
    writer_mod.set_writer_for_tests(w)
    yield w
    writer_mod.set_writer_for_tests(None)


def _queued_sql(writer: AnalyticsWriter) -> str:
    writer.drain_once()
    return str(writer._executor.call_args.args[0])  # type: ignore[attr-defined]


def test_flag_on_logs_redacted_term(writer: AnalyticsWriter) -> None:
    analytics_flags.override_for_tests(analytics_flags.COLLECT_FLAG, True)
    search_log.log_search_query(term="Fridge 0977123456", zero_result=True)
    sql = _queued_sql(writer)
    assert "0977123456" not in sql
    assert "'Fridge #'" in sql and "'fridge #'" in sql


def test_flag_off_logs_raw_term(monkeypatch: pytest.MonkeyPatch) -> None:
    analytics_flags.override_for_tests(analytics_flags.COLLECT_FLAG, False)
    fake = MagicMock(return_value=SqlResult(ok=True, rows=[]))
    monkeypatch.setattr(search_log, "run_sql_script", fake)
    search_log.log_search_query(term="Fridge 0977123456", zero_result=True)
    assert "0977123456" in fake.call_args.args[0]


def test_zero_result_app_log_redacted_when_flag_on(caplog: pytest.LogCaptureFixture) -> None:
    analytics_flags.override_for_tests(analytics_flags.COLLECT_FLAG, True)
    with caplog.at_level(logging.INFO, logger=search_service.logger.name):
        search_service.log_zero_result(query="tv a@b.com", filters={}, kind=None)
    assert [r.query for r in caplog.records if r.message == "search_zero_result"] == ["tv @"]  # type: ignore[attr-defined]


def test_session_id_sql_only_with_collect_on_and_valid_uuid() -> None:
    """OD-8: the anonymous session id is stored only under analytics_v2_collect."""
    from app.services.analytics import flags as analytics_flags
    from app.services.analytics.search_log import _session_id_sql

    sid = "0D080000-0000-4000-8000-000000000001"
    analytics_flags.override_for_tests(analytics_flags.COLLECT_FLAG, False)
    assert _session_id_sql(sid) == "null"
    analytics_flags.override_for_tests(analytics_flags.COLLECT_FLAG, True)
    assert _session_id_sql(sid) == f"'{sid.lower()}'::uuid"
    assert _session_id_sql("not-a-uuid'; drop table x;--") == "null"
    assert _session_id_sql(None) == "null"
