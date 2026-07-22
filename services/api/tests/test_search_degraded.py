from __future__ import annotations

import asyncio
from collections.abc import Generator
from typing import Any
from uuid import UUID

import pytest
from app.main import create_app
from app.services.search import run_search
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.test_search import (
    FakeSupabaseClient,
    _default_rpc_handler,
    _EmptyTableQuery,
    _semantic_embedding_fetcher,
)

VECTOR_EMBEDDING = [0.1] * 384


async def _raising_embedding_fetcher(_query: str) -> list[float] | None:
    raise RuntimeError("embedding service unavailable")


async def _none_embedding_fetcher(_query: str) -> list[float] | None:
    return None


async def _slow_embedding_fetcher(_query: str) -> list[float] | None:
    await asyncio.sleep(5.0)
    return VECTOR_EMBEDDING


async def _happy_embedding_fetcher(_query: str) -> list[float] | None:
    if "dress" in _query.lower() and "kitchen" in _query.lower():
        return VECTOR_EMBEDDING
    return None


@pytest.fixture
def fake_supabase() -> FakeSupabaseClient:
    return FakeSupabaseClient(_default_rpc_handler)


def _run_search(
    client: FakeSupabaseClient,
    *,
    query: str,
    embedding_fetcher: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    monkeypatch.setattr(
        "app.services.search.fetch_query_embedding",
        embedding_fetcher,
    )
    return asyncio.run(
        run_search(
            client,
            query=query,
            embedding_fetcher=embedding_fetcher,
        )
    )


def test_run_search_degrades_on_embedding_raise(
    fake_supabase: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_search(
        fake_supabase,
        query="itel A70",
        embedding_fetcher=_raising_embedding_fetcher,
        monkeypatch=monkeypatch,
    )
    assert result.degraded is True
    assert result.total >= 1
    assert any("Itel A70" in hit.title for hit in result.results)


def test_run_search_degrades_on_embedding_none(
    fake_supabase: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_search(
        fake_supabase,
        query="itel A70",
        embedding_fetcher=_none_embedding_fetcher,
        monkeypatch=monkeypatch,
    )
    assert result.degraded is True
    assert result.total >= 1
    assert any("Itel A70" in hit.title for hit in result.results)


def test_run_search_degrades_on_embedding_timeout(
    fake_supabase: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_EMBEDDING_TIMEOUT_SECONDS", "0.05")
    result = _run_search(
        fake_supabase,
        query="itel A70",
        embedding_fetcher=_slow_embedding_fetcher,
        monkeypatch=monkeypatch,
    )
    assert result.degraded is True
    assert result.total >= 1
    assert any("Itel A70" in hit.title for hit in result.results)


def test_run_search_happy_path_not_degraded(
    fake_supabase: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_search(
        fake_supabase,
        query="dress for kitchen party",
        embedding_fetcher=_happy_embedding_fetcher,
        monkeypatch=monkeypatch,
    )
    assert result.degraded is False
    titles = [hit.title for hit in result.results]
    assert titles == [
        "Women's Clothing Standard",
        "Kitchenware Standard",
    ]


def test_run_search_retries_when_vector_rpc_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = UUID("00000000-0000-4000-8000-000000000133")

    def handler(name: str, params: dict[str, Any]) -> list[Any]:
        if name == "expand_search_terms":
            return [str(params.get("p_query", ""))]
        if name != "search_rrf":
            return []
        if params.get("query_embedding"):
            raise RuntimeError("vector lane unavailable")
        return [
            {
                "id": str(product_id),
                "entity_kind": "product",
                "entity_id": str(product_id),
                "title": "Itel A70 Smartphone",
                "body": None,
                "category_path": "electronics/phones",
                "price_min_ngwee": 450000,
                "price_max_ngwee": 450000,
                "lat": None,
                "lng": None,
                "locale_terms": None,
                "boost_signals": {},
                "rrf_score": 1.2,
            },
        ]

    class _Client(FakeSupabaseClient):
        def table(self, _name: str) -> _EmptyTableQuery:
            return _EmptyTableQuery()

    async def _vector_embedding_fetcher(_query: str) -> list[float] | None:
        return VECTOR_EMBEDDING

    monkeypatch.setattr(
        "app.services.search.fetch_query_embedding",
        _vector_embedding_fetcher,
    )
    result = asyncio.run(
        run_search(
            _Client(handler),
            query="itel A70",
            embedding_fetcher=_vector_embedding_fetcher,
        )
    )
    assert result.degraded is True
    assert result.total >= 1
    assert result.results[0].title == "Itel A70 Smartphone"


def test_run_search_logs_degradation_once(
    fake_supabase: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO"):
        _run_search(
            fake_supabase,
            query="itel A70",
            embedding_fetcher=_none_embedding_fetcher,
            monkeypatch=monkeypatch,
        )
    degraded_logs = [record for record in caplog.records if record.message == "search_degraded"]
    assert len(degraded_logs) == 1
    assert getattr(degraded_logs[0], "degradation_reason", None) == "embedding_unavailable"


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


def test_search_http_degrades_on_embedding_failure(
    fake_supabase: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.deps import get_supabase_client

    class FakeServiceClient:
        def __init__(self, client: FakeSupabaseClient) -> None:
            self.client = client

    monkeypatch.setattr(
        "app.services.search.fetch_query_embedding",
        _raising_embedding_fetcher,
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


def test_readyz_includes_search_subchecks(client: TestClient) -> None:
    # Default probe is cheap: the vector RPC is NOT called, so search_rpc is unchecked.
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["search_rpc"] == "unchecked"
    assert body["search_embedding"] in {"ok", "degraded"}

    # Opt-in probe surfaces the vector RPC state.
    opted = client.get("/readyz", params={"checks": "search"}).json()
    assert opted["search_rpc"] in {"ok", "degraded"}


def test_readyz_status_ignores_search_health(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overall readiness must reflect Supabase only — search degradation never flips it."""
    import app.routers.health as health

    async def _supabase_up() -> bool:
        return True

    async def _search_down() -> bool:
        return False

    monkeypatch.setattr(health, "_supabase_reachable", _supabase_up)
    monkeypatch.setattr(health, "_search_vector_rpc_present", _search_down)

    # Default: vector RPC not probed; overall stays ok because Supabase is reachable.
    body = client.get("/readyz").json()
    assert body["status"] == "ok"
    assert body["search_rpc"] == "unchecked"

    # Opt-in: vector RPC is down, but overall readiness MUST NOT flip to degraded.
    opted = client.get("/readyz", params={"checks": "search"}).json()
    assert opted["status"] == "ok"
    assert opted["search_rpc"] == "degraded"


def test_readyz_search_embedding_reflects_env(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["search_embedding"] == "degraded"

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["search_embedding"] == "ok"
