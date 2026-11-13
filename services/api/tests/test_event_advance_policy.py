# ruff: noqa: F811  (db / db_url_env fixtures are imported from test_event_release)
"""Tiered organiser pre-event advance + organiser receivable (founder policy 2026-11-13).

* Unverified organisers: 100% held until after the event.
* Verified organisers (approved KYC tier >= min, active, signed undertaking, no
  unpaid/blacklisted advance debt): configurable advance (<= 50%) 7 days before.
* Cancelled after an advance: escrow refilled (organiser receivable + platform
  commission/fee handed back) so buyers are refunded in full; the receivable is
  netted against money owed to the organiser or repaid; unpaid past due ->
  suspended, blacklisted, legal follow-up flag. Ledger stays balanced throughout.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from app.services.escrow.event_release import (
    PHASE1_LEAD_DAYS,
    evaluate_event_release,
    phase1_release_key,
    resolve_advance_bps,
)
from app.services.escrow.release_accounting import (
    remaining_escrow_ngwee,
    summarize_order_release_ledger,
)
from app.services.events import advance_policy as ap
from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate
from tests.rls.conftest import PgConn
from tests.test_event_release import (  # noqa: F401  (pytest fixtures)
    _SERVICE,
    NET_NGEWEE,
    UNIT_PRICE_NGWEE,
    _insert_event,
    _insert_instance,
    _insert_ticket_order,
    _insert_ticket_type,
    db,
    db_url_env,
)

VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
VENDOR_B_OWNER_ID = "44444444-4444-4444-4444-444444444444"


def _scalar(db: PgConn, sql: str) -> str:
    result = db.run(sql)
    assert result.ok, result.error
    return result.rows[0] if result.rows else ""


def _set_flag(db: PgConn, enabled: bool) -> None:
    assert db.run(
        "INSERT INTO public.feature_flags (flag, enabled) VALUES "
        f"('{ap.ADVANCE_FLAG}', {str(enabled).lower()}) "
        "ON CONFLICT (flag) DO UPDATE SET enabled = EXCLUDED.enabled;"
    ).ok


@pytest.fixture
def advance_enabled(db: PgConn, db_url_env: None) -> Generator[None, None, None]:
    """Flag ON and no track-record minimum; restored to the shipped defaults after."""
    _set_flag(db, True)
    _set_config(db, ap.MIN_SUCCESSFUL_EVENTS_KEY, "0")
    yield
    _set_flag(db, False)
    _set_config(db, ap.MIN_SUCCESSFUL_EVENTS_KEY, "2")


@pytest.fixture
def verified_organiser(
    db: PgConn, db_url_env: None, advance_enabled: None
) -> Generator[str, None, None]:
    """VENDOR_B: active, approved KYC tier 2, ledger accounts, signed undertaking."""
    kyc_id = str(uuid.uuid4())
    assert db.run(
        f"""
        DELETE FROM public.organiser_advance_debts WHERE vendor_id = '{VENDOR_B}';
        DELETE FROM public.organiser_advance_undertakings WHERE vendor_id = '{VENDOR_B}';
        UPDATE public.vendors SET status = 'active' WHERE id = '{VENDOR_B}';
        INSERT INTO public.kyc_records (id, vendor_id, tier, status)
        VALUES ('{kyc_id}', '{VENDOR_B}', 2, 'approved');
        SELECT public.ensure_vendor_ledger_accounts('{VENDOR_B}');
        """
    ).ok
    _zero_organiser_balances(VENDOR_B)
    ap.accept_advance_undertaking(vendor_id=VENDOR_B, actor_user_id=VENDOR_B_OWNER_ID)
    yield VENDOR_B
    db.run(
        f"""
        DELETE FROM public.kyc_records WHERE id = '{kyc_id}';
        DELETE FROM public.organiser_advance_undertakings WHERE vendor_id = '{VENDOR_B}';
        UPDATE public.vendors SET status = 'active' WHERE id = '{VENDOR_B}';
        """
    )


def _zero_organiser_balances(vendor_id: str) -> None:
    """Shared test DB: start each test with nothing owed either way (balanced entries)."""
    from app.services.payouts.eligibility import released_balance_ngwee

    tag = uuid.uuid4().hex[:8]
    owed_by_organiser = ap.organiser_receivable_balance_ngwee(vendor_id)
    if owed_by_organiser > 0:
        post_transaction(
            idempotency_key=f"test-reset-receivable-{tag}",
            template=LedgerTemplate.ORGANISER_RECEIVABLE_REPAID,
            amount_ngwee=owed_by_organiser,
            vendor_id=vendor_id,
        )
    owed_to_organiser = released_balance_ngwee(vendor_id)
    if owed_to_organiser > 0:
        post_transaction(
            idempotency_key=f"test-reset-payable-{tag}",
            template=LedgerTemplate.PAYOUT_EXECUTED,
            amount_ngwee=owed_to_organiser,
            vendor_id=vendor_id,
        )


def _set_config(db: PgConn, key: str, raw: str | None) -> None:
    if raw is None:
        assert db.run(f"DELETE FROM public.platform_config WHERE key = '{key}';").ok
        return
    assert db.run(
        "INSERT INTO public.platform_config (key, value) VALUES "
        f"('{key}', '{raw}'::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;"
    ).ok


def _seed_early_order(db: PgConn, vendor_id: str) -> tuple[str, str, datetime]:
    event_id, instance_id, type_id, order_id = (str(uuid.uuid4()) for _ in range(4))
    starts_at = datetime(2026, 12, 20, 18, 0, tzinfo=UTC)
    _insert_event(db, event_id=event_id, organiser_vendor_id=vendor_id)
    _insert_instance(db, instance_id=instance_id, event_id=event_id, starts_at=starts_at)
    _insert_ticket_type(db, type_id=type_id, event_id=event_id)
    _insert_ticket_order(
        db,
        order_id=order_id,
        group_id=str(uuid.uuid4()),
        item_id=str(uuid.uuid4()),
        instance_id=instance_id,
        ticket_type_id=type_id,
        vendor_id=vendor_id,
        created_at=starts_at - timedelta(days=30),
        fund_escrow=True,
    )
    return event_id, order_id, starts_at


def _receivable(vendor_id: str) -> int:
    return ap.organiser_receivable_balance_ngwee(vendor_id)


def _debt(db: PgConn, order_id: str) -> str:
    return _scalar(
        db,
        "SELECT status || '|' || amount_ngwee || '|' || recovered_ngwee || '|' || "
        "(blacklisted_at IS NOT NULL) || '|' || (legal_followup_at IS NOT NULL) "
        f"FROM public.organiser_advance_debts WHERE order_id = '{order_id}';",
    )


def _ledger_globally_balanced(db: PgConn) -> bool:
    total = _scalar(db, "SELECT coalesce(sum(amount_ngwee), 0)::text FROM public.ledger_postings;")
    return total == "0"


class TestAdvanceDecision:
    def test_unverified_organiser_gets_no_advance(
        self, db: PgConn, db_url_env: None, advance_enabled: None
    ) -> None:
        # VENDOR_A has no approved KYC record (orphaned kyc_tier stays T1).
        decision = ap.organiser_advance_decision("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        assert decision.bps == 0
        assert decision.reason == "organiser_unverified"

    def test_verified_organiser_gets_configured_advance(
        self, db: PgConn, verified_organiser: str
    ) -> None:
        _set_config(db, ap.VERIFIED_ADVANCE_BPS_KEY, None)
        assert resolve_advance_bps(verified_organiser) == 5_000
        _set_config(db, ap.VERIFIED_ADVANCE_BPS_KEY, "3000")
        assert resolve_advance_bps(verified_organiser) == 3_000
        _set_config(db, ap.VERIFIED_ADVANCE_BPS_KEY, "9000")  # capped at 50%
        assert resolve_advance_bps(verified_organiser) == 5_000
        _set_config(db, ap.VERIFIED_ADVANCE_BPS_KEY, "0")
        assert ap.organiser_advance_decision(verified_organiser).reason == "advances_disabled"
        _set_config(db, ap.VERIFIED_ADVANCE_BPS_KEY, '"junk"')
        assert resolve_advance_bps(verified_organiser) == 5_000
        _set_config(db, ap.VERIFIED_ADVANCE_BPS_KEY, "5000")

    def test_flag_off_by_default_holds_everyone(self, db: PgConn, db_url_env: None) -> None:
        # Shipped default: the migration seeds the flag OFF.
        assert _scalar(
            db, f"SELECT enabled::text FROM public.feature_flags WHERE flag = '{ap.ADVANCE_FLAG}';"
        ) in {"f", "false"}
        assert ap.is_advance_enabled() is False

    def test_flag_off_disables_advance_for_verified_organiser(
        self, db: PgConn, verified_organiser: str
    ) -> None:
        assert resolve_advance_bps(verified_organiser) == 5_000
        _set_flag(db, False)
        decision = ap.organiser_advance_decision(verified_organiser)
        assert (decision.bps, decision.reason) == (0, "advances_disabled")
        _set_flag(db, True)

    def test_missing_flag_row_fails_closed(self, db: PgConn, verified_organiser: str) -> None:
        assert db.run(f"DELETE FROM public.feature_flags WHERE flag = '{ap.ADVANCE_FLAG}';").ok
        try:
            assert resolve_advance_bps(verified_organiser) == 0
        finally:
            _set_flag(db, True)

    def test_track_record_is_required(self, db: PgConn, verified_organiser: str) -> None:
        # VENDOR_B has no completed paid event in this fixture set.
        _set_config(db, ap.MIN_SUCCESSFUL_EVENTS_KEY, "1")
        decision = ap.organiser_advance_decision(verified_organiser)
        assert (decision.bps, decision.reason) == (0, "insufficient_track_record")
        _set_config(db, ap.MIN_SUCCESSFUL_EVENTS_KEY, None)  # default 2 also applies
        assert ap.organiser_advance_decision(verified_organiser).reason == (
            "insufficient_track_record"
        )

    def test_track_record_met_unlocks_advance(
        self, db: PgConn, verified_organiser: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.events import gmv_cap

        _set_config(db, ap.MIN_SUCCESSFUL_EVENTS_KEY, "2")
        monkeypatch.setattr(gmv_cap, "organiser_successful_paid_event_count", lambda _v: 2)
        assert resolve_advance_bps(verified_organiser) == 5_000
        monkeypatch.setattr(gmv_cap, "organiser_successful_paid_event_count", lambda _v: 1)
        assert resolve_advance_bps(verified_organiser) == 0

    def test_no_undertaking_means_no_advance(self, db: PgConn, verified_organiser: str) -> None:
        assert db.run(
            "UPDATE public.organiser_advance_undertakings SET revoked_at = now() "
            f"WHERE vendor_id = '{verified_organiser}';"
        ).ok
        decision = ap.organiser_advance_decision(verified_organiser)
        assert (decision.bps, decision.reason) == (0, "undertaking_missing")

    def test_min_kyc_tier_is_configurable(self, db: PgConn, verified_organiser: str) -> None:
        _set_config(db, ap.MIN_KYC_TIER_KEY, "3")
        try:
            assert ap.organiser_advance_decision(verified_organiser).reason == (
                "organiser_unverified"
            )
        finally:
            _set_config(db, ap.MIN_KYC_TIER_KEY, "2")

    def test_undertaking_acceptance_is_audited(self, db: PgConn, verified_organiser: str) -> None:
        count = _scalar(
            db,
            "SELECT count(*)::text FROM public.audit_log "
            f"WHERE entity_id = '{verified_organiser}' "
            f"AND action = '{ap.AUDIT_UNDERTAKING_ACCEPTED}';",
        )
        assert int(count) >= 1


class TestVerifiedAdvanceLifecycle:
    def test_verified_organiser_receives_half_before_event(
        self, db: PgConn, verified_organiser: str
    ) -> None:
        _event_id, order_id, starts_at = _seed_early_order(db, verified_organiser)
        result = evaluate_event_release(
            _SERVICE, order_id, now=starts_at - timedelta(days=PHASE1_LEAD_DAYS)
        )
        assert result.outcome == "released"
        assert result.phases_posted == ("phase1",)
        assert result.net_ngwee == NET_NGEWEE // 2

    def test_cancel_after_advance_not_paid_out_nets_receivable_immediately(
        self, db: PgConn, verified_organiser: str
    ) -> None:
        """Payouts off (pilot): the advance still sits in vendor_payable, so the
        receivable is offset at once and the debt is settled; buyer refund is full."""
        event_id, order_id, starts_at = _seed_early_order(db, verified_organiser)
        evaluate_event_release(_SERVICE, order_id, now=starts_at - timedelta(days=PHASE1_LEAD_DAYS))
        assert db.run(f"UPDATE public.events SET status = 'cancelled' WHERE id = '{event_id}';").ok

        result = evaluate_event_release(_SERVICE, order_id, now=starts_at - timedelta(days=5))
        assert result.outcome == "blocked_cancelled"

        summary = summarize_order_release_ledger(order_id)
        assert summary.advance_recovered_ngwee > 0
        # Escrow holds the whole ticket price again -> buyer refunded in full, and
        # execute_refund takes the escrow (pre-release) path instead of failing
        # closed with partial_release_refund_blocked.
        assert remaining_escrow_ngwee(order_id) == UNIT_PRICE_NGWEE
        from app.services.refunds.execute import _order_advance_recovered

        assert _order_advance_recovered(order_id)
        assert _receivable(verified_organiser) == 0
        assert _debt(db, order_id).startswith(f"settled|{NET_NGEWEE // 2}|{NET_NGEWEE // 2}")
        jobs = _scalar(
            db,
            "SELECT amount_ngwee::text FROM public.event_refund_jobs "
            f"WHERE order_id = '{order_id}' AND source = 'organiser_cancel';",
        )
        assert jobs == str(UNIT_PRICE_NGWEE)
        assert _ledger_globally_balanced(db)

        # Idempotent re-run: no second recovery, no double debt.
        evaluate_event_release(_SERVICE, order_id, now=starts_at - timedelta(days=4))
        assert summarize_order_release_ledger(order_id).advance_recovered_ngwee == (
            summary.advance_recovered_ngwee
        )

    def test_paid_out_advance_becomes_debt_then_suspension_and_blacklist(
        self, db: PgConn, verified_organiser: str
    ) -> None:
        event_id, order_id, starts_at = _seed_early_order(db, verified_organiser)
        advance = evaluate_event_release(
            _SERVICE, order_id, now=starts_at - timedelta(days=PHASE1_LEAD_DAYS)
        ).net_ngwee
        # Everything owed to the organiser (this advance included) was paid out.
        from app.services.payouts.eligibility import released_balance_ngwee

        owed = released_balance_ngwee(verified_organiser)
        assert owed == advance
        post_transaction(
            idempotency_key=f"test-payout-{order_id}",
            template=LedgerTemplate.PAYOUT_EXECUTED,
            amount_ngwee=owed,
            vendor_id=verified_organiser,
        )
        assert db.run(f"UPDATE public.events SET status = 'cancelled' WHERE id = '{event_id}';").ok
        cancelled_at = starts_at - timedelta(days=5)
        evaluate_event_release(_SERVICE, order_id, now=cancelled_at)

        assert _receivable(verified_organiser) == advance
        assert _debt(db, order_id) == f"open|{advance}|0|false|false"
        assert remaining_escrow_ngwee(order_id) == UNIT_PRICE_NGWEE
        assert _ledger_globally_balanced(db)
        # Outstanding debt -> no further advances.
        assert ap.organiser_advance_decision(verified_organiser).reason == (
            "advance_debt_outstanding"
        )

        # Not yet due: nothing happens.
        early = ap.enforce_overdue_advance_debts(now=datetime.now(UTC))
        assert early.debts_flagged == 0
        # Past the repayment window: suspend + blacklist + legal follow-up, audited.
        late = ap.enforce_overdue_advance_debts(
            now=datetime.now(UTC) + timedelta(days=ap.DEFAULT_REPAYMENT_DAYS + 1)
        )
        assert late.debts_flagged >= 1
        assert _debt(db, order_id) == f"open|{advance}|0|true|true"
        assert _scalar(db, f"SELECT status FROM public.vendors WHERE id = '{VENDOR_B}';") == (
            "suspended"
        )
        assert (
            int(
                _scalar(
                    db,
                    "SELECT count(*)::text FROM public.audit_log "
                    f"WHERE entity_id = '{VENDOR_B}' AND action = '{ap.AUDIT_DEBT_OVERDUE}';",
                )
            )
            >= 1
        )
        again = ap.enforce_overdue_advance_debts(
            now=datetime.now(UTC) + timedelta(days=ap.DEFAULT_REPAYMENT_DAYS + 2)
        )
        assert again.debts_flagged == 0  # idempotent

        # Finance records a repayment: ledger + debt settle; blacklist stays.
        with pytest.raises(Exception):  # noqa: B017 - over-repayment refused
            ap.record_organiser_repayment(
                vendor_id=VENDOR_B,
                amount_ngwee=advance + 1,
                actor_user_id=VENDOR_B_OWNER_ID,
                reference="bank-1",
            )
        ap.record_organiser_repayment(
            vendor_id=VENDOR_B,
            amount_ngwee=advance,
            actor_user_id=VENDOR_B_OWNER_ID,
            reference=f"bank-{order_id[:8]}",
        )
        assert _receivable(VENDOR_B) == 0
        assert _debt(db, order_id).startswith(f"settled|{advance}|{advance}|true")
        assert _ledger_globally_balanced(db)
        assert db.run(f"UPDATE public.vendors SET status = 'active' WHERE id = '{VENDOR_B}';").ok
        assert ap.organiser_advance_decision(VENDOR_B).reason == "advance_debt_outstanding"

    def test_unverified_organiser_order_never_advanced(self, db: PgConn, db_url_env: None) -> None:
        _event_id, order_id, starts_at = _seed_early_order(
            db, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        )
        result = evaluate_event_release(
            _SERVICE, order_id, now=starts_at - timedelta(days=PHASE1_LEAD_DAYS)
        )
        assert result.outcome == "not_eligible"
        assert result.reason == "timers_not_met"
        assert (
            int(
                _scalar(
                    db,
                    "SELECT count(*)::text FROM public.ledger_transactions "
                    f"WHERE idempotency_key = '{phase1_release_key(order_id)}';",
                )
            )
            == 0
        )


def _seed_overdue_debt(db: PgConn, organiser: str) -> tuple[str, int]:
    """Verified organiser gets an advance, is paid out, then the event is cancelled."""
    from app.services.payouts.eligibility import released_balance_ngwee

    event_id, order_id, starts_at = _seed_early_order(db, organiser)
    advance = evaluate_event_release(
        _SERVICE, order_id, now=starts_at - timedelta(days=PHASE1_LEAD_DAYS)
    ).net_ngwee
    owed = released_balance_ngwee(organiser)
    post_transaction(
        idempotency_key=f"test-payout-{order_id}",
        template=LedgerTemplate.PAYOUT_EXECUTED,
        amount_ngwee=owed,
        vendor_id=organiser,
    )
    assert db.run(f"UPDATE public.events SET status = 'cancelled' WHERE id = '{event_id}';").ok
    evaluate_event_release(_SERVICE, order_id, now=starts_at - timedelta(days=5))
    assert _debt(db, order_id) == f"open|{advance}|0|false|false"
    return order_id, advance


def _late() -> datetime:
    return datetime.now(UTC) + timedelta(days=ap.DEFAULT_REPAYMENT_DAYS + 1)


def _audit_count(db: PgConn, vendor_id: str, action: str) -> int:
    return int(
        _scalar(
            db,
            "SELECT count(*)::text FROM public.audit_log "
            f"WHERE entity_id = '{vendor_id}' AND action = '{action}';",
        )
    )


class TestGuardedSuspension:
    def test_overdue_suspension_uses_guarded_transition_with_audit(
        self, db: PgConn, verified_organiser: str
    ) -> None:
        _seed_overdue_debt(db, verified_organiser)
        before = _audit_count(db, verified_organiser, "vendor.suspended")
        result = ap.enforce_overdue_advance_debts(now=_late())
        assert result.vendors_suspended == 1
        assert _scalar(
            db, f"SELECT status FROM public.vendors WHERE id = '{verified_organiser}';"
        ) == ("suspended")
        assert _audit_count(db, verified_organiser, "vendor.suspended") == before + 1
        reason = _scalar(
            db,
            "SELECT after ->> 'reason' FROM public.audit_log "
            f"WHERE entity_id = '{verified_organiser}' AND action = 'vendor.suspended' "
            "ORDER BY at DESC, id DESC LIMIT 1;",
        )
        assert reason == ap.SUSPEND_REASON

    def test_non_active_vendor_is_never_forced_to_suspended(
        self, db: PgConn, verified_organiser: str
    ) -> None:
        order_id, advance = _seed_overdue_debt(db, verified_organiser)
        assert db.run(
            f"UPDATE public.vendors SET status = 'pending_kyc' WHERE id = '{verified_organiser}';"
        ).ok
        before = _audit_count(db, verified_organiser, "vendor.suspended")
        result = ap.enforce_overdue_advance_debts(now=_late())
        # Debt is still blacklisted and flagged; the vendor status is left alone.
        assert result.debts_flagged >= 1
        assert result.vendors_suspended == 0
        assert _debt(db, order_id) == f"open|{advance}|0|true|true"
        assert _scalar(
            db, f"SELECT status FROM public.vendors WHERE id = '{verified_organiser}';"
        ) == ("pending_kyc")
        assert _audit_count(db, verified_organiser, "vendor.suspended") == before
        outcome = _scalar(
            db,
            "SELECT after ->> 'suspension_outcome' FROM public.audit_log "
            f"WHERE entity_id = '{verified_organiser}' AND action = '{ap.AUDIT_DEBT_OVERDUE}' "
            "ORDER BY at DESC, id DESC LIMIT 1;",
        )
        assert outcome == "not_active"

    def test_guarded_transition_rejects_unknown_vendor_and_blank_reason(
        self, db: PgConn, db_url_env: None
    ) -> None:
        missing = db.run(
            "SELECT public.transition_vendor_suspend("
            f"'{uuid.uuid4()}'::uuid, '{VENDOR_B_OWNER_ID}'::uuid, 'x', '{{}}'::jsonb);"
        )
        assert not missing.ok
        assert "vendor_not_found" in (missing.error or "")
        blank = db.run(
            "SELECT public.transition_vendor_suspend("
            f"'{VENDOR_B}'::uuid, '{VENDOR_B_OWNER_ID}'::uuid, ' ', '{{}}'::jsonb);"
        )
        assert not blank.ok
        assert "reason is required" in (blank.error or "")

    def test_guarded_transition_not_callable_by_clients(self, db: PgConn, db_url_env: None) -> None:
        for role in ("anon", "authenticated"):
            allowed = _scalar(
                db,
                f"SELECT has_function_privilege('{role}', "
                "'public.transition_vendor_suspend(uuid, uuid, text, jsonb)', 'EXECUTE')::text;",
            )
            assert allowed in {"f", "false"}

    def test_sweeper_source_has_no_raw_vendor_status_update(self) -> None:
        import inspect
        import re

        source = inspect.getsource(ap)
        assert not re.search(r"UPDATE\s+public\.vendors", source, re.IGNORECASE)


class TestRepaymentBeforeDue:
    def test_full_repayment_before_due_stops_suspension_and_blacklist(
        self, db: PgConn, verified_organiser: str
    ) -> None:
        order_id, advance = _seed_overdue_debt(db, verified_organiser)
        ap.record_organiser_repayment(
            vendor_id=verified_organiser,
            amount_ngwee=advance,
            actor_user_id=VENDOR_B_OWNER_ID,
            reference=f"momo-{order_id[:8]}",
        )
        assert _debt(db, order_id) == f"settled|{advance}|{advance}|false|false"
        result = ap.enforce_overdue_advance_debts(now=_late())
        assert result.vendors_suspended == 0
        assert _debt(db, order_id) == f"settled|{advance}|{advance}|false|false"
        assert _scalar(
            db, f"SELECT status FROM public.vendors WHERE id = '{verified_organiser}';"
        ) == ("active")
        assert _receivable(verified_organiser) == 0
        assert _ledger_globally_balanced(db)

    def test_partial_repayment_is_still_enforced_when_overdue(
        self, db: PgConn, verified_organiser: str
    ) -> None:
        order_id, advance = _seed_overdue_debt(db, verified_organiser)
        ap.record_organiser_repayment(
            vendor_id=verified_organiser,
            amount_ngwee=advance - 1,
            actor_user_id=VENDOR_B_OWNER_ID,
            reference=f"part-{order_id[:8]}",
        )
        assert _debt(db, order_id) == f"open|{advance}|{advance - 1}|false|false"
        result = ap.enforce_overdue_advance_debts(now=_late())
        assert result.vendors_suspended == 1
        assert _debt(db, order_id) == f"open|{advance}|{advance - 1}|true|true"

    def test_admin_listing_filters_by_status_and_organiser(
        self, db: PgConn, verified_organiser: str
    ) -> None:
        order_id, advance = _seed_overdue_debt(db, verified_organiser)
        mine = ap.list_advance_debts(vendor_id=verified_organiser, status="open")
        row = next(r for r in mine if r.order_id == order_id)
        assert (row.amount_ngwee, row.outstanding_ngwee) == (advance, advance)
        assert all(r.vendor_id == verified_organiser and r.status == "open" for r in mine)
        assert not any(
            r.order_id == order_id
            for r in ap.list_advance_debts(vendor_id=verified_organiser, status="settled")
        )
        with pytest.raises(Exception):  # noqa: B017 - unknown status refused
            ap.list_advance_debts(status="bogus")


class TestRepaymentConcurrency:
    def test_parallel_overpaying_repayments_exactly_one_succeeds(
        self, db: PgConn, verified_organiser: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import threading
        from concurrent.futures import ThreadPoolExecutor

        from app.errors import AppError

        order_id, advance = _seed_overdue_debt(db, verified_organiser)
        # Both callers pass the Python fast-path read (stale balance) and wait at the
        # barrier, so only the DB guard can stop the second credit.
        barrier = threading.Barrier(2)
        real_balance = ap.organiser_receivable_balance_ngwee

        waited = threading.local()

        def stale_then_race(vendor_id: str) -> int:
            balance = real_balance(vendor_id)
            first_read = not getattr(waited, "done", False)
            if first_read and threading.current_thread() is not threading.main_thread():
                waited.done = True
                barrier.wait(timeout=10)
            return balance

        monkeypatch.setattr(ap, "organiser_receivable_balance_ngwee", stale_then_race)

        def repay(reference: str) -> str:
            try:
                ap.record_organiser_repayment(
                    vendor_id=verified_organiser,
                    amount_ngwee=advance,
                    actor_user_id=VENDOR_B_OWNER_ID,
                    reference=reference,
                )
                return "ok"
            except AppError as exc:
                assert exc.http_status == 409
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(repay, [f"race-a-{order_id[:8]}", f"race-b-{order_id[:8]}"]))

        monkeypatch.setattr(ap, "organiser_receivable_balance_ngwee", real_balance)
        assert sorted(outcomes) == ["ok", "repayment_exceeds_receivable"]
        assert _receivable(verified_organiser) == 0
        assert _debt(db, order_id) == f"settled|{advance}|{advance}|false|false"
        assert _ledger_globally_balanced(db)

    def test_db_guard_refuses_direct_overdraw(self, db: PgConn, verified_organiser: str) -> None:
        from app.services.ledger.engine import LedgerError

        _order_id, advance = _seed_overdue_debt(db, verified_organiser)
        with pytest.raises(LedgerError, match=ap.RECEIVABLE_OVERDRAWN):
            post_transaction(
                idempotency_key=f"test-overdraw-{uuid.uuid4().hex[:8]}",
                template=LedgerTemplate.ORGANISER_RECEIVABLE_REPAID,
                amount_ngwee=advance + 1,
                vendor_id=verified_organiser,
            )
        assert _receivable(verified_organiser) == advance
        assert _ledger_globally_balanced(db)
