"""Search cards need the listing image: hits must carry ``image_public_id``."""

from __future__ import annotations

from typing import Any

from app.services.search import SearchHit, attach_hit_images

LISTING = "11111111-1111-4111-8111-111111111111"
LISTING_NO_OWN = "22222222-2222-4222-8222-222222222222"
PRODUCT = "33333333-3333-4333-8333-333333333333"
PRODUCT_ONLY_LISTING = "44444444-4444-4444-8444-444444444444"


class _Resp:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _Query:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def in_(self, column: str, values: list[str]) -> _Query:
        self._rows = [r for r in self._rows if r.get(column) in values]
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self._rows = [r for r in self._rows if r.get(column) == value]
        return self

    def order(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def execute(self) -> _Resp:
        return _Resp(self._rows)


class _Client:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self._tables = tables

    def table(self, name: str) -> _Query:
        return _Query(list(self._tables.get(name, [])))


def _hit(kind: str, entity_id: str) -> SearchHit:
    return SearchHit(
        id=f"doc-{entity_id}",
        entity_kind=kind,
        entity_id=entity_id,
        title="Thing",
        rrf_score=0.1,
    )


def test_listing_hit_gets_lowest_position_image_and_product_hit_falls_back() -> None:
    client = _Client(
        {
            "vendor_listings": [
                {"id": LISTING, "product_id": PRODUCT, "status": "active"},
                {"id": LISTING_NO_OWN, "product_id": PRODUCT, "status": "active"},
                {"id": PRODUCT_ONLY_LISTING, "product_id": None, "status": "active"},
            ],
            "listing_images": [
                {"listing_id": LISTING, "cloudinary_public_id": "second", "position": 2},
                {"listing_id": LISTING, "cloudinary_public_id": "first", "position": 1},
            ],
            "product_images": [
                {"product_id": PRODUCT, "cloudinary_public_id": "canon", "position": 1},
            ],
        }
    )
    hits = attach_hit_images(
        client,
        [_hit("listing", LISTING), _hit("listing", LISTING_NO_OWN), _hit("product", PRODUCT)],
    )
    by_id = {h.entity_id: h.image_public_id for h in hits}
    assert by_id[LISTING] == "first"
    assert by_id[LISTING_NO_OWN] == "canon"  # no own photo -> canonical product photo
    assert by_id[PRODUCT] == "canon"


def test_product_hit_falls_back_to_active_listing_image() -> None:
    client = _Client(
        {
            "vendor_listings": [{"id": LISTING, "product_id": PRODUCT, "status": "active"}],
            "listing_images": [
                {"listing_id": LISTING, "cloudinary_public_id": "vendor-pic", "position": 1}
            ],
        }
    )
    (hit,) = attach_hit_images(client, [_hit("product", PRODUCT)])
    assert hit.image_public_id == "vendor-pic"


def test_lookup_failure_leaves_hits_untouched() -> None:
    class Boom:
        def table(self, _name: str) -> Any:
            raise RuntimeError("db down")

    (hit,) = attach_hit_images(Boom(), [_hit("listing", LISTING)])
    assert hit.image_public_id is None


def test_event_and_service_hits_get_first_jsonb_image() -> None:
    event_id = "55555555-5555-4555-8555-555555555555"
    service_id = "66666666-6666-4666-8666-666666666666"
    bare_event = "77777777-7777-4777-8777-777777777777"
    client = _Client(
        {
            "events": [
                {"id": event_id, "images": ["ev-1", "ev-2"]},
                {"id": bare_event, "images": []},
            ],
            "services": [{"id": service_id, "portfolio_images": ["svc-1"]}],
        }
    )
    hits = attach_hit_images(
        client, [_hit("event", event_id), _hit("event", bare_event), _hit("service", service_id)]
    )
    by_id = {h.entity_id: h.image_public_id for h in hits}
    assert by_id[event_id] == "ev-1"
    assert by_id[bare_event] is None
    assert by_id[service_id] == "svc-1"
