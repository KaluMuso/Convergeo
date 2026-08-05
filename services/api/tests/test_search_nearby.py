"""Tests for GET /search/nearby and geo distance helpers (R02)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.geo.distance import (
    LUSAKA_CENTER_LAT,
    LUSAKA_CENTER_LNG,
    bounding_box,
    haversine_km,
    round_coord,
)
from app.services.search import SearchHit
from app.services.search.nearby import run_nearby
from app.services.search.open_now import attach_open_now
from app.services.vendors.hours import LUSAKA_TZ
from fastapi import FastAPI
from fastapi.testclient import TestClient

LUSAKA = (LUSAKA_CENTER_LAT, LUSAKA_CENTER_LNG)
KITWE = (-12.8024, 28.2132)

NEAR_VENDOR = "00000000-0000-4000-8000-000000000101"
FAR_VENDOR = "00000000-0000-4000-8000-000000000102"
NEAR_LOC = "00000000-0000-4000-8000-000000000201"
FAR_LOC = "00000000-0000-4000-8000-000000000202"


class FakeTable:
    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self._name = ""
        self._filters: list[tuple[Any, ...]] = []
        self._select_cols = ""

    def select(self, cols: str) -> FakeTable:
        self._select_cols = cols
        return self

    def eq(self, col: str, value: Any) -> FakeTable:
        self._filters.append(("eq", col, value))
        return self

    def gte(self, col: str, value: Any) -> FakeTable:
        self._filters.append(("gte", col, value))
        return self

    def lte(self, col: str, value: Any) -> FakeTable:
        self._filters.append(("lte", col, value))
        return self

    def in_(self, col: str, values: list[str]) -> FakeTable:
        self._filters.append(("in", col, values))
        return self

    def execute(self) -> Any:
        return self._handler(self._name, self._select_cols, self._filters)


class FakeClient:
    def __init__(self, rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
        self._rows_by_table = rows_by_table

    def table(self, name: str) -> FakeTable:
        table = FakeTable(self._handle)
        table._name = name
        return table

    def _handle(self, name: str, _cols: str, _filters: list[tuple[str, Any]]) -> Any:
        class Result:
            data = self._rows_by_table.get(name, [])

        return Result()


def _nearby_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": NEAR_LOC,
            "vendor_id": NEAR_VENDOR,
            "label": "Main shop",
            "landmark": "Cairo Road",
            "lat": LUSAKA[0],
            "lng": LUSAKA[1],
            "hours": {"mon": "09:00-17:00"},
            "status": "active",
            "vendors": {
                "id": NEAR_VENDOR,
                "slug": "near-shop",
                "display_name": "Near Shop",
                "status": "active",
            },
        },
        {
            "id": FAR_LOC,
            "vendor_id": FAR_VENDOR,
            "label": None,
            "landmark": "Kitwe market",
            "lat": KITWE[0],
            "lng": KITWE[1],
            "hours": None,
            "status": "active",
            "vendors": {
                "id": FAR_VENDOR,
                "slug": "far-shop",
                "display_name": "Far Shop",
                "status": "active",
            },
        },
    ]


def test_bounding_box_contains_center() -> None:
    min_lat, max_lat, min_lng, max_lng = bounding_box(LUSAKA[0], LUSAKA[1], 25.0)
    assert min_lat < LUSAKA[0] < max_lat
    assert min_lng < LUSAKA[1] < max_lng


def test_haversine_lusaka_to_kitwe() -> None:
    distance = haversine_km(*LUSAKA, *KITWE)
    assert 250 < distance < 400


def test_round_coord_matches_two_decimal_precision() -> None:
    assert round_coord(-15.416789) == -15.42


def test_run_nearby_sorts_by_distance() -> None:
    with patch(
        "app.services.search.nearby.fetch_demo_only_vendor_ids",
        return_value=set(),
    ):
        client = FakeClient({"vendor_locations": _nearby_rows()})
        monday_noon = datetime(2026, 8, 3, 12, 0, tzinfo=LUSAKA_TZ)
        result = run_nearby(
            client,
            lat=LUSAKA[0],
            lng=LUSAKA[1],
            radius_km=50,
            now=monday_noon,
        )

    assert result.total == 1
    assert result.results[0].vendor_slug == "near-shop"
    assert result.results[0].distance_km < 1.0
    assert result.results[0].is_open_now is True


def test_run_nearby_open_now_filter_excludes_unknown_hours() -> None:
    with patch(
        "app.services.search.nearby.fetch_demo_only_vendor_ids",
        return_value=set(),
    ):
        client = FakeClient({"vendor_locations": _nearby_rows()})
        monday_noon = datetime(2026, 8, 3, 12, 0, tzinfo=LUSAKA_TZ)
        result = run_nearby(
            client,
            lat=LUSAKA[0],
            lng=LUSAKA[1],
            radius_km=500,
            open_now=True,
            now=monday_noon,
        )

    assert result.total == 1
    assert result.results[0].vendor_slug == "near-shop"


def test_attach_open_now_for_vendor_hit() -> None:
    vendor_id = NEAR_VENDOR
    hits = [
        SearchHit(
            id="doc-1",
            entity_kind="vendor",
            entity_id=vendor_id,
            title="Near Shop",
            rrf_score=1.0,
        )
    ]
    client = FakeClient(
        {
            "vendor_locations": [
                {
                    "vendor_id": vendor_id,
                    "hours": {"mon": "09:00-17:00"},
                    "status": "active",
                }
            ]
        }
    )
    monday_noon = datetime(2026, 8, 3, 12, 0, tzinfo=LUSAKA_TZ)
    enriched = attach_open_now(client, hits, now=monday_noon)
    assert enriched[0].is_open_now is True


@pytest.fixture
def nearby_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    class FakeServiceClient:
        def __init__(self, client: FakeClient) -> None:
            self.client = client

    fake = FakeClient({"vendor_locations": _nearby_rows()})

    def override() -> FakeServiceClient:
        return FakeServiceClient(fake)

    monkeypatch.setattr(
        "app.routers.search.bump_rate_counter",
        lambda **_kwargs: (True, 0),
    )
    monkeypatch.setattr(
        "app.services.search.nearby.fetch_demo_only_vendor_ids",
        lambda _client, _ids: set(),
    )

    app: FastAPI = create_app()
    app.dependency_overrides[get_supabase_client] = override
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def test_nearby_route_requires_lat_lng(nearby_client: TestClient) -> None:
    response = nearby_client.get("/search/nearby")
    assert response.status_code == 422


def test_nearby_route_returns_sorted_branches(nearby_client: TestClient) -> None:
    response = nearby_client.get(
        "/search/nearby",
        params={"lat": LUSAKA_CENTER_LAT, "lng": LUSAKA_CENTER_LNG, "radius_km": 50},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["vendor_slug"] == "near-shop"


def test_nearby_route_rejects_radius_over_cap(nearby_client: TestClient) -> None:
    response = nearby_client.get(
        "/search/nearby",
        params={"lat": LUSAKA_CENTER_LAT, "lng": LUSAKA_CENTER_LNG, "radius_km": 999},
    )
    assert response.status_code == 422
