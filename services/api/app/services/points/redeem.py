"""Redeem points into a coupon — the seam for the coupon engine (PR #792).

TODO-after-#792: #792's coupon tables (``coupons``/redemptions, ``marketing_expense``
ledger account, ``promo_monthly_budget_ngwee``) are not on release yet. When it
lands, implement ``CouponIssuer`` over ``services/coupons`` and add the SQL
function ``private.points_redeem_for_coupon(user, points, key)`` that, in ONE
transaction: locks the user (same advisory key as earn), checks the balance,
inserts a negative ``redeem`` row keyed ``redeem-<key>``, and issues a platform-
funded coupon drawn from ``promo_monthly_budget_ngwee``. Points never become cash.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class IssuedCoupon:
    coupon_id: str
    code: str
    value_ngwee: int


class CouponIssuer(Protocol):
    def issue_points_coupon(
        self, *, user_id: str, value_ngwee: int, idempotency_key: str
    ) -> IssuedCoupon: ...


class RedeemUnavailable(RuntimeError):
    """Redemption is not wired yet (TODO-after-#792)."""


def redeem_points_for_coupon(
    *, user_id: str, points: int, idempotency_key: str, issuer: CouponIssuer | None = None
) -> IssuedCoupon:
    _ = (user_id, points, idempotency_key)
    if issuer is None:
        msg = "points redemption needs the coupon engine (PR #792)"
        raise RedeemUnavailable(msg)
    msg = "TODO-after-#792: implement via private.points_redeem_for_coupon"
    raise RedeemUnavailable(msg)
