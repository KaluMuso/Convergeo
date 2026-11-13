"""GET /discovery/home end-to-end against a mocked service-role RPC client.

Staging run #55's aftermath proved GET /discovery/home returning HTTP 500,
traced to POST /rest/v1/rpc/bump_rate_counter. Two distinct DB-layer defects
were found and fixed in sequence: bump_rate_counter()'s own outer guard read
a stale JWT-role GUC (20260829120000), and once that cleared, its INSERT
against public.rate_counters still failed the same way inside the
rate_counters_guard_mutation trigger (this migration). Both are proven
against real Postgres in test_bump_rate_counter_service_role_auth.py and
test_guard_rate_counters_mutation_auth_role.py.

This file proves the application layer's own contribution: the route must
return 200 when the rate-counter RPC allows the request, and 429 (not 500)
when it denies — i.e. nothing in the FastAPI route/dependency wiring itself
introduces a 500 on the happy path. It mocks the Supabase RPC client (same
convention as test_pickup_locations.py / test_ratelimit.py), so it cannot by
itself catch a live DB-layer role-check regression — that is what the raw-SQL
trigger/function tests are for.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.main import create_app
from app.routers.catalog import CatalogListResponse, FacetCounts
from app.routers.directory import DirectoryFacets, DirectoryListResponse
from app.services.discovery.home import HomeFeedPayload
from fastapi.testclient import TestClient


class _RpcResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _RpcQuery:
    def __init__(self, response: _RpcResponse) -> None:
        self._response = response

    def execute(self) -> _RpcResponse:
        return self._response


class FakeServiceClient:
    """Mimics the Supabase client's .rpc("bump_rate_counter", ...) surface."""

    def __init__(self, *, bump_rows: list[dict[str, Any]]) -> None:
        self.client = self
        self.bump_rows = bump_rows
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> _RpcQuery:
        self.rpc_calls.append((name, params))
        if name == "bump_rate_counter":
            return _RpcQuery(_RpcResponse(self.bump_rows))
        raise AssertionError(f"unexpected rpc call: {name}")


def _empty_home_payload() -> HomeFeedPayload:
    return HomeFeedPayload(
        newest=CatalogListResponse(items=[], facets=FacetCounts(), total=0, next_cursor=None),
        services=[],
        vendors=DirectoryListResponse(
            items=[], facets=DirectoryFacets(), total=0, page=1, page_size=6
        ),
        department_rails=[],
        trending=[],
    )


@pytest.fixture
def fake_service_client() -> FakeServiceClient:
    return FakeServiceClient(bump_rows=[{"allowed": True, "retry_after_seconds": 0}])


@pytest.fixture
def client(fake_service_client: FakeServiceClient) -> Generator[TestClient, None, None]:
    app = create_app()
    with (
        patch("app.deps.get_supabase_service_client", return_value=fake_service_client),
        patch("app.supabase_client.get_supabase_service_client", return_value=fake_service_client),
        patch(
            "app.routers.discovery.build_home_feed",
            new=AsyncMock(return_value=_empty_home_payload()),
        ),
    ):
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client


class TestDiscoveryHomeRateCounterWiring:
    def test_returns_200_when_service_role_rpc_allows(
        self, client: TestClient, fake_service_client: FakeServiceClient
    ) -> None:
        response = client.get("/discovery/home")
        assert response.status_code == 200
        assert fake_service_client.rpc_calls
        assert fake_service_client.rpc_calls[0][0] == "bump_rate_counter"

    def test_returns_429_not_500_when_rpc_denies(
        self, client: TestClient, fake_service_client: FakeServiceClient
    ) -> None:
        fake_service_client.bump_rows = [{"allowed": False, "retry_after_seconds": 42}]
        response = client.get("/discovery/home")
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "rate_limited"
