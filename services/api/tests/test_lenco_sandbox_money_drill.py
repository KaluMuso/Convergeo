"""Unit coverage for the operator-facing Lenco sandbox drill script."""

from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest


@pytest.fixture
def drill_module() -> Any:
    script = Path(__file__).resolve().parents[3] / "scripts/drills/lenco_sandbox_money_drill.py"
    spec = importlib.util.spec_from_file_location("lenco_sandbox_money_drill_test", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def _args() -> Namespace:
    return Namespace(
        acceptance_evidence=None,
        cassette=None,
        report=None,
        skip_release=True,
    )


def _cassette(drill_module: Any) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(drill_module.DEFAULT_CASSETTE.read_text(encoding="utf-8")),
    )


def test_airtel_uses_the_airtel_sandbox_number_and_collection_rail(
    monkeypatch: pytest.MonkeyPatch,
    drill_module: Any,
) -> None:
    monkeypatch.setenv("DRILL_MOMO_RAIL", "airtel")
    monkeypatch.delenv("DRILL_MOMO_NUMBER", raising=False)
    config = drill_module.DrillConfig.from_env(
        mode=drill_module.RunMode.LIVE,
        args=_args(),
    )

    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"payment_id": "payment-airtel"}

    class FakeHttp:
        def post(self, _path: str, **kwargs: Any) -> FakeResponse:
            captured.update(kwargs["json"])
            return FakeResponse()

    client = object.__new__(drill_module.ApiDrillClient)
    client.config = config
    client.http = FakeHttp()

    assert client.payment_retry("checkout-airtel") == {"payment_id": "payment-airtel"}
    assert config.momo_number == "0971111111"
    assert captured == {
        "checkout_group_id": "checkout-airtel",
        "payer_number": "0971111111",
        "rail": "airtel",
    }


def test_live_drill_rejects_an_unsupported_collection_rail(
    monkeypatch: pytest.MonkeyPatch,
    drill_module: Any,
) -> None:
    monkeypatch.setenv("DRILL_MOMO_RAIL", "zamtel")
    config = drill_module.DrillConfig.from_env(
        mode=drill_module.RunMode.LIVE,
        args=_args(),
    )

    ready, blockers = config.live_ready()

    assert not ready
    assert "DRILL_MOMO_RAIL must be 'mtn' or 'airtel'" in blockers


def test_cassette_uses_actual_order_ledger_shapes_and_separate_card_identities(
    drill_module: Any,
) -> None:
    cassette = _cassette(drill_module)

    steps = drill_module.run_cassette_steps(cassette)

    assert [step.status for step in steps] == [drill_module.StepStatus.PASS] * 4
    momo = cassette["steps"]["momo_collection"]
    assert momo["charge_received_count"] == 0
    assert momo["escrow_hold_count"] == momo["order_count"]
    card = cassette["steps"]["card_verification"]
    assert card["negative_checkout_group_id"] != cassette["checkout_group_id"]
    assert card["positive_checkout_group_id"] != card["negative_checkout_group_id"]


@pytest.mark.parametrize(
    ("step_name", "path", "unsafe_value", "assertion_name"),
    [
        ("momo_collection", ("momo_collection", "order_count"), 0, "product_order_count_nonzero"),
        (
            "momo_collection",
            ("momo_collection", "idempotency_key_count"),
            1,
            "escrow_hold_idempotency_keys",
        ),
        (
            "momo_collection",
            ("momo_collection", "ledger_postings", "platform_cash"),
            1,
            "platform_cash_leg",
        ),
        (
            "webhook_replay",
            ("webhook_replay", "ledger_txn_count_after"),
            2,
            "ledger_txn_count_unchanged",
        ),
        (
            "release_payout_refund",
            ("release_payout_refund", "payout_status"),
            "pending",
            "vendor_payout_provider_terminal",
        ),
        (
            "release_payout_refund",
            ("release_payout_refund", "refund_payout_linked"),
            False,
            "refund_payout_linkage",
        ),
        (
            "release_payout_refund",
            ("release_payout_refund", "clawback_count"),
            0,
            "post_release_refund_uses_clawback",
        ),
        (
            "release_payout_refund",
            ("release_payout_refund", "vendor_id"),
            "",
            "vendor_identity_present",
        ),
        (
            "card_verification",
            ("card_verification", "positive_with_provider_evidence", "receipt_count"),
            0,
            "positive_receipt_exactly_once",
        ),
    ],
)
def test_cassette_negative_controls_fail_for_the_intended_assertion(
    drill_module: Any,
    step_name: str,
    path: tuple[str, ...],
    unsafe_value: object,
    assertion_name: str,
) -> None:
    cassette = deepcopy(_cassette(drill_module))
    target: dict[str, Any] = cassette["steps"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = unsafe_value

    steps = drill_module.run_cassette_steps(cassette)
    step = next(item for item in steps if item.name == step_name)

    assert step.status == drill_module.StepStatus.FAIL
    assertion = next(item for item in step.assertions if item.name == assertion_name)
    assert not assertion.passed


def test_cassette_rejects_reused_card_checkout(drill_module: Any) -> None:
    cassette = deepcopy(_cassette(drill_module))
    card = cassette["steps"]["card_verification"]
    card["positive_checkout_group_id"] = card["negative_checkout_group_id"]

    step = next(
        item
        for item in drill_module.run_cassette_steps(cassette)
        if item.name == "card_verification"
    )

    assert step.status == drill_module.StepStatus.FAIL
    assert not next(
        item
        for item in step.assertions
        if item.name == "positive_card_checkout_distinct_from_negative"
    ).passed


def test_live_initial_success_is_not_accepted_as_pending(
    monkeypatch: pytest.MonkeyPatch,
    drill_module: Any,
) -> None:
    class Api:
        def payment_retry(self, _checkout_id: str) -> dict[str, str]:
            return {"payment_id": "payment-1"}

        def payment_status(self, _checkout_id: str) -> dict[str, object]:
            return {"status": "success"}

    class Db:
        def scalar(self, _sql: str) -> str:
            return "2"

    class Ledger:
        db = Db()

        def count_orders(self, _checkout_id: str) -> int:
            return 2

        def count_charge_received(self, _checkout_id: str) -> int:
            return 0

        def count_collection_kind(self, _checkout_id: str, *, kind: str) -> int:
            assert kind == "escrow_hold"
            return 2

        def collection_postings(self, _checkout_id: str) -> dict[str, int]:
            return {"platform_cash": 25000, "escrow": -25000}

        def global_sum_ngwee(self) -> int:
            return 0

    config = Namespace(checkout_group_id="checkout-1", payment_id="")
    monkeypatch.setattr(
        drill_module,
        "_wait_for_payment_success",
        lambda *_args, **_kwargs: {"status": "success", "amount_ngwee": 25000},
    )

    result = drill_module.run_momo_collection_live(config, Api(), Ledger())

    assert result.status == drill_module.StepStatus.FAIL
    assert not next(
        item for item in result.assertions if item.name == "initial_status_not_success"
    ).passed


def test_escrow_probe_includes_checkout_funding_and_order_linkage(drill_module: Any) -> None:
    captured: dict[str, str] = {}

    class Db:
        def scalar(self, sql: str) -> str:
            captured["sql"] = sql
            return "0"

    probe = drill_module.LedgerProbe(Db())

    assert probe.escrow_remaining_ngwee("checkout-1", order_id="order-1") == 0
    assert "lt.checkout_group_id = 'checkout-1'::uuid" in captured["sql"]
    assert "OR lt.order_id = 'order-1'::uuid" in captured["sql"]


def test_release_refund_uses_customer_rail_and_payout_linked_terminal_evidence(
    monkeypatch: pytest.MonkeyPatch,
    drill_module: Any,
) -> None:
    captured: dict[str, Any] = {}

    class Api:
        def release_tick(self) -> dict[str, int]:
            return {}

        def payouts_tick(self) -> dict[str, int]:
            return {}

        def payouts_retry(self) -> dict[str, int]:
            return {}

        def admin_refund_execute(self, body: dict[str, Any]) -> dict[str, str]:
            captured.update(body)
            return {
                "refund_id": "00000000-0000-4000-8000-000000000005",
                "payout_id": "00000000-0000-4000-8000-000000000006",
            }

    class Db:
        dsn = "postgresql://isolated"

    class Ledger:
        db = Db()

        def count_kind(self, *, kind: str, order_id: str | None = None) -> int:
            assert order_id
            return 1 if kind in {"commission_capture", "release_to_vendor"} else 0

        def count_kind_for_payout(self, *, kind: str, payout_id: str) -> int:
            assert kind == "payout_executed"
            assert payout_id.endswith("4")
            return 1

        def payout_status(self, _payout_id: str) -> str:
            return "paid"

        def refund_payout_id(self, _refund_id: str) -> str:
            return "00000000-0000-4000-8000-000000000006"

        def refund_status(self, _refund_id: str) -> str:
            return "completed"

        def count_kind_for_refund(self, *, kind: str, refund_id: str) -> int:
            assert kind == "clawback"
            assert refund_id.endswith("5")
            return 1

        def escrow_remaining_ngwee(self, _checkout_id: str, *, order_id: str) -> int:
            assert order_id
            return 0

        def count_orphaned_payouts(self, _vendor_id: str) -> int:
            return 0

        def global_sum_ngwee(self) -> int:
            return 0

    monkeypatch.setattr(
        drill_module.subprocess,
        "run",
        lambda *_args, **_kwargs: Namespace(
            returncode=0,
            stdout="00000000-0000-4000-8000-000000000009\n",
            stderr="",
        ),
    )
    config = Namespace(
        skip_release=False,
        order_id="00000000-0000-4000-8000-000000000001",
        checkout_group_id="00000000-0000-4000-8000-000000000002",
        allow_sql_setup=False,
        vendor_payout_id="00000000-0000-4000-8000-000000000004",
        admin_token="admin",
        momo_number="0961111111",
        momo_rail="mtn",
    )

    result = drill_module.run_release_refund_live(config, Api(), Ledger())

    assert result.status == drill_module.StepStatus.PASS
    assert captured["customer_rail"] == "mtn"
    assert "rail" not in captured


def test_release_refund_blocks_when_admin_evidence_is_missing(
    drill_module: Any,
) -> None:
    class Api:
        def release_tick(self) -> dict[str, int]:
            return {}

        def payouts_tick(self) -> dict[str, int]:
            return {}

    class Ledger:
        def count_kind(self, *, kind: str, order_id: str | None = None) -> int:
            return 1

        def count_kind_for_payout(self, *, kind: str, payout_id: str) -> int:
            return 1

        def payout_status(self, _payout_id: str) -> str:
            return "paid"

    config = Namespace(
        skip_release=False,
        order_id="00000000-0000-4000-8000-000000000001",
        checkout_group_id="00000000-0000-4000-8000-000000000002",
        allow_sql_setup=False,
        vendor_payout_id="00000000-0000-4000-8000-000000000004",
        admin_token="",
    )

    result = drill_module.run_release_refund_live(config, Api(), Ledger())

    assert result.status == drill_module.StepStatus.BLOCKED
    assert "refund evidence cannot be skipped" in result.detail


def test_live_full_verdict_rejects_skip_and_missing_24_row_evidence(drill_module: Any) -> None:
    steps = [
        drill_module.StepResult(name=name, status=drill_module.StepStatus.PASS)
        for name in (
            "preflight",
            "momo_collection",
            "webhook_replay",
            "release_payout_refund",
            "card_verification",
        )
    ]

    assert (
        drill_module._final_verdict(
            steps,
            mode=drill_module.RunMode.LIVE,
            blockers=[],
            acceptance=None,
        )
        == "BLOCKED_EXTERNAL"
    )
    steps[-1].status = drill_module.StepStatus.SKIP
    assert (
        drill_module._final_verdict(
            steps,
            mode=drill_module.RunMode.LIVE,
            blockers=[],
            acceptance=None,
        )
        == "BLOCKED_EXTERNAL"
    )


def test_live_full_verdict_rejects_duplicate_step_even_with_all_names(drill_module: Any) -> None:
    steps = [
        drill_module.StepResult(name=name, status=drill_module.StepStatus.PASS)
        for name in (
            "preflight",
            "momo_collection",
            "webhook_replay",
            "release_payout_refund",
            "card_verification",
            "preflight",
        )
    ]

    assert (
        drill_module._final_verdict(
            steps,
            mode=drill_module.RunMode.LIVE,
            blockers=[],
            acceptance=Namespace(certifiable=True),
        )
        == "BLOCKED_EXTERNAL"
    )
