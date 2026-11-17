from __future__ import annotations

from typing import Any

from app.services.search import SearchHit
from app.services.search.relevance import (
    apply_relevance_guard,
    has_active_offer,
    hit_matches_lexically,
    is_short_query,
    significant_tokens,
)


def _hit(
    title: str,
    *,
    kind: str = "product",
    price: int | None = 10000,
    body: str | None = None,
    category_path: str | None = None,
    locale_terms: list[str] | None = None,
) -> SearchHit:
    payload: dict[str, Any] = {
        "id": title,
        "entity_kind": kind,
        "entity_id": title,
        "title": title,
        "body": body,
        "category_path": category_path,
        "price_min_ngwee": price,
        "price_max_ngwee": price,
        "locale_terms": locale_terms,
        "rrf_score": 1.0,
    }
    return SearchHit.model_validate(payload)


def test_short_query_detection() -> None:
    assert is_short_query("t-shirt")
    assert is_short_query("phone")
    assert is_short_query("solar panel kit")
    assert not is_short_query("where can i buy a solar fridge in lusaka")
    assert not is_short_query("   ")


def test_significant_tokens_drop_single_letters_and_dedupe() -> None:
    assert significant_tokens("t-shirt", "t-shirt cotton") == ["shirt", "cotton"]


def test_event_tier_is_dropped_for_short_product_queries() -> None:
    tier = _hit("Early Bird Ticket", kind="event", body="Standard entry", price=5000)
    shirt = _hit("Cotton T-Shirt Standard")
    for query in ("t-shirt", "phone"):
        kept = apply_relevance_guard([tier, shirt, _hit("Itel A70 Smartphone")], query=query)
        assert tier not in kept
    assert [h.title for h in apply_relevance_guard([tier, shirt], query="t-shirt")] == [
        "Cotton T-Shirt Standard"
    ]


def test_lexical_matches_plural_stem_alias_and_typo_survive() -> None:
    assert hit_matches_lexically(_hit("Itel A70 Smartphone"), ["phone"])
    assert hit_matches_lexically(_hit("Samsung Phone"), significant_tokens("phones"))
    assert hit_matches_lexically(_hit("Lusaka Plumbing Services", kind="service"), ["plumber"])
    assert hit_matches_lexically(_hit("6-Yard Chitenge Print"), ["chitange"])
    # Alias reaches the hit only through locale terms.
    assert hit_matches_lexically(
        _hit("Women's Clothing", locale_terms=["nguwafwila"]), ["nguwafwila"]
    )
    assert hit_matches_lexically(_hit("TShirt Basic"), ["shirt"])


def test_unrelated_hit_does_not_match() -> None:
    assert not hit_matches_lexically(_hit("Early Bird Ticket", kind="event"), ["shirt"])
    assert not hit_matches_lexically(_hit("Kitchenware Standard"), ["phone"])


def test_expanded_query_synonyms_keep_alias_only_hits() -> None:
    chitenge = _hit("6-Yard Chitenge Print")
    kept = apply_relevance_guard(
        [chitenge], query="citenge fabric", expanded_query="citenge fabric chitenge"
    )
    assert kept == [chitenge]


def test_long_natural_language_queries_keep_semantic_hits() -> None:
    semantic = _hit("Solar Fridge 120L")
    kept = apply_relevance_guard(
        [semantic], query="something to keep my food cold when the power goes off"
    )
    assert kept == [semantic]


def test_products_without_active_offers_are_hidden_even_for_long_queries() -> None:
    no_offer = _hit("Itel A70 Smartphone", price=None)
    priced = _hit("Itel A80 Smartphone")
    long_query = "which smartphone should i buy for my mother in lusaka"
    assert apply_relevance_guard([no_offer, priced], query=long_query) == [priced]
    assert apply_relevance_guard([no_offer, priced], query="smartphone") == [priced]


def test_only_catalogue_products_are_subject_to_the_offer_check() -> None:
    for kind in ("service", "event", "vendor", "listing"):
        assert has_active_offer(_hit("Anything", kind=kind, price=None))
    assert not has_active_offer(_hit("Anything", kind="product", price=None))


def test_empty_hits_and_empty_query_are_noops() -> None:
    assert apply_relevance_guard([], query="phone") == []
    hit = _hit("Anything")
    assert apply_relevance_guard([hit], query="") == [hit]
