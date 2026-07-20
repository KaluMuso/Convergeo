from __future__ import annotations

from typing import Any

from app.schemas.base import NgweeInt, StrictModel
from app.services.ask.filters import AskFilters
from app.services.listings.demo import drop_demo_listing_hits
from app.services.search import SearchHit, call_search_rrf, drop_wholesale_listing_hits
from app.services.search.embedding_client import fetch_query_embedding
from app.services.search.query_builder import build_filters

DEFAULT_TOP_K = 8


class RetrievedDoc(StrictModel):
    entity_kind: str
    entity_id: str
    title: str
    body: str | None = None
    category_path: str | None = None
    price_min_ngwee: NgweeInt | None = None
    price_max_ngwee: NgweeInt | None = None
    rrf_score: float = 0.0


def _hit_to_doc(hit: SearchHit) -> RetrievedDoc:
    return RetrievedDoc(
        entity_kind=hit.entity_kind,
        entity_id=hit.entity_id,
        title=hit.title,
        body=hit.body,
        category_path=hit.category_path,
        price_min_ngwee=hit.price_min_ngwee,
        price_max_ngwee=hit.price_max_ngwee,
        rrf_score=hit.rrf_score,
    )


def _build_rrf_filters(filters: AskFilters) -> dict[str, Any]:
    return build_filters(
        category_path=filters.category_path,
        price_min_ngwee=filters.price_min_ngwee,
        price_max_ngwee=filters.price_max_ngwee,
    )


async def top_k(
    client: Any,
    *,
    query: str,
    filters: AskFilters,
    limit: int = DEFAULT_TOP_K,
    embedding_fetcher: Any | None = None,
) -> list[RetrievedDoc]:
    """Retrieve top-k documents via search_rrf (FTS + trgm + vector fusion)."""
    fetcher = embedding_fetcher or fetch_query_embedding
    embedding = await fetcher(query)

    hits = call_search_rrf(
        client,
        query=query,
        embedding=embedding,
        filters=_build_rrf_filters(filters),
    )
    # Never surface wholesale (B2B) supplies in the consumer "Ask Vergeo" assistant.
    # The answer cache is keyed by query alone, so gating by caller eligibility would
    # leak across users; wholesale discovery lives in the gated supplies feed instead.
    hits = drop_wholesale_listing_hits(client, hits)
    # D25 / VC-P06: demo seed inventory must not ground Ask answers.
    hits = drop_demo_listing_hits(client, hits)
    return [_hit_to_doc(hit) for hit in hits[:limit]]
