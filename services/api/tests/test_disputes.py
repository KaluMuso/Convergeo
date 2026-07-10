"""Dispute lifecycle tests — hold-beats-timer, resolution dispatch, RLS, guarded transitions."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.services.disputes.state import (
    ActorRole,
    DisputeEvent,
    DisputeStatus,
    DisputeTransitionError,
    count_dispute_audit_events,
    transition_dispute,
)
from app.services.escrow.release import (
    DEFAULT_RELEASE_AFTER_DELIVERED_HOURS,
    evaluate_and_release,
)
from app.services.orders.state import SYSTEM_ACTOR_ID
from tests.rls.conftest import (
    MIGRATIONS_DIR,
    Persona,
    PgConn,
    RoleSession,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_CUSTOMER_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_OWNER_ID = "33333333-3333-3333-3333-333333333333"
ADMIN_ID = "66666666-6666-6666-6666-666666666666"
CUSTOMER_MOMO = "260971234567"

GROSS_NGEWEE = 200_000


class _ServiceWrapper:
    client: Any = None


_SERVICE = _ServiceWrapper()


def ensure_migration_0019(conn: PgConn) -> None:
    result = conn.run(
        """
        SELECT count(*)::text
        FROM pg_constraint
        WHERE conname = 'disputes_status_check'
          AND conrelid = 'public.disputes'::regclass
          AND pg_get_constraintdef(oid) LIKE '%under_review%';
        """
    )
    if result.ok and result.rows and result.rows[0] == "0":
        migration = MIGRATIONS_DIR / "0019_dispute_status_states.sql"
        applied = conn.run_file(migration)
        if not applied.ok:
            raise RuntimeError(f"failed to apply {migration.name}: {applied.error}")


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
    else:
        ensure_migration_0019(conn)
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


@pytest.fixture
def role_factory(db: PgConn) -> Callable[[Persona], RoleSession]:
    def _make(persona: Persona) -> RoleSession:
        return RoleSession(db, persona)

    return _make


def _insert_checkout_group(conn: PgConn, group_id: str, customer_id: str = CUSTOMER_ID) -> None:
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{group_id}', '{customer_id}', 'cg-{group_id}',
          {GROSS_NGEWEE}, 0, {GROSS_NGEWEE}, 'completed'
        ) ON CONFLICT (id) DO NOTHING;
        """
    )


def _insert_order(
    conn: PgConn,
    *,
    order_id: str,
    group_id: str,
    customer_id: str = CUSTOMER_ID,
    status: str = "completed",
) -> None:
    _insert_checkout_group(conn, group_id, customer_id)
    conn.run(
        f"""
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
          delivery_fee_ngwee, cod, commission_snapshot
        ) VALUES (
          '{order_id}', '{group_id}', '{VENDOR_A}', '{customer_id}',
          '{status}', 'delivery', 0, false, '{{}}'::jsonb
        ) ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.order_items (
          id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', 'product', 1, {GROSS_NGEWEE}, 'Test item'
        );
        """
    )


def _insert_order_event(
    conn: PgConn,
    *,
    order_id: str,
    from_status: str | None,
    to_status: str,
    actor: str | None,
    created_at: datetime,
) -> None:
    actor_sql = f"'{actor}'::uuid" if actor else "NULL"
    from_sql = f"'{from_status}'" if from_status else "NULL"
    ts = created_at.astimezone(UTC).isoformat()
    conn.run(
        f"""
        INSERT INTO public.order_events (
          id, order_id, actor, from_status, to_status, created_at
        ) VALUES (
          '{uuid.uuid4()}', '{order_id}', {actor_sql}, {from_sql},
          '{to_status}', '{ts}'::timestamptz
        );
        """
    )


def _insert_dispute(
    conn: PgConn,
    *,
    order_id: str,
    dispute_id: str | None = None,
    status: str = "open",
) -> str:
    did = dispute_id or str(uuid.uuid4())
    conn.run(
        f"""
        INSERT INTO public.disputes (
          id, order_id, opener_user_id, status
        ) VALUES (
          '{did}', '{order_id}', '{CUSTOMER_ID}', '{status}'
        ) ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;
        """
    )
    return did


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = list(filters)
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._in_filter: tuple[str, list[Any]] | None = None
        self._count: str | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        self._count = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in_filter = (column, values)
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

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = str(uuid.uuid4())
            self._parent.rows.append(row)
            return MagicMock(data=[row], count=None)

        rows = self._filtered_rows()
        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in rows:
                row.update(self._payload)
                updated.append(row)
            rows = updated

        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        if self._count == "exact":
            return MagicMock(data=rows, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        if self._in_filter is not None:
            column, values = self._in_filter
            allowed = set(values)
            rows = [row for row in rows if row.get(column) in allowed]
        return rows


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "orders": FakeTable(),
            "disputes": FakeTable(),
            "audit_log": FakeTable(),
            "order_items": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


class _FakeServiceWrapper:
    def __init__(self, client: FakeSupabaseClient) -> None:
        self.client = client


def _seed_fake_dispute(
    fake: FakeSupabaseClient,
    *,
    dispute_id: str,
    order_id: str,
    status: str = "under_review",
) -> None:
    fake.tables["disputes"].rows.append(
        {
            "id": dispute_id,
            "order_id": order_id,
            "opener_user_id": CUSTOMER_ID,
            "status": status,
            "evidence_paths": [],
            "vendor_response": None,
            "admin_decision": None,
            "created_at": "2026-07-10T00:00:00Z",
            "updated_at": "2026-07-10T00:00:00Z",
        }
    )
    fake.tables["orders"].rows.append(
        {
            "id": order_id,
            "customer_id": CUSTOMER_ID,
            "vendor_id": VENDOR_A,
            "delivery_fee_ngwee": 0,
        }
    )
    fake.tables["order_items"].rows.append(
        {
            "order_id": order_id,
            "qty": 1,
            "unit_price_ngwee": GROSS_NGEWEE,
        }
    )


class TestHoldBeatsTimer:
    def test_under_review_in_open_dispute_statuses(self) -> None:
        from app.services.escrow.release import OPEN_DISPUTE_STATUSES

        assert "under_review" in OPEN_DISPUTE_STATUSES
        assert "open" in OPEN_DISPUTE_STATUSES
        assert "vendor_responded" in OPEN_DISPUTE_STATUSES
        assert "resolved_refund" not in OPEN_DISPUTE_STATUSES

    def test_open_dispute_beats_auto_release_timer_pure(self) -> None:
        from app.services.escrow.release import evaluate_release_rules

        now = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
        delivered_at = now - timedelta(hours=DEFAULT_RELEASE_AFTER_DELIVERED_HOURS + 1)
        outcome, reason, rule = evaluate_release_rules(
            status="delivered",
            cod=False,
            has_open_dispute=True,
            already_released=False,
            buyer_confirmed=False,
            delivered_at=delivered_at,
            shipped_at=delivered_at - timedelta(days=1),
            release_after_delivered_hours=DEFAULT_RELEASE_AFTER_DELIVERED_HOURS,
            release_after_shipped_days=7,
            now=now,
        )
        assert outcome == "held"
        assert reason == "dispute_open"
        assert rule is None

    def test_open_dispute_holds_past_auto_release_window(
        self, db: PgConn, db_url_env: None
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
        delivered_at = now - timedelta(hours=DEFAULT_RELEASE_AFTER_DELIVERED_HOURS + 1)

        _insert_order(db, order_id=order_id, group_id=group_id, status="delivered")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="shipped",
            to_status="delivered",
            actor=SYSTEM_ACTOR_ID,
            created_at=delivered_at,
        )
        _insert_dispute(db, order_id=order_id, status="open")

        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "held"
        assert result.reason == "dispute_open"

    def test_under_review_dispute_holds_past_auto_release_window(
        self, db: PgConn, db_url_env: None
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
        delivered_at = now - timedelta(hours=DEFAULT_RELEASE_AFTER_DELIVERED_HOURS + 1)

        _insert_order(db, order_id=order_id, group_id=group_id, status="delivered")
        _insert_order_event(
            db,
            order_id=order_id,
            from_status="shipped",
            to_status="delivered",
            actor=SYSTEM_ACTOR_ID,
            created_at=delivered_at,
        )
        _insert_dispute(db, order_id=order_id, status="under_review")

        result = evaluate_and_release(_SERVICE, order_id, now=now)
        assert result.outcome == "held"
        assert result.reason == "dispute_open"


class TestGuardedTransitions:
    def test_legal_vendor_respond_writes_audit(self) -> None:
        dispute_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())
        fake = FakeSupabaseClient()
        fake.tables["disputes"].rows.append(
            {
                "id": dispute_id,
                "order_id": order_id,
                "opener_user_id": CUSTOMER_ID,
                "status": "open",
            }
        )
        service = _FakeServiceWrapper(fake)

        outcome = transition_dispute(
            service,
            dispute_id=dispute_id,
            event=DisputeEvent.VENDOR_RESPOND,
            actor_role=ActorRole.VENDOR,
            actor_id=VENDOR_OWNER_ID,
            note="Vendor response submitted",
            extra_updates={"vendor_response": "Package was delivered"},
        )
        assert outcome.to_status == DisputeStatus.VENDOR_RESPONDED
        assert count_dispute_audit_events(service, dispute_id) >= 1

    def test_illegal_transition_rejected(self) -> None:
        dispute_id = str(uuid.uuid4())
        fake = FakeSupabaseClient()
        fake.tables["disputes"].rows.append(
            {
                "id": dispute_id,
                "order_id": str(uuid.uuid4()),
                "opener_user_id": CUSTOMER_ID,
                "status": "open",
            }
        )
        service = _FakeServiceWrapper(fake)

        with pytest.raises(DisputeTransitionError):
            transition_dispute(
                service,
                dispute_id=dispute_id,
                event=DisputeEvent.RESOLVE_REFUND,
                actor_role=ActorRole.ADMIN,
                actor_id=ADMIN_ID,
                note="Invalid direct resolve",
            )


class TestResolutionDispatch:
    @patch("app.services.disputes.service.evaluate_and_release")
    @patch("app.services.disputes.service.execute_refund")
    def test_resolved_refund_calls_m08_refund(
        self,
        mock_refund: MagicMock,
        mock_release: MagicMock,
    ) -> None:
        from app.services.disputes.service import resolve

        order_id = str(uuid.uuid4())
        dispute_id = str(uuid.uuid4())
        fake = FakeSupabaseClient()
        _seed_fake_dispute(fake, dispute_id=dispute_id, order_id=order_id)
        service = _FakeServiceWrapper(fake)
        mock_refund.return_value = MagicMock(refund_id=str(uuid.uuid4()))

        record = resolve(
            service,
            dispute_id=dispute_id,
            admin_user_id=ADMIN_ID,
            decision="resolved_refund",
            admin_decision="Full refund to customer",
            customer_momo=CUSTOMER_MOMO,
        )
        assert record.status == "resolved_refund"
        mock_refund.assert_called_once()
        mock_release.assert_not_called()

    @patch("app.services.disputes.service.evaluate_and_release")
    @patch("app.services.disputes.service.execute_refund")
    def test_resolved_release_calls_m08_release(
        self,
        mock_refund: MagicMock,
        mock_release: MagicMock,
    ) -> None:
        from app.services.disputes.service import resolve

        order_id = str(uuid.uuid4())
        dispute_id = str(uuid.uuid4())
        fake = FakeSupabaseClient()
        _seed_fake_dispute(fake, dispute_id=dispute_id, order_id=order_id)
        service = _FakeServiceWrapper(fake)

        record = resolve(
            service,
            dispute_id=dispute_id,
            admin_user_id=ADMIN_ID,
            decision="resolved_release",
            admin_decision="Release to vendor",
            customer_momo=CUSTOMER_MOMO,
        )
        assert record.status == "resolved_release"
        mock_release.assert_called_once_with(service, order_id)
        mock_refund.assert_not_called()

    # Patch the symbol as bound into disputes.service (it does
    # `from app.services.refunds.config import load_restocking_fee_bps`),
    # not the origin module — patching `refunds.config` here is a no-op.
    @patch("app.services.disputes.service.load_restocking_fee_bps", return_value=1000)
    @patch("app.services.disputes.service.evaluate_and_release")
    @patch("app.services.disputes.service.execute_refund")
    def test_resolved_partial_calls_both_m08_paths(
        self,
        mock_refund: MagicMock,
        mock_release: MagicMock,
        _mock_bps: MagicMock,
    ) -> None:
        from app.services.disputes.service import resolve
        from app.services.refunds.math import compute_lane2_refund

        order_id = str(uuid.uuid4())
        dispute_id = str(uuid.uuid4())
        fake = FakeSupabaseClient()
        _seed_fake_dispute(fake, dispute_id=dispute_id, order_id=order_id)
        service = _FakeServiceWrapper(fake)
        mock_refund.return_value = MagicMock(refund_id=str(uuid.uuid4()))

        partial = 50_000
        record = resolve(
            service,
            dispute_id=dispute_id,
            admin_user_id=ADMIN_ID,
            decision="resolved_partial",
            admin_decision="Partial refund + release remainder",
            customer_momo=CUSTOMER_MOMO,
            partial_refund_ngwee=partial,
        )
        assert record.status == "resolved_partial"
        mock_release.assert_called_once_with(service, order_id)

        # Core invariant of this pebble: the executed lane-2 refund must equal
        # the admin-decided partial amount exactly. `execute_refund` is mocked,
        # so assert on the args and re-derive the amount via the real lane-2
        # formula from the back-solved return_transport it was handed.
        mock_refund.assert_called_once()
        kwargs = mock_refund.call_args.kwargs
        assert kwargs["lane"] == 2
        # item=200_000, delivery=0, restocking 10%=20_000 → return_transport=130_000
        assert kwargs["return_transport_ngwee"] == 130_000
        rederived = compute_lane2_refund(
            item_ngwee=GROSS_NGEWEE,
            outbound_delivery_ngwee=0,
            return_transport_ngwee=kwargs["return_transport_ngwee"],
            restocking_fee_bps=1000,
        )
        assert rederived.refund_ngwee == partial


class TestRlsIsolation:
    def test_other_customer_cannot_read_dispute(
        self, db: PgConn, role_factory: Callable[[Persona], RoleSession]
    ) -> None:
        order_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        dispute_id = str(uuid.uuid4())
        _insert_order(db, order_id=order_id, group_id=group_id, customer_id=CUSTOMER_ID)
        _insert_dispute(db, order_id=order_id, dispute_id=dispute_id)

        session = role_factory(Persona.OTHER_CUSTOMER)
        result = session.execute(
            f"SELECT count(*)::text FROM public.disputes WHERE id = '{dispute_id}';"
        )
        assert result.ok and result.rows
        assert result.rows[0] == "0"

    def test_cross_order_dispute_not_visible_to_customer(
        self, db: PgConn, role_factory: Callable[[Persona], RoleSession]
    ) -> None:
        order_b = str(uuid.uuid4())
        group_b = str(uuid.uuid4())
        dispute_b = str(uuid.uuid4())
        _insert_order(db, order_id=order_b, group_id=group_b, customer_id=OTHER_CUSTOMER_ID)
        _insert_dispute(db, order_id=order_b, dispute_id=dispute_b)

        session = role_factory(Persona.CUSTOMER)
        result = session.execute(
            f"SELECT count(*)::text FROM public.disputes WHERE id = '{dispute_b}';"
        )
        assert result.ok and result.rows
        assert result.rows[0] == "0"


class TestReportProblemOpenDisputePath:
    @patch("app.services.disputes.service.open_dispute")
    def test_not_delivered_routes_through_open_dispute(self, mock_open: MagicMock) -> None:
        from app.routers.order_confirmation import _create_dispute
        from app.services.disputes.service import OpenDisputeResult

        order_id = str(uuid.uuid4())
        fake = MagicMock()
        mock_open.return_value = OpenDisputeResult(
            dispute_id="dispute-123",
            order_id=order_id,
            status="open",
            created=True,
        )

        dispute_id = _create_dispute(
            fake,
            order_id=order_id,
            customer_id=CUSTOMER_ID,
            evidence_paths=["orders/x/y/evidence.jpg"],
        )
        assert dispute_id == "dispute-123"
        mock_open.assert_called_once()


class TestMigrationReplayNote:
    def test_0019_widens_status_check(self, db: PgConn) -> None:
        """Migration 0019 replay: under_review + resolved_partial allowed by CHECK."""
        result = db.run(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = 'disputes_status_check'
              AND conrelid = 'public.disputes'::regclass;
            """
        )
        assert result.ok and result.rows
        definition = result.rows[0]
        assert "under_review" in definition
        assert "resolved_partial" in definition
        assert "'open'" in definition
