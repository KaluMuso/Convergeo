from __future__ import annotations

from typing import Any

from app.errors import AppError

PriceTier = dict[str, Any]


def select_unit_price_ngwee(
    *,
    base_price_ngwee: int,
    wholesale: bool,
    qty: int,
    price_tiers: list[PriceTier] | None,
) -> int:
    """Pick the best wholesale tier price for qty; otherwise return base retail price."""
    if wholesale and price_tiers:
        applicable = [
            tier
            for tier in price_tiers
            if isinstance(tier.get("min_qty"), int)
            and isinstance(tier.get("price_ngwee"), int)
            and qty >= tier["min_qty"]
        ]
        if applicable:
            best = max(applicable, key=lambda tier: tier["min_qty"])
            return int(best["price_ngwee"])
    return base_price_ngwee


def validate_moq(*, wholesale: bool, moq: int, qty: int) -> None:
    """Reject wholesale lines below vendor MOQ."""
    if wholesale and qty < moq:
        raise AppError(
            code="cart.moq_violation",
            message="Quantity is below the minimum order quantity for this listing",
            http_status=400,
            details={"moq": moq, "qty": qty, "retry": True},
        )


def line_total_ngwee(qty: int, unit_price_ngwee: int) -> int:
    return qty * unit_price_ngwee


def cart_subtotal_ngwee(lines: list[tuple[int, int]]) -> int:
    """Sum line totals from (qty, unit_price_ngwee) pairs."""
    return sum(qty * unit_price for qty, unit_price in lines)
