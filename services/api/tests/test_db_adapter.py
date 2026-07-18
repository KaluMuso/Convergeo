"""WP-1A — native psycopg ``run_sql_script`` adapter contract tests.

Two layers:

* **Rendering unit tests** (no database) — pin the psql ``-At`` row projection that
  callers parse (``|`` join, ``NULL`` -> ``''``, raw ``bool`` -> ``t``/``f``, blank-row
  drop, multi-result-set ordering).
* **Integration tests** (real Postgres, skipped when unreachable — same contract as
  the rest of the DB suite) — build a tiny self-contained schema (an orders-like
  table with an audit trigger reading a transaction-local GUC, and a double-entry
  ledger) and prove: one script == one transaction, full rollback on failure,
  transaction-local ``set_config(..., true)`` reaching the audit trigger, and
  representative order/ledger write shapes.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Any, cast

import psycopg
import pytest
from app.services import db as db_module
from app.services.db import (
    SqlResult,
    _gather_rows,
    _render_row,
    _render_value,
    reset_pools,
    resolve_db_url,
    run_sql_script,
)
from app.services.orders.audit import ORDER_ACTOR_GUC, ORDER_NOTE_GUC, sql_literal


def _uuid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Rendering unit tests (no database required).
# --------------------------------------------------------------------------- #


def test_render_value_null_is_empty_string() -> None:
    assert _render_value(None) == ""


def test_render_value_bool_is_psql_t_f() -> None:
    # state.py:267 compares a raw boolean column via ``parts[4] == "t"``.
    assert _render_value(True) == "t"
    assert _render_value(False) == "f"


def test_render_value_scalars_match_str() -> None:
    assert _render_value(5) == "5"
    assert _render_value(-42) == "-42"
    oid = uuid.uuid4()
    assert _render_value(oid) == str(oid)


def test_render_value_bytes_is_bytea_hex() -> None:
    assert _render_value(b"\x00\xff") == "\\x00ff"


def test_render_value_container_is_compact_json() -> None:
    assert _render_value({"a": 1, "b": "x"}) == '{"a":1,"b":"x"}'
    assert _render_value([1, 2]) == "[1,2]"


def test_render_row_pipe_joins_columns_with_null_empty() -> None:
    assert _render_row((1, None, "x", True)) == "1||x|t"


class _FakeCursor:
    """Minimal cursor stand-in exercising the nextset()/description gather loop."""

    def __init__(self, result_sets: list[list[tuple[object, ...]] | None]) -> None:
        self._sets = result_sets
        self._idx = 0

    @property
    def description(self) -> object | None:
        rows = self._sets[self._idx]
        return object() if rows is not None else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._sets[self._idx] or []

    def nextset(self) -> bool:
        if self._idx + 1 < len(self._sets):
            self._idx += 1
            return True
        return False


def test_gather_rows_flattens_result_sets_in_order() -> None:
    # BEGIN (no rows) -> set_config (actor) -> set_config ('' dropped) -> RETURNING
    cursor = _FakeCursor([None, [("actor-1",)], [("",)], [("shipped",)], None])
    assert _gather_rows(cast("psycopg.Cursor[Any]", cursor)) == ["actor-1", "shipped"]


def test_gather_rows_drops_command_tag_and_noise_lookalikes() -> None:
    cursor = _FakeCursor([[("BEGIN",), ("UPDATE 3",), ("real-value",)]])
    assert _gather_rows(cast("psycopg.Cursor[Any]", cursor)) == ["real-value"]


# --------------------------------------------------------------------------- #
# Integration tests (real Postgres; skipped when unreachable).
# --------------------------------------------------------------------------- #

_SCHEMA_SQL = """
DROP TABLE IF EXISTS wp1a_ledger_postings CASCADE;
DROP TABLE IF EXISTS wp1a_ledger_transactions CASCADE;
DROP TABLE IF EXISTS wp1a_order_events CASCADE;
DROP TABLE IF EXISTS wp1a_orders CASCADE;

CREATE TABLE wp1a_orders (
  id uuid PRIMARY KEY,
  status text NOT NULL
);

CREATE TABLE wp1a_order_events (
  id bigserial PRIMARY KEY,
  order_id uuid NOT NULL,
  actor uuid,
  note text,
  from_status text,
  to_status text
);

-- Mirrors public.audit_orders_status_change (migration 0014): reads the
-- transaction-local app.order_actor / app.order_note GUCs primed in the same script.
CREATE OR REPLACE FUNCTION wp1a_audit_status_change() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
  audit_actor uuid;
  audit_note text;
BEGIN
  IF tg_op = 'UPDATE' AND new.status IS DISTINCT FROM old.status THEN
    audit_actor := nullif(current_setting('app.order_actor', true), '')::uuid;
    audit_note := nullif(current_setting('app.order_note', true), '');
    INSERT INTO wp1a_order_events (order_id, actor, note, from_status, to_status)
    VALUES (new.id, audit_actor, audit_note, old.status, new.status);
  END IF;
  RETURN new;
END;
$fn$;

DROP TRIGGER IF EXISTS wp1a_orders_audit ON wp1a_orders;
CREATE TRIGGER wp1a_orders_audit AFTER UPDATE ON wp1a_orders
  FOR EACH ROW EXECUTE FUNCTION wp1a_audit_status_change();

CREATE TABLE wp1a_ledger_transactions (
  id uuid PRIMARY KEY,
  idempotency_key text UNIQUE,
  kind text NOT NULL
);

CREATE TABLE wp1a_ledger_postings (
  id bigserial PRIMARY KEY,
  transaction_id uuid NOT NULL REFERENCES wp1a_ledger_transactions(id),
  account text NOT NULL,
  amount_ngwee bigint NOT NULL
);
"""

_TEARDOWN_SQL = (
    "DROP TABLE IF EXISTS wp1a_ledger_postings CASCADE;"
    "DROP TABLE IF EXISTS wp1a_ledger_transactions CASCADE;"
    "DROP TABLE IF EXISTS wp1a_order_events CASCADE;"
    "DROP TABLE IF EXISTS wp1a_orders CASCADE;"
)


def _db_reachable(url: str) -> bool:
    try:
        with psycopg.connect(url, connect_timeout=2):
            return True
    except psycopg.Error:
        return False


@pytest.fixture(scope="module")
def adapter_db() -> Generator[None, None, None]:
    url = resolve_db_url()
    if not _db_reachable(url):
        pytest.skip(f"Postgres not reachable at {url}")
    setup = run_sql_script(_SCHEMA_SQL)
    assert setup.ok, setup.error
    yield
    run_sql_script(_TEARDOWN_SQL)
    reset_pools()


@pytest.fixture
def order_id(adapter_db: None) -> str:
    oid = _uuid()
    inserted = run_sql_script(
        f"INSERT INTO wp1a_orders (id, status) VALUES ('{oid}', 'placed');"
    )
    assert inserted.ok, inserted.error
    return oid


def test_script_is_one_transaction_full_rollback_on_failure(adapter_db: None) -> None:
    oid = _uuid()
    result = run_sql_script(
        "BEGIN;"
        f"INSERT INTO wp1a_orders (id, status) VALUES ('{oid}', 'placed');"
        "DO $x$ BEGIN RAISE EXCEPTION 'wp1a injected failure'; END $x$;"
        "COMMIT;"
    )
    assert result.ok is False
    assert "wp1a injected failure" in (result.error or "")
    # The partial INSERT must be fully rolled back — never a partial write.
    check = run_sql_script(f"SELECT id::text FROM wp1a_orders WHERE id = '{oid}';")
    assert check.ok is True
    assert check.rows == []


def test_failure_without_explicit_begin_is_still_atomic(adapter_db: None) -> None:
    oid = _uuid()
    result = run_sql_script(
        f"INSERT INTO wp1a_orders (id, status) VALUES ('{oid}', 'placed');"
        "SELECT 1 / 0;"
    )
    assert result.ok is False
    check = run_sql_script(f"SELECT id::text FROM wp1a_orders WHERE id = '{oid}';")
    assert check.rows == []


def test_connection_reusable_after_rollback(adapter_db: None) -> None:
    # A failing script must not poison the pooled connection for the next caller.
    bad = run_sql_script("BEGIN; SELECT 1 / 0; COMMIT;")
    assert bad.ok is False
    good = run_sql_script("SELECT 'still-usable'::text;")
    assert good.ok is True
    assert good.rows == ["still-usable"]


def test_transaction_local_guc_reaches_audit_trigger(order_id: str) -> None:
    actor = _uuid()
    note = "shipped by courier"
    # set_config(..., true) + the status UPDATE in ONE script == ONE transaction,
    # so the AFTER UPDATE trigger observes the GUCs (state.py / job_completion.py shape).
    result = run_sql_script(
        "BEGIN;"
        f"SELECT set_config('{ORDER_ACTOR_GUC}', {sql_literal(actor)}, true);"
        f"SELECT set_config('{ORDER_NOTE_GUC}', {sql_literal(note)}, true);"
        f"UPDATE wp1a_orders SET status = 'shipped' WHERE id = '{order_id}' RETURNING status;"
        "COMMIT;"
    )
    assert result.ok is True
    # Multi-result-set: the two set_config value rows precede the RETURNING row.
    assert result.rows[-1] == "shipped"
    event = run_sql_script(
        f"SELECT actor::text, note FROM wp1a_order_events WHERE order_id = '{order_id}';"
    )
    assert event.rows == [f"{actor}|{note}"]


def test_guc_true_is_transaction_local_and_does_not_leak(adapter_db: None) -> None:
    # A set_config(..., true) in one script must not survive into the next call.
    primed = run_sql_script(
        f"SELECT set_config('{ORDER_ACTOR_GUC}', {sql_literal(_uuid())}, true);"
    )
    assert primed.ok is True
    leaked = run_sql_script(f"SELECT current_setting('{ORDER_ACTOR_GUC}', true);")
    assert leaked.rows == []  # empty '' -> blank line dropped -> no leak


def test_audit_trigger_not_fired_when_status_unchanged(order_id: str) -> None:
    # The 0014 trigger guards on ``new.status IS DISTINCT FROM old.status``.
    result = run_sql_script(
        "BEGIN;"
        f"SELECT set_config('{ORDER_ACTOR_GUC}', {sql_literal(_uuid())}, true);"
        f"UPDATE wp1a_orders SET status = 'placed' WHERE id = '{order_id}' RETURNING status;"
        "COMMIT;"
    )
    assert result.ok is True
    events = run_sql_script(
        f"SELECT count(*)::text FROM wp1a_order_events WHERE order_id = '{order_id}';"
    )
    assert events.rows == ["0"]


def test_multi_result_set_rows_flattened_in_order(adapter_db: None) -> None:
    result = run_sql_script("SELECT 'a'::text; SELECT 'b'::text; SELECT 'c'::text;")
    assert result.rows == ["a", "b", "c"]


def test_row_rendering_pipe_join_null_and_bool(adapter_db: None) -> None:
    result = run_sql_script("SELECT 1::text, true, false, null::text, 'x'::text;")
    assert result.rows == ["1|t|f||x"]


def test_jsonb_text_projection_matches_server(adapter_db: None) -> None:
    result = run_sql_script("SELECT '{\"a\":1,\"b\":\"x\"}'::jsonb;")
    assert result.rows == ['{"a": 1, "b": "x"}']


def test_representative_ledger_double_entry_write(adapter_db: None) -> None:
    # post_transaction shape: balanced double-entry insert in one transaction,
    # returning the new id as the last row (engine.py rows[-1] contract).
    txn = _uuid()
    key = f"key-{_uuid()}"
    result = run_sql_script(
        "BEGIN;"
        "WITH ins AS ("
        "  INSERT INTO wp1a_ledger_transactions (id, idempotency_key, kind)"
        f"  VALUES ('{txn}', {sql_literal(key)}, 'escrow_capture')"
        "  ON CONFLICT (idempotency_key) DO NOTHING RETURNING id"
        "), posted AS ("
        "  INSERT INTO wp1a_ledger_postings (transaction_id, account, amount_ngwee)"
        "  SELECT ins.id, v.account, v.amount FROM ins"
        "  CROSS JOIN (VALUES ('escrow', 550000), ('customer', -550000)) AS v(account, amount)"
        "  RETURNING transaction_id"
        ") SELECT id::text FROM ins;"
        "COMMIT;"
    )
    assert result.ok is True
    assert result.rows[-1] == txn
    balance = run_sql_script(
        "SELECT coalesce(sum(amount_ngwee), 0)::text FROM wp1a_ledger_postings "
        f"WHERE transaction_id = '{txn}';"
    )
    assert balance.rows == ["0"]  # double-entry zero-sum
    postings = run_sql_script(
        f"SELECT count(*)::text FROM wp1a_ledger_postings WHERE transaction_id = '{txn}';"
    )
    assert postings.rows == ["2"]


def test_idempotent_insert_returns_empty_rows_on_conflict(adapter_db: None) -> None:
    txn1, txn2 = _uuid(), _uuid()
    key = f"idem-{_uuid()}"
    first = run_sql_script(
        "INSERT INTO wp1a_ledger_transactions (id, idempotency_key, kind) "
        f"VALUES ('{txn1}', {sql_literal(key)}, 'k') ON CONFLICT (idempotency_key) DO NOTHING "
        "RETURNING id::text;"
    )
    assert first.rows == [txn1]
    second = run_sql_script(
        "INSERT INTO wp1a_ledger_transactions (id, idempotency_key, kind) "
        f"VALUES ('{txn2}', {sql_literal(key)}, 'k') ON CONFLICT (idempotency_key) DO NOTHING "
        "RETURNING id::text;"
    )
    assert second.ok is True
    assert second.rows == []  # conflict -> no RETURNING row (engine.py idempotent path)


def test_sql_error_returns_result_without_raising(adapter_db: None) -> None:
    result = run_sql_script("SELECT * FROM wp1a_nonexistent_table_zzz;")
    assert isinstance(result, SqlResult)
    assert result.ok is False
    assert result.rows == []
    assert result.error is not None
    assert "wp1a_nonexistent_table_zzz" in result.error


def test_pool_is_bounded_and_reused(adapter_db: None) -> None:
    # One bounded pool per DSN, reused across calls (not a fresh connection each time).
    pool = db_module._get_pool(resolve_db_url())
    assert pool.max_size == db_module._pool_max()
    assert pool.min_size == db_module._pool_min()
    assert db_module._get_pool(resolve_db_url()) is pool
