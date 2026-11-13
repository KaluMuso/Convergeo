"""``GET /home/stream`` — keyset-paginated "Popular now" listing stream."""

from __future__ import annotations

import base64
import json
from collections.abc import Generator
from typing import Any

import pytest
from app.main import create_app
from app.services.home_feed.stream import (
    HomeStreamPage,
    build_stream_page,
    decode_stream_cursor,
    encode_stream_cursor,
)
from fastapi.testclient import TestClient
from tests.test_catalog import FakeSupabaseClient, _listing, _search_doc

ACTIVE_VENDOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SUSPENDED_VENDOR = "cccccccc-cccc-cccc-cccc-cccccccccccc"
BLOCKED_VENDOR = "dddddddd-dddd-dddd-dddd-dddddddddddd"


def _id(n: int) -> str:
    return f"e1000000-0000-0000-0000-{n:012d}"


def _store(visible: int = 14) -> dict[str, list[dict[str, Any]]]:
    store: dict[str, list[dict[str, Any]]] = {
        "search_documents": [],
        "vendor_listings": [],
        "vendors": [
            {"id": ACTIVE_VENDOR, "slug": "ok", "display_name": "Ok Shop", "status": "active"},
            {
                "id": SUSPENDED_VENDOR,
                "slug": "s",
                "display_name": "Suspended",
                "status": "suspended",
            },
            {"id": BLOCKED_VENDOR, "slug": "b", "display_name": "Blocked", "status": "blocked"},
        ],
        "products": [],
        "vendor_locations": [],
        "listing_images": [],
        "order_item_products": [],
        "reviews": [],
        "feature_flags": [],
    }

    def add(n: int, *, vendor: str = ACTIVE_VENDOR, **overrides: Any) -> str:
        listing_id = _id(n)
        product_id = f"f1000000-0000-0000-0000-{n:012d}"
        # Many ties on updated_at so ordering has to fall back to the id tie-break.
        updated = f"2026-10-{(n % 4) + 1:02d}T00:00:00Z"
        doc = _search_doc(
            listing_id,
            title=f"Item {n}",
            category_path="electronics",
            price=10_000 + n,
            lat=-15.4,
            lng=28.3,
            updated_at=updated,
        )
        doc.update(overrides.pop("doc", {}))
        listing = _listing(listing_id, vendor_id=vendor, product_id=product_id)
        listing.update(overrides.pop("listing", {}))
        store["search_documents"].append(doc)
        store["vendor_listings"].append(listing)
        store["products"].append(
            {"id": product_id, "slug": f"item-{n}", "name": f"Item {n}", "status": "active"}
        )
        store["listing_images"].append(
            {
                "listing_id": listing_id,
                "cloudinary_public_id": f"vergeo5/catalog/item-{n}",
                "position": 1,
            }
        )
        return listing_id

    for n in range(1, visible + 1):
        add(n)
    # Never eligible:
    add(101, vendor=SUSPENDED_VENDOR)
    add(102, vendor=BLOCKED_VENDOR)
    add(103, listing={"status": "paused"})  # hidden / unpublished listing
    add(104, doc={"is_public": False})  # not searchable -> not public
    add(105, listing={"stock_mode": "tracked", "stock_qty": 0})  # sold out
    add(106, listing={"wholesale": True})  # B2B supply tier
    return store


HIDDEN_IDS = {_id(n) for n in (101, 102, 103, 104, 105, 106)}


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    from app.deps import get_supabase_client

    class Wrapper:
        def __init__(self, inner: FakeSupabaseClient) -> None:
            self.client = inner

    fake = FakeSupabaseClient(_store())
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: Wrapper(fake)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _no_cache_no_ratelimit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.routers.home_feed.get_cached_json", lambda _key: None)
    monkeypatch.setattr("app.routers.home_feed.set_cached_json", lambda *_a, **_k: None)
    monkeypatch.setattr("app.routers.home_feed.bump_rate_counter", lambda **_k: (True, 0))


def _walk(client: TestClient, limit: int) -> list[list[str]]:
    pages: list[list[str]] = []
    cursor: str | None = None
    for _ in range(50):
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/home/stream", params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        pages.append([item["id"] for item in body["items"]])
        cursor = body["next_cursor"]
        if cursor is None:
            return pages
    raise AssertionError("stream never terminated")


def test_pages_are_stable_complete_and_duplicate_free(client: TestClient) -> None:
    first = _walk(client, limit=5)
    flat = [listing_id for page in first for listing_id in page]
    assert len(flat) == len(set(flat)) == 14
    assert [len(page) for page in first] == [5, 5, 4]
    # Same request, same order (deterministic, id tie-break), and independent of page size.
    assert _walk(client, limit=5) == first
    assert [i for page in _walk(client, limit=3) for i in page] == flat
    assert [i for page in _walk(client, limit=12) for i in page] == flat


def test_hidden_blocked_suspended_and_unavailable_never_appear(client: TestClient) -> None:
    flat = {i for page in _walk(client, limit=4) for i in page}
    assert flat.isdisjoint(HIDDEN_IDS)
    assert len(flat) == 14


def test_no_duplicates_even_if_catalogue_changes_between_pages() -> None:
    store = _store()
    fake = FakeSupabaseClient(store)
    first = build_stream_page(fake, cursor=None, limit=5)
    seen = [item.id for item in first.items]
    # A new top-ranked listing appears (and one already shown is removed) mid-scroll.
    new_doc = _search_doc(
        _id(200),
        title="Brand new",
        category_path="electronics",
        price=1,
        lat=-15.4,
        lng=28.3,
        updated_at="2027-01-01T00:00:00Z",
    )
    store["search_documents"].append(new_doc)
    store["vendor_listings"].append(
        _listing(
            _id(200), vendor_id=ACTIVE_VENDOR, product_id="f1000000-0000-0000-0000-000000000200"
        )
    )
    store["products"].append(
        {"id": "f1000000-0000-0000-0000-000000000200", "slug": "n", "name": "N", "status": "active"}
    )
    store["listing_images"].append(
        {"listing_id": _id(200), "cloudinary_public_id": "vergeo5/catalog/new", "position": 1}
    )
    cursor = first.next_cursor
    while cursor:
        page = build_stream_page(fake, cursor=cursor, limit=5)
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
    assert len(seen) == len(set(seen))
    assert _id(200) not in seen  # ranks above the cursor, so it is not replayed mid-stream


@pytest.mark.parametrize(
    "cursor",
    [
        "!!!not-base64!!!",
        "bm90LWpzb24",  # "not-json"
        base64.urlsafe_b64encode(b"[1,2]").decode().rstrip("="),
        base64.urlsafe_b64encode(json.dumps({"v": 2, "k": [1, 1, 1, "x"], "id": "a"}).encode())
        .decode()
        .rstrip("="),
        base64.urlsafe_b64encode(json.dumps({"v": 1, "k": [1, 1], "id": "a"}).encode())
        .decode()
        .rstrip("="),
        base64.urlsafe_b64encode(json.dumps({"v": 1, "k": ["x", 1, 1, "t"], "id": "a"}).encode())
        .decode()
        .rstrip("="),
        base64.urlsafe_b64encode(json.dumps({"v": 1, "k": [1, 1, 1, "t"], "id": ""}).encode())
        .decode()
        .rstrip("="),
        "é",
    ],
)
def test_bad_cursor_is_400_and_never_restarts_the_stream(client: TestClient, cursor: str) -> None:
    response = client.get("/home/stream", params={"cursor": cursor})
    assert response.status_code == 400
    assert "invalid_cursor" in response.text


def test_oversized_cursor_and_limit_are_rejected(client: TestClient) -> None:
    assert client.get("/home/stream", params={"cursor": "a" * 300}).status_code == 422
    assert client.get("/home/stream", params={"limit": 999}).status_code == 422
    assert client.get("/home/stream", params={"limit": 0}).status_code == 422


def test_cursor_roundtrip() -> None:
    key = (4.0833, 1, 1, "2026-10-02T00:00:00Z", _id(7))
    assert decode_stream_cursor(encode_stream_cursor(key)) == key
    assert decode_stream_cursor(None) is None
    assert decode_stream_cursor("") is None


def test_endpoint_is_publicly_cacheable_and_ends_with_null_cursor(client: TestClient) -> None:
    response = client.get("/home/stream", params={"limit": 12})
    assert response.headers["cache-control"].startswith("public")
    page = HomeStreamPage.model_validate(response.json())
    assert len(page.items) == 12 and page.next_cursor is not None
    tail = client.get("/home/stream", params={"limit": 12, "cursor": page.next_cursor}).json()
    assert len(tail["items"]) == 2 and tail["next_cursor"] is None
