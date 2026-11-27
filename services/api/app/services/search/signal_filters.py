"""Signal filter boxes + per-hit signals for ``/search`` (docs/plan/product-signals.md).

Filters run on the already-ranked candidate window (<= ~300 hits), before
pagination, so ``total`` and pages stay consistent. Fail closed: when signals
cannot be loaded and a filter is active, the filter matches nothing rather than
silently showing unfiltered results as "verified".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.signals.loader import (
    build_signals_for_listing_ids,
    build_signals_for_product_ids,
)
from app.services.signals.models import SignalFacts
from app.services.signals.rules import haversine_km

_PRODUCT_KINDS = frozenset({"product", "listing"})


@dataclass(frozen=True, slots=True)
class SearchSignalFilters:
    verified: bool = False
    deals: bool = False
    in_stock: bool = False
    made_in_zambia: bool = False
    min_rating: int | None = None
    radius_km: float | None = None

    @property
    def active(self) -> bool:
        return bool(
            self.verified
            or self.deals
            or self.in_stock
            or self.made_in_zambia
            or self.min_rating is not None
            or self.radius_km is not None
        )


def facts_for_hits(
    client: Any,
    hits: list[Any],
    *,
    user_lat: float | None,
    user_lng: float | None,
) -> dict[tuple[str, str], SignalFacts]:
    """Signal facts keyed by (entity_kind, lower-cased entity_id)."""
    listing_ids = [h.entity_id for h in hits if h.entity_kind == "listing"]
    product_ids = [h.entity_id for h in hits if h.entity_kind == "product"]
    out: dict[tuple[str, str], SignalFacts] = {}
    if listing_ids:
        for key, fact in build_signals_for_listing_ids(
            client, listing_ids, user_lat=user_lat, user_lng=user_lng
        ).items():
            out[("listing", key)] = fact
    if product_ids:
        for key, fact in build_signals_for_product_ids(
            client, product_ids, user_lat=user_lat, user_lng=user_lng
        ).items():
            out[("product", key)] = fact
    return out


def _passes(
    fact: SignalFacts | None,
    hit: Any,
    flt: SearchSignalFilters,
    *,
    user_lat: float | None,
    user_lng: float | None,
) -> bool:
    if fact is None:
        return False
    if flt.verified and not fact.verified:
        return False
    if flt.deals and fact.deal_percent is None:
        return False
    if flt.in_stock and not fact.in_stock:
        return False
    if flt.made_in_zambia and not fact.made_in_zambia:
        return False
    if flt.min_rating is not None and fact.rating < flt.min_rating:
        return False
    if flt.radius_km is not None:
        if user_lat is None or user_lng is None or hit.lat is None or hit.lng is None:
            return False
        if haversine_km(user_lat, user_lng, hit.lat, hit.lng) > flt.radius_km:
            return False
    return True


def apply_signal_filters(
    client: Any,
    hits: list[Any],
    flt: SearchSignalFilters,
    *,
    user_lat: float | None,
    user_lng: float | None,
) -> list[Any]:
    if not flt.active:
        return hits
    facts = facts_for_hits(client, hits, user_lat=user_lat, user_lng=user_lng)
    kept: list[Any] = []
    for hit in hits:
        if hit.entity_kind not in _PRODUCT_KINDS:
            continue  # services / events / vendors have no product signals
        fact = facts.get((hit.entity_kind, str(hit.entity_id).lower()))
        if _passes(fact, hit, flt, user_lat=user_lat, user_lng=user_lng):
            kept.append(hit)
    return kept


def attach_hit_signals(
    client: Any,
    hits: list[Any],
    *,
    user_lat: float | None,
    user_lng: float | None,
) -> None:
    """Set ``hit.signals`` on product / listing hits of the visible page."""
    product_hits = [h for h in hits if h.entity_kind in _PRODUCT_KINDS]
    if not product_hits:
        return
    facts = facts_for_hits(client, product_hits, user_lat=user_lat, user_lng=user_lng)
    for hit in product_hits:
        fact = facts.get((hit.entity_kind, str(hit.entity_id).lower()))
        hit.signals = fact.to_wire() if fact is not None else None
