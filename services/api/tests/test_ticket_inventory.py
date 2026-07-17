from __future__ import annotations

import concurrent.futures
import json
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.ticket_types import TicketTypeCreateRequest
from app.services.tickets.inventory import claim_ticket, claim_ticket_or_raise
from fastapi.testclient import TestClient
from pydantic import ValidationError
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "demo"
CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B = "22222222-2222-2222-2222-222222222222"
VENDOR_A_OWNER = "33333333-3333-3333-3333-333333333333"
VENDOR_B_OWNER = "44444444-4444-4444-4444-444444444444"
SHOP_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SHOP_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TOKEN_A = "vendor-a-token"
TOKEN_B = "vendor-b-token"


def _load_ids() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES_DIR / "ids.json").read_text()))


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


def _insert_event_with_instance(
    conn: PgConn,
    *,
    event_id: str,
    instance_id: str,
    organiser_vendor_id: str = SHOP_B,
    capacity: int = 1,
) -> str:
    slug = f"evt-{event_id[:8]}"
    conn.run(
        f"""
        INSERT INTO public.events (
          id, organiser_vendor_id, title, slug, venue, lat, lng, status
        ) VALUES (
          '{event_id}', '{organiser_vendor_id}', 'Test Event', '{slug}',
          'Lusaka Showgrounds', -15.4167, 28.2833, 'draft'
        )
        ON CONFLICT (id) DO NOTHING;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.event_instances (id, event_id, starts_at, capacity)
        VALUES (
          '{instance_id}', '{event_id}', '2026-12-01T18:00:00Z', {capacity}
        )
        ON CONFLICT (id) DO UPDATE SET capacity = EXCLUDED.capacity;
        """
    )
    return event_id


def _insert_ticket_type(
    conn: PgConn,
    *,
    ticket_type_id: str,
    event_id: str,
    kind: str = "fixed",
    name: str = "GA",
    price_ngwee: int = 50000,
    qty_cap: int | None = None,
    per_customer_cap: int | None = None,
) -> str:
    qty_sql = "NULL" if qty_cap is None else str(qty_cap)
    per_sql = "NULL" if per_customer_cap is None else str(per_customer_cap)
    conn.run(
        f"""
        INSERT INTO public.ticket_types (
          id, event_id, kind, name, price_ngwee, qty_cap, per_customer_cap
        ) VALUES (
          '{ticket_type_id}', '{event_id}', '{kind}', '{name}', {price_ngwee},
          {qty_sql}, {per_sql}
        )
        ON CONFLICT (id) DO UPDATE
          SET qty_cap = EXCLUDED.qty_cap,
              per_customer_cap = EXCLUDED.per_customer_cap,
              price_ngwee = EXCLUDED.price_ngwee;
        """
    )
    return ticket_type_id


def _insert_allocation(
    conn: PgConn,
    *,
    ticket_type_id: str,
    instance_id: str,
    allocation: int,
) -> None:
    conn.run(
        f"""
        INSERT INTO public.ticket_type_instances (ticket_type_id, instance_id, allocation)
        VALUES ('{ticket_type_id}', '{instance_id}', {allocation})
        ON CONFLICT (ticket_type_id, instance_id)
          DO UPDATE SET allocation = EXCLUDED.allocation;
        """
    )


def _ticket_count(conn: PgConn, instance_id: str) -> int:
    result = conn.run(
        f"""
        SELECT count(*)::text FROM public.tickets
        WHERE instance_id = '{instance_id}' AND status <> 'void';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _mock_auth(monkeypatch: pytest.MonkeyPatch, user_id: str) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: frozenset({"vendor"}),
    )


class _FakeQuery:
    def __init__(self, parent: _FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._count_exact = False
        self._order: tuple[str, bool] | None = None
        self._on_conflict: list[str] = []

    def select(self, columns: str, *, count: str | None = None) -> _FakeQuery:
        self._count_exact = count == "exact"
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> _FakeQuery:
        self._filters.append(("neq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> _FakeQuery:
        self._filters.append(("in", column, list(values)))
        return self

    def order(self, column: str, *, desc: bool = False) -> _FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> _FakeQuery:
        return self

    def maybe_single(self) -> _FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> _FakeQuery:
        self._pending_op = "insert"
        self._payload = payload  # type: ignore[assignment]
        return self

    def upsert(
        self,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        on_conflict: str,
    ) -> _FakeQuery:
        self._pending_op = "upsert"
        self._payload = payload  # type: ignore[assignment]
        self._on_conflict = [col.strip() for col in on_conflict.split(",")]
        return self

    def update(self, payload: dict[str, Any]) -> _FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def delete(self) -> _FakeQuery:
        self._pending_op = "delete"
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            payload_rows: list[dict[str, Any]] = []
            if isinstance(self._payload, list):
                payload_rows = [row for row in self._payload if isinstance(row, dict)]
            elif isinstance(self._payload, dict):
                payload_rows = [self._payload]
            inserted: list[dict[str, Any]] = []
            for row in payload_rows:
                stored = dict(row)
                stored.setdefault("id", str(uuid.uuid4()))
                self._parent.rows.append(stored)
                inserted.append(dict(stored))
            if self._maybe_single:
                return MagicMock(data=inserted[0] if inserted else None, count=len(inserted))
            return MagicMock(data=inserted, count=len(inserted))

        if self._pending_op == "upsert":
            upsert_rows: list[dict[str, Any]] = []
            if isinstance(self._payload, list):
                upsert_rows = [row for row in self._payload if isinstance(row, dict)]
            elif isinstance(self._payload, dict):
                upsert_rows = [self._payload]
            written: list[dict[str, Any]] = []
            for row in upsert_rows:
                match = next(
                    (
                        existing
                        for existing in self._parent.rows
                        if all(existing.get(key) == row.get(key) for key in self._on_conflict)
                    ),
                    None,
                )
                if match is not None:
                    match.update(row)
                    written.append(dict(match))
                else:
                    stored = dict(row)
                    self._parent.rows.append(stored)
                    written.append(dict(stored))
            return MagicMock(data=written, count=len(written))

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            if self._maybe_single:
                return MagicMock(data=updated[0] if updated else None, count=len(updated))
            return MagicMock(data=updated, count=len(updated))

        if self._pending_op == "delete":
            kept: list[dict[str, Any]] = []
            deleted = 0
            for row in self._parent.rows:
                if self._matches(row):
                    deleted += 1
                else:
                    kept.append(row)
            self._parent.rows[:] = kept
            return MagicMock(data=[], count=deleted)

        rows = self._filtered_rows()
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        if self._count_exact:
            return MagicMock(data=rows, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
            elif op == "neq":
                rows = [row for row in rows if row.get(column) != value]
            elif op == "in":
                rows = [row for row in rows if row.get(column) in value]
        return rows

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "in" and row.get(column) not in value:
                return False
        return True


class _FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> _FakeQuery:
        return _FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> _FakeQuery:
        return _FakeQuery(self, []).insert(payload)

    def upsert(
        self,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        on_conflict: str,
    ) -> _FakeQuery:
        return _FakeQuery(self, []).upsert(payload, on_conflict=on_conflict)

    def update(self, payload: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self, []).update(payload)

    def delete(self) -> _FakeQuery:
        return _FakeQuery(self, []).delete()


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, _FakeTable] = {
            "vendors": _FakeTable(),
            "events": _FakeTable(),
            "ticket_types": _FakeTable(),
            "tickets": _FakeTable(),
            "event_instances": _FakeTable(),
            "ticket_type_instances": _FakeTable(),
        }

    def table(self, name: str) -> _FakeTable:
        return self.tables.setdefault(name, _FakeTable())


def _seed_fake_organiser_data(fake: _FakeSupabaseClient) -> dict[str, str]:
    ids = _load_ids()
    event_id = ids["events"]["festival"]
    ticket_type_id = ids["ticket_types"]["ga"]
    fake.tables["vendors"].rows.extend(
        [
            {
                "id": SHOP_A,
                "owner_user_id": VENDOR_A_OWNER,
                "status": "active",
                "kyc_tier": 2,
            },
            {
                "id": SHOP_B,
                "owner_user_id": VENDOR_B_OWNER,
                "status": "active",
                "kyc_tier": 2,
            },
        ]
    )
    fake.tables["events"].rows.append(
        {
            "id": event_id,
            "organiser_vendor_id": SHOP_B,
            "status": "published",
        }
    )
    fake.tables["ticket_types"].rows.append(
        {
            "id": ticket_type_id,
            "event_id": event_id,
            "kind": "fixed",
            "name": "General Admission",
            "price_ngwee": 75000,
            "qty_cap": 400,
            "per_customer_cap": None,
        }
    )
    return {"event_id": event_id, "ticket_type_id": ticket_type_id}


def _api_client(
    monkeypatch: pytest.MonkeyPatch,
    user_id: str,
    fake: _FakeSupabaseClient,
) -> TestClient:
    _mock_auth(monkeypatch, user_id)
    app = create_app()
    wrapper = MagicMock()
    wrapper.client = fake
    app.dependency_overrides[get_supabase_client] = lambda: wrapper
    return TestClient(app)


class TestConcurrentClaim:
    def test_two_concurrent_claims_at_capacity_one_exactly_one_succeeds(self, db: PgConn) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        ticket_type_id = str(uuid.uuid4())
        _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=1)
        _insert_ticket_type(db, ticket_type_id=ticket_type_id, event_id=event_id)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(
                claim_ticket,
                None,
                instance_id=instance_id,
                ticket_type_id=ticket_type_id,
                holder_user_id=CUSTOMER_A,
                qty=1,
            )
            future_b = executor.submit(
                claim_ticket,
                None,
                instance_id=instance_id,
                ticket_type_id=ticket_type_id,
                holder_user_id=CUSTOMER_B,
                qty=1,
            )
            results = [future_a.result(), future_b.result()]

        successes = [result for result in results if result.claimed]
        failures = [result for result in results if not result.claimed]

        assert len(successes) == 1
        assert len(failures) == 1
        assert _ticket_count(db, instance_id) == 1


class TestQtyCapBoundary:
    def test_qty_cap_blocks_second_claim(self, db: PgConn) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        ticket_type_id = str(uuid.uuid4())
        _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=10)
        _insert_ticket_type(
            db,
            ticket_type_id=ticket_type_id,
            event_id=event_id,
            qty_cap=1,
        )

        first = claim_ticket(
            None,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            holder_user_id=CUSTOMER_A,
        )
        second = claim_ticket(
            None,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            holder_user_id=CUSTOMER_B,
        )

        assert first.claimed
        assert not second.claimed
        assert _ticket_count(db, instance_id) == 1


class TestPerCustomerCap:
    def test_same_holder_over_cap_rejected(self, db: PgConn) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        ticket_type_id = str(uuid.uuid4())
        _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=10)
        _insert_ticket_type(
            db,
            ticket_type_id=ticket_type_id,
            event_id=event_id,
            per_customer_cap=1,
        )

        first = claim_ticket(
            None,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            holder_user_id=CUSTOMER_A,
        )
        second = claim_ticket(
            None,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            holder_user_id=CUSTOMER_A,
        )

        assert first.claimed
        assert not second.claimed
        assert _ticket_count(db, instance_id) == 1


class TestTierConfigValidation:
    def test_free_rsvp_price_must_be_zero(self) -> None:
        with pytest.raises(ValidationError):
            TicketTypeCreateRequest(
                kind="free_rsvp",
                name="RSVP",
                price_ngwee=100,
            )

    def test_fixed_tier_price_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            TicketTypeCreateRequest(
                kind="tier",
                name="VIP",
                price_ngwee=0,
            )

    def test_free_rsvp_accepts_zero_price(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeSupabaseClient()
        event_id = str(uuid.uuid4())
        fake.tables["vendors"].rows.append(
            {
                "id": SHOP_B,
                "owner_user_id": VENDOR_B_OWNER,
                "status": "active",
                "kyc_tier": 2,
            }
        )
        fake.tables["events"].rows.append(
            {
                "id": event_id,
                "organiser_vendor_id": SHOP_B,
                "status": "draft",
            }
        )
        client = _api_client(monkeypatch, VENDOR_B_OWNER, fake)

        response = client.post(
            f"/organiser/events/{event_id}/ticket-types",
            headers={"Authorization": f"Bearer {TOKEN_B}"},
            json={
                "kind": "free_rsvp",
                "name": "Free RSVP",
                "price_ngwee": 0,
            },
        )

        assert response.status_code == 201
        assert response.json()["price_ngwee"] == 0
        assert response.json()["kind"] == "free_rsvp"


class TestOrganiserAuthz:
    def test_cross_vendor_type_crud_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeSupabaseClient()
        seeded = _seed_fake_organiser_data(fake)
        event_id = seeded["event_id"]
        ticket_type_id = seeded["ticket_type_id"]
        client = _api_client(monkeypatch, VENDOR_A_OWNER, fake)

        list_resp = client.get(
            f"/organiser/events/{event_id}/ticket-types",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
        )
        assert list_resp.status_code == 403

        create_resp = client.post(
            f"/organiser/events/{event_id}/ticket-types",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
            json={
                "kind": "tier",
                "name": "Intruder",
                "price_ngwee": 10000,
            },
        )
        assert create_resp.status_code == 403

        patch_resp = client.patch(
            f"/organiser/ticket-types/{ticket_type_id}",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
            json={"name": "Hijacked"},
        )
        assert patch_resp.status_code == 403


class TestAttendeeNamed:
    def _seed_event(self, fake: _FakeSupabaseClient) -> str:
        event_id = str(uuid.uuid4())
        fake.tables["vendors"].rows.append(
            {
                "id": SHOP_B,
                "owner_user_id": VENDOR_B_OWNER,
                "status": "active",
                "kyc_tier": 2,
            }
        )
        fake.tables["events"].rows.append(
            {
                "id": event_id,
                "organiser_vendor_id": SHOP_B,
                "status": "draft",
            }
        )
        return event_id

    def test_create_defaults_attendee_named_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeSupabaseClient()
        event_id = self._seed_event(fake)
        client = _api_client(monkeypatch, VENDOR_B_OWNER, fake)

        response = client.post(
            f"/organiser/events/{event_id}/ticket-types",
            headers={"Authorization": f"Bearer {TOKEN_B}"},
            json={"kind": "fixed", "name": "General", "price_ngwee": 50000},
        )

        assert response.status_code == 201
        assert response.json()["attendee_named"] is False

    def test_create_and_toggle_attendee_named(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeSupabaseClient()
        event_id = self._seed_event(fake)
        client = _api_client(monkeypatch, VENDOR_B_OWNER, fake)

        created = client.post(
            f"/organiser/events/{event_id}/ticket-types",
            headers={"Authorization": f"Bearer {TOKEN_B}"},
            json={
                "kind": "free_rsvp",
                "name": "Workshop seat",
                "price_ngwee": 0,
                "attendee_named": True,
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["attendee_named"] is True
        # A free RSVP may still collect names (workshop roster).
        assert body["kind"] == "free_rsvp"

        toggled = client.patch(
            f"/organiser/ticket-types/{body['id']}",
            headers={"Authorization": f"Bearer {TOKEN_B}"},
            json={"attendee_named": False},
        )
        assert toggled.status_code == 200
        assert toggled.json()["attendee_named"] is False


class TestMigration0020:
    def test_per_customer_cap_column_replay_safe(self, db: PgConn) -> None:
        result = db.run(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'ticket_types'
              AND column_name = 'per_customer_cap';
            """
        )
        assert result.ok and result.rows
        assert result.rows[0] == "per_customer_cap"

        migration = (
            Path(__file__).resolve().parents[3]
            / "supabase"
            / "migrations"
            / "0020_ticket_type_per_customer_cap.sql"
        )
        replay = db.run_file(migration)
        assert replay.ok


class TestClaimTicketOrRaise:
    def test_oversell_raises_uniform_error(self, db: PgConn) -> None:
        from app.errors import AppError

        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        ticket_type_id = str(uuid.uuid4())
        _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=1)
        _insert_ticket_type(db, ticket_type_id=ticket_type_id, event_id=event_id)

        claim_ticket_or_raise(
            None,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            holder_user_id=CUSTOMER_A,
        )

        with pytest.raises(AppError) as exc_info:
            claim_ticket_or_raise(
                None,
                instance_id=instance_id,
                ticket_type_id=ticket_type_id,
                holder_user_id=CUSTOMER_B,
            )

        assert exc_info.value.code == "tickets.oversell"
        assert exc_info.value.http_status == 409


class TestMigration0048:
    def test_allocation_table_and_column_present(self, db: PgConn) -> None:
        result = db.run(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'ticket_type_instances'
              AND column_name = 'allocation';
            """
        )
        assert result.ok and result.rows
        assert result.rows[0] == "allocation"


class TestAllocationBoundary:
    def test_allocation_caps_below_instance_capacity(self, db: PgConn) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        ticket_type_id = str(uuid.uuid4())
        _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=10)
        _insert_ticket_type(db, ticket_type_id=ticket_type_id, event_id=event_id)
        _insert_allocation(
            db, ticket_type_id=ticket_type_id, instance_id=instance_id, allocation=1
        )

        first = claim_ticket(
            None,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            holder_user_id=CUSTOMER_A,
        )
        second = claim_ticket(
            None,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            holder_user_id=CUSTOMER_B,
        )

        assert first.claimed
        assert not second.claimed  # allocation 1 blocks the 2nd despite capacity 10
        assert _ticket_count(db, instance_id) == 1

    def test_absent_allocation_row_imposes_no_cap(self, db: PgConn) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        ticket_type_id = str(uuid.uuid4())
        _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=10)
        _insert_ticket_type(db, ticket_type_id=ticket_type_id, event_id=event_id)
        # No ticket_type_instances row → the allocation clause is a no-op.
        for holder in (CUSTOMER_A, CUSTOMER_B, CUSTOMER_A):
            result = claim_ticket(
                None,
                instance_id=instance_id,
                ticket_type_id=ticket_type_id,
                holder_user_id=holder,
            )
            assert result.claimed
        assert _ticket_count(db, instance_id) == 3

    def test_allocation_is_quantity_aware(self, db: PgConn) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        ticket_type_id = str(uuid.uuid4())
        _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=10)
        _insert_ticket_type(db, ticket_type_id=ticket_type_id, event_id=event_id)
        _insert_allocation(
            db, ticket_type_id=ticket_type_id, instance_id=instance_id, allocation=2
        )

        first = claim_ticket(
            None,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            holder_user_id=CUSTOMER_A,
            qty=2,
        )
        # 2 already sold against allocation 2 → any further claim is blocked.
        third = claim_ticket(
            None,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            holder_user_id=CUSTOMER_B,
            qty=1,
        )

        assert first.claimed
        assert not third.claimed
        assert _ticket_count(db, instance_id) == 2


class TestConcurrentAllocationClaim:
    def test_two_concurrent_claims_at_allocation_one(self, db: PgConn) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        ticket_type_id = str(uuid.uuid4())
        _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=10)
        _insert_ticket_type(db, ticket_type_id=ticket_type_id, event_id=event_id)
        _insert_allocation(
            db, ticket_type_id=ticket_type_id, instance_id=instance_id, allocation=1
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(
                claim_ticket,
                None,
                instance_id=instance_id,
                ticket_type_id=ticket_type_id,
                holder_user_id=CUSTOMER_A,
                qty=1,
            )
            future_b = executor.submit(
                claim_ticket,
                None,
                instance_id=instance_id,
                ticket_type_id=ticket_type_id,
                holder_user_id=CUSTOMER_B,
                qty=1,
            )
            results = [future_a.result(), future_b.result()]

        assert len([result for result in results if result.claimed]) == 1
        assert _ticket_count(db, instance_id) == 1


INSTANCE_1 = "eeee1111-1111-1111-1111-111111111111"
INSTANCE_2 = "eeee2222-2222-2222-2222-222222222222"


class TestAllocationApi:
    """Organiser allocation GET/PUT — authz + validation, against the fake client."""

    def _seed(self, fake: _FakeSupabaseClient) -> dict[str, str]:
        seeded = _seed_fake_organiser_data(fake)
        fake.tables["event_instances"].rows.extend(
            [
                {
                    "id": INSTANCE_1,
                    "event_id": seeded["event_id"],
                    "starts_at": "2026-12-01T18:00:00Z",
                },
                {
                    "id": INSTANCE_2,
                    "event_id": seeded["event_id"],
                    "starts_at": "2026-12-02T18:00:00Z",
                },
            ]
        )
        return seeded

    def test_put_then_get_reflects_allocations(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeSupabaseClient()
        seeded = self._seed(fake)
        client = _api_client(monkeypatch, VENDOR_B_OWNER, fake)

        resp = client.put(
            f"/organiser/ticket-types/{seeded['ticket_type_id']}/allocations",
            json={"allocations": [{"instance_id": INSTANCE_1, "allocation": 5}]},
            headers={"Authorization": f"Bearer {TOKEN_B}"},
        )
        assert resp.status_code == 200
        by_instance = {row["instance_id"]: row for row in resp.json()}
        assert by_instance[INSTANCE_1]["allocation"] == 5
        assert by_instance[INSTANCE_2]["allocation"] is None  # uncapped

        got = client.get(
            f"/organiser/ticket-types/{seeded['ticket_type_id']}/allocations",
            headers={"Authorization": f"Bearer {TOKEN_B}"},
        )
        assert got.status_code == 200
        allocations = {row["instance_id"]: row["allocation"] for row in got.json()}
        assert allocations == {INSTANCE_1: 5, INSTANCE_2: None}

    def test_put_removes_omitted_allocation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeSupabaseClient()
        seeded = self._seed(fake)
        fake.tables["ticket_type_instances"].rows.append(
            {
                "ticket_type_id": seeded["ticket_type_id"],
                "instance_id": INSTANCE_1,
                "allocation": 3,
            }
        )
        client = _api_client(monkeypatch, VENDOR_B_OWNER, fake)

        resp = client.put(
            f"/organiser/ticket-types/{seeded['ticket_type_id']}/allocations",
            json={"allocations": [{"instance_id": INSTANCE_2, "allocation": 7}]},
            headers={"Authorization": f"Bearer {TOKEN_B}"},
        )
        assert resp.status_code == 200
        capped = {row["instance_id"] for row in fake.tables["ticket_type_instances"].rows}
        assert capped == {INSTANCE_2}  # the omitted INSTANCE_1 cap was removed

    def test_put_rejects_allocation_below_sold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeSupabaseClient()
        seeded = self._seed(fake)
        fake.tables["tickets"].rows.append(
            {
                "id": str(uuid.uuid4()),
                "ticket_type_id": seeded["ticket_type_id"],
                "instance_id": INSTANCE_1,
                "status": "issued",
            }
        )
        client = _api_client(monkeypatch, VENDOR_B_OWNER, fake)

        resp = client.put(
            f"/organiser/ticket-types/{seeded['ticket_type_id']}/allocations",
            json={"allocations": [{"instance_id": INSTANCE_1, "allocation": 0}]},
            headers={"Authorization": f"Bearer {TOKEN_B}"},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "allocation_below_sold"

    def test_put_rejects_foreign_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeSupabaseClient()
        seeded = self._seed(fake)
        client = _api_client(monkeypatch, VENDOR_B_OWNER, fake)

        resp = client.put(
            f"/organiser/ticket-types/{seeded['ticket_type_id']}/allocations",
            json={
                "allocations": [
                    {"instance_id": "ffff9999-9999-9999-9999-999999999999", "allocation": 1}
                ]
            },
            headers={"Authorization": f"Bearer {TOKEN_B}"},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_instance"

    def test_non_owner_forbidden(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeSupabaseClient()
        seeded = self._seed(fake)
        # VENDOR_A owns SHOP_A; the event belongs to SHOP_B.
        client = _api_client(monkeypatch, VENDOR_A_OWNER, fake)

        resp = client.get(
            f"/organiser/ticket-types/{seeded['ticket_type_id']}/allocations",
            headers={"Authorization": f"Bearer {TOKEN_A}"},
        )
        assert resp.status_code == 403
