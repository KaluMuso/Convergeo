"""derive_pin: deterministic, per (order, version), and compatible with hash/verify."""

from __future__ import annotations

from app.services.pickup.tokens import derive_pin, hash_pin, verify_pin

ORDER = "57cecf01-9746-424c-8371-9f6743b471ba"


def test_derive_pin_is_deterministic_six_digits() -> None:
    a = derive_pin(order_id=ORDER, version=1, secret="s")
    assert a == derive_pin(order_id=ORDER, version=1, secret="s")
    assert len(a) == 6 and a.isdigit()


def test_derive_pin_changes_with_version_order_and_secret() -> None:
    base = derive_pin(order_id=ORDER, version=1, secret="s")
    variants = [
        derive_pin(order_id=ORDER, version=2, secret="s"),
        derive_pin(order_id="other-order", version=1, secret="s"),
        derive_pin(order_id=ORDER, version=1, secret="t"),
    ]
    # 6-digit space: a collision is possible but these fixed inputs do not collide.
    assert all(v != base for v in variants)


def test_derived_pin_verifies_against_its_hash_and_wrong_pin_fails() -> None:
    pin = derive_pin(order_id=ORDER, version=1, secret="s")
    stored = hash_pin(pin=pin, order_id=ORDER, secret="s")
    assert verify_pin(pin=pin, order_id=ORDER, pin_hash=stored, secret="s")
    wrong = "000000" if pin != "000000" else "111111"
    assert not verify_pin(pin=wrong, order_id=ORDER, pin_hash=stored, secret="s")
