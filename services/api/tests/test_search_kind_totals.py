"""Tests for search kind_totals helpers."""

from __future__ import annotations

from app.services.search import SearchHit
from app.services.search.kind_totals import compute_kind_totals, filter_hits_by_kind


def _hit(entity_kind: str, entity_id: str = "1") -> SearchHit:
    return SearchHit.model_validate(
        {
            "id": entity_id,
            "entity_kind": entity_kind,
            "entity_id": entity_id,
            "title": "Sample",
            "rrf_score": 1.0,
        }
    )


def test_compute_kind_totals_groups_products_and_listings() -> None:
    hits = [_hit("product"), _hit("listing", "2"), _hit("service", "3"), _hit("vendor", "4")]
    totals = compute_kind_totals(hits)
    assert totals["all"] == 4
    assert totals["products"] == 2
    assert totals["services"] == 1
    assert totals["vendors"] == 1


def test_filter_hits_by_kind_products_includes_listings() -> None:
    hits = [_hit("product"), _hit("listing", "2"), _hit("service", "3")]
    filtered = filter_hits_by_kind(hits, "products")
    assert len(filtered) == 2
    assert {hit.entity_kind for hit in filtered} == {"product", "listing"}
