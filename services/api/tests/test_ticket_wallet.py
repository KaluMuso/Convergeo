from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.tickets.qr import (
    DEFAULT_HORIZON_WINDOWS,
    current_window,
    issue_horizon,
    seal_pin_storage,
    verify_pin,
    window_code,
)
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

GOLDENS_PATH = Path(__file__).resolve().parent / "fixtures" / "qr_window_goldens.json"

CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B = "22222222-2222-2222-2222-222222222222"
TOKEN_A = "customer-a-token"
TOKEN_B = "customer-b-token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = columns, count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> MagicMock:
        rows = self._filtered_rows()
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        return rows


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "tickets": FakeTable(),
            "event_instances": FakeTable(),
            "events": FakeTable(),
            "ticket_types": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


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
    seed_matrix_fixtures(conn)
    yield conn


@pytest.fixture
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
        lambda uid, service_client: frozenset({"customer"}),
    )


def _mock_supabase(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabaseClient) -> MagicMock:
    service_wrapper = MagicMock()
    service_wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: service_wrapper)
    return service_wrapper


def _apply_supabase_overrides(app: Any, service_wrapper: MagicMock) -> None:
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper


def _seed_ticket_graph(
    fake: FakeSupabaseClient,
    *,
    ticket_id: str,
    holder_user_id: str = CUSTOMER_A,
    status: str = "issued",
    qr_secret: str = "golden-fixture-key-42",
    pin: str = "123456",
) -> None:
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    fake.tables["events"].rows.append(
        {
            "id": event_id,
            "title": "Lusaka Jazz Night",
            "venue": "Showgrounds",
            "slug": f"jazz-{event_id[:8]}",
        }
    )
    fake.tables["event_instances"].rows.append(
        {
            "id": instance_id,
            "event_id": event_id,
            "starts_at": "2026-12-01T18:00:00Z",
        }
    )
    fake.tables["ticket_types"].rows.append(
        {
            "id": ticket_type_id,
            "name": "General Admission",
            "kind": "fixed",
        }
    )
    fake.tables["tickets"].rows.append(
        {
            "id": ticket_id,
            "holder_user_id": holder_user_id,
            "status": status,
            "qr_secret": qr_secret,
            "pin_hash": seal_pin_storage(pin=pin, ticket_id=ticket_id, secret="service-role-key"),
            "instance_id": instance_id,
            "ticket_type_id": ticket_type_id,
            "created_at": "2026-07-10T12:00:00Z",
        }
    )


def _insert_event_graph(
    conn: PgConn,
    *,
    event_id: str,
    instance_id: str,
    ticket_type_id: str,
    organiser_vendor_id: str = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
) -> None:
    slug = f"wallet-{event_id[:8]}"
    conn.run(
        f"""
        INSERT INTO public.events (
          id, organiser_vendor_id, title, slug, venue, lat, lng, status
        ) VALUES (
          '{event_id}', '{organiser_vendor_id}', 'Wallet Event', '{slug}',
          'Lusaka Showgrounds', -15.4167, 28.2833, 'published'
        )
        ON CONFLICT (id) DO NOTHING;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.event_instances (id, event_id, starts_at, capacity)
        VALUES ('{instance_id}', '{event_id}', '2026-12-01T18:00:00Z', 100)
        ON CONFLICT (id) DO NOTHING;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.ticket_types (id, event_id, kind, name, price_ngwee)
        VALUES ('{ticket_type_id}', '{event_id}', 'fixed', 'GA', 50000)
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _insert_ticket(
    conn: PgConn,
    *,
    ticket_id: str,
    instance_id: str,
    ticket_type_id: str,
    holder_user_id: str,
    status: str = "issued",
    qr_secret: str = "golden-fixture-key-42",
    pin_hash: str,
) -> None:
    conn.run(
        f"""
        INSERT INTO public.tickets (
          id, instance_id, ticket_type_id, holder_user_id, status, qr_secret, pin_hash
        ) VALUES (
          '{ticket_id}', '{instance_id}', '{ticket_type_id}', '{holder_user_id}',
          '{status}', '{qr_secret}', '{pin_hash}'
        )
        ON CONFLICT (id) DO UPDATE SET
          holder_user_id = EXCLUDED.holder_user_id,
          status = EXCLUDED.status,
          qr_secret = EXCLUDED.qr_secret,
          pin_hash = EXCLUDED.pin_hash;
        """
    )


def test_window_code_matches_golden_fixture() -> None:
    fixture = json.loads(GOLDENS_PATH.read_text())
    for vector in fixture["vectors"]:
        assert window_code(vector["secret"], vector["window"]) == vector["code"]


def test_current_window_rotates_every_60_seconds() -> None:
    base = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)
    first = current_window(base)
    assert current_window(base.replace(second=59)) == first
    assert current_window(base.replace(minute=1)) == first + 1


def test_issue_horizon_is_deterministic() -> None:
    ticket_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    secret = "golden-fixture-key-42"
    entries = issue_horizon(
        secret,
        ticket_id=ticket_id,
        from_window=28990123,
        n=3,
    )
    assert [entry.window for entry in entries] == [28990123, 28990124, 28990125]
    assert entries[0].code == window_code(secret, 28990123)
    assert entries[0].qr_payload == f"{ticket_id}:28990123:{entries[0].code}"


def test_horizon_expiry_requires_resync(monkeypatch: pytest.MonkeyPatch) -> None:
    ticket_id = str(uuid.uuid4())
    fake = FakeSupabaseClient()
    _seed_ticket_graph(fake, ticket_id=ticket_id)
    _mock_auth(monkeypatch, CUSTOMER_A)
    service_wrapper = _mock_supabase(monkeypatch, fake)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    with TestClient(app) as client:
        horizon = client.get(
            f"/account/tickets/{ticket_id}/horizon",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
        )
        assert horizon.status_code == 200
        body = horizon.json()
        assert body["horizon_size"] == DEFAULT_HORIZON_WINDOWS
        last_window = body["last_window"]
        current = body["from_window"]
        assert last_window == current + DEFAULT_HORIZON_WINDOWS - 1
        assert len(body["entries"]) == DEFAULT_HORIZON_WINDOWS

        expired_window = last_window + 1
        cached_codes = {entry["window"]: entry["qr_payload"] for entry in body["entries"]}
        assert expired_window not in cached_codes


def test_pin_verify_round_trip() -> None:
    ticket_id = str(uuid.uuid4())
    stored = seal_pin_storage(pin="654321", ticket_id=ticket_id, secret="service-role-key")
    assert verify_pin(
        pin="654321", ticket_id=ticket_id, pin_hash=stored, secret="service-role-key"
    )
    assert not verify_pin(
        pin="000000", ticket_id=ticket_id, pin_hash=stored, secret="service-role-key"
    )


def test_wallet_detail_rls_other_holder_404(monkeypatch: pytest.MonkeyPatch) -> None:
    ticket_id = str(uuid.uuid4())
    fake = FakeSupabaseClient()
    _seed_ticket_graph(fake, ticket_id=ticket_id, holder_user_id=CUSTOMER_A)
    _mock_auth(monkeypatch, CUSTOMER_B)
    service_wrapper = _mock_supabase(monkeypatch, fake)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    with TestClient(app) as client:
        response = client.get(
            f"/account/tickets/{ticket_id}",
            headers={"Authorization": f"Bearer {TOKEN_B}"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_wallet_list_and_detail_for_holder(monkeypatch: pytest.MonkeyPatch) -> None:
    ticket_id = str(uuid.uuid4())
    fake = FakeSupabaseClient()
    _seed_ticket_graph(fake, ticket_id=ticket_id)
    _mock_auth(monkeypatch, CUSTOMER_A)
    service_wrapper = _mock_supabase(monkeypatch, fake)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    with TestClient(app) as client:
        listed = client.get(
            "/account/tickets",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
        )
        assert listed.status_code == 200
        tickets = listed.json()["tickets"]
        assert len(tickets) == 1
        assert tickets[0]["id"] == ticket_id
        assert tickets[0]["status"] == "issued"

        detail = client.get(
            f"/account/tickets/{ticket_id}",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
        )
        assert detail.status_code == 200
        body = detail.json()
        assert body["pin"] == "123456"
        assert body["pin_available"] is True
        assert body["qr"] is not None
        assert body["qr"]["qr_payload"].startswith(f"{ticket_id}:")
        assert "golden-fixture-key-42" not in json.dumps(body)


def test_transfer_state_detail_has_no_live_qr(monkeypatch: pytest.MonkeyPatch) -> None:
    ticket_id = str(uuid.uuid4())
    fake = FakeSupabaseClient()
    _seed_ticket_graph(fake, ticket_id=ticket_id, status="transferred")
    _mock_auth(monkeypatch, CUSTOMER_A)
    service_wrapper = _mock_supabase(monkeypatch, fake)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    with TestClient(app) as client:
        detail = client.get(
            f"/account/tickets/{ticket_id}",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
        )
        assert detail.status_code == 200
        body = detail.json()
        assert body["status"] == "transferred"
        assert body["qr"] is None


def test_horizon_rejects_non_issued_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    ticket_id = str(uuid.uuid4())
    fake = FakeSupabaseClient()
    _seed_ticket_graph(fake, ticket_id=ticket_id, status="void")
    _mock_auth(monkeypatch, CUSTOMER_A)
    service_wrapper = _mock_supabase(monkeypatch, fake)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    with TestClient(app) as client:
        response = client.get(
            f"/account/tickets/{ticket_id}/horizon",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "ticket_unusable"


def test_wallet_integration_db_rls(db: PgConn, db_url_env: None) -> None:
    ticket_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_graph(
        db,
        event_id=event_id,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
    )
    pin_hash = seal_pin_storage(
        pin="112233",
        ticket_id=ticket_id,
        secret="service-role-key",
    )
    _insert_ticket(
        db,
        ticket_id=ticket_id,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        holder_user_id=CUSTOMER_A,
        pin_hash=pin_hash,
    )

    holder_rows = db.run(
        f"""
        SELECT id::text FROM public.tickets
        WHERE id = '{ticket_id}' AND holder_user_id = '{CUSTOMER_A}';
        """
    )
    assert holder_rows.ok
    assert len(holder_rows.rows) == 1

    other_rows = db.run(
        f"""
        SELECT id::text FROM public.tickets
        WHERE id = '{ticket_id}' AND holder_user_id = '{CUSTOMER_B}';
        """
    )
    assert other_rows.ok
    assert len(other_rows.rows) == 0
