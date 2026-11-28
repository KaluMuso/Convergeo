"""Wrong-vendor PIN attempts get 403 before the PIN is ever checked."""

from __future__ import annotations

import pytest
from app.errors import AppError
from app.services.pickup import verify as verify_mod
from app.services.pickup.tokens import derive_pin, hash_pin

ORDER = "57cecf01-9746-424c-8371-9f6743b471ba"
OWNER = "b1000000-0000-4000-8000-000000000004"
OTHER = "b1000000-0000-4000-8000-000000000005"


def _state() -> dict[str, str | int | bool | None]:
    pin = derive_pin(order_id=ORDER, version=1, secret="s")
    return {
        "order_id": ORDER,
        "vendor_id": OWNER,
        "status": "ready",
        "fulfilment": "pickup",
        "pin_hash": hash_pin(pin=pin, order_id=ORDER, secret="s"),
        "token_version": 1,
        "collected": False,
    }


@pytest.mark.parametrize("pin", ["000000", "123456"])
def test_other_vendor_gets_403_for_any_pin(monkeypatch: pytest.MonkeyPatch, pin: str) -> None:
    monkeypatch.setattr(verify_mod, "_fetch_pickup_state", lambda _oid: _state())
    with pytest.raises(AppError) as exc:
        verify_mod.verify_pickup_by_pin(order_id=ORDER, pin=pin, vendor_id=OTHER, actor_id="u")
    assert exc.value.http_status == 403


def test_owner_with_wrong_pin_still_gets_invalid_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify_mod, "_fetch_pickup_state", lambda _oid: _state())
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "s")
    with pytest.raises(AppError) as exc:
        verify_mod.verify_pickup_by_pin(order_id=ORDER, pin="000001", vendor_id=OWNER, actor_id="u")
    assert exc.value.code == "pickup_invalid_pin"
