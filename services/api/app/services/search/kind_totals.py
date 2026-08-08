"""Tab-kind totals derived from a single unkinded search candidate set."""

from __future__ import annotations

from collections import Counter
from typing import Literal, Protocol

from app.services.search.query_builder import SearchKind

SearchKindFilter = Literal["all", "products", "services", "events", "vendors"]


class KindCountableHit(Protocol):
    entity_kind: str


_ENTITY_KIND_TO_TAB: dict[str, SearchKind] = {
    "product": "products",
    "listing": "products",
    "service": "services",
    "event": "events",
    "vendor": "vendors",
}


def filter_hits_by_kind[T: KindCountableHit](hits: list[T], kind: SearchKind | None) -> list[T]:
    """Client-side kind filter — products tab includes both product and listing hits."""
    if kind is None:
        return hits
    if kind == "products":
        return [hit for hit in hits if hit.entity_kind in {"product", "listing"}]
    mapping = {
        "services": "service",
        "events": "event",
        "vendors": "vendor",
        "supplies": "listing",
    }
    entity_kind = mapping.get(kind)
    if entity_kind is None:
        return hits
    return [hit for hit in hits if hit.entity_kind == entity_kind]


def compute_kind_totals[T: KindCountableHit](hits: list[T]) -> dict[SearchKindFilter, int]:
    """Deterministic per-tab counts from one candidate hit list."""
    by_tab = Counter(_ENTITY_KIND_TO_TAB.get(hit.entity_kind, "") for hit in hits)
    return {
        "all": len(hits),
        "products": by_tab.get("products", 0),
        "services": by_tab.get("services", 0),
        "events": by_tab.get("events", 0),
        "vendors": by_tab.get("vendors", 0),
    }
