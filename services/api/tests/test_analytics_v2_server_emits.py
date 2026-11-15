"""Convergeo Intelligence 1A-05: server funnel/search emits leave the request path.

Flag OFF: the inline write runs exactly as before. Flag ON: the same idempotent SQL
goes to the bounded writer and nothing touches the DB on the caller's thread.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from app.services.analytics import flags as analytics_flags
from app.services.analytics import funnel, search_log
from app.services.analytics import writer as writer_mod
from app.services.analytics.writer import AnalyticsWriter
from app.services.db import SqlResult

GROUP = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
CUSTOMER = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


@pytest.fixture
def writer() -> Generator[AnalyticsWriter, None, None]:
    executor = MagicMock(return_value=SqlResult(ok=True, rows=[]))
    w = AnalyticsWriter(executor=executor, autostart=False, maxsize=2)
    writer_mod.set_writer_for_tests(w)
    yield w
    writer_mod.set_writer_for_tests(None)


@pytest.fixture
def inline_db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock(return_value=SqlResult(ok=True, rows=["id|cart_add|ts"]))
    monkeypatch.setattr(funnel, "run_sql_script", fake)
    monkeypatch.setattr(search_log, "run_sql_script", fake)
    return fake


def _flag(value: bool) -> None:
    analytics_flags.override_for_tests(analytics_flags.COLLECT_FLAG, value)


class TestFunnel:
    def test_flag_off_writes_inline(self, inline_db: MagicMock, writer: AnalyticsWriter) -> None:
        _flag(False)
        row = funnel.record_event_best_effort(
            stage="checkout_start", checkout_group_id=GROUP, customer_id=CUSTOMER, snapshot={}
        )
        assert row == {"id": "id", "stage": "cart_add", "created_at": "ts"}
        inline_db.assert_called_once()
        assert writer.stats()["submitted_sql"] == 0

    def test_flag_on_queues_same_sql(self, inline_db: MagicMock, writer: AnalyticsWriter) -> None:
        _flag(True)
        row = funnel.record_event_best_effort(
            stage="checkout_start",
            checkout_group_id=GROUP,
            customer_id=CUSTOMER,
            snapshot={"total_ngwee": 1500},
        )
        assert row is None
        inline_db.assert_not_called()
        stats = writer.stats()
        assert stats["submitted_sql"] == 1 and stats["sql_by_kind"] == {"funnel_checkout_start": 1}
        writer.drain_once()
        executed = writer._executor.call_args.args[0]  # type: ignore[attr-defined]
        assert "ON CONFLICT (checkout_group_id, stage)" in executed
        assert executed.startswith("BEGIN;\nSET LOCAL statement_timeout")
        assert executed == writer_mod._guarded(
            funnel.build_record_event_sql(
                stage="checkout_start",
                checkout_group_id=GROUP,
                customer_id=CUSTOMER,
                snapshot={"total_ngwee": 1500},
            )
        )

    def test_flag_on_invalid_input_swallowed(
        self, inline_db: MagicMock, writer: AnalyticsWriter
    ) -> None:
        _flag(True)
        assert (
            funnel.record_event_best_effort(
                stage="cart_add", checkout_group_id="nope", customer_id=None, snapshot={}
            )
            is None
        )
        assert writer.stats()["submitted_sql"] == 0
        inline_db.assert_not_called()

    def test_flag_on_full_queue_never_raises(
        self, inline_db: MagicMock, writer: AnalyticsWriter
    ) -> None:
        _flag(True)
        for _ in range(5):  # maxsize=2
            funnel.record_event_best_effort(
                stage="cart_add", checkout_group_id=None, customer_id=None, snapshot={}
            )
        assert writer.stats()["dropped_overload"] == 3

    def test_record_event_unchanged_for_sweeper(self, inline_db: MagicMock) -> None:
        _flag(True)  # the abandonment sweeper's direct record_event stays inline
        funnel.record_event(stage="abandoned", checkout_group_id=GROUP, snapshot={})
        inline_db.assert_called_once()


class TestSearchLog:
    def test_flag_off_inline(self, inline_db: MagicMock, writer: AnalyticsWriter) -> None:
        _flag(False)
        search_log.log_search_query(term="Phones", zero_result=False)
        inline_db.assert_called_once()
        assert writer.stats()["submitted_sql"] == 0

    def test_flag_on_queued(self, inline_db: MagicMock, writer: AnalyticsWriter) -> None:
        _flag(True)
        search_log.log_search_query(term="Phones", zero_result=True)
        search_log.log_ask_query(term="Where?", usd_micros=5)
        inline_db.assert_not_called()
        assert writer.stats()["sql_by_kind"] == {"search_log": 1, "ask_log": 1}
