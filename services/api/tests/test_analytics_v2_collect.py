"""Convergeo Intelligence 1A-03: analytics_v2 collect path, writer, limiter, client key.

DB-free. The flag is pinned via ``flags.override_for_tests``; the writer runs with a
fake executor and ``autostart=False`` so draining is deterministic. The live-DB
idempotency/projection check lives in ``tests/rls/test_analytics_v2_writer_db.py``.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.inproc_ratelimit import InProcessRateLimiter
from app.routers import analytics_collect as collect_mod
from app.services.analytics import flags as analytics_flags
from app.services.analytics import writer as writer_mod
from app.services.analytics.client_key import is_cloudflare_ip, trusted_client_key
from app.services.analytics.envelope import LogRow
from app.services.analytics.writer import AnalyticsWriter, build_insert_script
from app.services.db import SqlResult
from fastapi.testclient import TestClient
from starlette.requests import Request

ANON = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PRODUCT = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
CF_EDGE = "172.70.1.2"  # inside 172.64.0.0/13


def _eid(n: int) -> str:
    return f"eeeeeeee-eeee-4eee-8eee-{n:012d}"


def _pv(n: int) -> dict[str, Any]:
    return {
        "event": "product_view",
        "ev": 1,
        "id": _eid(n),
        "seq": n,
        "page": "pdp",
        "props": {"product_id": PRODUCT},
    }


def _v2_body(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "v": 2,
        "app": "customer",
        "session_id": ANON,
        "anon": ANON,
        "sid": SID,
        "events": events,
    }


class FakeExecutor:
    def __init__(self, result: SqlResult | None = None, exc: Exception | None = None) -> None:
        self.scripts: list[str] = []
        self.result = result or SqlResult(ok=True, rows=["1|1"])
        self.exc = exc

    def __call__(self, script: str) -> SqlResult:
        self.scripts.append(script)
        if self.exc is not None:
            raise self.exc
        return self.result


@pytest.fixture
def fake_writer() -> Generator[tuple[AnalyticsWriter, FakeExecutor], None, None]:
    executor = FakeExecutor()
    writer = AnalyticsWriter(executor=executor, autostart=False, maxsize=4)
    writer_mod.set_writer_for_tests(writer)
    yield writer, executor
    writer_mod.set_writer_for_tests(None)


@pytest.fixture
def v2_on(monkeypatch: pytest.MonkeyPatch) -> Generator[MagicMock, None, None]:
    analytics_flags.override_for_tests(analytics_flags.COLLECT_FLAG, True)
    collect_mod.reset_v2_state_for_tests(
        InProcessRateLimiter(
            global_rate_per_sec=1000, global_burst=1000, key_rate_per_sec=1000, key_burst=1000
        )
    )
    # The v2 path must never touch the DB-backed limiter or the v1 sink.
    bump = MagicMock(side_effect=AssertionError("v2 must not use the DB rate limiter"))
    record = MagicMock(side_effect=AssertionError("v2 must not write inline"))
    monkeypatch.setattr(collect_mod, "bump_rate_counter", bump)
    monkeypatch.setattr(collect_mod, "record_event", record)
    yield bump
    analytics_flags.override_for_tests(analytics_flags.COLLECT_FLAG, False)


class TestFlagOffKeepsV1:
    def test_v2_batch_with_flag_off_takes_v1_path(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_writer: Any
    ) -> None:
        bump = MagicMock(return_value=(True, 0))
        record = MagicMock(return_value={"id": "x"})
        monkeypatch.setattr(collect_mod, "bump_rate_counter", bump)
        monkeypatch.setattr(collect_mod, "record_event", record)
        resp = client.post("/analytics/collect", json=_v2_body([_pv(1)]))
        assert resp.status_code == 200
        assert resp.json() == {"accepted": 1, "skipped": 0, "rejected": 0}
        bump.assert_called_once()  # v1 DB limiter still in force
        # v1 semantics: the legacy session_id is stored, v2 extras are ignored.
        assert record.call_args.kwargs["session_id"] == ANON
        assert record.call_args.kwargs["props"] == {"product_id": PRODUCT}
        writer, _ = fake_writer
        assert writer.stats()["submitted_rows"] == 0


class TestCollectV2:
    def test_accepts_and_queues_without_db_io(
        self, client: TestClient, v2_on: MagicMock, fake_writer: Any
    ) -> None:
        resp = client.post(
            "/analytics/collect",
            json=_v2_body(
                [_pv(1), _pv(2), {"event": "cart_add", "props": {}}, {"event": "nope", "props": {}}]
            ),
        )
        assert resp.status_code == 200
        assert resp.json() == {"accepted": 2, "skipped": 1, "rejected": 1}
        writer, executor = fake_writer
        assert writer.stats()["queue_depth"] == 1
        assert executor.scripts == []  # nothing written on the request
        v2_on.assert_not_called()
        counters = collect_mod.ingest_counters()
        assert counters["accepted"] == 2 and counters["rejected_unknown"] == 1

    def test_v1_shaped_batch_is_accepted(
        self, client: TestClient, v2_on: MagicMock, fake_writer: Any
    ) -> None:
        body = {
            "session_id": ANON,
            "events": [{"event": "product_view", "props": {"product_id": PRODUCT}}],
        }
        resp = client.post("/analytics/collect", json=body)
        assert resp.json() == {"accepted": 1, "skipped": 0, "rejected": 0}

    def test_batch_cap_still_413(self, client: TestClient, v2_on: MagicMock) -> None:
        resp = client.post("/analytics/collect", json=_v2_body([_pv(i) for i in range(21)]))
        assert resp.status_code == 413

    def test_rate_limited_returns_429_and_counts(
        self, client: TestClient, v2_on: MagicMock, fake_writer: Any
    ) -> None:
        collect_mod.reset_v2_state_for_tests(
            InProcessRateLimiter(
                global_rate_per_sec=0.001, global_burst=1, key_rate_per_sec=1000, key_burst=1000
            )
        )
        assert client.post("/analytics/collect", json=_v2_body([_pv(1)])).status_code == 200
        assert client.post("/analytics/collect", json=_v2_body([_pv(2)])).status_code == 429
        assert collect_mod.ingest_counters()["dropped_rate_limited"] == 1

    def test_writer_full_drops_not_errors(
        self, client: TestClient, v2_on: MagicMock, fake_writer: Any
    ) -> None:
        for n in range(6):  # maxsize=4
            assert client.post("/analytics/collect", json=_v2_body([_pv(n)])).status_code == 200
        writer, _ = fake_writer
        assert writer.stats()["dropped_overload"] == 2
        assert collect_mod.ingest_counters()["dropped_overload"] == 2

    def test_malformed_body_never_500s(
        self, client: TestClient, v2_on: MagicMock, fake_writer: Any
    ) -> None:
        resp = client.post("/analytics/collect", json={"v": 2, "anon": 5, "events": []})
        assert resp.status_code == 200
        assert collect_mod.ingest_counters()["rejected_malformed"] == 1


class TestWriter:
    def _row(self, n: int) -> LogRow:
        return LogRow(
            event_id=_eid(n),
            event_name="product_view",
            event_version=1,
            source_app="customer",
            anon_id=ANON,
            session_id=SID,
            user_id=None,
            client_ts_ms=1_800_000_000_000,
            seq=n,
            page_key="pdp",
            entity_type="product",
            entity_id=PRODUCT,
            props={"product_id": PRODUCT, "q": "it's"},
        )

    def test_coalesces_queued_batches_into_one_insert(self) -> None:
        executor = FakeExecutor(SqlResult(ok=True, rows=["3|3"]))
        writer = AnalyticsWriter(executor=executor, autostart=False)
        writer.submit_rows([self._row(1)])
        writer.submit_rows([self._row(2), self._row(3)])
        assert writer.drain_once() is True
        assert len(executor.scripts) == 1
        stats = writer.stats()
        assert stats["inserted_rows"] == 3 and stats["deduped_rows"] == 0
        assert stats["projected_v1_rows"] == 3 and stats["queue_depth"] == 0
        assert writer.drain_once() is False

    def test_dedup_counted_from_insert_result(self) -> None:
        writer = AnalyticsWriter(
            executor=FakeExecutor(SqlResult(ok=True, rows=["1|0"])), autostart=False
        )
        writer.submit_rows([self._row(1), self._row(2)])
        writer.drain_once()
        assert writer.stats()["deduped_rows"] == 1

    def test_errors_swallowed_and_counted(self) -> None:
        for executor in (
            FakeExecutor(SqlResult(ok=False, rows=[], error="boom")),
            FakeExecutor(exc=RuntimeError("pool timeout")),
        ):
            writer = AnalyticsWriter(executor=executor, autostart=False)
            writer.submit_rows([self._row(1)])
            writer.submit_sql("SELECT 1;", kind="funnel")
            writer.drain_once()
            writer.drain_once()
            assert writer.stats()["errors"] == 2

    def test_max_rows_split(self) -> None:
        executor = FakeExecutor()
        writer = AnalyticsWriter(executor=executor, autostart=False, max_rows=2)
        writer.submit_rows([self._row(1), self._row(2), self._row(3)])
        writer.drain_once()
        assert len(executor.scripts) == 2

    def test_script_is_guarded_and_escaped(self) -> None:
        script = build_insert_script([self._row(1)])
        assert script.startswith("BEGIN;\nSET LOCAL statement_timeout = '2000ms';")
        assert "SET LOCAL lock_timeout = '500ms';" in script
        assert "ON CONFLICT (event_id) DO NOTHING" in script
        assert "it''s" in script  # quotes doubled inside the jsonb literal
        assert "to_timestamp(1800000000000 / 1000.0)" in script
        assert script.rstrip().endswith("COMMIT;")

    def test_sql_jobs_are_guarded(self) -> None:
        executor = FakeExecutor()
        writer = AnalyticsWriter(executor=executor, autostart=False)
        writer.submit_sql("INSERT INTO x VALUES (1);", kind="funnel")
        writer.drain_once()
        assert executor.scripts[0].startswith("BEGIN;\nSET LOCAL statement_timeout")
        assert writer.stats()["sql_jobs_ok"] == 1 and writer.stats()["sql_by_kind"] == {"funnel": 1}


class TestLimiter:
    def test_per_key_and_global(self) -> None:
        now = [0.0]
        limiter = InProcessRateLimiter(
            global_rate_per_sec=1,
            global_burst=3,
            key_rate_per_sec=1,
            key_burst=2,
            clock=lambda: now[0],
        )
        assert limiter.allow("a") and limiter.allow("a")
        assert not limiter.allow("a")  # key exhausted
        assert limiter.allow("b")  # global still has one
        assert not limiter.allow("c")  # global exhausted
        now[0] = 2.0
        assert limiter.allow("c")

    def test_lru_bounded(self) -> None:
        limiter = InProcessRateLimiter(
            global_rate_per_sec=100, global_burst=100, key_rate_per_sec=1, key_burst=1, max_keys=3
        )
        for key in "abcde":
            limiter.allow(key)
        assert limiter.tracked_keys() == 3

    def test_rejects_bad_config(self) -> None:
        with pytest.raises(ValueError):
            InProcessRateLimiter(
                global_rate_per_sec=0, global_burst=1, key_rate_per_sec=1, key_burst=1
            )


def _request(headers: dict[str, str], peer: str = "10.0.0.5") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/analytics/collect",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 1234),
    }
    return Request(scope)


class TestClientKey:
    def test_leftmost_xff_is_never_trusted(self) -> None:
        req = _request({"X-Forwarded-For": "6.6.6.6, 41.77.1.9"})
        assert trusted_client_key(req) == "41.77.1.9"

    def test_cf_connecting_ip_used_only_behind_cloudflare(self) -> None:
        via_cf = _request({"X-Forwarded-For": CF_EDGE, "CF-Connecting-IP": "41.77.1.9"})
        assert trusted_client_key(via_cf) == "41.77.1.9"
        spoofed = _request({"X-Forwarded-For": "41.77.1.9", "CF-Connecting-IP": "1.2.3.4"})
        assert trusted_client_key(spoofed) == "41.77.1.9"

    def test_falls_back_to_peer_and_handles_garbage(self) -> None:
        assert trusted_client_key(_request({})) == "10.0.0.5"
        assert trusted_client_key(_request({"X-Forwarded-For": "not-an-ip"})) == "unknown"
        cf_bad = _request({"X-Forwarded-For": CF_EDGE, "CF-Connecting-IP": "zzz"})
        assert trusted_client_key(cf_bad) == CF_EDGE

    def test_cloudflare_ranges(self) -> None:
        assert is_cloudflare_ip("104.16.0.1") and is_cloudflare_ip("2606:4700::1")
        assert not is_cloudflare_ip("41.77.1.9") and not is_cloudflare_ip("garbage")


class TestIngestStats:
    def test_requires_token_and_reports(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_writer: Any
    ) -> None:
        assert client.get("/internal/analytics/ingest-stats").status_code == 401
        resp = client.get(
            "/internal/analytics/ingest-stats",
            headers={"X-Internal-Token": "dev-internal-analytics"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"pid", "flags", "ingest", "limiter_tracked_keys", "writer"}
        assert body["flags"]["analytics_v2_collect"] is False
        assert "dropped_overload" in body["writer"]
