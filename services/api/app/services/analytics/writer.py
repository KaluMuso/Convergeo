"""Bounded, off-request analytics writer (plan §R-D).

One daemon thread per uvicorn worker drains a bounded queue. Properties the rest of
the platform relies on:

* **Non-blocking:** ``submit_*`` never waits — a full queue drops the item and counts
  it (``dropped_overload``). Request handlers do no analytics DB I/O.
* **Bounded:** at most ``maxsize`` queued items per worker; at most ONE pooled DB
  connection per worker is ever used for analytics (single consumer thread), so
  checkout/payment/order requests always keep the rest of the pool.
* **Coalesced:** queued event rows are merged into one multi-row
  ``INSERT … ON CONFLICT (event_id) DO NOTHING`` per drain (≤ ``max_rows`` rows).
* **Short-held:** every script runs in a transaction with ``statement_timeout`` and
  ``lock_timeout`` so analytics can never hold a connection or a lock for long.
* **Isolated failures:** every exception is swallowed and counted; nothing propagates.

v1 compatibility (plan §F.4): newly inserted ``product_view`` rows are projected into
``public.analytics_events`` in the same transaction, with exactly the v1 shape
(``session_id`` = the legacy visitor id, no entity columns, the same props), so the v1
``analytics_event_stream`` view and dashboards keep working unchanged.

Queued data is in memory: a worker restart loses at most the queue (analytics only).
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

from app.services.analytics.envelope import LogRow, is_uuid
from app.services.db import SqlResult
from app.services.orders.audit import run_sql_script, sql_literal

logger = logging.getLogger(__name__)

DEFAULT_MAXSIZE: Final = 256
DEFAULT_MAX_ROWS: Final = 500
STATEMENT_TIMEOUT_MS: Final = 2_000
LOCK_TIMEOUT_MS: Final = 500

#: v1 events still projected into ``analytics_events`` (the v1 sink's only event).
V1_PROJECTED_EVENTS: Final[frozenset[str]] = frozenset({"product_view"})

Executor = Callable[[str], SqlResult]


@dataclass(slots=True)
class _RowsItem:
    rows: list[LogRow]


@dataclass(slots=True)
class _SqlItem:
    script: str
    kind: str


@dataclass(slots=True)
class WriterStats:
    submitted_rows: int = 0
    submitted_sql: int = 0
    dropped_overload: int = 0
    batches: int = 0
    inserted_rows: int = 0
    deduped_rows: int = 0
    projected_v1_rows: int = 0
    sql_jobs_ok: int = 0
    errors: int = 0
    last_write_ms: float = 0.0
    max_write_ms: float = 0.0
    last_error_at: float | None = None
    by_kind: dict[str, int] = field(default_factory=dict)


def _uuid_sql(value: str | None) -> str:
    if value is None or not is_uuid(value):
        return "NULL"
    return f"{sql_literal(value)}::uuid"


def _text_sql(value: str | None) -> str:
    return "NULL" if value is None else sql_literal(value)


def _int_sql(value: int | None) -> str:
    if value is None or isinstance(value, bool) or not isinstance(value, int):
        return "NULL"
    return str(value)


def _ts_sql(ms: int | None) -> str:
    if ms is None or isinstance(ms, bool) or not isinstance(ms, int):
        return "NULL"
    return f"to_timestamp({ms} / 1000.0)"


def _json_sql(value: dict[str, Any]) -> str:
    return sql_literal(json.dumps(value, separators=(",", ":"), sort_keys=True)) + "::jsonb"


def _row_values(row: LogRow) -> str:
    return (
        "("
        + ", ".join(
            (
                _uuid_sql(row.event_id),
                _ts_sql(row.client_ts_ms),
                sql_literal(row.event_name),
                str(int(row.event_version)),
                sql_literal(row.source_app),
                _uuid_sql(row.anon_id),
                _uuid_sql(row.session_id),
                _uuid_sql(row.user_id),
                _int_sql(row.seq),
                _text_sql(row.page_key),
                _text_sql(row.entity_type),
                _uuid_sql(row.entity_id),
                _json_sql(row.props),
            )
        )
        + ")"
    )


def _guarded(body: str) -> str:
    return (
        "BEGIN;\n"
        f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms';\n"
        f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_MS}ms';\n"
        f"{body}\n"
        "COMMIT;\n"
    )


def build_insert_script(rows: list[LogRow]) -> str:
    """One transaction: idempotent multi-row insert + v1 projection of new rows.

    Returns ``"<inserted>|<projected>"`` as its final row.
    """
    projected = ", ".join(sql_literal(name) for name in sorted(V1_PROJECTED_EVENTS))
    values = ",\n  ".join(_row_values(row) for row in rows if is_uuid(row.event_id))
    body = f"""WITH ins AS (
  INSERT INTO public.analytics_event_log (
    event_id, client_ts, event_name, event_version, source_app, anon_id, session_id,
    user_id, seq, page_key, entity_type, entity_id, props
  ) VALUES
  {values}
  ON CONFLICT (event_id) DO NOTHING
  RETURNING event_name, anon_id, user_id, props
), proj AS (
  INSERT INTO public.analytics_events (event_type, session_id, user_id, props)
  SELECT event_name, anon_id, user_id, props FROM ins WHERE event_name IN ({projected})
  RETURNING 1
)
SELECT (SELECT count(*) FROM ins)::text || '|' || (SELECT count(*) FROM proj)::text;"""
    return _guarded(body)


class AnalyticsWriter:
    def __init__(
        self,
        *,
        maxsize: int = DEFAULT_MAXSIZE,
        max_rows: int = DEFAULT_MAX_ROWS,
        executor: Executor | None = None,
        autostart: bool = True,
    ) -> None:
        self._queue: queue.Queue[_RowsItem | _SqlItem] = queue.Queue(maxsize=maxsize)
        self._max_rows = max_rows
        self._executor: Executor = executor or run_sql_script
        self._autostart = autostart
        self._thread: threading.Thread | None = None
        self._thread_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._stats = WriterStats()

    # ------------------------------------------------------------------ submit
    def _enqueue(self, item: _RowsItem | _SqlItem) -> bool:
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            with self._stats_lock:
                self._stats.dropped_overload += 1
            return False
        self._ensure_thread()
        return True

    def submit_rows(self, rows: list[LogRow]) -> bool:
        """Queue validated event rows. Never blocks; False = dropped (queue full)."""
        if not rows:
            return True
        ok = self._enqueue(_RowsItem(rows=list(rows)))
        if ok:
            with self._stats_lock:
                self._stats.submitted_rows += len(rows)
        return ok

    def submit_sql(self, script: str, *, kind: str) -> bool:
        """Queue a self-contained best-effort analytics SQL script (server emits)."""
        ok = self._enqueue(_SqlItem(script=script, kind=kind))
        if ok:
            with self._stats_lock:
                self._stats.submitted_sql += 1
                self._stats.by_kind[kind] = self._stats.by_kind.get(kind, 0) + 1
        return ok

    # ------------------------------------------------------------------ drain
    def _ensure_thread(self) -> None:
        if not self._autostart:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        with self._thread_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run, name="analytics-writer", daemon=True
                )
                self._thread.start()

    def _run(self) -> None:  # pragma: no cover — exercised via drain_once in tests
        while True:
            try:
                first = self._queue.get()
                self._process(first)
            except Exception:  # noqa: BLE001 — the writer thread must never die
                logger.exception("analytics writer loop error (continuing)")
                time.sleep(0.5)

    def drain_once(self) -> bool:
        """Process whatever is queued now (tests / shutdown). False when empty."""
        try:
            first = self._queue.get_nowait()
        except queue.Empty:
            return False
        self._process(first)
        return True

    def _process(self, first: _RowsItem | _SqlItem) -> None:
        if isinstance(first, _SqlItem):
            self._exec_sql(first)
            return
        rows = list(first.rows)
        pending_sql: list[_SqlItem] = []
        while len(rows) < self._max_rows:
            try:
                nxt = self._queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(nxt, _SqlItem):
                pending_sql.append(nxt)
            else:
                rows.extend(nxt.rows)
        self._exec_rows(rows[: self._max_rows])
        if len(rows) > self._max_rows:
            self._exec_rows(rows[self._max_rows :])
        for item in pending_sql:
            self._exec_sql(item)

    def _timed(self, script: str) -> tuple[SqlResult | None, float]:
        started = time.perf_counter()
        try:
            result: SqlResult | None = self._executor(script)
        except Exception:  # noqa: BLE001
            logger.debug("analytics writer executor raised", exc_info=True)
            result = None
        return result, (time.perf_counter() - started) * 1000.0

    def _record_timing(self, elapsed_ms: float) -> None:
        self._stats.last_write_ms = elapsed_ms
        self._stats.max_write_ms = max(self._stats.max_write_ms, elapsed_ms)

    def _exec_rows(self, rows: list[LogRow]) -> None:
        if not rows:
            return
        result, elapsed = self._timed(build_insert_script(rows))
        with self._stats_lock:
            self._stats.batches += 1
            self._record_timing(elapsed)
            if result is None or not result.ok:
                self._stats.errors += 1
                self._stats.last_error_at = time.time()
                if result is not None:
                    logger.debug("analytics writer insert failed: %s", result.error)
                return
            inserted, projected = 0, 0
            if result.rows:
                parts = result.rows[-1].split("|")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    inserted, projected = int(parts[0]), int(parts[1])
            self._stats.inserted_rows += inserted
            self._stats.deduped_rows += max(0, len(rows) - inserted)
            self._stats.projected_v1_rows += projected

    def _exec_sql(self, item: _SqlItem) -> None:
        result, elapsed = self._timed(_guarded(item.script))
        with self._stats_lock:
            self._record_timing(elapsed)
            if result is None or not result.ok:
                self._stats.errors += 1
                self._stats.last_error_at = time.time()
                if result is not None:
                    logger.debug("analytics writer %s job failed: %s", item.kind, result.error)
                return
            self._stats.sql_jobs_ok += 1

    # ------------------------------------------------------------------ stats
    def stats(self) -> dict[str, Any]:
        with self._stats_lock:
            s = self._stats
            return {
                "queue_depth": self._queue.qsize(),
                "queue_max": self._queue.maxsize,
                "thread_alive": bool(self._thread and self._thread.is_alive()),
                "submitted_rows": s.submitted_rows,
                "submitted_sql": s.submitted_sql,
                "dropped_overload": s.dropped_overload,
                "batches": s.batches,
                "inserted_rows": s.inserted_rows,
                "deduped_rows": s.deduped_rows,
                "projected_v1_rows": s.projected_v1_rows,
                "sql_jobs_ok": s.sql_jobs_ok,
                "errors": s.errors,
                "last_write_ms": round(s.last_write_ms, 2),
                "max_write_ms": round(s.max_write_ms, 2),
                "last_error_at": s.last_error_at,
                "sql_by_kind": dict(s.by_kind),
            }


_writer: AnalyticsWriter | None = None
_writer_lock = threading.Lock()


def get_writer() -> AnalyticsWriter:
    """The per-worker writer (created lazily, after the uvicorn worker process starts)."""
    global _writer
    if _writer is None:
        with _writer_lock:
            if _writer is None:
                _writer = AnalyticsWriter()
    return _writer


def set_writer_for_tests(writer: AnalyticsWriter | None) -> None:
    global _writer
    with _writer_lock:
        _writer = writer
