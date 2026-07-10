from __future__ import annotations

import concurrent.futures
import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.routers.ticket_verify import (
    BatchScanItem,
    build_qr_code,
    current_window,
    hash_ticket_pin,
    verify_and_check_in_ticket,
    verify_batch_scans,
    window_sig,
)
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
GOLDENS_PATH = FIXTURES_DIR / "qr_window_goldens.json"

CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
VENDOR_B_OWNER = "44444444-4444-4444-4444-444444444444"
SHOP_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SHOP_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TOKEN_B = "vendor-b-token"
FESTIVAL_INSTANCE = "e1000000-0000-0000-0000-000000000001"
GA_TICKET_TYPE = "e2000000-0000-0000-0000-000000000001"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    url = resolve_db_url()
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


def _mock_auth(monkeypatch: pytest.MonkeyPatch, user_id: str) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: frozenset({"vendor"}),
    )


def _insert_ticket(
    conn: PgConn,
    *,
    ticket_id: str,
    instance_id: str = FESTIVAL_INSTANCE,
    ticket_type_id: str = GA_TICKET_TYPE,
    holder_user_id: str = CUSTOMER_A,
    status: str = "issued",
    qr_secret: str = "ticket-secret-abc",
    pin: str = "123456",
) -> str:
    pin_hash = hash_ticket_pin(pin=pin, ticket_id=ticket_id)
    checked_sql = "timezone('utc', now())" if status == "checked_in" else "NULL"
    conn.run(
        f"""
        INSERT INTO public.tickets (
          id, instance_id, ticket_type_id, holder_user_id, status,
          qr_secret, pin_hash, checked_in_at
        ) VALUES (
          '{ticket_id}', '{instance_id}', '{ticket_type_id}', '{holder_user_id}',
          '{status}', {_sql_literal(qr_secret)}, {_sql_literal(pin_hash)}, {checked_sql}
        )
        ON CONFLICT (id) DO UPDATE
          SET status = EXCLUDED.status,
              qr_secret = EXCLUDED.qr_secret,
              pin_hash = EXCLUDED.pin_hash,
              checked_in_at = EXCLUDED.checked_in_at;
        """
    )
    return ticket_id


def _ticket_status(conn: PgConn, ticket_id: str) -> str:
    result = conn.run(f"SELECT status FROM public.tickets WHERE id = '{ticket_id}';")
    assert result.ok and result.rows
    return result.rows[0]


def _ticket_checked_in(conn: PgConn, ticket_id: str) -> bool:
    result = conn.run(
        f"SELECT checked_in_at IS NOT NULL FROM public.tickets WHERE id = '{ticket_id}';"
    )
    assert result.ok and result.rows
    return result.rows[0] == "t"


@pytest.mark.usefixtures("db", "db_url_env")
class TestTicketVerifyWindowMatrix:
    def test_window_matrix_offsets(self, db: PgConn) -> None:
        now = datetime(2026, 7, 10, 12, 30, 0, tzinfo=UTC)
        base_window = current_window(now)
        secret = "window-matrix-secret"

        for offset in (0, -1, 1):
            ticket_id = str(uuid.uuid4())
            _insert_ticket(db, ticket_id=ticket_id, qr_secret=secret)
            code = build_qr_code(
                ticket_id=ticket_id,
                ticket_secret=secret,
                window=base_window + offset,
            )
            result = verify_and_check_in_ticket(
                ticket_id=ticket_id,
                vendor_id=SHOP_B,
                code=code,
                now=now,
            )
            assert result.to_status == "checked_in"

        for offset in (-2, 2):
            ticket_id = str(uuid.uuid4())
            _insert_ticket(db, ticket_id=ticket_id, qr_secret=secret)
            code = build_qr_code(
                ticket_id=ticket_id,
                ticket_secret=secret,
                window=base_window + offset,
            )
            with pytest.raises(AppError) as exc:
                verify_and_check_in_ticket(
                    ticket_id=ticket_id,
                    vendor_id=SHOP_B,
                    code=code,
                    now=now,
                )
            assert exc.value.code == "ticket_qr_stale"

    def test_shared_goldens_if_present(self, db: PgConn) -> None:
        if not GOLDENS_PATH.is_file():
            pytest.skip("TODO(M10-P04): qr_window_goldens.json not yet created")

        payload = json.loads(GOLDENS_PATH.read_text())
        vectors = payload.get("vectors", payload)
        reference_now = payload.get("reference_now", "2026-07-10T12:00:00+00:00")
        now = datetime.fromisoformat(reference_now)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        for entry in vectors:
            ticket_id = str(uuid.uuid4())
            secret = entry["secret"]
            window = int(entry["window"])
            expected_code = entry["code"].replace(entry["ticket_id"], ticket_id)
            _insert_ticket(db, ticket_id=ticket_id, qr_secret=secret)
            computed = build_qr_code(ticket_id=ticket_id, ticket_secret=secret, window=window)
            assert computed == expected_code
            assert window_sig(secret, window) == expected_code.split(":")[-1]

            result = verify_and_check_in_ticket(
                ticket_id=ticket_id,
                vendor_id=SHOP_B,
                code=computed,
                now=datetime.fromtimestamp(window * 60, tz=UTC),
            )
            assert result.to_status == "checked_in"


@pytest.mark.usefixtures("db", "db_url_env")
class TestTicketVerifyRace:
    def test_concurrent_verify_exactly_one_check_in(self, db: PgConn) -> None:
        ticket_id = str(uuid.uuid4())
        secret = "race-secret"
        _insert_ticket(db, ticket_id=ticket_id, qr_secret=secret)
        now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)
        code = build_qr_code(
            ticket_id=ticket_id,
            ticket_secret=secret,
            window=current_window(now),
        )

        def attempt() -> str:
            try:
                verify_and_check_in_ticket(
                    ticket_id=ticket_id,
                    vendor_id=SHOP_B,
                    code=code,
                    now=now,
                )
                return "ok"
            except AppError as exc:
                return exc.code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = (executor.submit(attempt), executor.submit(attempt))
            results = [future.result() for future in futures]

        assert results.count("ok") == 1
        assert results.count("ticket_already_checked_in") == 1
        assert _ticket_status(db, ticket_id) == "checked_in"
        assert _ticket_checked_in(db, ticket_id)


@pytest.mark.usefixtures("db", "db_url_env")
class TestTicketVerifyBatch:
    def test_earliest_scanned_at_wins_and_later_duplicate(self, db: PgConn) -> None:
        ticket_id = str(uuid.uuid4())
        secret = "batch-secret"
        _insert_ticket(db, ticket_id=ticket_id, qr_secret=secret)
        now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)
        code = build_qr_code(
            ticket_id=ticket_id,
            ticket_secret=secret,
            window=current_window(now),
        )
        earlier = now - timedelta(seconds=30)
        later = now + timedelta(seconds=30)

        results = verify_batch_scans(
            scans=[
                BatchScanItem(ticket_id=ticket_id, code=code, scanned_at=later),
                BatchScanItem(ticket_id=ticket_id, code=code, scanned_at=earlier),
            ],
            vendor_id=SHOP_B,
            now=now,
        )

        assert results[0].outcome == "duplicate"
        assert results[0].error_code == "ticket_duplicate_scan"
        assert results[1].outcome == "checked_in"
        assert _ticket_status(db, ticket_id) == "checked_in"

    def test_batch_replay_is_idempotent(self, db: PgConn) -> None:
        ticket_id = str(uuid.uuid4())
        secret = "replay-secret"
        _insert_ticket(db, ticket_id=ticket_id, qr_secret=secret)
        now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)
        code = build_qr_code(
            ticket_id=ticket_id,
            ticket_secret=secret,
            window=current_window(now),
        )
        scans = [
            BatchScanItem(
                ticket_id=ticket_id,
                code=code,
                scanned_at=now - timedelta(seconds=5),
            ),
            BatchScanItem(
                ticket_id=ticket_id,
                code=code,
                scanned_at=now + timedelta(seconds=5),
            ),
        ]

        first = verify_batch_scans(scans=scans, vendor_id=SHOP_B, now=now)
        second = verify_batch_scans(scans=scans, vendor_id=SHOP_B, now=now)

        assert first[0].outcome == "checked_in"
        assert first[1].outcome == "duplicate"
        assert second[0].outcome == "already_checked_in"
        assert second[1].outcome == "duplicate"
        assert _ticket_status(db, ticket_id) == "checked_in"


@pytest.mark.usefixtures("db", "db_url_env")
class TestTicketVerifyAuthzAndStatus:
    def test_cross_organiser_denied(self, db: PgConn) -> None:
        ticket_id = str(uuid.uuid4())
        secret = "authz-secret"
        _insert_ticket(db, ticket_id=ticket_id, qr_secret=secret)
        now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)
        code = build_qr_code(
            ticket_id=ticket_id,
            ticket_secret=secret,
            window=current_window(now),
        )

        with pytest.raises(AppError) as exc:
            verify_and_check_in_ticket(
                ticket_id=ticket_id,
                vendor_id=SHOP_A,
                code=code,
                now=now,
            )
        assert exc.value.http_status == 403
        assert _ticket_status(db, ticket_id) == "issued"

    def test_void_and_transferred_rejected(self, db: PgConn) -> None:
        now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)
        secret = "status-secret"

        void_id = str(uuid.uuid4())
        _insert_ticket(db, ticket_id=void_id, qr_secret=secret, status="void")
        void_code = build_qr_code(
            ticket_id=void_id,
            ticket_secret=secret,
            window=current_window(now),
        )
        with pytest.raises(AppError) as void_exc:
            verify_and_check_in_ticket(
                ticket_id=void_id,
                vendor_id=SHOP_B,
                code=void_code,
                now=now,
            )
        assert void_exc.value.code == "ticket_void"

        transferred_id = str(uuid.uuid4())
        _insert_ticket(db, ticket_id=transferred_id, qr_secret=secret, status="transferred")
        transferred_code = build_qr_code(
            ticket_id=transferred_id,
            ticket_secret=secret,
            window=current_window(now),
        )
        with pytest.raises(AppError) as transferred_exc:
            verify_and_check_in_ticket(
                ticket_id=transferred_id,
                vendor_id=SHOP_B,
                code=transferred_code,
                now=now,
            )
        assert transferred_exc.value.code == "ticket_transferred"

    def test_pin_fallback_checks_in(self, db: PgConn) -> None:
        ticket_id = str(uuid.uuid4())
        _insert_ticket(db, ticket_id=ticket_id, pin="654321")
        result = verify_and_check_in_ticket(
            ticket_id=ticket_id,
            vendor_id=SHOP_B,
            pin="654321",
        )
        assert result.to_status == "checked_in"
        assert _ticket_status(db, ticket_id) == "checked_in"


@pytest.mark.usefixtures("db", "db_url_env")
class TestTicketVerifyHttp:
    def test_verify_http_success(self, db: PgConn, monkeypatch: pytest.MonkeyPatch) -> None:
        ticket_id = str(uuid.uuid4())
        secret = "http-secret"
        _insert_ticket(db, ticket_id=ticket_id, qr_secret=secret)
        now = datetime.now(UTC)
        code = build_qr_code(
            ticket_id=ticket_id,
            ticket_secret=secret,
            window=current_window(now),
        )
        _mock_auth(monkeypatch, VENDOR_B_OWNER)
        monkeypatch.setattr(
            "app.routers.ticket_verify.bump_rate_counter",
            lambda **kwargs: (True, 0),
        )

        service_wrapper = MagicMock()
        real_client = MagicMock()
        real_client.table.side_effect = lambda name: _VendorLookupTable(name)
        service_wrapper.client = real_client

        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: service_wrapper

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/tickets/verify",
                headers={"Authorization": f"Bearer {TOKEN_B}"},
                json={"ticket_id": ticket_id, "code": code},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["ticket_id"] == ticket_id
        assert payload["to_status"] == "checked_in"
        assert _ticket_status(db, ticket_id) == "checked_in"


class _VendorLookupTable:
    def __init__(self, name: str) -> None:
        self._name = name

    def select(self, columns: str) -> _VendorLookupQuery:
        return _VendorLookupQuery(self._name)


class _VendorLookupQuery:
    def __init__(self, name: str) -> None:
        self._name = name

    def eq(self, column: str, value: Any) -> _VendorLookupQuery:
        return self

    def maybe_single(self) -> _VendorLookupQuery:
        return self

    def execute(self) -> MagicMock:
        if self._name != "vendors":
            raise AssertionError(f"unexpected table {self._name}")
        return MagicMock(
            data={
                "id": SHOP_B,
                "owner_user_id": VENDOR_B_OWNER,
            }
        )
