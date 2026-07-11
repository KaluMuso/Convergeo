"""M11-P05 job completion — provider complete → confirm → single escrow release.

MONEY-CRITICAL. Isolation-clean: unique UUIDs per test; the release ledger post is
asserted as an exactly-once count keyed by ``release-{order_id}``; the auto-confirm
window is exercised with deterministic ``now`` offsets from the recorded marker.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import timedelta
from typing import Any

import pytest
from app.errors import AppError
from app.routers.job_completion import (
    PROVIDER_COMPLETE_ACTION,
    auto_confirm_due_jobs,
    confirm_job_completion,
    job_review_unlocked,
    mark_job_complete,
)
from app.routers.reviews import REVIEWABLE_ORDER_STATUSES
from app.services.escrow.release import release_idempotency_key
from app.services.rfq.engagement import accept_quote
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
OTHER_CUSTOMER = "22222222-2222-2222-2222-222222222222"
STRANGER = "33333333-3333-3333-3333-333333333333"

PLATFORM_CASH_ID = "c1000000-0000-0000-0000-000000000001"
ESCROW_ID = "c2000000-0000-0000-0000-000000000002"
COMMISSION_ID = "c3000000-0000-0000-0000-000000000003"


class _ServiceWrapper:
    client: Any = None


_SERVICE = _ServiceWrapper()


def _seed_platform_accounts(conn: PgConn) -> None:
    conn.run(
        f"""
        INSERT INTO public.ledger_accounts (id, kind) VALUES
          ('{PLATFORM_CASH_ID}', 'platform_cash'),
          ('{ESCROW_ID}', 'escrow'),
          ('{COMMISSION_ID}', 'commission_revenue')
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _seed_vendor_payable(conn: PgConn, vendor_id: str) -> None:
    conn.run(
        f"""
        INSERT INTO public.ledger_accounts (id, kind, vendor_id)
        SELECT gen_random_uuid(), 'vendor_payable', '{vendor_id}'
        WHERE NOT EXISTS (
          SELECT 1 FROM public.ledger_accounts
          WHERE kind = 'vendor_payable' AND vendor_id = '{vendor_id}'
        );
        """
    )


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
    _seed_platform_accounts(conn)
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


# ---------------------------------------------------------------------------
# Seed / query helpers
# ---------------------------------------------------------------------------


def _any_vendor_id(conn: PgConn) -> str:
    result = conn.run("SELECT id::text FROM public.vendors LIMIT 1")
    assert result.ok and result.rows, "matrix seed must provide a vendor"
    return result.rows[0]


def _vendor_owner(conn: PgConn, vendor_id: str) -> str:
    result = conn.run(
        f"SELECT owner_user_id::text FROM public.vendors WHERE id = '{vendor_id}'"
    )
    assert result.ok and result.rows
    return result.rows[0]


def _seed_job(conn: PgConn, *, job_id: str, customer_id: str, status: str = "quoted") -> None:
    conn.run(
        f"""
        INSERT INTO public.jobs (id, customer_id, category, description, status)
        VALUES ('{job_id}', '{customer_id}', 'home_services', 'Fix a tap', '{status}')
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _seed_quote(
    conn: PgConn, *, quote_id: str, job_id: str, vendor_id: str, amount_ngwee: int
) -> None:
    conn.run(
        f"""
        INSERT INTO public.job_quotes (id, job_id, provider_vendor_id, amount_ngwee, status)
        VALUES ('{quote_id}', '{job_id}', '{vendor_id}', {amount_ngwee}, 'submitted')
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _accept(conn: PgConn, *, customer_id: str = CUSTOMER_A, total: int = 250_000) -> Any:
    job_id = str(uuid.uuid4())
    quote_id = str(uuid.uuid4())
    vendor_id = _any_vendor_id(conn)
    _seed_vendor_payable(conn, vendor_id)
    _seed_job(conn, job_id=job_id, customer_id=customer_id)
    _seed_quote(conn, quote_id=quote_id, job_id=job_id, vendor_id=vendor_id, amount_ngwee=total)
    return accept_quote(_SERVICE, job_id=job_id, quote_id=quote_id, customer_id=customer_id)


def _order_status(conn: PgConn, order_id: str) -> str:
    result = conn.run(f"SELECT status FROM public.orders WHERE id = '{order_id}'")
    assert result.ok and result.rows
    return result.rows[0]


def _release_count(conn: PgConn, order_id: str) -> int:
    key = release_idempotency_key(order_id)
    result = conn.run(
        f"SELECT count(*)::text FROM public.ledger_transactions "
        f"WHERE idempotency_key = '{key}';"
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _balance_item_count(conn: PgConn, order_id: str) -> int:
    result = conn.run(
        f"SELECT count(*)::text FROM public.order_items "
        f"WHERE order_id = '{order_id}' AND item_kind = 'service_balance';"
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _marker_at(conn: PgConn, job_id: str) -> Any:
    from datetime import datetime

    result = conn.run(
        f"SELECT min(at)::text FROM public.audit_log "
        f"WHERE entity_type = 'job' AND entity_id = '{job_id}' "
        f"AND action = '{PROVIDER_COMPLETE_ACTION}';"
    )
    assert result.ok and result.rows and result.rows[0]
    raw = result.rows[0].strip().replace(" ", "T", 1).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(raw)
    from datetime import UTC

    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Double-confirm idempotency + single release + balance-leg-once
# ---------------------------------------------------------------------------


class TestDoubleConfirmIdempotency:
    def test_confirm_releases_once_and_double_confirm_is_noop(
        self, db: PgConn, db_url_env: None
    ) -> None:
        accepted = _accept(db, total=250_000)
        provider = _vendor_owner(db, accepted.vendor_id)
        # find the job id via the order's service link
        job_row = db.run(
            f"SELECT ois.job_id::text FROM public.order_item_services ois "
            f"JOIN public.order_items oi ON oi.id = ois.order_item_id "
            f"WHERE oi.order_id = '{accepted.order_id}' AND oi.item_kind = 'service_deposit';"
        )
        job_id = job_row.rows[0]

        mark = mark_job_complete(job_id, provider)
        assert mark.marked is True
        assert mark.order_id == accepted.order_id

        first = confirm_job_completion(job_id, actor_id=CUSTOMER_A)
        assert first.already_confirmed is False
        assert first.released is True
        assert first.release_created is True
        assert first.balance_created is True
        assert first.balance_ngwee == accepted.balance_ngwee
        # Vendor net == total − 12% commission (single snapshot), integer-exact.
        assert first.net_ngwee == accepted.total_job_ngwee - accepted.commission_ngwee

        # Order completed; exactly one balance leg and one release posting.
        assert _order_status(db, accepted.order_id) == "completed"
        assert _balance_item_count(db, accepted.order_id) == 1
        assert _release_count(db, accepted.order_id) == 1

        # Second confirm is an idempotent no-op — no second release, no second balance leg.
        second = confirm_job_completion(job_id, actor_id=CUSTOMER_A)
        assert second.already_confirmed is True
        assert second.released is False
        assert _balance_item_count(db, accepted.order_id) == 1
        assert _release_count(db, accepted.order_id) == 1

    def test_confirm_before_mark_complete_rejected(
        self, db: PgConn, db_url_env: None
    ) -> None:
        accepted = _accept(db)
        job_row = db.run(
            f"SELECT ois.job_id::text FROM public.order_item_services ois "
            f"JOIN public.order_items oi ON oi.id = ois.order_item_id "
            f"WHERE oi.order_id = '{accepted.order_id}' AND oi.item_kind = 'service_deposit';"
        )
        job_id = job_row.rows[0]

        with pytest.raises(AppError) as exc:
            confirm_job_completion(job_id, actor_id=CUSTOMER_A)
        assert exc.value.http_status == 409
        # No side effects: order still placed, no release.
        assert _order_status(db, accepted.order_id) == "placed"
        assert _release_count(db, accepted.order_id) == 0

    def test_non_owner_cannot_confirm(self, db: PgConn, db_url_env: None) -> None:
        accepted = _accept(db)
        provider = _vendor_owner(db, accepted.vendor_id)
        job_row = db.run(
            f"SELECT ois.job_id::text FROM public.order_item_services ois "
            f"JOIN public.order_items oi ON oi.id = ois.order_item_id "
            f"WHERE oi.order_id = '{accepted.order_id}' AND oi.item_kind = 'service_deposit';"
        )
        job_id = job_row.rows[0]
        mark_job_complete(job_id, provider)

        with pytest.raises(AppError) as exc:
            confirm_job_completion(job_id, actor_id=OTHER_CUSTOMER)
        assert exc.value.http_status == 403
        assert _release_count(db, accepted.order_id) == 0

    def test_non_provider_cannot_mark_complete(self, db: PgConn, db_url_env: None) -> None:
        accepted = _accept(db)
        job_row = db.run(
            f"SELECT ois.job_id::text FROM public.order_item_services ois "
            f"JOIN public.order_items oi ON oi.id = ois.order_item_id "
            f"WHERE oi.order_id = '{accepted.order_id}' AND oi.item_kind = 'service_deposit';"
        )
        job_id = job_row.rows[0]

        with pytest.raises(AppError) as exc:
            mark_job_complete(job_id, STRANGER)
        assert exc.value.http_status == 403


# ---------------------------------------------------------------------------
# Auto-confirm honors the window
# ---------------------------------------------------------------------------


class TestAutoConfirmWindow:
    def test_before_window_holds_after_window_releases_once(
        self, db: PgConn, db_url_env: None
    ) -> None:
        accepted = _accept(db, total=300_000)
        provider = _vendor_owner(db, accepted.vendor_id)
        job_row = db.run(
            f"SELECT ois.job_id::text FROM public.order_item_services ois "
            f"JOIN public.order_items oi ON oi.id = ois.order_item_id "
            f"WHERE oi.order_id = '{accepted.order_id}' AND oi.item_kind = 'service_deposit';"
        )
        job_id = job_row.rows[0]
        mark_job_complete(job_id, provider)
        marked_at = _marker_at(db, job_id)

        # 47h after the marker — inside the 48h window → THIS order is held, no release.
        # (Assertions are order-scoped: the module DB is shared across sibling tests.)
        auto_confirm_due_jobs(now=marked_at + timedelta(hours=47))
        assert _order_status(db, accepted.order_id) == "placed"
        assert _release_count(db, accepted.order_id) == 0

        # 49h after the marker — window elapsed → THIS order auto-confirms + releases once.
        after = auto_confirm_due_jobs(now=marked_at + timedelta(hours=49))
        assert after.confirmed >= 1
        assert _order_status(db, accepted.order_id) == "completed"
        assert _release_count(db, accepted.order_id) == 1

        # Re-running the tick after completion never double-releases this order.
        auto_confirm_due_jobs(now=marked_at + timedelta(hours=72))
        assert _release_count(db, accepted.order_id) == 1


# ---------------------------------------------------------------------------
# Review gating — only post-completion (verified engagement)
# ---------------------------------------------------------------------------


class TestReviewGating:
    def test_review_locked_pre_completion_unlocked_post(
        self, db: PgConn, db_url_env: None
    ) -> None:
        accepted = _accept(db)
        provider = _vendor_owner(db, accepted.vendor_id)
        job_row = db.run(
            f"SELECT ois.job_id::text FROM public.order_item_services ois "
            f"JOIN public.order_items oi ON oi.id = ois.order_item_id "
            f"WHERE oi.order_id = '{accepted.order_id}' AND oi.item_kind = 'service_deposit';"
        )
        job_id = job_row.rows[0]
        mark_job_complete(job_id, provider)

        # Pre-completion: order is 'placed' → the reviews gate rejects it.
        assert _order_status(db, accepted.order_id) == "placed"
        assert _order_status(db, accepted.order_id) not in REVIEWABLE_ORDER_STATUSES
        assert job_review_unlocked(job_id) is False

        confirm_job_completion(job_id, actor_id=CUSTOMER_A)

        # Post-completion: order is 'completed' → the reviews gate admits it.
        assert _order_status(db, accepted.order_id) == "completed"
        assert _order_status(db, accepted.order_id) in REVIEWABLE_ORDER_STATUSES
        assert job_review_unlocked(job_id) is True
