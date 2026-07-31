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
