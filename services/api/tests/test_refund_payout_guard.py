"""Payout kill switch blocks every refund-creating path while PAYOUTS_ENABLED is off.

A refund = refund_lane1/2 (or clawback) ledger legs + a ``refunds`` row + a pending
``customer_refund`` payout row that the sweeper sends once payouts are enabled. With
payouts disabled each caller must refuse BEFORE any of those writes, with a stable
409 code; non-money outcomes (dispute release) keep working; with payouts enabled
behaviour is unchanged (covered by the existing refund/dispute/returns suites, which
pin PAYOUTS_ENABLED=true).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.errors import AppError
from app.services.escrow.release_accounting import OrderReleaseLedgerSummary
from app.services.payouts.gate import (
    DISPUTE_REFUND_UNAVAILABLE_PAYOUTS_DISABLED,
    REFUND_UNAVAILABLE_PAYOUTS_DISABLED,
    RefundPayoutsDisabledError,
    assert_customer_refund_allowed,
)
from app.services.refunds.execute import ensure_refund_allowed, execute_refund
from tests.test_disputes import (
    ADMIN_ID,
    CUSTOMER_MOMO,
    _FakeServiceWrapper,
    _seed_fake_dispute,
)
from tests.test_disputes import FakeSupabaseClient as DisputeFakeClient
from tests.test_refund_execute import (
    CALLER_KEY,
    ORDER_ID,
    FakeServiceClient,
    FakeSupabaseClient,
    IdempotentPostTransaction,
    _gate_decision_for_fake,
    _seed_order,
)

_EMPTY_SUMMARY = OrderReleaseLedgerSummary(
    order_id=ORDER_ID,
    charge_received_ngwee=0,
    commission_captured_ngwee=0,
    vendor_released_ngwee=0,
    refund_drained_ngwee=0,
)


@pytest.fixture
def payouts_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAYOUTS_ENABLED", raising=False)


@pytest.fixture
def payouts_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYOUTS_ENABLED", "true")


def _money_rows(fake: Any) -> dict[str, int]:
    return {
        name: len(fake.table(name).rows) for name in ("refunds", "payouts", "ledger_transactions")
    }


# --- shared helper -----------------------------------------------------------


class TestGateHelper:
    def test_refuses_when_disabled_with_stable_code(
        self, payouts_off: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING), pytest.raises(RefundPayoutsDisabledError) as exc:
            assert_customer_refund_allowed(surface="unit")
        assert exc.value.code == REFUND_UNAVAILABLE_PAYOUTS_DISABLED
        assert exc.value.http_status == 409
        assert exc.value.details["reason"] == "payouts_disabled"
        assert any(getattr(r, "event", None) == "customer_refund_blocked" for r in caplog.records)

    def test_custom_code(self, payouts_off: None) -> None:
        with pytest.raises(AppError) as exc:
            assert_customer_refund_allowed(
                surface="unit", code=DISPUTE_REFUND_UNAVAILABLE_PAYOUTS_DISABLED
            )
        assert exc.value.code == "dispute.refund_unavailable_payouts_disabled"

    @pytest.mark.parametrize("value", ["", "false", "0", "off", "no"])
    def test_falsy_values_refuse(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PAYOUTS_ENABLED", value)
        with pytest.raises(RefundPayoutsDisabledError):
            assert_customer_refund_allowed(surface="unit")

    def test_noop_when_enabled(self, payouts_on: None) -> None:
        assert_customer_refund_allowed(surface="unit")


# --- execute_refund backstop (covers admin POST /admin/refunds/execute) --------


class TestExecuteRefundBackstop:
    def _run(self, fake: FakeSupabaseClient, ledger: IdempotentPostTransaction) -> Any:
        with (
            patch("app.services.refunds.execute.post_transaction", ledger),
            patch(
                "app.services.refunds.execute.decide_refund_phase_under_gate",
                side_effect=_gate_decision_for_fake(fake),
            ) as gate,
            patch(
                "app.services.refunds.execute.summarize_order_release_ledger",
                return_value=_EMPTY_SUMMARY,
            ),
        ):
            result = execute_refund(
                service_client=FakeServiceClient(fake),
                order_id=ORDER_ID,
                lane=1,
                customer_momo="+260971234567",
                idempotency_key=CALLER_KEY,
            )
            return result, gate

    def test_new_refund_refused_writes_nothing(self, payouts_off: None) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake)
        ledger = IdempotentPostTransaction()
        with pytest.raises(AppError) as exc:
            self._run(fake, ledger)
        assert exc.value.code == REFUND_UNAVAILABLE_PAYOUTS_DISABLED
        assert exc.value.http_status == 409
        assert ledger.keys == []
        assert fake.tables["refunds"].rows == []
        assert fake.tables["payouts"].rows == []

    def test_processing_resume_refused_writes_nothing(self, payouts_off: None) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake)
        fake.tables["refunds"].rows.append(
            {
                "id": str(uuid.uuid4()),
                "order_id": ORDER_ID,
                "source_key": CALLER_KEY,
                "lane": 1,
                "amount_ngwee": 105_000,
                "status": "processing",
                "breakdown": {"phase": "pre_release", "idempotency_key": CALLER_KEY},
            }
        )
        ledger = IdempotentPostTransaction()
        with pytest.raises(AppError) as exc:
            self._run(fake, ledger)
        assert exc.value.code == REFUND_UNAVAILABLE_PAYOUTS_DISABLED
        assert ledger.keys == []
        assert fake.tables["payouts"].rows == []
        assert fake.tables["refunds"].rows[0]["status"] == "processing"

    def test_awaiting_payout_replay_still_idempotent_when_off(
        self,
        payouts_on: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Refund created while ON; a retry after the switch goes OFF replays as before."""
        fake = FakeSupabaseClient()
        _seed_order(fake)
        ledger = IdempotentPostTransaction()
        first, _ = self._run(fake, ledger)
        assert first.created is True
        before = (len(ledger.keys), len(fake.tables["payouts"].rows))

        monkeypatch.delenv("PAYOUTS_ENABLED", raising=False)
        second, _ = self._run(fake, ledger)
        assert second.created is False
        assert second.refund_id == first.refund_id
        assert (len(ledger.keys), len(fake.tables["payouts"].rows)) == before

    def test_enabled_unchanged(self, payouts_on: None) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake)
        ledger = IdempotentPostTransaction()
        result, _ = self._run(fake, ledger)
        assert result.created is True
        assert len(fake.tables["payouts"].rows) == 1
        assert ledger.created_count == 1


# --- dispute resolve (POST /admin/disputes/{id}/decide + /disputes/{id}/resolve) --


class TestDisputeResolveGuard:
    @pytest.mark.parametrize(
        ("decision", "partial"),
        [("resolved_refund", None), ("resolved_partial", 50_000)],
    )
    @patch("app.services.disputes.service.load_restocking_fee_bps", return_value=1000)
    @patch("app.services.disputes.service.evaluate_and_release")
    @patch("app.services.refunds.execute.post_transaction")
    def test_refund_outcomes_refused_before_any_write(
        self,
        mock_post: MagicMock,
        mock_release: MagicMock,
        _mock_bps: MagicMock,
        payouts_off: None,
        decision: Any,
        partial: int | None,
    ) -> None:
        from app.services.disputes.service import resolve

        order_id = str(uuid.uuid4())
        dispute_id = str(uuid.uuid4())
        fake = DisputeFakeClient()
        _seed_fake_dispute(fake, dispute_id=dispute_id, order_id=order_id)
        audit_before = len(fake.table("audit_log").rows)

        with pytest.raises(AppError) as exc:
            resolve(
                _FakeServiceWrapper(fake),
                dispute_id=dispute_id,
                admin_user_id=ADMIN_ID,
                decision=decision,
                admin_decision="Refund the customer",
                customer_momo=CUSTOMER_MOMO,
                partial_refund_ngwee=partial,
            )

        assert exc.value.code == DISPUTE_REFUND_UNAVAILABLE_PAYOUTS_DISABLED
        assert exc.value.http_status == 409
        mock_post.assert_not_called()
        mock_release.assert_not_called()
        assert _money_rows(fake) == {"refunds": 0, "payouts": 0, "ledger_transactions": 0}
        # Dispute untouched (still re-drivable once payouts are on); no transition audit.
        assert fake.tables["disputes"].rows[0]["status"] == "under_review"
        assert fake.tables["disputes"].rows[0]["admin_decision"] is None
        assert len(fake.table("audit_log").rows) == audit_before

    @patch("app.services.disputes.service.evaluate_and_release")
    @patch("app.services.disputes.service.execute_refund")
    def test_release_outcome_still_works_when_off(
        self, mock_refund: MagicMock, mock_release: MagicMock, payouts_off: None
    ) -> None:
        from app.services.disputes.service import resolve

        order_id = str(uuid.uuid4())
        dispute_id = str(uuid.uuid4())
        fake = DisputeFakeClient()
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

    @patch("app.services.disputes.service.evaluate_and_release")
    @patch("app.services.disputes.service.execute_refund")
    def test_redrive_of_existing_refund_allowed_when_off(
        self, mock_refund: MagicMock, mock_release: MagicMock, payouts_off: None
    ) -> None:
        """Refund already awaiting provider (created while ON): re-driving the
        resolution is a pure replay, so it is not blocked."""
        from app.services.disputes.service import resolve

        order_id = str(uuid.uuid4())
        dispute_id = str(uuid.uuid4())
        fake = DisputeFakeClient()
        _seed_fake_dispute(fake, dispute_id=dispute_id, order_id=order_id)
        fake.table("refunds").rows.append(
            {
                "id": str(uuid.uuid4()),
                "order_id": order_id,
                "source_key": f"dispute-{dispute_id}-refund",
                "status": "awaiting_payout",
                "created_at": "2026-11-01T00:00:00Z",
            }
        )
        mock_refund.return_value = MagicMock(refund_id=str(uuid.uuid4()))

        record = resolve(
            _FakeServiceWrapper(fake),
            dispute_id=dispute_id,
            admin_user_id=ADMIN_ID,
            decision="resolved_refund",
            admin_decision="Full refund",
            customer_momo=CUSTOMER_MOMO,
        )
        assert record.status == "resolved_refund"
        assert mock_refund.call_args.kwargs["idempotency_key"] == f"dispute-{dispute_id}-refund"

    @patch("app.services.disputes.service.evaluate_and_release")
    @patch("app.services.disputes.service.execute_refund")
    def test_refund_outcome_unchanged_when_on(
        self, mock_refund: MagicMock, mock_release: MagicMock, payouts_on: None
    ) -> None:
        from app.services.disputes.service import resolve

        order_id = str(uuid.uuid4())
        dispute_id = str(uuid.uuid4())
        fake = DisputeFakeClient()
        _seed_fake_dispute(fake, dispute_id=dispute_id, order_id=order_id)
        mock_refund.return_value = MagicMock(refund_id=str(uuid.uuid4()))

        record = resolve(
            _FakeServiceWrapper(fake),
            dispute_id=dispute_id,
            admin_user_id=ADMIN_ID,
            decision="resolved_refund",
            admin_decision="Full refund",
            customer_momo=CUSTOMER_MOMO,
        )
        assert record.status == "resolved_refund"
        kwargs = mock_refund.call_args.kwargs
        assert kwargs["idempotency_key"] == f"dispute-{dispute_id}-refund"
        assert kwargs["lane"] == 1


# --- returns lane 1 (vendor accept) / lane 2 (customer create) -----------------


class TestReturnsGuard:
    def test_lane1_accept_refused_before_status_cas(
        self, payouts_off: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.returns import lane1

        return_id = str(uuid.uuid4())
        cas = MagicMock()
        refund = MagicMock()
        monkeypatch.setattr(
            lane1,
            "_load_return_row",
            lambda *_a, **_k: {
                "id": return_id,
                "lane": 1,
                "status": "requested",
            },
        )
        monkeypatch.setattr(
            lane1,
            "_assert_vendor_owns_return",
            lambda *_a, **_k: (
                {},
                {"id": "item"},
                {"id": ORDER_ID, "customer_id": "c", "vendor_id": "v"},
            ),
        )
        monkeypatch.setattr(lane1, "_cas_update_return_status", cas)
        monkeypatch.setattr(lane1, "execute_refund", refund)
        fake = DisputeFakeClient()

        with pytest.raises(AppError) as exc:
            lane1.vendor_accept_lane1_return(
                _FakeServiceWrapper(fake), return_id=return_id, vendor_owner_id="owner"
            )
        assert exc.value.code == REFUND_UNAVAILABLE_PAYOUTS_DISABLED
        cas.assert_not_called()  # return stays `requested`
        refund.assert_not_called()
        assert _money_rows(fake) == {"refunds": 0, "payouts": 0, "ledger_transactions": 0}

    def test_lane2_create_refused_before_return_insert(
        self, payouts_off: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.returns import lane2

        refund = MagicMock()
        monkeypatch.setattr(
            lane2, "check_eligibility", lambda *_a, **_k: MagicMock(eligible=True, reason=None)
        )
        monkeypatch.setattr(
            lane2,
            "_load_order_item_context",
            lambda *_a, **_k: {
                "order_id": ORDER_ID,
                "qty": 1,
                "unit_price_ngwee": 100_000,
            },
        )
        monkeypatch.setattr(
            lane2,
            "_load_order",
            lambda *_a, **_k: {
                "id": ORDER_ID,
                "customer_id": "cust",
                "delivery_fee_ngwee": 0,
            },
        )
        monkeypatch.setattr(lane2, "_prorated_outbound_delivery", lambda *_a, **_k: 0)
        monkeypatch.setattr(lane2, "load_restocking_fee_bps", lambda *_a, **_k: 1000)
        monkeypatch.setattr(lane2, "execute_refund", refund)
        fake = DisputeFakeClient()

        with pytest.raises(AppError) as exc:
            lane2.create_lane2_return(
                _FakeServiceWrapper(fake),
                order_item_id=str(uuid.uuid4()),
                customer_id="cust",
                unused_declared=True,
                customer_momo=CUSTOMER_MOMO,
            )
        assert exc.value.code == REFUND_UNAVAILABLE_PAYOUTS_DISABLED
        refund.assert_not_called()
        assert fake.table("returns").rows == []


# --- event cancellation refund jobs sweeper -----------------------------------


class TestEventRefundJobGuard:
    def test_job_left_queued_untouched_when_off(
        self, payouts_off: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.events import refund_jobs

        job = {
            "id": "job-1",
            "status": "queued",
            "order_id": ORDER_ID,
            "customer_id": "cust",
            "event_id": "evt",
            "amount_ngwee": "5000",
            "attempts": "0",
            "next_retry_at": "",
        }
        claim = MagicMock(return_value=True)
        update = MagicMock()
        refund = MagicMock()
        monkeypatch.setattr(refund_jobs, "_load_job", lambda _id: dict(job))
        monkeypatch.setattr(refund_jobs, "_claim_job", claim)
        monkeypatch.setattr(refund_jobs, "_update_job", update)
        monkeypatch.setattr(refund_jobs, "execute_refund", refund)

        outcome = refund_jobs.process_event_refund_job(MagicMock(), "job-1")

        assert outcome.outcome == "skipped"
        assert outcome.reason == "payouts_disabled"
        claim.assert_not_called()  # attempts not bumped, stays queued
        update.assert_not_called()  # never parked in manual_review / dead
        refund.assert_not_called()

    def test_race_refusal_requeues_not_manual_review(
        self, payouts_on: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.events import refund_jobs

        job = {
            "id": "job-2",
            "status": "queued",
            "order_id": ORDER_ID,
            "customer_id": "cust",
            "event_id": "evt",
            "amount_ngwee": "5000",
            "attempts": "0",
            "next_retry_at": "",
        }
        update = MagicMock()
        monkeypatch.setattr(refund_jobs, "_load_job", lambda _id: dict(job))
        monkeypatch.setattr(refund_jobs, "_claim_job", MagicMock(return_value=True))
        monkeypatch.setattr(refund_jobs, "_update_job", update)
        monkeypatch.setattr(
            refund_jobs,
            "load_customer_refund_destination",
            lambda *_a, **_k: (CUSTOMER_MOMO, "mtn"),
        )
        monkeypatch.setattr(
            refund_jobs, "execute_refund", MagicMock(side_effect=RefundPayoutsDisabledError())
        )

        outcome = refund_jobs.process_event_refund_job(MagicMock(), "job-2")

        assert outcome.reason == "payouts_disabled"
        update.assert_called_once()
        assert update.call_args.kwargs["status"] == "queued"


def test_ensure_refund_allowed_noop_when_enabled(payouts_on: None) -> None:
    fake = FakeSupabaseClient()
    ensure_refund_allowed(
        FakeServiceClient(fake), order_id=ORDER_ID, idempotency_key=None, surface="unit"
    )
