"""Unit coverage for the operator-facing Lenco sandbox drill script."""

from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

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
    return Namespace(cassette=None, report=None, skip_release=True)


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


@pytest.mark.parametrize(
    ("responses", "expected_status", "expected_observed", "times_out"),
    [
        (
            [{"status": "pending"}, {"status": "success", "amount_ngwee": 25000}],
            "PASS",
            "success",
            False,
        ),
        (
            [{"status": "ussd_pushed"}, {"status": "success", "amount_ngwee": 25000}],
            "PASS",
            "success",
            False,
        ),
        (
            [{"status": "pay_offline"}, {"status": "success", "amount_ngwee": 25000}],
            "PASS",
            "success",
            False,
        ),
        ([{"status": "success", "amount_ngwee": 25000}], "PASS", "success", False),
        ([{"status": "failed"}], "FAIL", "failed", False),
        ([{"status": "expired"}], "FAIL", "expired", False),
        ([{"status": "cancelled"}], "FAIL", "cancelled", False),
        ([{"status": "mystery"}], "FAIL", "mystery", True),
        ([{}], "FAIL", None, True),
        ([{"status": {"unexpected": "state"}}], "FAIL", {"unexpected": "state"}, True),
        (["success"], "FAIL", None, False),
        ([{"status": "pending", "amount_ngwee": 25000}], "FAIL", "pending", True),
    ],
    ids=[
        "pending-then-authoritative-success",
        "ussd-pushed-then-success",
        "pay-offline-then-success",
        "immediate-success",
        "terminal-failure",
        "terminal-expired",
        "terminal-cancelled",
        "unknown-state",
        "missing-state",
        "malformed-state",
        "malformed-response",
        "timeout",
    ],
)
def test_momo_collection_uses_authoritative_settlement(
    monkeypatch: pytest.MonkeyPatch,
    drill_module: Any,
    responses: list[Any],
    expected_status: str,
    expected_observed: Any,
    times_out: bool,
) -> None:
    monkeypatch.setattr(drill_module.time, "sleep", lambda _seconds: None)
    if times_out:
        ticks = iter([0.0, 0.0, 0.0, 121.0, 121.0])
        monkeypatch.setattr(drill_module.time, "monotonic", lambda: next(ticks))

    class FakeApi:
        def __init__(self) -> None:
            self.status_reads = 0
            self.drains = 0
            self.polls = 0

        def payment_retry(self, checkout_group_id: str) -> dict[str, str]:
            assert checkout_group_id == "checkout-1"
            return {"payment_id": "payment-1"}

        def webhook_drain(self) -> None:
            self.drains += 1

        def poll_tick(self) -> None:
            self.polls += 1

        def payment_status(self, checkout_group_id: str) -> Any:
            assert checkout_group_id == "checkout-1"
            response = responses[min(self.status_reads, len(responses) - 1)]
            self.status_reads += 1
            return response

    class FakeLedger:
        def count_charge_received(self, checkout_group_id: str) -> int:
            assert checkout_group_id == "checkout-1"
            return 1

        def charge_received_postings(self, checkout_group_id: str) -> dict[str, int]:
            assert checkout_group_id == "checkout-1"
            return {"platform_cash": 25000, "escrow": -25000}

        def global_sum_ngwee(self) -> int:
            return 0

    config = Namespace(checkout_group_id="checkout-1", payment_id="")
    api = FakeApi()
    result = drill_module.run_momo_collection_live(config, api, FakeLedger())

    assert config.payment_id == "payment-1"
    assert result.status.value == expected_status
    assert api.status_reads == len(responses)
    assert api.drains == api.polls == api.status_reads
    settlement = next(item for item in result.assertions if item.name == "payment_status_success")
    assert settlement.actual == expected_observed
    assert settlement.passed == (expected_status == "PASS")
    assert "pending_not_success" not in {item.name for item in result.assertions}
    assert drill_module._map_gates([result])["S1"] == expected_status
    assert (
        drill_module._final_verdict([result], mode=drill_module.RunMode.LIVE, blockers=[])
        == expected_status
    )
    assert next(item for item in result.assertions if item.name == "charge_received_count").passed
    assert next(item for item in result.assertions if item.name == "global_ledger_balanced").passed
    if expected_status == "PASS":
        assert next(item for item in result.assertions if item.name == "platform_cash_leg").passed
        assert next(item for item in result.assertions if item.name == "escrow_leg").passed
    if times_out and expected_observed == "pending":
        assert next(item for item in result.assertions if item.name == "platform_cash_leg").passed


@pytest.mark.parametrize(
    ("charge_count", "global_sum", "failed_assertion"),
    [
        (2, 0, "charge_received_count"),
        (1, 1, "global_ledger_balanced"),
    ],
    ids=["duplicate-charge", "ledger-imbalance"],
)
def test_success_status_does_not_override_ledger_failure(
    drill_module: Any,
    charge_count: int,
    global_sum: int,
    failed_assertion: str,
) -> None:
    class FakeApi:
        def payment_retry(self, _checkout_group_id: str) -> dict[str, str]:
            return {"payment_id": "payment-1"}

        def webhook_drain(self) -> None:
            pass

        def poll_tick(self) -> None:
            pass

        def payment_status(self, _checkout_group_id: str) -> dict[str, Any]:
            return {"status": "success", "amount_ngwee": 25000}

    class FakeLedger:
        def count_charge_received(self, _checkout_group_id: str) -> int:
            return charge_count

        def charge_received_postings(self, _checkout_group_id: str) -> dict[str, int]:
            return {"platform_cash": 25000, "escrow": -25000}

        def global_sum_ngwee(self) -> int:
            return global_sum

    config = Namespace(checkout_group_id="checkout-1", payment_id="")
    result = drill_module.run_momo_collection_live(config, FakeApi(), FakeLedger())

    assertions = {item.name: item for item in result.assertions}
    assert assertions["payment_status_success"].passed
    assert assertions["platform_cash_leg"].passed
    assert assertions["escrow_leg"].passed
    assert not assertions[failed_assertion].passed
    assert result.status == drill_module.StepStatus.FAIL
    assert drill_module._map_gates([result])["S1"] == "FAIL"
    assert (
        drill_module._final_verdict([result], mode=drill_module.RunMode.LIVE, blockers=[]) == "FAIL"
    )
