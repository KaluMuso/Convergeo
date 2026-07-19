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
from app.routers import job_completion as jc
from app.routers.job_completion import (
    PROVIDER_COMPLETE_ACTION,
    auto_confirm_due_jobs,
    confirm_job_completion,
    job_review_unlocked,
    mark_job_complete,
)
from app.routers.reviews import REVIEWABLE_ORDER_STATUSES
from app.services.escrow.release import release_idempotency_key
from app.services.ledger.engine import account_balance_ngwee
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


def _commission_capture_count(conn: PgConn, order_id: str) -> int:
    key_prefix = f"{release_idempotency_key(order_id)}-commission-"
    result = conn.run(
        f"SELECT count(*)::text FROM public.ledger_transactions "
        f"WHERE kind = 'commission_capture' AND idempotency_key LIKE '{key_prefix}%';"
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


# ---------------------------------------------------------------------------
# Failure-injection: partial-confirm never strands escrow (net invariant)
# ---------------------------------------------------------------------------


def _job_id_for(db: PgConn, order_id: str) -> str:
    row = db.run(
        f"SELECT ois.job_id::text FROM public.order_item_services ois "
        f"JOIN public.order_items oi ON oi.id = ois.order_item_id "
        f"WHERE oi.order_id = '{order_id}' AND oi.item_kind = 'service_deposit';"
    )
    assert row.ok and row.rows
    return row.rows[0]


def _completion_event_actor(db: PgConn, order_id: str) -> str | None:
    """actor of the most recent placed→completed order_events row (None if NULL/absent)."""
    result = db.run(
        f"SELECT coalesce(actor::text, '') FROM public.order_events "
        f"WHERE order_id = '{order_id}' AND to_status = 'completed' "
        f"ORDER BY created_at DESC, id DESC LIMIT 1;"
    )
    assert result.ok and result.rows, "expected a placed→completed order_events row"
    return result.rows[0] or None


class TestConfirmFailureNoStrand:
    def test_failure_after_release_before_complete_then_rerun_completes_single_release(
        self, db: PgConn, db_url_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Inject a failure between the vendor RELEASE and the order completion.

        The release has already posted, but the crash pre-empts the placed→completed
        flip. Net invariant: the order is NOT left completed-without-release — it stays
        'placed' (never falsely done), and a re-run re-drives to completion with the
        release posted EXACTLY ONCE (idempotency key ``release-{order_id}``).
        """
        accepted = _accept(db, total=280_000)
        provider = _vendor_owner(db, accepted.vendor_id)
        job_id = _job_id_for(db, accepted.order_id)
        mark_job_complete(job_id, provider)

        def _boom(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("injected crash after release, before complete")

        monkeypatch.setattr(jc, "_complete_order", _boom)
        with pytest.raises(RuntimeError):
            confirm_job_completion(job_id, actor_id=CUSTOMER_A)

        # Release posted, but the order is NOT stranded as completed — it stays 'placed'.
        assert _order_status(db, accepted.order_id) == "placed"
        assert _release_count(db, accepted.order_id) == 1

        # Re-run drives to completion; the release is still posted exactly once.
        monkeypatch.undo()
        recovered = confirm_job_completion(job_id, actor_id=CUSTOMER_A)
        assert recovered.already_confirmed is False
        assert recovered.release_created is False  # release already posted on the first pass
        assert _order_status(db, accepted.order_id) == "completed"
        assert _release_count(db, accepted.order_id) == 1
        assert _balance_item_count(db, accepted.order_id) == 1

    def test_failure_during_release_leaves_order_placed_no_release(
        self, db: PgConn, db_url_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A crash inside the release step must not complete the order (release is first)."""
        accepted = _accept(db, total=260_000)
        provider = _vendor_owner(db, accepted.vendor_id)
        job_id = _job_id_for(db, accepted.order_id)
        mark_job_complete(job_id, provider)

        def _boom(*_args: Any, **_kwargs: Any) -> tuple[bool, int]:
            raise RuntimeError("injected crash during release")

        monkeypatch.setattr(jc, "_release_service_order", _boom)
        with pytest.raises(RuntimeError):
            confirm_job_completion(job_id, actor_id=CUSTOMER_A)

        assert _order_status(db, accepted.order_id) == "placed"
        assert _release_count(db, accepted.order_id) == 0

        # Recovery: full re-run completes with a single release.
        monkeypatch.undo()
        confirm_job_completion(job_id, actor_id=CUSTOMER_A)
        assert _order_status(db, accepted.order_id) == "completed"
        assert _release_count(db, accepted.order_id) == 1


# ---------------------------------------------------------------------------
# Audit actor — the completion order_events row records the real confirmer (#8)
# ---------------------------------------------------------------------------


class TestServiceReleaseFailClosedUnit:
    """Service confirm shares product release accounting fail-closed gates."""

    def test_require_amounts_rejects_empty_snapshot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.escrow.release_accounting import ReleaseAccountingError

        monkeypatch.setattr(jc, "_order_gross_ngwee", lambda *_a, **_k: 250_000)
        monkeypatch.setattr(jc, "_load_commission_snapshot", lambda *_a, **_k: {})

        def _boom(**_kwargs: Any) -> Any:
            raise ReleaseAccountingError("invalid_commission_snapshot")

        monkeypatch.setattr(jc, "compute_release_amounts", _boom)
        with pytest.raises(AppError) as exc_info:
            jc._require_service_release_amounts(
                order_id=str(uuid.uuid4()), delivery_fee_ngwee=0
            )
        assert exc_info.value.code == "invalid_commission_snapshot"

    def test_assert_release_allowed_blocks_on_refund(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            jc, "release_blocked_reason", lambda **_k: "order_refunded"
        )
        with pytest.raises(AppError) as exc_info:
            jc._assert_service_release_allowed(
                order_id=str(uuid.uuid4()), status="placed"
            )
        assert exc_info.value.code == "release_blocked"
        assert exc_info.value.details == {"reason": "order_refunded"}

    def test_assert_release_allowed_fail_closed_on_dispute_lookup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.escrow.release_accounting import ReleaseAccountingError

        monkeypatch.setattr(jc, "release_blocked_reason", lambda **_k: None)

        def _boom(_order_id: str) -> bool:
            raise ReleaseAccountingError("dispute_lookup_failed")

        monkeypatch.setattr(jc, "order_has_open_dispute", _boom)
        with pytest.raises(AppError) as exc_info:
            jc._assert_service_release_allowed(
                order_id=str(uuid.uuid4()), status="placed"
            )
        assert exc_info.value.code == "release_blocked"
        assert exc_info.value.details == {"reason": "dispute_lookup_failed"}
        assert exc_info.value.http_status == 503


class TestCompletionCapturesCommission:
    """M08-P08b: confirm captures commission (once) before the vendor release."""

    def test_confirm_captures_commission_before_release(
        self, db: PgConn, db_url_env: None
    ) -> None:
        accepted = _accept(db, total=250_000)
        provider = _vendor_owner(db, accepted.vendor_id)
        job_id = _job_id_for(db, accepted.order_id)
        mark_job_complete(job_id, provider)

        commission_before = account_balance_ngwee(COMMISSION_ID)

        result = confirm_job_completion(job_id, actor_id=CUSTOMER_A)
        assert result.released is True

        captured = _commission_capture_count(db, accepted.order_id)
        assert captured >= 1
        # Commission recognized as revenue (credit-negative), exactly the snapshot value.
        assert (
            account_balance_ngwee(COMMISSION_ID)
            == commission_before - accepted.commission_ngwee
        )
        # Vendor net unchanged: total − commission (single snapshot).
        assert result.net_ngwee == accepted.total_job_ngwee - accepted.commission_ngwee

        # Double-confirm never captures a second time (idempotent per order).
        second = confirm_job_completion(job_id, actor_id=CUSTOMER_A)
        assert second.already_confirmed is True
        assert _commission_capture_count(db, accepted.order_id) == captured
        assert (
            account_balance_ngwee(COMMISSION_ID)
            == commission_before - accepted.commission_ngwee
        )


class TestCompletionAuditActor:
    def test_customer_confirm_records_actor(self, db: PgConn, db_url_env: None) -> None:
        accepted = _accept(db, total=240_000)
        provider = _vendor_owner(db, accepted.vendor_id)
        job_id = _job_id_for(db, accepted.order_id)
        mark_job_complete(job_id, provider)

        confirm_job_completion(job_id, actor_id=CUSTOMER_A)

        actor = _completion_event_actor(db, accepted.order_id)
        assert actor is not None, "completion audit row must not have a NULL actor"
        assert actor == CUSTOMER_A

    def test_auto_confirm_records_system_actor(self, db: PgConn, db_url_env: None) -> None:
        from app.routers.job_completion import SYSTEM_ACTOR_ID

        accepted = _accept(db, total=220_000)
        provider = _vendor_owner(db, accepted.vendor_id)
        job_id = _job_id_for(db, accepted.order_id)
        mark_job_complete(job_id, provider)
        marked_at = _marker_at(db, job_id)

        auto_confirm_due_jobs(now=marked_at + timedelta(hours=49))

        assert _order_status(db, accepted.order_id) == "completed"
        actor = _completion_event_actor(db, accepted.order_id)
        assert actor == SYSTEM_ACTOR_ID
