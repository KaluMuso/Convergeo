"""Busy mode: levels, 30 s cache, audit on change, and the never-pause-money rule."""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.routers import admin_config
from app.services import busy_mode
from app.services.busy_mode import Feature
from pydantic import ValidationError

APP_DIR = pathlib.Path(__file__).resolve().parent.parent / "app"


class FakeClient:
    """Minimal platform_config table behind ``.client.table(...)``."""

    def __init__(self, value: Any = None, *, fail: bool = False) -> None:
        self.value = value
        self.fail = fail
        self.reads = 0
        self.upserts: list[dict[str, Any]] = []
        self.client = MagicMock()
        self.client.table.side_effect = lambda name: self._table(name)

    def _table(self, name: str) -> Any:
        assert name == "platform_config"
        outer = self
        query = MagicMock()

        def execute() -> Any:
            outer.reads += 1
            if outer.fail:
                raise RuntimeError("db down")
            if outer.value is None:
                return MagicMock(data=None)
            return MagicMock(data={"value": outer.value})

        query.select.return_value = query
        query.eq.return_value = query
        query.maybe_single.return_value = query
        query.execute.side_effect = execute

        def upsert(row: dict[str, Any], **_: Any) -> Any:
            outer.upserts.append(row)
            outer.value = row["value"]
            return MagicMock()

        query.upsert.side_effect = upsert
        return query


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    busy_mode.clear_cache()


def test_missing_row_is_level_zero_and_pauses_nothing() -> None:
    client = FakeClient(None)
    assert busy_mode.get_level(client) == 0
    assert busy_mode.paused_features(0) == []


@pytest.mark.parametrize("bad", [True, 7, -1, "3", 2.5])
def test_garbage_values_mean_normal(bad: Any) -> None:
    assert busy_mode.clamp_level(bad) == 0


def test_levels_pause_the_documented_features() -> None:
    assert busy_mode.paused_features(1) == []
    assert busy_mode.paused_features(2) == ["clips_autoplay", "live_counts", "recommendation_rails"]
    assert "ask_vergeo" in busy_mode.paused_features(3)
    assert "personalised_feed" in busy_mode.paused_features(3)
    assert "search_suggest" in busy_mode.paused_features(3)
    assert "clips_feed" not in busy_mode.paused_features(3)
    assert "clips_feed" in busy_mode.paused_features(4)


def test_level_is_cached_for_30_seconds() -> None:
    client = FakeClient(3)
    assert busy_mode.get_level(client) == 3
    client.value = 0
    assert busy_mode.get_level(client) == 3
    assert client.reads == 1
    busy_mode.clear_cache()
    assert busy_mode.get_level(client) == 0


def test_read_error_keeps_last_known_level() -> None:
    client = FakeClient(2)
    assert busy_mode.get_level(client) == 2
    busy_mode.clear_cache()
    busy_mode._cache = (0.0, 2)  # expired, last known 2
    client.fail = True
    assert busy_mode.get_level(client) == 2


def test_read_error_with_no_history_is_normal() -> None:
    assert busy_mode.get_level(FakeClient(fail=True)) == 0


# --- Hard rule: money paths can never be paused ------------------------------
def test_no_feature_names_a_protected_surface() -> None:
    values = {f.value for f in Feature}
    assert not values & busy_mode.PROTECTED_SURFACES
    for value in values:
        for protected in busy_mode.PROTECTED_SURFACES:
            assert protected not in value


MONEY_PATH_FILES = [
    "routers/cart.py",
    "routers/cart_tickets.py",
    "routers/checkout.py",
    "routers/checkout_extras.py",
    "routers/checkout_group.py",
    "routers/checkout_payment.py",
    "routers/orders_create.py",
    "routers/payment_status.py",
    "routers/payments_card.py",
    "routers/webhooks_lenco.py",
    "routers/internal_payment_sweeper.py",
    "routers/internal_payouts.py",
    "routers/vendor_payouts.py",
]
MONEY_PATH_DIRS = [
    "services/cart",
    "services/orders",
    "services/payments",
    "services/escrow",
    "services/ledger",
    "services/payouts",
    "services/refunds",
]


def test_money_paths_never_import_busy_mode() -> None:
    files = [APP_DIR / rel for rel in MONEY_PATH_FILES]
    for rel in MONEY_PATH_DIRS:
        files.extend((APP_DIR / rel).rglob("*.py"))
    assert len(files) > len(MONEY_PATH_FILES)
    for path in files:
        if not path.exists():
            continue
        assert "busy_mode" not in path.read_text(), f"{path} must not depend on busy mode"


def test_only_the_expected_routers_consult_busy_mode() -> None:
    users = sorted(
        str(p.relative_to(APP_DIR))
        for p in APP_DIR.rglob("*.py")
        if "busy_mode" in p.read_text() and p.name != "busy_mode.py"
    )
    assert users == [
        "routers/admin_config.py",
        "routers/ask.py",
        "routers/clips.py",
        "routers/home_feed.py",
        "routers/public_config.py",
        "routers/search.py",
    ]


# --- Admin switch -------------------------------------------------------------
def test_set_level_upserts_audits_and_clears_cache() -> None:
    client = FakeClient(0)
    assert busy_mode.get_level(client) == 0  # warm the cache
    recorder = MagicMock()

    out = asyncio.run(
        admin_config.set_busy_mode(admin_config.BusyModeUpdate(level=3), recorder, client)
    )

    assert out.level == 3 and out.label == "lean"
    assert client.upserts[0]["key"] == "busy_mode_level"
    assert client.upserts[0]["value"] == 3
    recorder.record.assert_called_once()
    kwargs = recorder.record.call_args.kwargs
    assert kwargs["action"] == "config.busy_mode.update"
    assert kwargs["before"]["value"] == 0
    assert kwargs["after"]["value"] == 3
    # The change is visible immediately on this worker (cache cleared).
    assert busy_mode.get_level(client) == 3


@pytest.mark.parametrize("bad", [-1, 5, 99])
def test_out_of_range_level_rejected(bad: int) -> None:
    with pytest.raises(ValidationError):
        admin_config.BusyModeUpdate(level=bad)


def test_platform_patch_cannot_set_busy_level_directly() -> None:
    assert busy_mode.LEVEL_KEY not in admin_config.EDITABLE_PLATFORM_KEYS
