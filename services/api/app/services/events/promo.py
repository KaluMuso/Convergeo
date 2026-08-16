"""Promo-code discount math. Redemption is recorded by the purchase path."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from app.errors import AppError
from app.services.stock.claim import run_sql_script, sql_uuid

DiscountKind = Literal["percent", "fixed"]


def apply_promo_discount(
    *,
    line_total_ngwee: int,
    discount_kind: DiscountKind,
    discount_value: int,
) -> int:
    if line_total_ngwee <= 0 or discount_value <= 0:
        return 0
    if discount_kind == "percent":
        if discount_value > 100:
            discount_value = 100
        return (line_total_ngwee * discount_value) // 100
    return min(line_total_ngwee, discount_value)


def assert_promo_redeemable(
    row: dict[str, Any],
    *,
    event_id: str,
    now: datetime | None = None,
    redemption_count: int,
) -> None:
    if str(row.get("event_id")) != event_id:
        raise AppError(
            code="promo_not_found",
            message="Promo code is not valid for this event",
            http_status=422,
            details={"message_key": "events.ticketPurchase.errors.promoInvalid"},
        )
    if row.get("active") is False:
        raise AppError(
            code="promo_inactive",
            message="This promo code is no longer active",
            http_status=422,
            details={"message_key": "events.ticketPurchase.errors.promoInvalid"},
        )
    instant = now or datetime.now(UTC)
    starts = row.get("starts_at")
    ends = row.get("ends_at")
    if isinstance(starts, str) and starts.strip():
        start_dt = datetime.fromisoformat(starts.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=UTC)
        if instant < start_dt.astimezone(UTC):
            raise AppError(
                code="promo_not_started",
                message="This promo code is not active yet",
                http_status=422,
                details={"message_key": "events.ticketPurchase.errors.promoInvalid"},
            )
    if isinstance(ends, str) and ends.strip():
        end_dt = datetime.fromisoformat(ends.replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=UTC)
        if instant > end_dt.astimezone(UTC):
            raise AppError(
                code="promo_expired",
                message="This promo code has expired",
                http_status=422,
                details={"message_key": "events.ticketPurchase.errors.promoInvalid"},
            )
    max_redemptions = row.get("max_redemptions")
    if isinstance(max_redemptions, int) and redemption_count >= max_redemptions:
        raise AppError(
            code="promo_exhausted",
            message="This promo code has been fully redeemed",
            http_status=422,
            details={"message_key": "events.ticketPurchase.errors.promoInvalid"},
        )


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def resolve_promo_discount(
    client: Any,
    *,
    event_id: str,
    code: str | None,
    line_total_ngwee: int,
) -> tuple[int, str | None, str | None]:
    """Return (discount_ngwee, promo_id, normalized_code). Zero discount if unused."""
    if not code or not code.strip():
        return 0, None, None
    normalized = code.strip().upper()
    response = (
        client.table("event_promo_codes")
        .select(
            "id, event_id, code, discount_kind, discount_value, max_redemptions, "
            "starts_at, ends_at, active"
        )
        .eq("event_id", event_id)
        .eq("code", normalized)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="promo_not_found",
            message="Promo code is not valid for this event",
            http_status=422,
            details={"message_key": "events.ticketPurchase.errors.promoInvalid"},
        )
    promo_id = str(row["id"])
    count_result = run_sql_script(
        f"""
SELECT count(*)::text FROM public.event_promo_redemptions
WHERE promo_id = {sql_uuid(promo_id, "promo_id")};
"""
    )
    redemption_count = int(count_result.rows[0]) if count_result.ok and count_result.rows else 0
    assert_promo_redeemable(row, event_id=event_id, redemption_count=redemption_count)
    kind = row.get("discount_kind")
    if kind not in {"percent", "fixed"}:
        raise AppError(
            code="promo_not_found",
            message="Promo code is not valid for this event",
            http_status=422,
            details={"message_key": "events.ticketPurchase.errors.promoInvalid"},
        )
    discount = apply_promo_discount(
        line_total_ngwee=line_total_ngwee,
        discount_kind=kind,
        discount_value=int(row.get("discount_value") or 0),
    )
    return discount, promo_id, normalized


def record_promo_redemption(
    *,
    promo_id: str,
    event_id: str,
    order_id: str,
    customer_id: str,
    discount_ngwee: int,
) -> None:
    promo_sql = sql_uuid(promo_id, "promo_id")
    event_sql = sql_uuid(event_id, "event_id")
    order_sql = sql_uuid(order_id, "order_id")
    customer_sql = sql_uuid(customer_id, "customer_id")
    result = run_sql_script(
        f"""
INSERT INTO public.event_promo_redemptions (
  promo_id, event_id, order_id, customer_id, discount_ngwee
) VALUES (
  {promo_sql}, {event_sql}, {order_sql}, {customer_sql}, {int(discount_ngwee)}
)
ON CONFLICT (order_id) DO NOTHING;
"""
    )
    if not result.ok:
        raise RuntimeError(f"promo redemption insert failed: {result.error}")

