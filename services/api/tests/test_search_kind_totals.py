"""Tests for search kind_totals helpers + single-RRF proof."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.services.search import SearchHit, run_search
from app.services.search.kind_totals import compute_kind_totals, filter_hits_by_kind
from app.services.search.query_builder import SearchKind, build_filters


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


async def _no_embedding(_term: str) -> None:
    return None


def _stub_search_side_effects(
    monkeypatch: pytest.MonkeyPatch, hits: list[SearchHit]
) -> list[dict[str, Any]]:
    """Patch RRF + post filters; return a list that records each RRF call's kwargs."""
    import app.services.search as search_mod

    calls: list[dict[str, Any]] = []

    def _rrf(*_args: Any, **kwargs: Any) -> list[SearchHit]:
        calls.append(kwargs)
        return list(hits)

    monkeypatch.setattr(search_mod, "expand_query", lambda _client, q: q)
    monkeypatch.setattr(search_mod, "call_search_rrf", _rrf)
    monkeypatch.setattr(search_mod, "drop_wholesale_listing_hits", lambda _c, h: h)
    monkeypatch.setattr(search_mod, "drop_demo_listing_hits", lambda _c, h: h)
    monkeypatch.setattr(search_mod, "attach_open_now", lambda _c, h: h)
    monkeypatch.setattr(search_mod, "attach_route_slugs", lambda _c, h: h)
    monkeypatch.setattr(search_mod, "log_search_query", lambda **_kw: None)
    monkeypatch.setattr(search_mod, "log_zero_result", lambda **_kw: None)
    monkeypatch.setattr(search_mod, "call_search_query_facets", lambda *_a, **_kw: None)
    return calls


@pytest.mark.asyncio
async def test_include_kind_totals_single_rrf_not_five(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proof: include_kind_totals=true → exactly 1 search_rrf call (not 5 kind fan-out)."""
    hits = [
        _hit("product", "p1"),
        _hit("listing", "l1"),
        _hit("service", "s1"),
        _hit("event", "e1"),
        _hit("vendor", "v1"),
    ]
    calls = _stub_search_side_effects(monkeypatch, hits)

    resp = await run_search(
        MagicMock(),
        query="phone",
        kind="products",
        include_kind_totals=True,
        embedding_fetcher=_no_embedding,
        include_wholesale=True,
    )

    assert len(calls) == 1, f"expected 1 RRF RPC, got {len(calls)}"
    # Unkinded RPC filters — kind stripped so one candidate set feeds all tabs.
    assert calls[0]["filters"] == build_filters(kind=None)
    assert resp.kind_totals is not None
    assert resp.kind_totals.all == 5
    assert resp.kind_totals.products == 2
    assert resp.kind_totals.services == 1
    assert resp.kind_totals.events == 1
    assert resp.kind_totals.vendors == 1
    assert all(hit.entity_kind in {"product", "listing"} for hit in resp.results)


@pytest.mark.asyncio
async def test_without_kind_totals_passes_kind_to_rrf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hits = [_hit("product", "p1")]
    calls = _stub_search_side_effects(monkeypatch, hits)

    resp = await run_search(
        MagicMock(),
        query="phone",
        kind="products",
        include_kind_totals=False,
        embedding_fetcher=_no_embedding,
        include_wholesale=True,
    )

    assert len(calls) == 1
    assert calls[0]["filters"] == build_filters(kind="products")
    assert resp.kind_totals is None


@pytest.mark.asyncio
async def test_legacy_five_kind_fanout_would_call_rrf_five_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Document before/after: naive tab counts = 5 RRF; unified path = 1."""
    hits = [_hit("product", "p1"), _hit("service", "s1")]
    calls = _stub_search_side_effects(monkeypatch, hits)

    kinds: list[SearchKind | None] = [None, "products", "services", "events", "vendors"]
    for kind in kinds:
        await run_search(
            MagicMock(),
            query="phone",
            kind=kind,
            include_kind_totals=False,
            embedding_fetcher=_no_embedding,
            include_wholesale=True,
        )

    assert len(calls) == 5

    calls.clear()
    await run_search(
        MagicMock(),
        query="phone",
        kind="products",
        include_kind_totals=True,
        embedding_fetcher=_no_embedding,
        include_wholesale=True,
    )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_kind_totals_path_latency_not_worse_than_five_fanout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timed evidence: unified path finishes well under a 5× sequential fan-out."""
    hits = [_hit("product", f"p{i}") for i in range(20)] + [_hit("service", "s1")]

    def _slow_rrf(*_a: Any, **_k: Any) -> list[SearchHit]:
        time.sleep(0.005)
        return list(hits)

    import app.services.search as search_mod

    monkeypatch.setattr(search_mod, "expand_query", lambda _client, q: q)
    monkeypatch.setattr(search_mod, "call_search_rrf", _slow_rrf)
    monkeypatch.setattr(search_mod, "drop_wholesale_listing_hits", lambda _c, h: h)
    monkeypatch.setattr(search_mod, "drop_demo_listing_hits", lambda _c, h: h)
    monkeypatch.setattr(search_mod, "attach_open_now", lambda _c, h: h)
    monkeypatch.setattr(search_mod, "attach_route_slugs", lambda _c, h: h)
    monkeypatch.setattr(search_mod, "log_search_query", lambda **_kw: None)
    monkeypatch.setattr(search_mod, "log_zero_result", lambda **_kw: None)
    monkeypatch.setattr(search_mod, "call_search_query_facets", lambda *_a, **_kw: None)

    t0 = time.perf_counter()
    await run_search(
        MagicMock(),
        query="phone",
        kind="products",
        include_kind_totals=True,
        embedding_fetcher=_no_embedding,
        include_wholesale=True,
    )
    unified_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    kinds2: list[SearchKind | None] = [None, "products", "services", "events", "vendors"]
    for kind in kinds2:
        await run_search(
            MagicMock(),
            query="phone",
            kind=kind,
            include_kind_totals=False,
            embedding_fetcher=_no_embedding,
            include_wholesale=True,
        )
    fanout_ms = (time.perf_counter() - t1) * 1000

    # Unified must be substantially faster than five sequential RRF calls.
    assert unified_ms < fanout_ms * 0.5, (
        f"unified={unified_ms:.1f}ms fanout={fanout_ms:.1f}ms — expected ~5× speedup"
    )
