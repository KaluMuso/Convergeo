"""KYC state-machine compare-and-swap transition tests (FIX-J)."""

from __future__ import annotations

import concurrent.futures
import json
import uuid
from collections.abc import Generator
from typing import Any

import pytest
from app.errors import AppError
from app.services.kyc.state_machine import (
    KycTransitionError,
    transition_approve,
    transition_reject,
    transition_start_review,
)
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    load_fixture_ids,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

ADMIN_ID = "66666666-6666-6666-6666-666666666666"
# vendors.owner_user_id references profiles(id). Reuse a profile the module `db`
# fixture already seeds via seed_matrix_fixtures — a random UUID silently violates
# the FK, leaving the vendor uninserted so transitions raise "Vendor not found".
VENDOR_OWNER_ID = load_fixture_ids()["users"]["vendor_a_owner"]


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


def _sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict | list):
        return f"'{json.dumps(value).replace(chr(39), chr(39) + chr(39))}'::jsonb"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _json_rows(rows: list[str]) -> list[dict[str, Any]]:
    return [json.loads(row) for row in rows]


class _SqlTableClient:
    def __init__(self, conn: PgConn, table: str) -> None:
        self._conn = conn
        self._table = table
        self._select_cols = "*"
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._mode = "select"
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str) -> _SqlTableClient:
        self._select_cols = columns
        return self

    def eq(self, column: str, value: Any) -> _SqlTableClient:
        self._filters.append(("eq", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> _SqlTableClient:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> _SqlTableClient:
        self._limit = count
        return self

    def maybe_single(self) -> _SqlTableClient:
        self._maybe_single = True
        return self

    def insert(self, row: dict[str, Any]) -> _SqlTableClient:
        self._mode = "insert"
        self._payload = row
        return self

    def update(self, patch: dict[str, Any]) -> _SqlTableClient:
        self._mode = "update"
        self._payload = patch
        return self

    def _where_sql(self) -> str:
        if not self._filters:
            return ""
        clauses = [f"{col} = {_sql_value(val)}" for _op, col, val in self._filters]
        return "WHERE " + " AND ".join(clauses)

    def execute(self) -> _FakeResponse:
        if self._mode == "insert":
            assert self._payload is not None
            columns = list(self._payload.keys())
            col_sql = ", ".join(columns)
            val_sql = ", ".join(_sql_value(self._payload[col]) for col in columns)
            sql = (
                f"INSERT INTO public.{self._table} ({col_sql}) VALUES ({val_sql}) "
                f"RETURNING to_jsonb({self._table}.*);"
            )
            result = self._conn.run(sql)
            assert result.ok, result.error
            return _FakeResponse(_json_rows(result.rows))

        if self._mode == "update":
            assert self._payload is not None
            set_sql = ", ".join(f"{col} = {_sql_value(val)}" for col, val in self._payload.items())
            sql = (
                f"UPDATE public.{self._table} SET {set_sql} {self._where_sql()} "
                f"RETURNING to_jsonb({self._table}.*);"
            )
            result = self._conn.run(sql)
            assert result.ok, result.error
            return _FakeResponse(_json_rows(result.rows))

        order_sql = ""
        if self._order is not None:
            column, desc = self._order
            order_sql = f" ORDER BY {column} {'DESC' if desc else 'ASC'}"
        limit_sql = f" LIMIT {self._limit}" if self._limit is not None else ""
        sql = (
            f"SELECT to_jsonb(t) FROM (SELECT {self._select_cols} FROM public.{self._table} "
            f"{self._where_sql()}{order_sql}{limit_sql}) t;"
        )
        result = self._conn.run(sql)
        assert result.ok, result.error
        rows = _json_rows(result.rows)
        if self._maybe_single:
            return _FakeResponse(rows[0] if rows else None)
        return _FakeResponse(rows)


class _RealPgServiceClient:
    def __init__(self, conn: PgConn) -> None:
        self._conn = conn

    def table(self, name: str) -> _SqlTableClient:
        return _SqlTableClient(self._conn, name)


class _ServiceWrapper:
    def __init__(self, conn: PgConn) -> None:
        self.client = _RealPgServiceClient(conn)


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    try:
        url = resolve_db_url()
    except FileNotFoundError:
        pytest.skip("psql not available for Postgres-backed KYC CAS tests")
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    seed_matrix_fixtures(conn)
    yield conn


def _seed_pending_kyc_vendor(db: PgConn, *, vendor_id: str, kyc_id: str) -> None:
    slug = f"kyc-cas-{vendor_id[:8]}"
    vendor_result = db.run(
        f"""
        INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status)
        VALUES ('{vendor_id}', '{VENDOR_OWNER_ID}', '{slug}', 'CAS Vendor', 'pending_kyc');
        """
    )
    assert vendor_result.ok, vendor_result.error
    kyc_result = db.run(
        f"""
        INSERT INTO public.kyc_records (
          id, vendor_id, tier, doc_storage_paths, momo_name_match, status
        ) VALUES (
          '{kyc_id}', '{vendor_id}', 2, '{{}}', '{{"matched": true}}'::jsonb, 'submitted'
        );
        """
    )
    assert kyc_result.ok, kyc_result.error


def _vendor_status(db: PgConn, vendor_id: str) -> str:
    result = db.run(f"SELECT status FROM public.vendors WHERE id = '{vendor_id}';")
    assert result.ok and result.rows
    return result.rows[0]


@pytest.mark.usefixtures("db")
class TestKycVendorCas:
    def test_concurrent_approve_exactly_one_wins(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending_kyc_vendor(db, vendor_id=vendor_id, kyc_id=kyc_id)
        wrapper = _ServiceWrapper(db)

        def approve() -> object:
            try:
                return transition_approve(
                    actor_id=ADMIN_ID,
                    vendor_id=vendor_id,
                    kyc_record_id=kyc_id,
                    tier=2,
                    service_client=wrapper,
                )
            except AppError as exc:
                if exc.code == "kyc_transition_conflict":
                    return None
                raise

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(approve), executor.submit(approve)]
            results = [future.result() for future in futures]

        assert _vendor_status(db, vendor_id) == "active"
        successes = [result for result in results if result is not None]
        assert len(successes) == 1

    def test_approve_happy_path_succeeds(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending_kyc_vendor(db, vendor_id=vendor_id, kyc_id=kyc_id)
        wrapper = _ServiceWrapper(db)

        result = transition_approve(
            actor_id=ADMIN_ID,
            vendor_id=vendor_id,
            kyc_record_id=kyc_id,
            tier=2,
            service_client=wrapper,
        )

        assert result["vendor"]["status"] == "active"
        assert result["kyc_record"]["status"] == "approved"
        assert _vendor_status(db, vendor_id) == "active"

    def test_illegal_transition_rejected_by_guard(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending_kyc_vendor(db, vendor_id=vendor_id, kyc_id=kyc_id)
        wrapper = _ServiceWrapper(db)
        transition_approve(
            actor_id=ADMIN_ID,
            vendor_id=vendor_id,
            kyc_record_id=kyc_id,
            tier=2,
            service_client=wrapper,
        )

        with pytest.raises(KycTransitionError) as exc_info:
            transition_start_review(
                actor_id=ADMIN_ID,
                vendor_id=vendor_id,
                kyc_record_id=kyc_id,
                service_client=wrapper,
            )

        assert exc_info.value.code == "kyc_invalid_transition"
        assert exc_info.value.http_status == 409

    def test_concurrent_reject_exactly_one_wins(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending_kyc_vendor(db, vendor_id=vendor_id, kyc_id=kyc_id)
        wrapper = _ServiceWrapper(db)

        def reject() -> object:
            try:
                return transition_reject(
                    actor_id=ADMIN_ID,
                    vendor_id=vendor_id,
                    kyc_record_id=kyc_id,
                    reviewer_notes="duplicate reject race",
                    service_client=wrapper,
                )
            except AppError as exc:
                if exc.code == "kyc_transition_conflict":
                    return None
                raise

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(reject), executor.submit(reject)]
            results = [future.result() for future in futures]

        result = db.run(f"SELECT status FROM public.kyc_records WHERE id = '{kyc_id}';")
        assert result.ok and result.rows
        assert result.rows[0] == "rejected"
        successes = [result for result in results if result is not None]
        assert len(successes) == 1
