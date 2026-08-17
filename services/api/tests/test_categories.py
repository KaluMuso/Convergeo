from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from app.core.ttl_cache import InMemoryTtlCacheStore, clear_ttl_cache_store
from app.deps import get_supabase_client
from app.main import create_app
from app.services.categories.public import (
    CATEGORIES_CACHE_KEY,
    CATEGORIES_CACHE_TTL_SECONDS,
    list_public_categories,
    load_public_categories_from_db,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

PARENT_ID = "11111111-1111-1111-1111-111111111111"
CHILD_ID = "22222222-2222-2222-2222-222222222222"
PROHIBITED_ID = "33333333-3333-3333-3333-333333333333"

SEED_CATEGORIES = [
    {
        "id": PARENT_ID,
        "name": "Electronics",
        "slug": "electronics",
        "path": "electronics",
        "position": 1,
        "parent_id": None,
        "prohibited": False,
    },
    {
        "id": CHILD_ID,
        "name": "Phones",
        "slug": "phones",
        "path": "electronics/phones",
        "position": 2,
        "parent_id": PARENT_ID,
        "prohibited": False,
    },
    {
        "id": PROHIBITED_ID,
        "name": "Restricted",
        "slug": "restricted",
        "path": "restricted",
        "position": 99,
        "parent_id": None,
        "prohibited": True,
    },
]


class FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._filters: list[tuple[str, Any]] = []
        self._order: tuple[str, bool] | None = None

    def select(self, _columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append((column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def execute(self) -> Any:
        rows = list(self._rows)
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column) or 0, reverse=desc)
        return type("Result", (), {"data": rows})()


class FakeSupabaseClient:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        policies: list[dict[str, Any]] | None = None,
    ) -> None:
        self._rows = rows
        self._policies = policies or []
        self.db_calls = 0

    def table(self, name: str) -> FakeQuery:
        self.db_calls += 1
        if name == "category_product_policies":
            return FakeQuery(list(self._policies))
        assert name == "categories"
        return FakeQuery(list(self._rows))


@pytest.fixture(autouse=True)
def _clear_category_cache() -> Generator[None, None, None]:
    clear_ttl_cache_store()
    yield
    clear_ttl_cache_store()


@pytest.fixture
def categories_client() -> Generator[TestClient, None, None]:
    fake = FakeSupabaseClient(SEED_CATEGORIES)

    class FakeServiceClient:
        def __init__(self, client: FakeSupabaseClient) -> None:
            self.client = client

    app: FastAPI = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: FakeServiceClient(fake)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def test_load_public_categories_excludes_prohibited() -> None:
    client = FakeSupabaseClient(SEED_CATEGORIES)
    categories = load_public_categories_from_db(client)
    ids = {category.id for category in categories}
    assert ids == {PARENT_ID, CHILD_ID}
    assert all(not category.prohibited for category in categories)


def test_list_public_categories_uses_cache() -> None:
    client = FakeSupabaseClient(SEED_CATEGORIES)
    store = InMemoryTtlCacheStore()

    first = list_public_categories(client, use_cache=True, store=store)
    assert client.db_calls == 2
    assert len(first) == 2

    second = list_public_categories(client, use_cache=True, store=store)
    assert client.db_calls == 2
    assert [row.model_dump() for row in second] == [row.model_dump() for row in first]


def test_categories_endpoint_matches_db_shape(categories_client: TestClient) -> None:
    response = categories_client.get("/categories")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0] == {
        "id": PARENT_ID,
        "name": "Electronics",
        "slug": "electronics",
        "path": "electronics",
        "position": 1,
        "parent_id": None,
        "prohibited": False,
    }
    assert body[1]["parent_id"] == PARENT_ID


def test_categories_endpoint_sets_cache_control(categories_client: TestClient) -> None:
    response = categories_client.get("/categories")
    cache_control = response.headers.get("cache-control", "")
    assert "s-maxage=3600" in cache_control


def test_load_public_categories_hides_disabled_policy_rows() -> None:
    client = FakeSupabaseClient(
        SEED_CATEGORIES,
        policies=[{"category_id": CHILD_ID, "enabled": False}],
    )
    categories = load_public_categories_from_db(client)
    ids = {category.id for category in categories}
    assert ids == {PARENT_ID}


def test_categories_cache_key_and_ttl_constants() -> None:
    assert CATEGORIES_CACHE_KEY == "public:categories:v2"
    assert CATEGORIES_CACHE_TTL_SECONDS == 3600
