"""Event escrow release timing (M10-P08) — timing matrix, cancel/dispute holds,
idempotency-key distinctness, and organiser dashboard-lite stats aggregation.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from app.services.escrow.event_release import (
    PHASE1_LEAD_DAYS,
    PHASED_THRESHOLD_DAYS,
    determine_branch,
    evaluate_event_release,
    full_release_key,
    phase1_release_key,
    phase2_release_key,
    sweep_event_releases,
)
from app.services.escrow.release import release_idempotency_key
from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate, commission_ngwee_from_bps
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

# Fixture ids from tests/fixtures/demo/ids.json (seeded by seed_matrix_fixtures).
CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_A_OWNER_ID = "33333333-3333-3333-3333-333333333333"
VENDOR_B_OWNER_ID = "44444444-4444-4444-4444-444444444444"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

PLATFORM_CASH_ID = "ea000000-0000-0000-0000-000000000001"
ESCROW_ID = "ea000000-0000-0000-0000-000000000002"
COMMISSION_ID = "ea000000-0000-0000-0000-000000000003"
VENDOR_PAYABLE_ID = "ea000000-0000-0000-0000-000000000005"

UNIT_PRICE_NGWEE = 100_000
COMMISSION_BPS = 500
COMMISSION_NGEWEE = commission_ngwee_from_bps(
    gross_ngwee=UNIT_PRICE_NGWEE, commission_bps=COMMISSION_BPS
)
NET_NGEWEE = UNIT_PRICE_NGWEE - COMMISSION_NGEWEE


class _ServiceWrapper:
    client: Any = None


_SERVICE = _ServiceWrapper()


def _commission_snapshot(*, ticket_type_id: str, instance_id: str) -> dict[str, Any]:
    return {
        "lines": [
            {
                "ticket_type_id": ticket_type_id,
                "instance_id": instance_id,
                "category_key": "event_tickets",
                "rate_bps": COMMISSION_BPS,
                "qty": 1,
                "unit_price_ngwee": UNIT_PRICE_NGWEE,
                "line_total_ngwee": UNIT_PRICE_NGWEE,
                "title_snapshot": "GA",
            }
        ],
        "rate_bps": COMMISSION_BPS,
        "category_key": "event_tickets",
    }


def seed_ledger_accounts(conn: PgConn) -> None:
    # Conflict targets match the partial unique indexes in 0006_money.sql (one
    # platform-kind row per kind; one vendor_payable row per vendor) rather than
    # the id primary key, since another test module may already have created
    # these accounts with different fixed ids in the same shared local DB.
    script = f"""
BEGIN;
SET LOCAL role service_role;
INSERT INTO public.ledger_accounts (id, kind) VALUES
  ('{PLATFORM_CASH_ID}', 'platform_cash'),
  ('{ESCROW_ID}', 'escrow'),
  ('{COMMISSION_ID}', 'commission_revenue')
ON CONFLICT (kind) WHERE vendor_id IS NULL DO NOTHING;
INSERT INTO public.ledger_accounts (id, kind, vendor_id) VALUES
  ('{VENDOR_PAYABLE_ID}', 'vendor_payable', '{VENDOR_A}')
ON CONFLICT (kind, vendor_id) WHERE vendor_id IS NOT NULL DO NOTHING;
COMMIT;
"""
    result = conn.run_script(script)
    if not result.ok:
        raise RuntimeError(f"ledger account seed failed: {result.error}")


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
        seed_matrix_fixtures(conn)
    seed_ledger_accounts(conn)
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


def _insert_event(
    conn: PgConn, *, event_id: str, organiser_vendor_id: str, status: str = "published"
) -> None:
    slug = f"evt-{event_id[:8]}"
    conn.run(
        f"""
        INSERT INTO public.events (id, organiser_vendor_id, title, slug, status)
        VALUES ('{event_id}', '{organiser_vendor_id}', 'Test Event', '{slug}', '{status}')
        ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;
        """
    )


def _insert_instance(
    conn: PgConn, *, instance_id: str, event_id: str, starts_at: datetime, capacity: int = 100
) -> None:
    ts = starts_at.astimezone(UTC).isoformat()
    conn.run(
        f"""
        INSERT INTO public.event_instances (id, event_id, starts_at, capacity)
        VALUES ('{instance_id}', '{event_id}', '{ts}'::timestamptz, {capacity})
        ON CONFLICT (id) DO UPDATE SET starts_at = EXCLUDED.starts_at;
        """
    )


def _insert_ticket_type(
    conn: PgConn,
    *,
    type_id: str,
    event_id: str,
    kind: str = "fixed",
    name: str = "GA",
    price_ngwee: int = UNIT_PRICE_NGWEE,
) -> None:
    conn.run(
        f"""
        INSERT INTO public.ticket_types (id, event_id, kind, name, price_ngwee)
        VALUES ('{type_id}', '{event_id}', '{kind}', '{name}', {price_ngwee})
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _insert_ticket_order(
    conn: PgConn,
    *,
    order_id: str,
    group_id: str,
    item_id: str,
    instance_id: str,
    ticket_type_id: str,
    vendor_id: str = VENDOR_A,
    customer_id: str = CUSTOMER_ID,
    unit_price_ngwee: int = UNIT_PRICE_NGWEE,
    created_at: datetime,
    paid: bool = True,
) -> None:
    snapshot = _commission_snapshot(ticket_type_id=ticket_type_id, instance_id=instance_id)
    snapshot_sql = json.dumps(snapshot).replace("'", "''")
    created_sql = created_at.astimezone(UTC).isoformat()
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee,
          total_ngwee, status
        ) VALUES (
          '{group_id}', '{customer_id}', 'cg-{group_id}', {unit_price_ngwee}, 0,
          {unit_price_ngwee}, 'completed'
        ) ON CONFLICT (id) DO NOTHING;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
          delivery_fee_ngwee, cod, commission_snapshot, created_at
        ) VALUES (
          '{order_id}', '{group_id}', '{vendor_id}', '{customer_id}', 'placed', 'pickup',
          0, false, '{snapshot_sql}'::jsonb, '{created_sql}'::timestamptz
        ) ON CONFLICT (id) DO UPDATE
          SET commission_snapshot = EXCLUDED.commission_snapshot,
              created_at = EXCLUDED.created_at;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.order_items (
          id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES (
          '{item_id}', '{order_id}', 'ticket', 1, {unit_price_ngwee}, 'GA'
        ) ON CONFLICT (id) DO NOTHING;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.order_item_tickets (order_item_id, ticket_type_id, instance_id)
        VALUES ('{item_id}', '{ticket_type_id}', '{instance_id}')
        ON CONFLICT (order_item_id) DO NOTHING;
        """
    )
    if paid:
        ref = f"tkt-{order_id[:8]}-{uuid.uuid4().hex[:6]}"
        conn.run(
            f"""
            INSERT INTO public.payments (
              id, checkout_group_id, provider, rail, lenco_reference, amount_ngwee, status
            ) VALUES (
              gen_random_uuid(), '{group_id}', 'lenco', 'mtn', '{ref}',
              {unit_price_ngwee}, 'success'
            ) ON CONFLICT (lenco_reference) DO NOTHING;
            """
        )


def _insert_ticket(
    conn: PgConn,
    *,
    ticket_id: str,
    instance_id: str,
    ticket_type_id: str,
    order_item_id: str,
    holder_user_id: str = CUSTOMER_ID,
    status: str = "issued",
) -> None:
    checked_in_sql = "timezone('utc', now())" if status == "checked_in" else "NULL"
    conn.run(
        f"""
        INSERT INTO public.tickets (
          id, instance_id, ticket_type_id, holder_user_id, order_item_id, status, checked_in_at
        ) VALUES (
          '{ticket_id}', '{instance_id}', '{ticket_type_id}', '{holder_user_id}',
          '{order_item_id}', '{status}', {checked_in_sql}
        )
        ON CONFLICT (id) DO UPDATE
          SET status = EXCLUDED.status, checked_in_at = EXCLUDED.checked_in_at;
        """
    )


def _insert_dispute(conn: PgConn, *, order_id: str, status: str = "open") -> None:
    conn.run(
        f"""
        INSERT INTO public.disputes (id, order_id, opener_user_id, status)
        VALUES ('{uuid.uuid4()}', '{order_id}', '{CUSTOMER_ID}', '{status}');
        """
    )


def _txn_count(conn: PgConn, key: str) -> int:
    result = conn.run(
        f"SELECT count(*)::text FROM public.ledger_transactions WHERE idempotency_key = '{key}';"
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _audit_flag_count(conn: PgConn, order_id: str) -> int:
    result = conn.run(
        f"""
        SELECT count(*)::text FROM public.audit_log
        WHERE entity_type = 'order' AND entity_id = '{order_id}'
          AND action = 'event_release.mass_refund_flagged';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


class TestBranchDecision:
    def test_full_branch_within_14_days(self) -> None:
        purchased = datetime(2026, 7, 1, tzinfo=UTC)
        starts = purchased + timedelta(days=PHASED_THRESHOLD_DAYS - 1)
        assert determine_branch(purchased_at=purchased, starts_at=starts) == "full"

    def test_full_branch_at_exactly_14_days(self) -> None:
        purchased = datetime(2026, 7, 1, tzinfo=UTC)
        starts = purchased + timedelta(days=PHASED_THRESHOLD_DAYS)
        assert determine_branch(purchased_at=purchased, starts_at=starts) == "full"

    def test_phased_branch_beyond_14_days(self) -> None:
        purchased = datetime(2026, 7, 1, tzinfo=UTC)
        starts = purchased + timedelta(days=PHASED_THRESHOLD_DAYS + 1)
        assert determine_branch(purchased_at=purchased, starts_at=starts) == "phased"


class TestIdempotencyKeyDistinctness:
    def test_event_keys_never_collide_with_order_engine_key(self) -> None:
        order_id = str(uuid.uuid4())
        order_release_key = release_idempotency_key(order_id)
        assert full_release_key(order_id) != order_release_key
        assert phase1_release_key(order_id) != order_release_key
        assert phase2_release_key(order_id) != order_release_key
        # And the three event-release keys are mutually distinct too.
        keys = {
            full_release_key(order_id),
            phase1_release_key(order_id),
            phase2_release_key(order_id),
            order_release_key,
        }
        assert len(keys) == 4


class TestFullReleaseBranch:
    def test_full_release_at_t_plus_24h_not_before(
        self, db: PgConn, db_url_env: None
    ) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        type_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())
        starts_at = datetime(2026, 8, 1, 18, 0, tzinfo=UTC)
        purchased_at = starts_at - timedelta(days=13)  # <=14d -> full branch

        _insert_event(db, event_id=event_id, organiser_vendor_id=VENDOR_A)
        _insert_instance(db, instance_id=instance_id, event_id=event_id, starts_at=starts_at)
        _insert_ticket_type(db, type_id=type_id, event_id=event_id)
        _insert_ticket_order(
            db,
            order_id=order_id,
            group_id=str(uuid.uuid4()),
            item_id=str(uuid.uuid4()),
            instance_id=instance_id,
            ticket_type_id=type_id,
            created_at=purchased_at,
        )

        too_early = evaluate_event_release(_SERVICE, order_id, now=starts_at)
        assert too_early.outcome == "not_eligible"
        assert too_early.reason == "timers_not_met"
        assert _txn_count(db, full_release_key(order_id)) == 0

        due = starts_at + timedelta(hours=24)
        result = evaluate_event_release(_SERVICE, order_id, now=due)
        assert result.outcome == "released"
        assert result.branch == "full"
        assert result.phases_posted == ("full",)
        assert result.net_ngwee == NET_NGEWEE
        assert _txn_count(db, full_release_key(order_id)) == 1

        again = evaluate_event_release(_SERVICE, order_id, now=due + timedelta(days=1))
        assert again.outcome == "already_released"
        assert _txn_count(db, full_release_key(order_id)) == 1


class TestPhasedReleaseBranch:
    def test_phase1_then_phase2_sum_to_net_exactly(
        self, db: PgConn, db_url_env: None
    ) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        type_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())
        starts_at = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
        purchased_at = starts_at - timedelta(days=20)  # >14d -> phased branch

        _insert_event(db, event_id=event_id, organiser_vendor_id=VENDOR_A)
        _insert_instance(db, instance_id=instance_id, event_id=event_id, starts_at=starts_at)
        _insert_ticket_type(db, type_id=type_id, event_id=event_id)
        _insert_ticket_order(
            db,
            order_id=order_id,
            group_id=str(uuid.uuid4()),
            item_id=str(uuid.uuid4()),
            instance_id=instance_id,
            ticket_type_id=type_id,
            created_at=purchased_at,
        )

        phase1_due = starts_at - timedelta(days=PHASE1_LEAD_DAYS)
        phase1_result = evaluate_event_release(_SERVICE, order_id, now=phase1_due)
        assert phase1_result.outcome == "released"
        assert phase1_result.branch == "phased"
        assert phase1_result.phases_posted == ("phase1",)
        phase1_amount = phase1_result.net_ngwee
        assert phase1_amount == NET_NGEWEE // 2

        mid = evaluate_event_release(_SERVICE, order_id, now=starts_at - timedelta(days=1))
        assert mid.outcome == "not_eligible"
        assert mid.reason == "timers_not_met"

        phase2_due = starts_at + timedelta(days=1)
        phase2_result = evaluate_event_release(_SERVICE, order_id, now=phase2_due)
        assert phase2_result.outcome == "released"
        assert phase2_result.phases_posted == ("phase2",)
        phase2_amount = phase2_result.net_ngwee

        assert phase1_amount + phase2_amount == NET_NGEWEE
        assert _txn_count(db, phase1_release_key(order_id)) == 1
        assert _txn_count(db, phase2_release_key(order_id)) == 1

        already = evaluate_event_release(_SERVICE, order_id, now=phase2_due + timedelta(days=1))
        assert already.outcome == "already_released"


class TestCancellationHold:
    def test_cancelled_event_blocks_release_and_flags_once(
        self, db: PgConn, db_url_env: None
    ) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        type_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())
        starts_at = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
        purchased_at = starts_at - timedelta(days=5)

        _insert_event(
            db, event_id=event_id, organiser_vendor_id=VENDOR_A, status="cancelled"
        )
        _insert_instance(db, instance_id=instance_id, event_id=event_id, starts_at=starts_at)
        _insert_ticket_type(db, type_id=type_id, event_id=event_id)
        _insert_ticket_order(
            db,
            order_id=order_id,
            group_id=str(uuid.uuid4()),
            item_id=str(uuid.uuid4()),
            instance_id=instance_id,
            ticket_type_id=type_id,
            created_at=purchased_at,
        )

        far_future = starts_at + timedelta(days=30)
        result = evaluate_event_release(_SERVICE, order_id, now=far_future)
        assert result.outcome == "blocked_cancelled"
        assert result.reason == "event_cancelled"
        assert _txn_count(db, full_release_key(order_id)) == 0
        assert _audit_flag_count(db, order_id) == 1

        # Re-run does not double-flag or release.
        again = evaluate_event_release(_SERVICE, order_id, now=far_future)
        assert again.outcome == "blocked_cancelled"
        assert _audit_flag_count(db, order_id) == 1
        assert _txn_count(db, full_release_key(order_id)) == 0


class TestDisputeHold:
    def test_open_dispute_holds_before_release(self, db: PgConn, db_url_env: None) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        type_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())
        starts_at = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
        purchased_at = starts_at - timedelta(days=5)

        _insert_event(db, event_id=event_id, organiser_vendor_id=VENDOR_A)
        _insert_instance(db, instance_id=instance_id, event_id=event_id, starts_at=starts_at)
        _insert_ticket_type(db, type_id=type_id, event_id=event_id)
        _insert_ticket_order(
            db,
            order_id=order_id,
            group_id=str(uuid.uuid4()),
            item_id=str(uuid.uuid4()),
            instance_id=instance_id,
            ticket_type_id=type_id,
            created_at=purchased_at,
        )
        _insert_dispute(db, order_id=order_id, status="open")

        due = starts_at + timedelta(hours=24)
        result = evaluate_event_release(_SERVICE, order_id, now=due)
        assert result.outcome == "held"
        assert result.reason == "dispute_open"
        assert _txn_count(db, full_release_key(order_id)) == 0


class TestUnpaidAndNonTicketOrders:
    def test_unpaid_ticket_order_not_eligible(self, db: PgConn, db_url_env: None) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        type_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())
        starts_at = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)
        purchased_at = starts_at - timedelta(days=5)

        _insert_event(db, event_id=event_id, organiser_vendor_id=VENDOR_A)
        _insert_instance(db, instance_id=instance_id, event_id=event_id, starts_at=starts_at)
        _insert_ticket_type(db, type_id=type_id, event_id=event_id)
        _insert_ticket_order(
            db,
            order_id=order_id,
            group_id=str(uuid.uuid4()),
            item_id=str(uuid.uuid4()),
            instance_id=instance_id,
            ticket_type_id=type_id,
            created_at=purchased_at,
            paid=False,
        )

        due = starts_at + timedelta(hours=24)
        result = evaluate_event_release(_SERVICE, order_id, now=due)
        assert result.outcome == "not_eligible"
        assert result.reason == "unpaid"

    def test_unknown_order_not_eligible(self, db: PgConn, db_url_env: None) -> None:
        result = evaluate_event_release(_SERVICE, str(uuid.uuid4()), now=datetime.now(UTC))
        assert result.outcome == "not_eligible"
        assert result.reason == "not_ticket_order"


class TestSweepEventReleases:
    def test_sweep_counts_released_and_not_eligible(
        self, db: PgConn, db_url_env: None
    ) -> None:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        type_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())
        starts_at = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
        purchased_at = starts_at - timedelta(days=10)

        _insert_event(db, event_id=event_id, organiser_vendor_id=VENDOR_A)
        _insert_instance(db, instance_id=instance_id, event_id=event_id, starts_at=starts_at)
        _insert_ticket_type(db, type_id=type_id, event_id=event_id)
        _insert_ticket_order(
            db,
            order_id=order_id,
            group_id=str(uuid.uuid4()),
            item_id=str(uuid.uuid4()),
            instance_id=instance_id,
            ticket_type_id=type_id,
            created_at=purchased_at,
        )

        due = starts_at + timedelta(hours=24)
        sweep_result, _next_cursor = sweep_event_releases(_SERVICE, now=due)
        assert sweep_result.released >= 1
        assert _txn_count(db, full_release_key(order_id)) == 1


class TestOrganiserStats:
    def test_sales_checkin_and_escrow_split(self, db: PgConn, db_url_env: None) -> None:
        from app.routers.organiser_stats import (
            EscrowSplit,
            _load_escrow_split,
            _load_sales_by_type,
            _mass_refund_flagged,
        )

        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        type_id = str(uuid.uuid4())
        starts_at = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
        purchased_at = starts_at - timedelta(days=13)  # full branch

        _insert_event(db, event_id=event_id, organiser_vendor_id=VENDOR_A)
        _insert_instance(db, instance_id=instance_id, event_id=event_id, starts_at=starts_at)
        _insert_ticket_type(db, type_id=type_id, event_id=event_id, name="GA")

        order_ids = [str(uuid.uuid4()) for _ in range(3)]
        item_ids = [str(uuid.uuid4()) for _ in range(3)]
        for order_id, item_id in zip(order_ids, item_ids, strict=True):
            _insert_ticket_order(
                db,
                order_id=order_id,
                group_id=str(uuid.uuid4()),
                item_id=item_id,
                instance_id=instance_id,
                ticket_type_id=type_id,
                created_at=purchased_at,
            )
            # Simulate the per-order escrow hold a payment-success handler would post
            # (no such handler is wired yet in the codebase as of this pebble — see report).
            post_transaction(
                idempotency_key=f"escrow-hold-{order_id}",
                template=LedgerTemplate.ESCROW_HOLD,
                order_id=order_id,
                order_amount_ngwee=UNIT_PRICE_NGWEE,
            )

        statuses = ["checked_in", "issued", "checked_in"]
        for _order_id, item_id, status in zip(order_ids, item_ids, statuses, strict=True):
            _insert_ticket(
                db,
                ticket_id=str(uuid.uuid4()),
                instance_id=instance_id,
                ticket_type_id=type_id,
                order_item_id=item_id,
                status=status,
            )

        sales = _load_sales_by_type(event_id)
        assert len(sales) == 1
        assert sales[0].sold == 3
        assert sales[0].checked_in == 2
        assert sales[0].revenue_ngwee == UNIT_PRICE_NGWEE * 3

        # Release only the first order in full.
        release_result = evaluate_event_release(
            _SERVICE, order_ids[0], now=starts_at + timedelta(hours=24)
        )
        assert release_result.outcome == "released"

        escrow = _load_escrow_split(event_id)
        expected_pending = COMMISSION_NGEWEE + 2 * UNIT_PRICE_NGWEE
        expected_released = NET_NGEWEE
        assert escrow == EscrowSplit(
            pending_ngwee=expected_pending, released_ngwee=expected_released
        )
        assert _mass_refund_flagged(event_id) is False


class TestOrganiserStatsAuthz:
    def test_cross_organiser_forbidden(
        self, db: PgConn, db_url_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.main import create_app

        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        starts_at = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
        # Event belongs to vendor B (shop_b); vendor A must not be able to read its stats.
        _insert_event(db, event_id=event_id, organiser_vendor_id=VENDOR_B)
        _insert_instance(db, instance_id=instance_id, event_id=event_id, starts_at=starts_at)

        def verify(token: str, settings: Any) -> dict[str, Any]:
            _ = settings
            if token == "vendor-a-token":
                return {"sub": VENDOR_A_OWNER_ID, "exp": 9_999_999_999}
            if token == "vendor-b-token":
                return {"sub": VENDOR_B_OWNER_ID, "exp": 9_999_999_999}
            raise ValueError("invalid token")

        def roles(user_id: str, service_client: Any) -> frozenset[str]:
            _ = user_id, service_client
            return frozenset({"vendor"})

        monkeypatch.setattr("app.core.auth.verify_supabase_jwt", verify)
        monkeypatch.setattr("app.core.auth._load_user_roles", roles)

        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            forbidden = client.get(
                f"/organiser/events/{event_id}/stats",
                headers={"Authorization": "Bearer vendor-a-token"},
            )
            assert forbidden.status_code == 403

            not_found = client.get(
                f"/organiser/events/{uuid.uuid4()}/stats",
                headers={"Authorization": "Bearer vendor-a-token"},
            )
            assert not_found.status_code == 404

            owner_ok = client.get(
                f"/organiser/events/{event_id}/stats",
                headers={"Authorization": "Bearer vendor-b-token"},
            )
            assert owner_ok.status_code == 200

    def test_tick_requires_internal_token(self) -> None:
        from app.main import create_app
        from app.services.escrow.event_release import EventReleaseSweepResult

        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            denied = client.post("/internal/event-release/tick")
            assert denied.status_code == 401

            with patch(
                "app.routers.internal_event_release.sweep_event_releases",
                return_value=(
                    EventReleaseSweepResult(
                        scanned=2,
                        released=1,
                        held=0,
                        already_released=1,
                        not_eligible=0,
                        blocked_cancelled=0,
                    ),
                    None,
                ),
            ):
                ok = client.post(
                    "/internal/event-release/tick",
                    headers={"X-Internal-Token": "dev-internal-event-release"},
                )
            assert ok.status_code == 200
            assert ok.json() == {
                "scanned": 2,
                "released": 1,
                "held": 0,
                "already_released": 1,
                "not_eligible": 0,
                "blocked_cancelled": 0,
                "next_cursor": None,
            }
