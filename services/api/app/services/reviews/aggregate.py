"""Bayesian review aggregation (M15-P02).

Single source of truth for star ratings on cards, PDP, and vendor pages. The heavy lifting
(count/sum/Bayesian/boost-merge) lives in idempotent SQL functions shipped by migration 0028 so
that the incremental-on-write path (the `reviews` trigger) and the nightly bulk path both call
the SAME `recompute_review_aggregate(kind, id)` — they converge by construction, no float drift.

This module is the thin service seam:

* ``recompute_all`` — nightly tick, delegates to ``recompute_all_review_aggregates()``.
* ``apply_review`` — incremental recompute for a single review's order_item (backfill / manual
  reconcile; production writes are handled automatically by the 0028 trigger).
* ``load_bayes_config`` / ``bayesian_average`` — pure Python mirror of the SQL formula, used for
  golden tests and any in-process display maths.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

BAYES_PRIOR_M_KEY = "review_bayes_prior_m"
BAYES_CONFIDENCE_C_KEY = "review_bayes_confidence_c"
DEFAULT_PRIOR_M = Decimal("4.0")
DEFAULT_CONFIDENCE_C = Decimal("10")
BAYES_QUANTUM = Decimal("0.001")


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class BayesConfig:
    """Bayesian shrinkage parameters (mirrors platform_config)."""

    prior_m: Decimal
    confidence_c: Decimal


def bayesian_average(
    rating_sum: int,
    rating_count: int,
    config: BayesConfig,
) -> Decimal:
    """Bayesian-shrunk mean: (C*m + rating_sum) / (C + rating_count), rounded to 3 dp.

    * 0 reviews  -> the prior mean m (a brand-new item is not "5 stars").
    * 1 review   -> shrunk toward m, blocking single-review 5-star gaming.
    * many       -> converges on the true mean.

    ``rating_sum`` / ``rating_count`` are exact integers; only the returned value is fractional.
    """
    numerator = config.confidence_c * config.prior_m + Decimal(rating_sum)
    denominator = config.confidence_c + Decimal(rating_count)
    if denominator == 0:
        return config.prior_m.quantize(BAYES_QUANTUM, rounding=ROUND_HALF_UP)
    return (numerator / denominator).quantize(BAYES_QUANTUM, rounding=ROUND_HALF_UP)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _as_decimal(value: Any, default: Decimal) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return default


def load_bayes_config(service: ServiceRoleClient) -> BayesConfig:
    """Read m / C from platform_config, falling back to the launch defaults."""
    response = (
        service.client.table("platform_config")
        .select("key, value")
        .in_("key", [BAYES_PRIOR_M_KEY, BAYES_CONFIDENCE_C_KEY])
        .execute()
    )
    values = {str(row.get("key")): row.get("value") for row in _rows(response)}
    return BayesConfig(
        prior_m=_as_decimal(values.get(BAYES_PRIOR_M_KEY), DEFAULT_PRIOR_M),
        confidence_c=_as_decimal(values.get(BAYES_CONFIDENCE_C_KEY), DEFAULT_CONFIDENCE_C),
    )


def _rpc_scalar(response: Any) -> int:
    data = getattr(response, "data", None)
    if isinstance(data, int):
        return data
    if isinstance(data, list) and data and isinstance(data[0], int):
        return data[0]
    if isinstance(data, str):
        try:
            return int(data)
        except ValueError:
            return 0
    return 0


def recompute_all(service: ServiceRoleClient) -> int:
    """Nightly bulk recompute of every product/listing/vendor aggregate.

    Returns the number of entities touched. Delegates to the 0028 SQL function so the maths is
    identical to the incremental trigger path.
    """
    response = service.client.rpc("recompute_all_review_aggregates", {}).execute()
    return _rpc_scalar(response)


def apply_review(service: ServiceRoleClient, *, order_item_id: str) -> None:
    """Incrementally recompute the aggregates touched by a single review's order_item.

    Production review writes are recomputed automatically by the 0028 trigger; this entry point
    exists for backfills and manual reconciliation and shares the same SQL recompute, so it can
    never drift from the nightly result.
    """
    service.client.rpc(
        "recompute_review_aggregate_for_order_item",
        {"p_order_item_id": order_item_id},
    ).execute()
