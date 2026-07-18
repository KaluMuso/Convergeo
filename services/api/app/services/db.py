"""Native PostgreSQL write adapter — the one authoritative ``run_sql_script`` path.

This module replaces the historical ``psql`` subprocess implementation with a
native psycopg 3 solution backed by an explicitly bounded connection pool, while
keeping the public ``run_sql_script(script) -> SqlResult`` contract byte-compatible
for the callers that parse ``SqlResult.rows``.

Guarantees the callers rely on (preserved here):

* **One logical script == one transaction on one connection.** The whole ``script``
  is sent as a single simple-query message, so a script that opens its own
  ``BEGIN … COMMIT`` runs as one transaction, and a multi-statement script without
  explicit transaction control is still wrapped in a single implicit transaction by
  Postgres. Transaction-local ``set_config(..., true)`` GUCs are therefore visible
  to audit triggers fired by later statements in the *same* script.
* **Full rollback on any statement failure — never a partial write.** A mid-script
  error aborts the transaction; the connection is rolled back before it returns to
  the pool so nothing is partially committed and the connection stays reusable.
* **psql ``-At`` row projection.** Each output row is rendered as its columns joined
  by ``|`` with SQL ``NULL`` -> ``''``; blank rows are dropped; and the rows of every
  row-returning statement are concatenated in execution order (so ``rows[-1]`` is the
  final ``RETURNING``/``SELECT`` row, exactly as under psql).

The direct/session Postgres DSN is taken from ``SUPABASE_DB_URL`` (the connection
contract already intended for it) — never the transaction pooler, so session-scoped
behaviour and prepared statements are safe.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.types.string import TextLoader
from psycopg_pool import ConnectionPool

_DEFAULT_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

# psql printed transaction-control acknowledgements ("BEGIN"/"COMMIT"/…) and command
# tags ("INSERT 0 1"/"UPDATE 2"/…) to stdout, and the previous adapter filtered them
# out. psycopg never surfaces those as result rows, so this filter is a belt-and-braces
# parity shim: a genuine data value that happens to equal one of these tokens would
# have been dropped by the old psql path too, so dropping it here keeps behaviour 1:1.
_NOISE_LINES = frozenset({"BEGIN", "COMMIT", "ROLLBACK", "DO", "SET"})
_COMMAND_TAG_RE = re.compile(r"^(?:INSERT|UPDATE|DELETE|SELECT) \d+$")


@dataclass(frozen=True, slots=True)
class SqlResult:
    ok: bool
    rows: list[str]
    error: str | None = None


def resolve_db_url() -> str:
    """Direct/session Postgres DSN (``SUPABASE_DB_URL``); local stack by default."""
    return os.environ.get("SUPABASE_DB_URL", _DEFAULT_DB_URL)


# --------------------------------------------------------------------------- #
# Bounded connection pool (one pool per resolved DSN).
#
# Production resolves a single DSN, so exactly one bounded pool exists; the test
# suite flips ``SUPABASE_DB_URL`` between ephemeral databases, so pools are keyed by
# DSN to keep each test talking to its own database.
# --------------------------------------------------------------------------- #

_POOL_NAME = "vergeo5-db"


def _pool_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _pool_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _pool_min() -> int:
    return _pool_int("SUPABASE_DB_POOL_MIN", 1)


def _pool_max() -> int:
    # Direct/session connections are scarce; keep the ceiling explicit and small,
    # and never below the floor.
    return max(_pool_min(), _pool_int("SUPABASE_DB_POOL_MAX", 5))


def _configure_connection(conn: Connection[Any]) -> None:
    """Per-connection setup: return json/jsonb as raw server text.

    psql ``-At`` prints the server's text rendering of a json/jsonb column; psycopg
    would otherwise parse it into a Python object. Loading it as text keeps the row
    projection identical to psql and keeps callers that ``json.loads`` the column
    receiving a string.
    """
    conn.adapters.register_loader("json", TextLoader)
    conn.adapters.register_loader("jsonb", TextLoader)


_pools: dict[str, ConnectionPool[Connection[Any]]] = {}
_pools_lock = threading.Lock()


def _get_pool(dsn: str) -> ConnectionPool[Connection[Any]]:
    pool = _pools.get(dsn)
    if pool is not None:
        return pool
    with _pools_lock:
        pool = _pools.get(dsn)
        if pool is None:
            pool = ConnectionPool(
                conninfo=dsn,
                min_size=_pool_min(),
                max_size=_pool_max(),
                timeout=_pool_float("SUPABASE_DB_POOL_TIMEOUT", 10.0),
                max_idle=_pool_float("SUPABASE_DB_POOL_MAX_IDLE", 300.0),
                max_lifetime=_pool_float("SUPABASE_DB_POOL_MAX_LIFETIME", 3600.0),
                kwargs={"autocommit": True, "prepare_threshold": None},
                configure=_configure_connection,
                check=ConnectionPool.check_connection,
                name=_POOL_NAME,
                open=False,
            )
            pool.open()
            _pools[dsn] = pool
        return pool


@atexit.register
def _close_pools() -> None:
    for pool in list(_pools.values()):
        try:
            pool.close()
        except Exception:  # pragma: no cover - best-effort shutdown
            pass
    _pools.clear()


def reset_pools() -> None:
    """Close and forget every pool (test/teardown helper)."""
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        try:
            pool.close()
        except Exception:  # pragma: no cover - best-effort
            pass


# --------------------------------------------------------------------------- #
# Row projection (psql ``-At`` compatible).
# --------------------------------------------------------------------------- #


def _render_value(value: Any) -> str:
    if value is None:
        return ""
    if value is True:
        return "t"
    if value is False:
        return "f"
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "\\x" + bytes(value).hex()
    if isinstance(value, (dict, list)):
        # Defensive: json/jsonb already load as text (see _configure_connection);
        # this only trips for a container type without a text loader.
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def _render_row(record: Iterable[Any]) -> str:
    return "|".join(_render_value(column) for column in record)


def _gather_rows(cursor: psycopg.Cursor[Any]) -> list[str]:
    """Flatten every row-returning result set, psql ``-At`` style, in order."""
    rows: list[str] = []
    first = True
    while True:
        if not first and not cursor.nextset():
            break
        first = False
        if cursor.description is not None:
            for record in cursor.fetchall():
                rendered = _render_row(record)
                if rendered:  # psql drops blank output lines (single NULL / '' column)
                    rows.append(rendered)
    return [row for row in rows if row not in _NOISE_LINES and not _COMMAND_TAG_RE.match(row)]


def _format_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def run_sql_script(script: str) -> SqlResult:
    """Execute ``script`` as one transaction on one pooled connection.

    Mirrors the historical psql ``-At`` / ``ON_ERROR_STOP=1`` contract: on success,
    the concatenated projected rows are returned; on any failure the whole
    transaction is rolled back and ``ok=False`` is returned with the Postgres error
    text (so callers' substring checks on ``.error`` keep working).
    """
    dsn = resolve_db_url()
    try:
        pool = _get_pool(dsn)
        with pool.connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(script)
                    rows = _gather_rows(cursor)
                return SqlResult(ok=True, rows=rows)
            except psycopg.Error as exc:
                # The script-opened transaction is now aborted; roll it back so the
                # pooled connection is clean and nothing is partially committed.
                conn.rollback()
                return SqlResult(ok=False, rows=[], error=_format_error(exc))
    except Exception as exc:  # pool acquisition / connection failure (DB down, timeout)
        return SqlResult(ok=False, rows=[], error=_format_error(exc))
