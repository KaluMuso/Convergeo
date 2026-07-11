"""Tests for M10-P07 transfer-to-friend (services/api/app/routers/ticket_transfer.py).

Runs the router's async handlers directly (not through TestClient/HTTP) against a
real local Postgres so that both the `.table()`-shaped calls (via `_RealPgServiceClient`,
a minimal supabase-py-compatible query builder backed by real SQL) and the raw-SQL
atomic claim transition (`run_sql_script`, same DB) observe the same data — this is
required for the "old QR/PIN void after claim" assertions, which read the ticket row
through `ticket_verify.py`'s real verify path.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from app.core.auth import CurrentUser
from app.errors import AppError
from app.routers.ticket_transfer import (
    CancelTransferResponse,
    ClaimTransferResponse,
    CurrentTransferResponse,
    InboundTransfersResponse,
    InitiateTransferRequest,
    InitiateTransferResponse,
    cancel_transfer,
    claim_transfer,
    get_current_transfer,
    initiate_transfer,
    list_inbound_transfers,
)
from app.routers.ticket_verify import build_qr_code, current_window, verify_and_check_in_ticket
from app.services.tickets.qr import extract_pin_for_holder, seal_pin_storage
from fastapi import Request
from pydantic import ValidationError
from tests.rls.conftest import (
    MIGRATIONS_DIR,
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_A = "11111111-1111-1111-1111-111111111111"  # seeded phone +260971000001 (sender)
CUSTOMER_B = "22222222-2222-2222-2222-222222222222"  # seeded phone +260971000002 (recipient)
SHOP_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


def ensure_ticket_transfers_table(conn: PgConn) -> None:
    """0026 replay: apply the migration directly if a cached schema predates it."""
    result = conn.run(
        """
        SELECT count(*)::text
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'ticket_transfers';
        """
    )
    if result.ok and result.rows and result.rows[0] == "0":
        migration = MIGRATIONS_DIR / "0026_ticket_transfers.sql"
        applied = conn.run_file(migration)
        if not applied.ok:
            raise RuntimeError(f"failed to apply {migration.name}: {applied.error}")


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    try:
        url = resolve_db_url()
    except FileNotFoundError:
        pytest.skip("psql is not available in this environment")
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    ensure_ticket_transfers_table(conn)
    seed_matrix_fixtures(conn)
    # seed_matrix_fixtures' profiles INSERT is `ON CONFLICT (id) DO NOTHING`, but
    # inserting into auth.users first fires `handle_new_user()` (0010_profile_bootstrap.sql),
    # which creates a bare (phone=NULL) profiles row ahead of it — so the intended
    # seeded phone numbers never actually land. Force them explicitly since this
    # pebble's phone-match logic depends on them.
    _insert_user_with_phone(conn, user_id=CUSTOMER_A, phone="+260971000001")
    _insert_user_with_phone(conn, user_id=CUSTOMER_B, phone="+260971000002")
    yield conn


@pytest.fixture(autouse=True)
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    import os

    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


@pytest.fixture(autouse=True)
def _bypass_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.ticket_transfer.bump_rate_counter",
        lambda **kwargs: (True, 0),
    )


# ---------------------------------------------------------------------------
# Minimal supabase-py-compatible query builder, backed by real Postgres (test-only).
# Needed because ticket_transfer.py's endpoints use `service_client.client.table(...)`
# for reads/writes that must observe the SAME rows the raw-SQL claim transition and
# ticket_verify.py's raw-SQL verify path operate on.
# ---------------------------------------------------------------------------


def _sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict | list):
        return "'" + json.dumps(value).replace("'", "''") + "'::jsonb"
    if isinstance(value, int | float):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


# psql -At still prints the command-completion tag (e.g. "INSERT 0 1") alongside a
# RETURNING result row for plain (non-BEGIN-wrapped) statements — strip it before
# parsing the remaining lines as JSON.
_COMMAND_TAG_RE = re.compile(r"^(?:INSERT \d+ \d+|UPDATE \d+|DELETE \d+|SELECT \d+)$")


def _json_rows(rows: list[str]) -> list[Any]:
    return [json.loads(line) for line in rows if not _COMMAND_TAG_RE.match(line)]


def _infer_sqlstate(result: Any) -> str | None:
    """PgConn's sqlstate extraction depends on VERBOSITY=verbose, which plain -c
    single-statement invocations don't set — fall back to sniffing common error
    text so tests can still assert on the 23505 (unique_violation) code."""
    if result.sqlstate:
        return str(result.sqlstate)
    if result.error and "duplicate key value violates unique constraint" in result.error:
        return "23505"
    return None


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _PgApiError(Exception):
    """Stand-in for postgrest.exceptions.APIError, same `.code` contract."""

    def __init__(self, code: str | None, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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

    def gt(self, column: str, value: Any) -> _SqlTableClient:
        self._filters.append(("gt", column, value))
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
        operators = {"eq": "=", "gt": ">"}
        clauses = [f"{col} {operators[op]} {_sql_value(val)}" for op, col, val in self._filters]
        return "WHERE " + " AND ".join(clauses)

    def execute(self) -> _FakeResponse:
        if self._mode == "insert":
            return self._execute_insert()
        if self._mode == "update":
            return self._execute_update()
        return self._execute_select()

    def _execute_select(self) -> _FakeResponse:
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
        if not result.ok:
            raise RuntimeError(f"select on {self._table} failed: {result.error}")
        rows = _json_rows(result.rows)
        if self._maybe_single:
            return _FakeResponse(rows[0] if rows else None)
        return _FakeResponse(rows)

    def _execute_insert(self) -> _FakeResponse:
        assert self._payload is not None
        columns = list(self._payload.keys())
        col_sql = ", ".join(columns)
        val_sql = ", ".join(_sql_value(self._payload[col]) for col in columns)
        sql = (
            f"INSERT INTO public.{self._table} ({col_sql}) VALUES ({val_sql}) "
            f"RETURNING to_jsonb({self._table}.*);"
        )
        result = self._conn.run(sql)
        if not result.ok:
            raise _PgApiError(_infer_sqlstate(result), result.error or "insert failed")
        rows = _json_rows(result.rows)
        return _FakeResponse(rows)

    def _execute_update(self) -> _FakeResponse:
        assert self._payload is not None
        set_sql = ", ".join(f"{col} = {_sql_value(val)}" for col, val in self._payload.items())
        sql = (
            f"UPDATE public.{self._table} SET {set_sql} {self._where_sql()} "
            f"RETURNING to_jsonb({self._table}.*);"
        )
        result = self._conn.run(sql)
        if not result.ok:
            raise RuntimeError(f"update on {self._table} failed: {result.error}")
        rows = _json_rows(result.rows)
        return _FakeResponse(rows)


class _RealPgServiceClient:
    def __init__(self, conn: PgConn) -> None:
        self._conn = conn

    def table(self, name: str) -> _SqlTableClient:
        return _SqlTableClient(self._conn, name)


class _ServiceWrapper:
    def __init__(self, conn: PgConn) -> None:
        self.client = _RealPgServiceClient(conn)


class _FakeRequest:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.client = None


def _fake_request() -> Request:
    """A duck-typed stand-in for fastapi.Request — only `.headers`/`.client` are
    touched (by get_client_ip in the rate limiter), so a real ASGI Request isn't
    needed. Cast to satisfy the route functions' type signature."""
    return cast(Request, _FakeRequest())


def _monkeypatch_apierror(monkeypatch: pytest.MonkeyPatch) -> None:
    """ticket_transfer.py catches postgrest.exceptions.APIError by `.code` — our fake
    unique-violation stand-in (_PgApiError) walks and quacks the same, but the router
    imports the real class for isinstance/except matching, so swap it for the duration
    of tests that need to trigger the unique-violation branch."""
    monkeypatch.setattr("app.routers.ticket_transfer.APIError", _PgApiError)


def _user(user_id: str) -> CurrentUser:
    return CurrentUser(id=user_id, roles=frozenset({"customer"}), token="test-token")


# ---------------------------------------------------------------------------
# Fixture graph helpers
# ---------------------------------------------------------------------------


def _insert_event_instance(conn: PgConn, *, starts_at: datetime) -> dict[str, str]:
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    slug = f"transfer-{event_id[:8]}"
    conn.run(
        f"""
        INSERT INTO public.events (
          id, organiser_vendor_id, title, slug, venue, lat, lng, status
        ) VALUES (
          '{event_id}', '{SHOP_B}', 'Transfer Event', '{slug}',
          'Lusaka Showgrounds', -15.4167, 28.2833, 'published'
        );
        INSERT INTO public.event_instances (id, event_id, starts_at, capacity)
        VALUES ('{instance_id}', '{event_id}', '{starts_at.isoformat()}', 10);
        INSERT INTO public.ticket_types (
          id, event_id, kind, name, price_ngwee
        ) VALUES ('{ticket_type_id}', '{event_id}', 'fixed', 'GA', 20000);
        """
    )
    return {"event_id": event_id, "instance_id": instance_id, "ticket_type_id": ticket_type_id}


def _insert_ticket(
    conn: PgConn,
    *,
    ticket_id: str,
    instance_id: str,
    ticket_type_id: str,
    holder_user_id: str = CUSTOMER_A,
    status: str = "issued",
    qr_secret: str = "sender-secret",
    pin: str = "111111",
    with_order_item: bool = True,
) -> None:
    item_sql = "NULL"
    if with_order_item:
        item_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        conn.run(
            f"""
            INSERT INTO public.checkout_groups (
              id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee,
              total_ngwee, status
            ) VALUES (
              '{group_id}', '{holder_user_id}', 'transfer-{ticket_id[:8]}', 0, 0, 0, 'completed'
            );
            INSERT INTO public.orders (
              id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
              delivery_fee_ngwee, cod, commission_snapshot
            ) VALUES (
              '{order_id}', '{group_id}', '{SHOP_B}', '{holder_user_id}', 'completed', 'pickup',
              0, false, '{{}}'::jsonb
            );
            INSERT INTO public.order_items (
              id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
            ) VALUES (
              '{item_id}', '{order_id}', 'ticket', 1, 1000, 'Transfer fixture'
            );
            INSERT INTO public.order_item_tickets (order_item_id, ticket_type_id, instance_id)
            VALUES ('{item_id}', '{ticket_type_id}', '{instance_id}');
            """
        )
        item_sql = f"'{item_id}'"

    pin_hash = seal_pin_storage(pin=pin, ticket_id=ticket_id)
    checked_sql = "timezone('utc', now())" if status == "checked_in" else "NULL"
    conn.run(
        f"""
        INSERT INTO public.tickets (
          id, instance_id, ticket_type_id, holder_user_id, status,
          qr_secret, pin_hash, checked_in_at, order_item_id
        ) VALUES (
          '{ticket_id}', '{instance_id}', '{ticket_type_id}', '{holder_user_id}',
          '{status}', '{qr_secret}', '{pin_hash}', {checked_sql}, {item_sql}
        );
        """
    )


def _insert_user_with_phone(conn: PgConn, *, user_id: str, phone: str) -> None:
    email = f"{user_id[:8]}@transfer-fixture.test"
    conn.run(
        f"""
        INSERT INTO auth.users (
          instance_id, id, aud, role, email, encrypted_password,
          email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at
        ) VALUES (
          '00000000-0000-0000-0000-000000000000', '{user_id}', 'authenticated', 'authenticated',
          '{email}', 'hash', timezone('utc', now()), '{{}}'::jsonb, '{{}}'::jsonb,
          timezone('utc', now()), timezone('utc', now())
        ) ON CONFLICT (id) DO NOTHING;
        INSERT INTO public.profiles (id, phone, display_name)
        VALUES ('{user_id}', '{phone}', 'Transfer Fixture User')
        ON CONFLICT (id) DO UPDATE SET phone = EXCLUDED.phone;
        """
    )


def _ticket_row(conn: PgConn, ticket_id: str) -> dict[str, str]:
    result = conn.run(
        f"""
        SELECT status || '|' || holder_user_id::text || '|' || coalesce(qr_secret, '')
          || '|' || coalesce(pin_hash, '')
        FROM public.tickets WHERE id = '{ticket_id}';
        """
    )
    assert result.ok and result.rows
    status, holder_user_id, qr_secret, pin_hash = result.rows[0].split("|")
    return {
        "status": status,
        "holder_user_id": holder_user_id,
        "qr_secret": qr_secret,
        "pin_hash": pin_hash,
    }


def _transfer_status(conn: PgConn, transfer_id: str) -> str:
    result = conn.run(f"SELECT status FROM public.ticket_transfers WHERE id = '{transfer_id}';")
    assert result.ok and result.rows
    return result.rows[0]


# ---------------------------------------------------------------------------
# Pydantic-level: phone normalisation (no DB required)
# ---------------------------------------------------------------------------


class TestPhoneNormalisation:
    def test_local_number_normalises_to_zambia_e164(self) -> None:
        body = InitiateTransferRequest(to_phone="0977123456")
        assert body.to_phone == "+260977123456"

    def test_already_e164_passes_through(self) -> None:
        body = InitiateTransferRequest(to_phone="+260977123456")
        assert body.to_phone == "+260977123456"

    def test_garbage_phone_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InitiateTransferRequest(to_phone="abc")


# ---------------------------------------------------------------------------
# Cutoff boundary
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("db", "db_url_env")
class TestTransferCutoff:
    async def test_t_minus_6h01m_allows_initiate(self, db: PgConn) -> None:
        now = datetime.now(UTC)
        starts_at = now + timedelta(hours=6, minutes=1)
        graph = _insert_event_instance(db, starts_at=starts_at)
        ticket_id = str(uuid.uuid4())
        _insert_ticket(
            db,
            ticket_id=ticket_id,
            instance_id=graph["instance_id"],
            ticket_type_id=graph["ticket_type_id"],
        )

        response = await initiate_transfer(
            ticket_id,
            InitiateTransferRequest(to_phone="+260971000002"),
            _fake_request(),
            _user(CUSTOMER_A),
            _ServiceWrapper(db),
        )
        assert isinstance(response, InitiateTransferResponse)
        assert response.transfer.status == "pending"

    async def test_t_minus_5h59m_rejects_initiate(self, db: PgConn) -> None:
        now = datetime.now(UTC)
        starts_at = now + timedelta(hours=5, minutes=59)
        graph = _insert_event_instance(db, starts_at=starts_at)
        ticket_id = str(uuid.uuid4())
        _insert_ticket(
            db,
            ticket_id=ticket_id,
            instance_id=graph["instance_id"],
            ticket_type_id=graph["ticket_type_id"],
        )

        with pytest.raises(AppError) as exc:
            await initiate_transfer(
                ticket_id,
                InitiateTransferRequest(to_phone="+260971000002"),
                _fake_request(),
                _user(CUSTOMER_A),
                _ServiceWrapper(db),
            )
        assert exc.value.code == "ticket_transfer_cutoff_passed"
        assert exc.value.http_status == 409


# ---------------------------------------------------------------------------
# Void-after-claim: old QR/PIN rejected by the real verify path, new ones work.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("db", "db_url_env")
class TestClaimVoidsOldSecrets:
    async def test_old_qr_and_pin_rejected_new_holder_can_check_in(self, db: PgConn) -> None:
        far_future = datetime.now(UTC) + timedelta(hours=7)
        graph = _insert_event_instance(db, starts_at=far_future)
        ticket_id = str(uuid.uuid4())
        old_secret = "sender-secret-void-me"
        old_pin = "111111"
        _insert_ticket(
            db,
            ticket_id=ticket_id,
            instance_id=graph["instance_id"],
            ticket_type_id=graph["ticket_type_id"],
            qr_secret=old_secret,
            pin=old_pin,
        )

        initiated = await initiate_transfer(
            ticket_id,
            InitiateTransferRequest(to_phone="+260971000002"),
            _fake_request(),
            _user(CUSTOMER_A),
            _ServiceWrapper(db),
        )
        transfer_id = initiated.transfer.id

        claimed = await claim_transfer(
            transfer_id,
            _fake_request(),
            _user(CUSTOMER_B),
            _ServiceWrapper(db),
        )
        assert isinstance(claimed, ClaimTransferResponse)
        assert claimed.ticket_id == ticket_id
        assert claimed.transfer.status == "claimed"

        row = _ticket_row(db, ticket_id)
        assert row["holder_user_id"] == CUSTOMER_B
        assert row["qr_secret"] != old_secret
        assert row["pin_hash"] != seal_pin_storage(pin=old_pin, ticket_id=ticket_id)

        now = datetime.now(UTC)
        old_code = build_qr_code(
            ticket_id=ticket_id, ticket_secret=old_secret, window=current_window(now)
        )
        with pytest.raises(AppError) as old_qr_exc:
            verify_and_check_in_ticket(
                ticket_id=ticket_id, vendor_id=SHOP_B, code=old_code, now=now
            )
        assert old_qr_exc.value.code == "ticket_invalid_code"

        with pytest.raises(AppError) as old_pin_exc:
            verify_and_check_in_ticket(ticket_id=ticket_id, vendor_id=SHOP_B, pin=old_pin, now=now)
        assert old_pin_exc.value.code == "ticket_invalid_pin"

        new_code = build_qr_code(
            ticket_id=ticket_id, ticket_secret=row["qr_secret"], window=current_window(now)
        )
        result = verify_and_check_in_ticket(
            ticket_id=ticket_id, vendor_id=SHOP_B, code=new_code, now=now
        )
        assert result.to_status == "checked_in"

        new_pin = extract_pin_for_holder(row["pin_hash"], ticket_id=ticket_id)
        assert new_pin is not None
        assert new_pin != old_pin


# ---------------------------------------------------------------------------
# Double-transfer guard: partial-unique index -> caught -> 409.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("db", "db_url_env")
class TestDoubleTransferGuard:
    async def test_second_pending_transfer_returns_409(
        self, db: PgConn, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _monkeypatch_apierror(monkeypatch)
        far_future = datetime.now(UTC) + timedelta(hours=7)
        graph = _insert_event_instance(db, starts_at=far_future)
        ticket_id = str(uuid.uuid4())
        _insert_ticket(
            db,
            ticket_id=ticket_id,
            instance_id=graph["instance_id"],
            ticket_type_id=graph["ticket_type_id"],
        )

        first = await initiate_transfer(
            ticket_id,
            InitiateTransferRequest(to_phone="+260971000002"),
            _fake_request(),
            _user(CUSTOMER_A),
            _ServiceWrapper(db),
        )
        assert first.transfer.status == "pending"

        with pytest.raises(AppError) as exc:
            await initiate_transfer(
                ticket_id,
                InitiateTransferRequest(to_phone="+260971000009"),
                _fake_request(),
                _user(CUSTOMER_A),
                _ServiceWrapper(db),
            )
        assert exc.value.code == "ticket_transfer_pending_exists"
        assert exc.value.http_status == 409


# ---------------------------------------------------------------------------
# Claim phone match: mismatch -> 403; new-signup phone match -> success.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("db", "db_url_env")
class TestClaimPhoneMatch:
    async def test_mismatched_phone_forbidden_new_signup_phone_succeeds(self, db: PgConn) -> None:
        far_future = datetime.now(UTC) + timedelta(hours=7)
        graph = _insert_event_instance(db, starts_at=far_future)
        ticket_id = str(uuid.uuid4())
        _insert_ticket(
            db,
            ticket_id=ticket_id,
            instance_id=graph["instance_id"],
            ticket_type_id=graph["ticket_type_id"],
        )

        new_signup_id = str(uuid.uuid4())
        new_signup_phone = "+260966555000"
        _insert_user_with_phone(db, user_id=new_signup_id, phone=new_signup_phone)

        initiated = await initiate_transfer(
            ticket_id,
            InitiateTransferRequest(to_phone=new_signup_phone),
            _fake_request(),
            _user(CUSTOMER_A),
            _ServiceWrapper(db),
        )
        transfer_id = initiated.transfer.id

        # The sender (wrong phone) may not claim their own transfer.
        with pytest.raises(AppError) as exc:
            await claim_transfer(
                transfer_id,
                _fake_request(),
                _user(CUSTOMER_A),
                _ServiceWrapper(db),
            )
        assert exc.value.code == "forbidden"
        assert exc.value.http_status == 403
        assert _transfer_status(db, transfer_id) == "pending"

        # The freshly-signed-up user with the matching verified phone may claim.
        claimed = await claim_transfer(
            transfer_id,
            _fake_request(),
            _user(new_signup_id),
            _ServiceWrapper(db),
        )
        assert claimed.ticket_id == ticket_id
        row = _ticket_row(db, ticket_id)
        assert row["holder_user_id"] == new_signup_id


# ---------------------------------------------------------------------------
# Checked-in ticket is untransferable — at initiate time, and defensively at claim.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("db", "db_url_env")
class TestCheckedInUntransferable:
    async def test_initiate_rejects_checked_in_ticket(self, db: PgConn) -> None:
        far_future = datetime.now(UTC) + timedelta(hours=7)
        graph = _insert_event_instance(db, starts_at=far_future)
        ticket_id = str(uuid.uuid4())
        _insert_ticket(
            db,
            ticket_id=ticket_id,
            instance_id=graph["instance_id"],
            ticket_type_id=graph["ticket_type_id"],
            status="checked_in",
        )

        with pytest.raises(AppError) as exc:
            await initiate_transfer(
                ticket_id,
                InitiateTransferRequest(to_phone="+260971000002"),
                _fake_request(),
                _user(CUSTOMER_A),
                _ServiceWrapper(db),
            )
        assert exc.value.code == "ticket_not_transferable"
        assert exc.value.http_status == 409

    async def test_claim_rejects_ticket_checked_in_after_initiate(self, db: PgConn) -> None:
        far_future = datetime.now(UTC) + timedelta(hours=7)
        graph = _insert_event_instance(db, starts_at=far_future)
        ticket_id = str(uuid.uuid4())
        _insert_ticket(
            db,
            ticket_id=ticket_id,
            instance_id=graph["instance_id"],
            ticket_type_id=graph["ticket_type_id"],
        )

        initiated = await initiate_transfer(
            ticket_id,
            InitiateTransferRequest(to_phone="+260971000002"),
            _fake_request(),
            _user(CUSTOMER_A),
            _ServiceWrapper(db),
        )
        transfer_id = initiated.transfer.id

        # Simulate a race: the ticket gets checked in after the transfer was
        # initiated but before it was claimed.
        db.run(
            f"""
            UPDATE public.tickets
            SET status = 'checked_in', checked_in_at = timezone('utc', now())
            WHERE id = '{ticket_id}';
            """
        )

        with pytest.raises(AppError) as exc:
            await claim_transfer(
                transfer_id,
                _fake_request(),
                _user(CUSTOMER_B),
                _ServiceWrapper(db),
            )
        assert exc.value.code == "ticket_not_transferable"
        assert exc.value.http_status == 409
        # Nothing was mutated on the transfer side of the failed atomic claim.
        assert _transfer_status(db, transfer_id) == "pending"


# ---------------------------------------------------------------------------
# Cancel before claim.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("db", "db_url_env")
class TestCancelBeforeClaim:
    async def test_sender_can_cancel_pending_transfer(self, db: PgConn) -> None:
        far_future = datetime.now(UTC) + timedelta(hours=7)
        graph = _insert_event_instance(db, starts_at=far_future)
        ticket_id = str(uuid.uuid4())
        _insert_ticket(
            db,
            ticket_id=ticket_id,
            instance_id=graph["instance_id"],
            ticket_type_id=graph["ticket_type_id"],
        )

        initiated = await initiate_transfer(
            ticket_id,
            InitiateTransferRequest(to_phone="+260971000002"),
            _fake_request(),
            _user(CUSTOMER_A),
            _ServiceWrapper(db),
        )
        transfer_id = initiated.transfer.id

        cancelled = await cancel_transfer(
            transfer_id,
            _fake_request(),
            _user(CUSTOMER_A),
            _ServiceWrapper(db),
        )
        assert isinstance(cancelled, CancelTransferResponse)
        assert cancelled.transfer.status == "cancelled"
        assert _transfer_status(db, transfer_id) == "cancelled"

        # A cancelled transfer can no longer be claimed.
        with pytest.raises(AppError) as exc:
            await claim_transfer(
                transfer_id,
                _fake_request(),
                _user(CUSTOMER_B),
                _ServiceWrapper(db),
            )
        assert exc.value.code == "ticket_transfer_not_pending"

        # And cannot be cancelled twice.
        with pytest.raises(AppError) as exc2:
            await cancel_transfer(
                transfer_id,
                _fake_request(),
                _user(CUSTOMER_A),
                _ServiceWrapper(db),
            )
        assert exc2.value.code == "ticket_transfer_not_pending"

        # Only the sender may cancel — a new pending transfer, attempted by someone
        # else, is forbidden.
        second = await initiate_transfer(
            ticket_id,
            InitiateTransferRequest(to_phone="+260971000002"),
            _fake_request(),
            _user(CUSTOMER_A),
            _ServiceWrapper(db),
        )
        with pytest.raises(AppError) as exc3:
            await cancel_transfer(
                second.transfer.id,
                _fake_request(),
                _user(CUSTOMER_B),
                _ServiceWrapper(db),
            )
        assert exc3.value.code == "forbidden"
        assert exc3.value.http_status == 403


# ---------------------------------------------------------------------------
# GET endpoints (current transfer + inbound listing) — light coverage.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("db", "db_url_env")
class TestReadEndpoints:
    async def test_current_transfer_and_inbound_listing(self, db: PgConn) -> None:
        far_future = datetime.now(UTC) + timedelta(hours=7)
        graph = _insert_event_instance(db, starts_at=far_future)
        ticket_id = str(uuid.uuid4())
        _insert_ticket(
            db,
            ticket_id=ticket_id,
            instance_id=graph["instance_id"],
            ticket_type_id=graph["ticket_type_id"],
        )

        empty = await get_current_transfer(ticket_id, _user(CUSTOMER_A), _ServiceWrapper(db))
        assert isinstance(empty, CurrentTransferResponse)
        assert empty.transfer is None

        initiated = await initiate_transfer(
            ticket_id,
            InitiateTransferRequest(to_phone="+260971000002"),
            _fake_request(),
            _user(CUSTOMER_A),
            _ServiceWrapper(db),
        )

        current = await get_current_transfer(ticket_id, _user(CUSTOMER_A), _ServiceWrapper(db))
        assert current.transfer is not None
        assert current.transfer.id == initiated.transfer.id

        inbound = await list_inbound_transfers(_user(CUSTOMER_B), _ServiceWrapper(db))
        assert isinstance(inbound, InboundTransfersResponse)
        assert any(item.id == initiated.transfer.id for item in inbound.transfers)
