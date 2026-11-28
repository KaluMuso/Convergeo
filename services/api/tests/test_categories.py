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
        "umbrella": "product",
        "status": "published",
        "show_in_customer": True,
        "image_public_id": "taxonomy/product/electronics",
        "image_alt": "Electronics",
        "icon": None,
    },
    {
        "id": CHILD_ID,
        "name": "Phones",
        "slug": "phones",
        "path": "electronics/phones",
        "position": 2,
        "parent_id": PARENT_ID,
        "prohibited": False,
        "umbrella": "product",
        "status": "published",
        "show_in_customer": True,
    },
    {
        "id": PROHIBITED_ID,
        "name": "Restricted",
        "slug": "restricted",
        "path": "restricted",
        "position": 99,
        "parent_id": None,
        "prohibited": True,
        "umbrella": "product",
        "status": "published",
        "show_in_customer": True,
    },
    {
        "id": "44444444-4444-4444-4444-444444444444",
        "name": "Blocked",
        "slug": "blocked",
        "path": "blocked",
        "position": 50,
        "parent_id": None,
        "prohibited": False,
        "umbrella": "product",
        "status": "blocked",
        "show_in_customer": True,
    },
    {
        "id": "55555555-5555-5555-5555-555555555555",
        "name": "Vendor only",
        "slug": "vendor-only",
        "path": "vendor-only",
        "position": 60,
        "parent_id": None,
        "prohibited": False,
        "umbrella": "wholesale",
        "status": "published",
        "show_in_customer": False,
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
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.db_calls = 0

    def table(self, name: str) -> FakeQuery:
        assert name == "categories"
        self.db_calls += 1
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


def test_public_categories_hide_blocked_and_non_customer_rows() -> None:
    client = FakeSupabaseClient(SEED_CATEGORIES)
    slugs = {category.slug for category in load_public_categories_from_db(client)}
    assert slugs == {"electronics", "phones"}


def test_list_public_categories_uses_cache() -> None:
    client = FakeSupabaseClient(SEED_CATEGORIES)
    store = InMemoryTtlCacheStore()

    first = list_public_categories(client, use_cache=True, store=store)
    assert client.db_calls == 1
    assert len(first) == 2

    second = list_public_categories(client, use_cache=True, store=store)
    assert client.db_calls == 1
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
        "umbrella": "product",
        "image_url": body[0]["image_url"],
        "image_alt": "Electronics",
        "icon": None,
    }
    assert body[0]["image_url"] is None or "taxonomy/product/electronics" in body[0]["image_url"]
    assert body[1]["parent_id"] == PARENT_ID


def test_categories_endpoint_sets_cache_control(categories_client: TestClient) -> None:
    response = categories_client.get("/categories")
    cache_control = response.headers.get("cache-control", "")
    assert "s-maxage=300" in cache_control


def test_categories_cache_key_and_ttl_constants() -> None:
    assert CATEGORIES_CACHE_KEY == "public:categories:v2"
    assert CATEGORIES_CACHE_TTL_SECONDS == 300


def test_event_taxonomy_exposes_persisted_parent_and_hides_blocked_rows() -> None:
    from types import SimpleNamespace

    visible = {"status": "published", "show_in_customer": True, "show_in_vendor": True}

    class EventClient:
        def table(self, name: str) -> FakeQuery:
            assert name == "event_categories"
            return FakeQuery(
                [
                    {
                        "slug": "music",
                        "parent_slug": None,
                        "label_key": "events.categories.music",
                        "name": "Music",
                        "sort": 1,
                        **visible,
                    },
                    {
                        "slug": "concerts",
                        "parent_slug": "music",
                        "label_key": "events.categories.concerts",
                        "name": "Concerts",
                        "sort": 2,
                        **visible,
                    },
                    {
                        "slug": "blocked-one",
                        "parent_slug": "music",
                        "label_key": "unknown",
                        "sort": 3,
                        **visible,
                        "status": "blocked",
                    },
                    {
                        "slug": "orphan",
                        "parent_slug": "blocked-one",
                        "label_key": "unknown",
                        "sort": 4,
                        **visible,
                    },
                ]
            )

    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: SimpleNamespace(client=EventClient())
    with TestClient(app) as client:
        response = client.get("/categories/events")
    assert response.status_code == 200
    body = response.json()
    assert [(row["slug"], row["parent_slug"]) for row in body] == [
        ("music", None),
        ("concerts", "music"),
    ]
    assert body[0]["name"] == "Music"


def test_event_taxonomy_read_failure_is_not_an_empty_success() -> None:
    from types import SimpleNamespace

    class FailedClient:
        def table(self, name: str) -> None:
            raise RuntimeError("unavailable")

    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: SimpleNamespace(client=FailedClient())
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/categories/events").status_code == 500
