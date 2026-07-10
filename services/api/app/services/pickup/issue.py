"""Issue signed pickup QR tokens and hashed PINs when an order is ready for pickup."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from app.errors import AppError
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import sql_uuid
from app.services.pickup.tokens import generate_pin, hash_pin, sign_pickup_qr_token


@dataclass(frozen=True, slots=True)
class PickupIssueResult:
    order_id: str
    vendor_id: str
    qr_token: str
    pin: str
    token_version: int


def _fetch_pickup_order(order_id: str) -> dict[str, str | int | None]:
    order_sql = sql_uuid(order_id, "order_id")
    script = f"""
SELECT
  id::text,
  vendor_id::text,
  status,
  fulfilment,
  coalesce(pickup_token_version, 0)::text
FROM public.orders
WHERE id = {order_sql};
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"pickup order lookup failed: {result.error}")
    if not result.rows:
        raise AppError(code="not_found", message="Order not found", http_status=404)

    parts = result.rows[0].split("|")
    if len(parts) != 5:
        raise RuntimeError("unexpected pickup order lookup shape")

    return {
        "order_id": parts[0],
        "vendor_id": parts[1],
        "status": parts[2],
        "fulfilment": parts[3],
        "token_version": int(parts[4]),
    }


def issue_pickup_tokens(*, order_id: str, reissue: bool = False) -> PickupIssueResult:
    """Generate pickup QR + PIN for a ready pickup order; bumps token version."""
    row = _fetch_pickup_order(order_id)
    if str(row["fulfilment"]) != "pickup":
        raise AppError(
            code="pickup_not_applicable",
            message="Pickup tokens apply only to pickup fulfilment orders",
            http_status=409,
        )
    if str(row["status"]) != "ready":
        raise AppError(
            code="pickup_not_ready",
            message="Pickup tokens can only be issued when the order is ready",
            http_status=409,
        )

    current_version = int(str(row["token_version"]))
    if reissue and current_version == 0:
        raise AppError(
            code="pickup_not_issued",
            message="Cannot re-issue pickup tokens before the first issue",
            http_status=409,
        )

    next_version = current_version + 1
    vendor_id = str(row["vendor_id"])
    nonce = secrets.token_urlsafe(16)
    pin = generate_pin()
    qr_token = sign_pickup_qr_token(
        order_id=order_id,
        vendor_id=vendor_id,
        nonce=nonce,
        version=next_version,
    )
    pin_hash = hash_pin(pin=pin, order_id=order_id)

    order_sql = sql_uuid(order_id, "order_id")
    update_script = f"""
UPDATE public.orders
SET
  pickup_qr_secret = {sql_literal(qr_token)},
  pickup_pin_hash = {sql_literal(pin_hash)},
  pickup_token_version = {next_version}
WHERE id = {order_sql}
  AND status = 'ready'
  AND fulfilment = 'pickup'
  AND pickup_token_version = {current_version}
RETURNING pickup_token_version::text;
"""
    update_result = run_sql_script(update_script)
    if not update_result.ok:
        raise RuntimeError(f"pickup token issue failed: {update_result.error}")
    if not update_result.rows or int(update_result.rows[-1]) != next_version:
        raise AppError(
            code="pickup_issue_conflict",
            message="Pickup token issue conflict; retry",
            http_status=409,
        )

    return PickupIssueResult(
        order_id=order_id,
        vendor_id=vendor_id,
        qr_token=qr_token,
        pin=pin,
        token_version=next_version,
    )
