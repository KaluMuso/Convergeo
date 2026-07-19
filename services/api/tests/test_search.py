from __future__ import annotations

from collections.abc import Generator
from typing import Any
from uuid import UUID

import pytest
from app.main import create_app
from app.services.search import call_search_rrf
from fastapi import FastAPI
from fastapi.testclient import TestClient

ITEL_ID = UUID("00000000-0000-4000-8000-000000000133")
CHITENGE_ID = UUID("00000000-0000-4000-8000-000000000136")
DRESS_ID = UUID("00000000-0000-4000-8000-000000000039")
KITCHEN_ID = UUID("00000000-0000-4000-8000-000000000073")


def _hit(
    *,
    entity_id: UUID,
    title: str,
    entity_kind: str = "product",
    category_path: str | None = None,
    price_min_ngwee: int | None = None,
    price_max_ngwee: int | None = None,
    locale_terms: list[str] | None = None,
    score: float = 0.9,
) -> dict[str, Any]:
    return {
        "id": str(UUID(int=entity_id.int % (2**128 - 1))),
        "entity_kind": entity_kind,
        "entity_id": str(entity_id),
        "title": title,
        "body": None,
        "category_path": category_path,
        "price_min_ngwee": price_min_ngwee,
        "price_max_ngwee": price_max_ngwee,
        "lat": None,
        "lng": None,
        "locale_terms": locale_terms,
        "boost_signals": {},
        "rrf_score": score,
    }


ITEL_HIT = _hit(
    entity_id=ITEL_ID,
    title="Itel A70 Smartphone",
    category_path="electronics/phones",
    price_min_ngwee=450000,
    price_max_ngwee=450000,
    score=1.2,
)
CHITENGE_HIT = _hit(
    entity_id=CHITENGE_ID,
    title="6-Yard Chitenge Print",
    category_path="fashion-beauty/chitenge-fabric",
    locale_terms=["chitenge", "chitange"],
    score=1.0,
)
DRESS_HIT = _hit(
    entity_id=DRESS_ID,
    title="Women's Clothing Standard",
    category_path="fashion-beauty/womens-clothing",
    locale_terms=["dress", "nguwafwila"],
    score=0.95,
)
KITCHEN_HIT = _hit(
    entity_id=KITCHEN_ID,
    title="Kitchenware Standard",
    category_path="home-living/kitchenware",
    locale_terms=["kitchenware", "pots", "pans"],
    score=0.7,
)


class FakeRpcResponse:
    def __init__(self, data: list[Any]) -> None:
        self.data = data


class FakeRpc:
    def __init__(self, name: str, params: dict[str, Any], handler: Any) -> None:
        self.name = name
        self.params = params
        self._handler = handler

    def execute(self) -> FakeRpcResponse:
        return FakeRpcResponse(self._handler(self.name, self.params))


class _EmptyTableQuery:
    """No-op table stub so ``attach_route_slugs`` can run against RPC-only fakes."""

    def select(self, *_a: Any, **_k: Any) -> _EmptyTableQuery:
        return self

    def in_(self, *_a: Any, **_k: Any) -> _EmptyTableQuery:
        return self

    def eq(self, *_a: Any, **_k: Any) -> _EmptyTableQuery:
        return self

    def execute(self) -> FakeRpcResponse:
        return FakeRpcResponse([])


class FakeSupabaseClient:
    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpc:
        self.calls.append((name, params))
        return FakeRpc(name, params, self._handler)

    def table(self, _name: str) -> _EmptyTableQuery:
        return _EmptyTableQuery()


def _default_rpc_handler(name: str, params: dict[str, Any]) -> list[Any]:
    if name == "expand_search_terms":
        query = str(params.get("p_query", ""))
        if query.lower() == "chitange":
            return [f"{query} chitenge"]
        return [query]

    if name != "search_rrf":
        return []

    query = str(params.get("query", "")).lower()
    filters = params.get("filters") or {}
    entity_kind = filters.get("entity_kind")
    category_path = filters.get("category_path")
    price_min = filters.get("price_min_ngwee")
    price_max = filters.get("price_max_ngwee")

    candidates: list[dict[str, Any]] = []
    if "itel" in query:
        candidates.append(ITEL_HIT)
    if "chitange" in query or "chitenge" in query:
        candidates.append(CHITENGE_HIT)
    if "dress" in query or "kitchen" in query or "party" in query:
        candidates.extend([DRESS_HIT, KITCHEN_HIT])

    if not candidates and query:
        candidates = [ITEL_HIT, CHITENGE_HIT, DRESS_HIT]

    filtered: list[dict[str, Any]] = []
    for row in candidates:
        if entity_kind is not None and row["entity_kind"] != entity_kind:
            continue
        row_path = row.get("category_path")
        if category_path is not None and (
            not isinstance(row_path, str) or not row_path.startswith(str(category_path))
        ):
            continue
        row_max = row.get("price_max_ngwee")
        if price_min is not None and row_max is not None and row_max < price_min:
            continue
        row_min = row.get("price_min_ngwee")
        if price_max is not None and row_min is not None and row_min > price_max:
            continue
        filtered.append(row)

    return filtered


@pytest.fixture
def fake_supabase() -> FakeSupabaseClient:
    return FakeSupabaseClient(_default_rpc_handler)


@pytest.fixture
def search_client(
    fake_supabase: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    from app.deps import get_supabase_client

    class FakeServiceClient:
        def __init__(self, client: FakeSupabaseClient) -> None:
            self.client = client

    def override() -> FakeServiceClient:
        return FakeServiceClient(fake_supabase)

    monkeypatch.setattr(
        "app.services.search.fetch_query_embedding",
        _semantic_embedding_fetcher,
    )
    app: FastAPI = create_app()
    app.dependency_overrides[get_supabase_client] = override
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


async def _semantic_embedding_fetcher(query: str) -> list[float] | None:
    if "dress" in query.lower() and "kitchen" in query.lower():
        return [0.1] * 384
    return None


async def _failing_embedding_fetcher(_query: str) -> list[float] | None:
    raise RuntimeError("embedding service unavailable")


def test_exact_query_returns_itel_a70(search_client: TestClient) -> None:
    response = search_client.get("/search", params={"q": "itel A70"})
    assert response.status_code == 200
    body = response.json()
    titles = [item["title"] for item in body["results"]]
    assert any("Itel A70" in title for title in titles)
    assert body["total"] >= 1


def test_fuzzy_query_chitange_returns_chitenge(search_client: TestClient) -> None:
    response = search_client.get("/search", params={"q": "chitange"})
    assert response.status_code == 200
    body = response.json()
    assert "chitenge" in body["expanded_query"].lower()
    titles = [item["title"].lower() for item in body["results"]]
    assert any("chitenge" in title for title in titles)


def test_semantic_query_returns_dress_results(search_client: TestClient) -> None:
    response = search_client.get("/search", params={"q": "dress for kitchen party"})
    assert response.status_code == 200
    body = response.json()
    titles = [item["title"].lower() for item in body["results"]]
    assert any("women" in title or "dress" in title for title in titles)
    assert body["degraded"] is False


def test_embedding_failure_degrades_without_500(
    fake_supabase: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.deps import get_supabase_client

    class FakeServiceClient:
        def __init__(self, client: FakeSupabaseClient) -> None:
            self.client = client

    monkeypatch.setattr(
        "app.services.search.fetch_query_embedding",
        _failing_embedding_fetcher,
    )
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: FakeServiceClient(fake_supabase)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/search", params={"q": "itel A70"})
        assert response.status_code == 200
        body = response.json()
        assert body["degraded"] is True
        assert body["total"] >= 1
    app.dependency_overrides.clear()


def test_facet_filters_compose(search_client: TestClient) -> None:
    response = search_client.get(
        "/search",
        params={
            "q": "itel",
            "kind": "products",
            "category_path": "electronics",
            "price_min_ngwee": 400000,
            "price_max_ngwee": 500000,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["title"] == "Itel A70 Smartphone"


def test_injection_safe_tsquery_string(search_client: TestClient) -> None:
    malicious = 'foo & bar | baz !"()'
    response = search_client.get("/search", params={"q": malicious})
    assert response.status_code == 200
    body = response.json()
    assert "results" in body
    assert body["total"] >= 0


def test_suggest_returns_prefix_matches(search_client: TestClient) -> None:
    response = search_client.get("/search/suggest", params={"q": "itel"})
    assert response.status_code == 200
    body = response.json()
    assert body["suggestions"]
    assert all(item["title"].lower().startswith("itel") for item in body["suggestions"])


def test_search_rrf_uses_bound_parameters(fake_supabase: FakeSupabaseClient) -> None:
    hits = call_search_rrf(
        fake_supabase,
        query='foo & bar | baz',
        embedding=None,
        filters={"entity_kind": "product"},
    )
    assert isinstance(hits, list)
    rpc_calls = [call for call in fake_supabase.calls if call[0] == "search_rrf"]
    assert rpc_calls
    _, params = rpc_calls[-1]
    assert params["query"] == 'foo & bar | baz'
    assert "query_embedding" not in params


RETAIL_LISTING_ID = UUID("00000000-0000-4000-8000-0000000004a1")
WHOLESALE_LISTING_ID = UUID("00000000-0000-4000-8000-0000000004a2")


class _ListingTableQuery(_EmptyTableQuery):
    """Minimal PostgREST-ish stub for vendor_listings id/wholesale lookups."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._ids: set[str] | None = None
        self._wholesale_only = False

    def select(self, *_a: Any, **_k: Any) -> _ListingTableQuery:
        return self

    def in_(self, _column: str, values: list[str]) -> _ListingTableQuery:
        self._ids = {str(value) for value in values}
        return self

    def eq(self, column: str, value: Any) -> _ListingTableQuery:
        if column == "wholesale":
            self._wholesale_only = bool(value)
        return self

    def execute(self) -> FakeRpcResponse:
        rows = self._rows
        if self._ids is not None:
            rows = [row for row in rows if str(row.get("id")) in self._ids]
        if self._wholesale_only:
            rows = [row for row in rows if row.get("wholesale")]
        return FakeRpcResponse([{"id": row["id"]} for row in rows])


class FakeClientWithListings(FakeSupabaseClient):
    def __init__(self, handler: Any, listing_rows: list[dict[str, Any]]) -> None:
        super().__init__(handler)
        self._listing_rows = listing_rows

    def table(self, _name: str) -> _ListingTableQuery:
        return _ListingTableQuery(self._listing_rows)


async def _no_embedding(_query: str) -> list[float] | None:
    return None


def _charger_handler(name: str, params: dict[str, Any]) -> list[Any]:
    if name == "expand_search_terms":
        return [str(params.get("p_query", ""))]
    if name != "search_rrf":
        return []
    retail = _hit(
        entity_id=RETAIL_LISTING_ID,
        title="Single Phone Charger",
        entity_kind="listing",
    )
    wholesale = _hit(
        entity_id=WHOLESALE_LISTING_ID,
        title="Bulk Chargers — carton of 50",
        entity_kind="listing",
    )
    return [retail, wholesale]


def _charger_client() -> FakeClientWithListings:
    return FakeClientWithListings(
        _charger_handler,
        [
            {"id": str(RETAIL_LISTING_ID), "wholesale": False},
            {"id": str(WHOLESALE_LISTING_ID), "wholesale": True},
        ],
    )


def test_search_attaches_public_slugs_for_product_and_listing_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Search must emit route slugs — customer PDP looks up by slug, not UUID."""
    import asyncio

    from app.services.search import run_search

    product_id = UUID("a0000133-0000-4000-8000-000000000001")
    listing_id = UUID("1036bd7b-f861-9ea2-b97c-0ddbf22eb2ed")

    def handler(name: str, params: dict[str, Any]) -> list[Any]:
        if name == "expand_search_terms":
            return [str(params.get("p_query", ""))]
        if name != "search_rrf":
            return []
        return [
            _hit(
                entity_id=listing_id,
                title="Itel A70 Smartphone",
                entity_kind="listing",
                score=1.1,
            ),
            _hit(
                entity_id=product_id,
                title="Itel A70 Smartphone",
                entity_kind="product",
                score=1.0,
            ),
        ]

    class _SlugTableQuery(_EmptyTableQuery):
        def __init__(self, table: str) -> None:
            self._table = table
            self._ids: set[str] | None = None
            self._wholesale_only = False

        def select(self, *_a: Any, **_k: Any) -> _SlugTableQuery:
            return self

        def in_(self, _column: str, values: list[str]) -> _SlugTableQuery:
            self._ids = {str(value) for value in values}
            return self

        def eq(self, column: str, value: Any) -> _SlugTableQuery:
            if column == "wholesale":
                self._wholesale_only = bool(value)
            return self

        def execute(self) -> FakeRpcResponse:
            # Wholesale filter probe must not invent wholesale rows.
            if self._wholesale_only:
                return FakeRpcResponse([])
            ids = self._ids or set()
            if self._table == "products":
                rows: list[dict[str, Any]] = [
                    {"id": str(product_id), "slug": "itel-a70"}
                    for entity_id in ids
                    if entity_id == str(product_id)
                ]
                return FakeRpcResponse(rows)
            if self._table == "vendor_listings":
                rows = [
                    {
                        "id": str(listing_id),
                        "products": {"slug": "itel-a70"},
                    }
                    for entity_id in ids
                    if entity_id == str(listing_id)
                ]
                return FakeRpcResponse(rows)
            return FakeRpcResponse([])

    class _Client(FakeSupabaseClient):
        def table(self, name: str) -> _SlugTableQuery:
            return _SlugTableQuery(name)

    monkeypatch.setattr("app.services.search.fetch_query_embedding", _no_embedding)
    result = asyncio.run(run_search(_Client(handler), query="itel"))
    by_kind = {hit.entity_kind: hit for hit in result.results}
    assert by_kind["product"].slug == "itel-a70"
    assert by_kind["listing"].slug == "itel-a70"
    assert by_kind["product"].entity_id == str(product_id)
    assert by_kind["listing"].entity_id == str(listing_id)


def test_search_hides_wholesale_listings_from_consumers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from app.services.search import run_search

    monkeypatch.setattr("app.services.search.fetch_query_embedding", _no_embedding)
    result = asyncio.run(
        run_search(_charger_client(), query="charger", include_wholesale=False)
    )
    ids = {hit.entity_id for hit in result.results}
    assert str(RETAIL_LISTING_ID) in ids
    assert str(WHOLESALE_LISTING_ID) not in ids
    assert result.total == 1


def test_search_shows_wholesale_listings_to_verified_business(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from app.services.search import run_search

    monkeypatch.setattr("app.services.search.fetch_query_embedding", _no_embedding)
    result = asyncio.run(
        run_search(_charger_client(), query="charger", include_wholesale=True)
    )
    ids = {hit.entity_id for hit in result.results}
    assert str(RETAIL_LISTING_ID) in ids
    assert str(WHOLESALE_LISTING_ID) in ids
    assert result.total == 2


def test_suggest_hides_wholesale_listings_from_consumers() -> None:
    from app.services.search import run_suggest

    suggestions = run_suggest(
        _charger_client(), query="charger", include_wholesale=False
    ).suggestions
    titles = {item.title for item in suggestions}
    assert "Single Phone Charger" in titles
    assert "Bulk Chargers — carton of 50" not in titles


def test_zero_result_is_logged(
    fake_supabase: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.services.search import run_search

    def empty_handler(name: str, params: dict[str, Any]) -> list[Any]:
        if name == "expand_search_terms":
            return [str(params.get("p_query", ""))]
        return []

    empty_client = FakeSupabaseClient(empty_handler)
    monkeypatch.setattr(
        "app.services.search.fetch_query_embedding",
        _semantic_embedding_fetcher,
    )

    with caplog.at_level("INFO"):
        import asyncio

        result = asyncio.run(
            run_search(
                empty_client,
                query="absolutely-nothing-matches-xyz",
            )
        )

    assert result.total == 0
    assert any(record.message == "search_zero_result" for record in caplog.records)
