"""Cumulative refund cap — refunds on one order can never exceed what was paid.

Migration 0065 dropped the one-refund-per-order unique index, so a return refund and
a dispute refund (distinct source keys) on the same order are both legal rows. The
cap in ``execute_refund`` is what stops them draining more than the customer paid,
in BOTH the pre-release and post-release phases.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.errors import AppError
from app.services.escrow.release_accounting import OrderReleaseLedgerSummary
from app.services.ledger.engine import PostedTransaction
from app.services.refunds import execute as execute_mod
from app.services.refunds.execute import execute_refund
from tests.test_refunds import (
    CUSTOMER_MOMO,
    ORDER_ID,
    FakeServiceClient,
    FakeSupabaseClient,
    _gate_decision_for_fake,
    _seed_order,
)

# _seed_order defaults: 100_000 items + 5_000 delivery = 105_000 paid.
PAID = 105_000


@pytest.fixture(autouse=True)
def _payouts_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYOUTS_ENABLED", "true")


def _summary(*, charge: int, released: bool = False) -> OrderReleaseLedgerSummary:
    return OrderReleaseLedgerSummary(
        order_id=ORDER_ID,
        charge_received_ngwee=charge,
        commission_captured_ngwee=0,
        vendor_released_ngwee=charge if released else 0,
        refund_drained_ngwee=0,
    )


def _posted(*_: Any, **kwargs: Any) -> PostedTransaction:
    return PostedTransaction(
        id=f"txn-{kwargs['idempotency_key']}",
        kind="refund_lane1",
        idempotency_key=kwargs["idempotency_key"],
        created=True,
    )


@contextmanager
def _env(fake: FakeSupabaseClient, summary: OrderReleaseLedgerSummary) -> Iterator[MagicMock]:
    with (
        patch("app.services.refunds.execute.post_transaction", side_effect=_posted) as post,
        patch(
            "app.services.refunds.execute.decide_refund_phase_under_gate",
            side_effect=_gate_decision_for_fake(fake),
        ),
        patch("app.services.refunds.execute.summarize_order_release_ledger", return_value=summary),
        patch("app.services.refunds.execute.delivery_revenue_held_ngwee", return_value=5_000),
    ):
        yield post


def _refund(
    service: FakeServiceClient,
    key: str,
    *,
    items: int | None = None,
    delivery: int | None = None,
) -> Any:
    return execute_refund(
        service_client=service,
        order_id=ORDER_ID,
        lane=1,
        customer_momo=CUSTOMER_MOMO,
        idempotency_key=key,
        item_ngwee_override=items,
        delivery_fee_ngwee_override=delivery,
    )


def _active(fake: FakeSupabaseClient) -> list[dict[str, Any]]:
    return [r for r in fake.tables["refunds"].rows if r["status"] not in {"failed", "cancelled"}]


class TestCumulativeCap:
    @pytest.mark.parametrize("released", [True, False], ids=["post_release", "pre_release"])
    def test_return_then_dispute_second_is_rejected(self, released: bool) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake, released=released)
        service = FakeServiceClient(fake)
        with _env(fake, _summary(charge=PAID, released=released)) as post:
            first = _refund(service, "return-1", items=60_000, delivery=0)
            calls_after_first = post.call_count
            with pytest.raises(AppError) as exc:
                # Whole-order dispute refund (105_000) on top of the 60_000 return.
                _refund(service, "dispute-1")
        assert first.amount_ngwee == 60_000
        assert exc.value.code == "refund_exceeds_paid"
        assert exc.value.details["already_refunded_ngwee"] == 60_000
        assert exc.value.details["paid_ngwee"] == PAID
        assert len(_active(fake)) == 1
        # Rejected BEFORE any ledger leg / refund row / payout row for the second.
        assert post.call_count == calls_after_first
        assert len(fake.tables["payouts"].rows) == 1

    @pytest.mark.parametrize("released", [True, False], ids=["post_release", "pre_release"])
    def test_exact_remaining_is_allowed(self, released: bool) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake, released=released)
        service = FakeServiceClient(fake)
        with _env(fake, _summary(charge=PAID, released=released)):
            _refund(service, "return-1", items=60_000, delivery=0)
            second = _refund(service, "return-2", items=40_000, delivery=5_000)
        assert second.amount_ngwee == 45_000
        assert sum(r["amount_ngwee"] for r in _active(fake)) == PAID

    @pytest.mark.parametrize("released", [True, False], ids=["post_release", "pre_release"])
    def test_over_by_one_ngwee_is_rejected(self, released: bool) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake, released=released)
        service = FakeServiceClient(fake)
        with _env(fake, _summary(charge=PAID, released=released)):
            _refund(service, "return-1", items=60_000, delivery=0)
            with pytest.raises(AppError) as exc:
                _refund(service, "return-2", items=40_001, delivery=5_000)
        assert exc.value.code == "refund_exceeds_paid"
        assert len(_active(fake)) == 1

    def test_pre_release_cap_applies_when_charge_not_order_linked(self) -> None:
        """charge_received == 0 (charge booked on the checkout group) used to skip the cap."""
        fake = FakeSupabaseClient()
        _seed_order(fake)
        service = FakeServiceClient(fake)
        with _env(fake, _summary(charge=0)):
            _refund(service, "return-1", items=60_000, delivery=0)
            with pytest.raises(AppError) as exc:
                _refund(service, "dispute-1")
        assert exc.value.code == "refund_exceeds_paid"
        assert exc.value.details["paid_ngwee"] == PAID

    def test_failed_and_cancelled_refunds_do_not_count(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake)
        for status in ("failed", "cancelled"):
            fake.tables["refunds"].rows.append(
                {
                    "id": f"old-{status}",
                    "order_id": ORDER_ID,
                    "source_key": f"old-{status}",
                    "status": status,
                    "amount_ngwee": PAID,
                    "breakdown": {},
                }
            )
        service = FakeServiceClient(fake)
        with _env(fake, _summary(charge=PAID)):
            result = _refund(service, "dispute-1")
        assert result.amount_ngwee == PAID

    def test_replay_of_same_key_is_not_blocked_by_its_own_amount(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake)
        service = FakeServiceClient(fake)
        with _env(fake, _summary(charge=PAID)):
            first = _refund(service, "dispute-1")
            replay = _refund(service, "dispute-1")
        assert replay.refund_id == first.refund_id
        assert replay.created is False
        assert len(_active(fake)) == 1

    def test_promo_return_counts_toward_the_cap(self) -> None:
        fake = FakeSupabaseClient()
        fake.tables["refunds"].rows.append(
            {
                "id": "r1",
                "order_id": ORDER_ID,
                "status": "awaiting_payout",
                "amount_ngwee": 90_000,
                "breakdown": {"promo_return_ngwee": 10_000},
            }
        )
        service = FakeServiceClient(fake)
        assert execute_mod._refunded_total_ngwee(service, ORDER_ID) == 100_000

    def test_concurrent_loser_fails_closed_before_any_money_moves(self) -> None:
        """Pre-check passes, but a racing refund committed first: post-insert re-check rejects."""
        fake = FakeSupabaseClient()
        _seed_order(fake)
        service = FakeServiceClient(fake)
        real = execute_mod._assert_within_paid_cap
        calls = {"n": 0}

        def racing(*args: Any, **kwargs: Any) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                return None  # pre-check saw nothing yet
            return real(*args, **kwargs)

        fake.tables["refunds"].rows.append(
            {
                "id": "racer",
                "order_id": ORDER_ID,
                "source_key": "racer",
                "status": "processing",
                "amount_ngwee": PAID,
                "breakdown": {},
            }
        )
        with (
            _env(fake, _summary(charge=PAID)) as post,
            patch.object(execute_mod, "_assert_within_paid_cap", side_effect=racing),
            pytest.raises(AppError) as exc,
        ):
            _refund(service, "dispute-1")
        assert exc.value.code == "refund_exceeds_paid"
        mine = next(r for r in fake.tables["refunds"].rows if r["source_key"] == "dispute-1")
        assert mine["status"] == "failed"
        post.assert_not_called()
        assert fake.tables["payouts"].rows == []


class TestCapFailureMarkingIsNotLoadBearing:
    def test_stuck_processing_row_over_cap_is_rechecked_on_same_key_retry(self) -> None:
        """If the 'failed' write was lost, a same-key retry must not skip the cap."""
        from app.services.refunds.execute import _refund_source_key

        fake = FakeSupabaseClient()
        _seed_order(fake)
        service = FakeServiceClient(fake)
        with _env(fake, _summary(charge=PAID)) as post:
            _refund(service, "return-1", items=60_000, delivery=0)
            calls_after_first = post.call_count
            # The state a lost 'failed' update leaves behind: a whole-order refund
            # row still 'processing' although 60_000 is already refunded.
            fake.tables["refunds"].rows.append(
                {
                    "id": "stuck-refund",
                    "order_id": ORDER_ID,
                    "source_key": _refund_source_key("dispute-1", ORDER_ID),
                    "lane": 1,
                    "amount_ngwee": PAID,
                    "status": "processing",
                    "breakdown": {"phase": "pre_release", "idempotency_key": "dispute-1"},
                }
            )
            with pytest.raises(AppError) as exc:
                _refund(service, "dispute-1")
        assert exc.value.code == "refund_exceeds_paid"
        # No ledger leg and no payout for the stuck row; it is now marked failed.
        assert post.call_count == calls_after_first
        assert len(fake.tables["payouts"].rows) == 1
        stuck = next(r for r in fake.tables["refunds"].rows if r["id"] == "stuck-refund")
        assert stuck["status"] == "failed"

    def test_failed_marking_error_does_not_mask_the_cap_error(self) -> None:
        """Simulate the race: pre-check passes, post-insert check fails, marking is lost."""
        fake = FakeSupabaseClient()
        _seed_order(fake)
        service = FakeServiceClient(fake)
        real_check = execute_mod._assert_within_paid_cap
        calls = {"n": 0}

        def _second_check_fails(*args: Any, **kwargs: Any) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                return real_check(*args, **kwargs)
            raise AppError("refund_exceeds_paid", "over cap", 409, {})

        with _env(fake, _summary(charge=PAID)):
            refunds = fake.tables["refunds"]
            real_update = refunds.update

            def _lost_update(payload: dict[str, Any]) -> Any:
                if payload.get("status") == "failed":
                    raise RuntimeError("db write lost")
                return real_update(payload)

            with (
                patch.object(execute_mod, "_assert_within_paid_cap", _second_check_fails),
                patch.object(refunds, "update", side_effect=_lost_update),
                pytest.raises(AppError) as exc,
            ):
                _refund(service, "dispute-1")
        assert exc.value.code == "refund_exceeds_paid"
        # The marking was lost, so the row is still 'processing' - the retry test
        # above proves the next same-key call re-checks the cap.
        assert [r["status"] for r in refunds.rows] == ["processing"]
