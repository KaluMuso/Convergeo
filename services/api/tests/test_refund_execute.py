"""FIX-B — refund double-execution guard (double payout + double escrow drain).

Proves the caller idempotency_key now flows into the ledger keys + payout reference so a
retry collapses to one ledger drain + one payout, and that a concurrent/duplicate insert
(rejected by the 0032 partial unique index) returns the existing refund without posting a
second ledger transaction or payout.
"""

from __future__ import annotations

import os
import subprocess
import threading
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.services.escrow.order_money_gate import RefundGateDecision
from app.services.ledger.engine import PostedTransaction
from app.services.ledger.templates import LedgerTemplate
from app.services.payments.references import make_refund_reference
from app.services.refunds.execute import RefundPhase, execute_refund
from postgrest.exceptions import APIError

ORDER_ID = "70707070-7070-7070-7070-707070707070"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CUSTOMER_MOMO = "+260971234567"
CALLER_KEY = "dispute-11111111-2222-3333-4444-555555555555-refund"


class IdempotentPostTransaction:
    """Thread-safe stand-in for the ledger engine's ON CONFLICT(idempotency_key) dedup.

    Same idempotency_key returns the same transaction id with ``created=False`` — mirrors
    the real ``post_transaction`` so a duplicated posting cannot drain escrow twice.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_key: dict[str, str] = {}
        self.keys: list[str] = []
        self.created_count = 0

    def __call__(
        self, *, idempotency_key: str, template: LedgerTemplate, **_: Any
    ) -> PostedTransaction:
        with self._lock:
            self.keys.append(idempotency_key)
            existing = self._by_key.get(idempotency_key)
            if existing is not None:
                return PostedTransaction(
                    id=existing, kind=template.value, idempotency_key=idempotency_key, created=False
                )
            txn_id = str(uuid.uuid4())
            self._by_key[idempotency_key] = txn_id
            self.created_count += 1
            return PostedTransaction(
                id=txn_id, kind=template.value, idempotency_key=idempotency_key, created=True
            )


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, _columns: str) -> FakeQuery:
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
            assert self._payload is not None
            row = self._parent.do_insert(dict(self._payload))
            return MagicMock(data=[row])
        if self._pending_op == "update":
            assert self._payload is not None
            with self._parent.lock:
                for row in self._parent.rows:
                    if all(row.get(c) == v for op, c, v in self._filters if op == "eq"):
                        row.update(self._payload)
            return MagicMock(data=[])
        self._parent.on_select(self._filters)
        rows = self._parent.filter_rows(self._filters)
        if self._order is not None:
            col, desc = self._order
            rows = sorted(rows, key=lambda r: r.get(col, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    #: statuses that the 0032 partial unique index treats as occupying an order.
    _ACTIVE = frozenset({"pending", "processing", "completed"})

    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.select_barrier: threading.Barrier | None = None
        self._barrier_tripped = False

    def select(self, columns: str) -> FakeQuery:
        return FakeQuery(self, []).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)

    def on_select(self, filters: list[tuple[str, str, Any]]) -> None:
        # Force both concurrent workers past the "no existing refund" pre-check before
        # either inserts, so the insert-time unique enforcement is genuinely exercised.
        if self.name != "refunds" or self.select_barrier is None:
            return
        with self.lock:
            if self._barrier_tripped:
                return
        try:
            self.select_barrier.wait(timeout=5)
        except threading.BrokenBarrierError:
            pass
        with self.lock:
            self._barrier_tripped = True

    def do_insert(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self.name == "refunds":
                order_id = row.get("order_id")
                status = row.get("status")
                if status in self._ACTIVE and any(
                    r.get("order_id") == order_id and r.get("status") in self._ACTIVE
                    for r in self.rows
                ):
                    raise APIError(
                        {
                            "code": "23505",
                            "message": "duplicate key value violates unique constraint "
                            '"refunds_order_id_active_uniq"',
                        }
                    )
            self.rows.append(row)
            return row

    def filter_rows(self, filters: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        with self.lock:
            result = list(self.rows)
        for op, column, value in filters:
            if op == "eq":
                result = [r for r in result if r.get(column) == value]
        return result


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            name: FakeTable(name)
            for name in (
                "orders",
                "order_items",
                "refunds",
                "payouts",
                "ledger_transactions",
                "platform_config",
            )
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


class FakeServiceClient:
    def __init__(self, client: FakeSupabaseClient) -> None:
        self.client = client


def _seed_order(fake: FakeSupabaseClient, *, item_total: int = 100_000, delivery_fee: int = 5_000,
                released: bool = False) -> None:
    fake.tables["orders"].rows.append(
        {"id": ORDER_ID, "vendor_id": VENDOR_ID, "delivery_fee_ngwee": delivery_fee,
         "status": "delivered"}
    )
    fake.tables["order_items"].rows.append(
        {"order_id": ORDER_ID, "qty": 1, "unit_price_ngwee": item_total}
    )
    if released:
        fake.tables["ledger_transactions"].rows.append(
            {"id": "release-txn-1", "order_id": ORDER_ID, "kind": "release_to_vendor"}
        )


def _gate_decision_for_fake(fake: FakeSupabaseClient):
    """DB-less stand-in for decide_refund_phase_under_gate (avoids real SQL)."""

    def _decide(order_id: str) -> RefundGateDecision:
        released = any(
            row.get("order_id") == order_id and row.get("kind") == "release_to_vendor"
            for row in fake.tables["ledger_transactions"].rows
        )
        if released:
            return RefundGateDecision(phase="post_release", claimed=False)
        return RefundGateDecision(phase="pre_release", claimed=True)

    return _decide


class TestConcurrentAndRetry:
    def test_two_concurrent_execute_refund_one_payout_one_drain(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake, released=False)
        fake.tables["refunds"].select_barrier = threading.Barrier(2)
        service = FakeServiceClient(fake)
        ledger = IdempotentPostTransaction()

        results: list[Any] = []
        errors: list[BaseException] = []
        result_lock = threading.Lock()

        def worker() -> None:
            try:
                res = execute_refund(
                    service_client=service,
                    order_id=ORDER_ID,
                    lane=1,
                    customer_momo=CUSTOMER_MOMO,
                    idempotency_key=CALLER_KEY,
                )
                with result_lock:
                    results.append(res)
            except BaseException as exc:  # noqa: BLE001 — surface any worker failure
                with result_lock:
                    errors.append(exc)

        with (
            patch("app.services.refunds.execute.post_transaction", ledger),
            patch(
                "app.services.refunds.execute.decide_refund_phase_under_gate",
                side_effect=_gate_decision_for_fake(fake),
            ),
        ):
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        assert not errors, f"worker raised: {errors}"
        assert len(results) == 2
        # Exactly one active refund row for the order (the 0032 backstop held).
        active = [r for r in fake.tables["refunds"].rows
                  if r["status"] in FakeTable._ACTIVE]
        assert len(active) == 1
        # Exactly one payout — the loser returned the winner's refund, never paid out.
        assert len(fake.tables["payouts"].rows) == 1
        # Escrow drained exactly once: one distinct ledger idempotency key created.
        assert ledger.created_count == 1
        assert ledger.keys.count(f"{CALLER_KEY}-ledger") == 1
        # Both callers observe the same refund; exactly one performed the creation.
        assert {r.refund_id for r in results} == {active[0]["id"]}
        assert sum(1 for r in results if r.created) == 1
        # The single payout reference is derived from the stable caller key.
        payout_ref = fake.tables["payouts"].rows[0]["lenco_reference"]
        assert payout_ref == make_refund_reference(CALLER_KEY)

    def test_retry_same_idempotency_key_is_idempotent(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake, released=False)
        service = FakeServiceClient(fake)
        ledger = IdempotentPostTransaction()

        with (
            patch("app.services.refunds.execute.post_transaction", ledger),
            patch(
                "app.services.refunds.execute.decide_refund_phase_under_gate",
                side_effect=_gate_decision_for_fake(fake),
            ),
        ):
            first = execute_refund(service_client=service, order_id=ORDER_ID, lane=1,
                                   customer_momo=CUSTOMER_MOMO, idempotency_key=CALLER_KEY)
            second = execute_refund(service_client=service, order_id=ORDER_ID, lane=1,
                                    customer_momo=CUSTOMER_MOMO, idempotency_key=CALLER_KEY)

        assert first.created is True
        assert second.created is False
        assert second.refund_id == first.refund_id
        assert len(fake.tables["payouts"].rows) == 1  # no second payout
        assert ledger.created_count == 1  # no second ledger drain

    def test_duplicate_insert_returns_existing_without_ledger_or_payout(self) -> None:
        # Winner already inserted (fast-path pre-check will still miss it in this thread's
        # snapshot only if seeded after; here we seed it so the insert hits the unique index).
        fake = FakeSupabaseClient()
        _seed_order(fake, released=False)
        winner_id = "c0ffee00-0000-0000-0000-000000000001"
        fake.tables["refunds"].rows.append(
            {"id": winner_id, "order_id": ORDER_ID, "lane": 1, "amount_ngwee": 105_000,
             "status": "processing",
             "breakdown": {"phase": "pre_release", "lenco_reference": "rfd-winner",
                           "ledger_transaction_ids": ["txn-w"]}}
        )
        service = FakeServiceClient(fake)
        ledger = IdempotentPostTransaction()

        with patch("app.services.refunds.execute.post_transaction", ledger):
            result = execute_refund(service_client=service, order_id=ORDER_ID, lane=1,
                                    customer_momo=CUSTOMER_MOMO, idempotency_key=CALLER_KEY)

        assert result.created is False
        assert result.refund_id == winner_id
        assert ledger.created_count == 0
        assert len(fake.tables["payouts"].rows) == 0


class TestKeyDerivation:
    def test_ledger_and_payout_keys_use_caller_key_lane1_pre_release(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake, released=False)
        service = FakeServiceClient(fake)
        ledger = IdempotentPostTransaction()

        with (
            patch("app.services.refunds.execute.post_transaction", ledger),
            patch(
                "app.services.refunds.execute.decide_refund_phase_under_gate",
                side_effect=_gate_decision_for_fake(fake),
            ),
        ):
            result = execute_refund(service_client=service, order_id=ORDER_ID, lane=1,
                                    customer_momo=CUSTOMER_MOMO, idempotency_key=CALLER_KEY)

        assert result.phase == RefundPhase.PRE_RELEASE
        assert ledger.keys == [f"{CALLER_KEY}-ledger"]
        payout_ref = fake.tables["payouts"].rows[0]["lenco_reference"]
        assert payout_ref == make_refund_reference(CALLER_KEY)

    def test_clawback_key_uses_caller_key_post_release(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake, released=True)
        service = FakeServiceClient(fake)
        ledger = IdempotentPostTransaction()

        with (
            patch("app.services.refunds.execute.post_transaction", ledger),
            patch(
                "app.services.refunds.execute.decide_refund_phase_under_gate",
                side_effect=_gate_decision_for_fake(fake),
            ),
        ):
            result = execute_refund(service_client=service, order_id=ORDER_ID, lane=1,
                                    customer_momo=CUSTOMER_MOMO, idempotency_key=CALLER_KEY)

        assert result.phase == RefundPhase.POST_RELEASE
        assert ledger.keys == [f"{CALLER_KEY}-clawback"]

    def test_keys_fall_back_to_order_id_when_no_caller_key(self) -> None:
        fake = FakeSupabaseClient()
        _seed_order(fake, released=False)
        service = FakeServiceClient(fake)
        ledger = IdempotentPostTransaction()
        base = f"refund-order-{ORDER_ID}"

        with (
            patch("app.services.refunds.execute.post_transaction", ledger),
            patch(
                "app.services.refunds.execute.decide_refund_phase_under_gate",
                side_effect=_gate_decision_for_fake(fake),
            ),
        ):
            execute_refund(service_client=service, order_id=ORDER_ID, lane=1,
                           customer_momo=CUSTOMER_MOMO)

        assert ledger.keys == [f"{base}-ledger"]
        assert fake.tables["payouts"].rows[0]["lenco_reference"] == make_refund_reference(base)


# ---------------------------------------------------------------------------
# Real-Postgres backstop: the 0032 partial unique index itself. Gated on a DB URL
# (set FIXB_TEST_DB_URL to a Postgres 16 with all migrations applied) so the suite
# stays hermetic in CI environments without a database.
# ---------------------------------------------------------------------------

_DB_URL = os.environ.get("FIXB_TEST_DB_URL")


def _psql(sql: str) -> subprocess.CompletedProcess[str]:
    assert _DB_URL is not None
    return subprocess.run(
        ["psql", _DB_URL, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
        capture_output=True, text=True, check=False,
    )


@pytest.mark.skipif(_DB_URL is None, reason="FIXB_TEST_DB_URL not set")
class TestPartialUniqueIndexRealPostgres:
    def test_index_rejects_second_active_refund_but_allows_after_failed(self) -> None:
        # Requires a seeded order+vendor; skip cleanly if fixtures are absent.
        oid = _psql("select id::text from public.orders limit 1;")
        assert oid.returncode == 0, oid.stderr
        order_id = oid.stdout.strip()
        if not order_id:
            pytest.skip("no seed order available in target database")

        _psql(f"delete from public.refunds where order_id = '{order_id}';")
        first = _psql(
            f"insert into public.refunds (order_id, lane, amount_ngwee, status) "
            f"values ('{order_id}', 1, 1000, 'processing');"
        )
        assert first.returncode == 0, first.stderr
        second = _psql(
            f"insert into public.refunds (order_id, lane, amount_ngwee, status) "
            f"values ('{order_id}', 1, 1000, 'processing');"
        )
        assert second.returncode != 0
        assert "refunds_order_id_active_uniq" in second.stderr
        # Once the first refund is failed, the order is free for a fresh refund again.
        _psql(f"update public.refunds set status = 'failed' where order_id = '{order_id}';")
        third = _psql(
            f"insert into public.refunds (order_id, lane, amount_ngwee, status) "
            f"values ('{order_id}', 1, 1000, 'processing');"
        )
        assert third.returncode == 0, third.stderr
        _psql(f"delete from public.refunds where order_id = '{order_id}';")
