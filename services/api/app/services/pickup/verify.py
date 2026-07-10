"""Atomic pickup claim + state-machine transition to delivered."""

from __future__ import annotations

from dataclasses import dataclass

from app.errors import AppError
from app.services.orders.audit import run_sql_script
from app.services.orders.state import (
    ActorRole,
    OrderEvent,
    OrderStatus,
    TransitionOutcome,
    resolve_transition,
    sql_uuid,
    transition_order,
)
from app.services.pickup.tokens import (
    PickupTokenPayload,
    parse_pickup_qr_token,
    verify_pin,
)


@dataclass(frozen=True, slots=True)
class PickupVerifyResult:
    order_id: str
    vendor_id: str
    token_version: int
    transition: TransitionOutcome


def _fetch_pickup_state(order_id: str) -> dict[str, str | int | None]:
    order_sql = sql_uuid(order_id, "order_id")
    script = f"""
SELECT
  id::text,
  vendor_id::text,
  status,
  fulfilment,
  pickup_pin_hash,
  coalesce(pickup_token_version, 0)::text,
  CASE WHEN pickup_collected_at IS NULL THEN 'false' ELSE 'true' END
FROM public.orders
WHERE id = {order_sql};
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"pickup verify lookup failed: {result.error}")
    if not result.rows:
        raise AppError(code="not_found", message="Order not found", http_status=404)

    parts = result.rows[0].split("|")
    if len(parts) != 7:
        raise RuntimeError("unexpected pickup verify lookup shape")

    return {
        "order_id": parts[0],
        "vendor_id": parts[1],
        "status": parts[2],
        "fulfilment": parts[3],
        "pin_hash": parts[4] or None,
        "token_version": int(parts[5]),
        "collected": parts[6] == "true",
    }


def _assert_vendor_scope(*, expected_vendor_id: str, order_vendor_id: str) -> None:
    if expected_vendor_id != order_vendor_id:
        raise AppError(
            code="forbidden",
            message="Vendor may only verify their own orders",
            http_status=403,
            details={"message_key": "vendor.pickup.errors.forbidden"},
        )


def _assert_token_version(*, expected_version: int, current_version: int) -> None:
    if expected_version != current_version:
        raise AppError(
            code="pickup_token_stale",
            message="Pickup token has expired or was re-issued",
            http_status=409,
        )


def _atomic_claim_pickup(*, order_id: str, vendor_id: str, token_version: int) -> bool:
    """Single-use claim: exactly one concurrent caller may set pickup_collected_at."""
    order_sql = sql_uuid(order_id, "order_id")
    vendor_sql = sql_uuid(vendor_id, "vendor_id")
    script = f"""
BEGIN;
WITH locked AS (
  SELECT id
  FROM public.orders
  WHERE id = {order_sql}
    AND vendor_id = {vendor_sql}
    AND pickup_collected_at IS NULL
    AND pickup_token_version = {token_version}
    AND status = 'ready'
    AND fulfilment = 'pickup'
  FOR UPDATE
)
UPDATE public.orders o
SET pickup_collected_at = timezone('utc', now())
FROM locked l
WHERE o.id = l.id
RETURNING o.id::text;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"pickup claim failed: {result.error}")
    return bool(result.rows)


def verify_pickup_by_qr(
    *,
    qr_token: str,
    vendor_id: str,
    actor_id: str,
    note: str = "Pickup verified via QR",
) -> PickupVerifyResult:
    payload = parse_pickup_qr_token(qr_token)
    return _verify_pickup(
        order_id=payload.order_id,
        vendor_id=vendor_id,
        token_version=payload.version,
        actor_id=actor_id,
        note=note,
        qr_payload=payload,
    )


def verify_pickup_by_pin(
    *,
    order_id: str,
    pin: str,
    vendor_id: str,
    actor_id: str,
    note: str = "Pickup verified via PIN",
) -> PickupVerifyResult:
    row = _fetch_pickup_state(order_id)
    pin_hash = row.get("pin_hash")
    if not isinstance(pin_hash, str):
        pin_ok = False
    else:
        pin_ok = verify_pin(pin=pin, order_id=order_id, pin_hash=pin_hash)
    if not pin_ok:
        raise AppError(
            code="pickup_invalid_pin",
            message="Invalid pickup PIN",
            http_status=422,
        )
    return _verify_pickup(
        order_id=order_id,
        vendor_id=vendor_id,
        token_version=int(str(row["token_version"])),
        actor_id=actor_id,
        note=note,
        qr_payload=None,
    )


def _verify_pickup(
    *,
    order_id: str,
    vendor_id: str,
    token_version: int,
    actor_id: str,
    note: str,
    qr_payload: PickupTokenPayload | None,
) -> PickupVerifyResult:
    row = _fetch_pickup_state(order_id)
    order_vendor_id = str(row["vendor_id"])
    _assert_vendor_scope(expected_vendor_id=vendor_id, order_vendor_id=order_vendor_id)

    if qr_payload is not None and qr_payload.vendor_id != order_vendor_id:
        raise AppError(
            code="forbidden",
            message="Vendor may only verify their own orders",
            http_status=403,
            details={"message_key": "vendor.pickup.errors.forbidden"},
        )

    if str(row["fulfilment"]) != "pickup":
        raise AppError(
            code="pickup_not_applicable",
            message="Pickup verification applies only to pickup fulfilment orders",
            http_status=409,
        )
    if bool(row["collected"]):
        raise AppError(
            code="pickup_already_claimed",
            message="Pickup has already been collected",
            http_status=409,
        )

    current_version = int(str(row["token_version"]))
    if current_version < 1:
        raise AppError(
            code="pickup_not_issued",
            message="Pickup tokens have not been issued for this order",
            http_status=409,
        )
    _assert_token_version(expected_version=token_version, current_version=current_version)

    resolved = resolve_transition(
        from_status=OrderStatus(str(row["status"])),
        event=OrderEvent.VERIFY_PICKUP,
        actor_role=ActorRole.VENDOR,
        fulfilment="pickup",
    )
    if not resolved.permitted:
        raise AppError(
            code="order_invalid_transition",
            message=resolved.reason or "Pickup verify transition not permitted",
            http_status=409,
            details={
                "from_status": str(row["status"]),
                "event": OrderEvent.VERIFY_PICKUP.value,
                "actor_role": ActorRole.VENDOR.value,
            },
        )

    if not _atomic_claim_pickup(
        order_id=order_id,
        vendor_id=order_vendor_id,
        token_version=token_version,
    ):
        raise AppError(
            code="pickup_already_claimed",
            message="Pickup has already been collected",
            http_status=409,
        )

    transition = transition_order(
        order_id=order_id,
        event=OrderEvent.VERIFY_PICKUP,
        actor_role=ActorRole.VENDOR,
        actor_id=actor_id,
        note=note,
    )

    return PickupVerifyResult(
        order_id=order_id,
        vendor_id=order_vendor_id,
        token_version=token_version,
        transition=transition,
    )
