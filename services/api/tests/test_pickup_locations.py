"""GET /products/listings/{listing_id}/pickup-locations.

Backs the Customer PDP's required-branch-selection flow (audit found the PDP
sent Add to Cart with no pickup_location_id at all for branch-tracked
listings, which the backend correctly rejects with cart.pickup_location_required
— this endpoint is what the PDP now calls first to know whether a branch
must be chosen and which ones are valid).

Mocks the location_stock.py helpers directly (unit-level: this endpoint's
own routing/visibility/shaping logic) rather than hitting real Postgres —
services/api/tests/test_location_stock.py already covers is_branch_tracked /
fetch_branch_stock_rows against real Postgres.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from app.errors import AppError
from app.main import create_app
from app.services.inventory.location_stock import BranchStockRow
from fastapi import FastAPI
from fastapi.testclient import TestClient

LISTING_ID = "11111111-1111-1111-1111-111111111111"
BUSINESS_LISTING_ID = "22222222-2222-2222-2222-222222222222"
ACTIVE_BRANCH = "33333333-3333-3333-3333-333333333333"
INACTIVE_BRANCH = "44444444-4444-4444-4444-444444444444"


class FakeVendorLocationsQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._ids: list[str] | None = None

    def select(self, _columns: str) -> FakeVendorLocationsQuery:
        return self

    def in_(self, _column: str, values: list[str]) -> FakeVendorLocationsQuery:
        self._ids = values
        return self

    def execute(self) -> Any:
        class Response:
            data = [row for row in self._rows if self._ids is None or row["id"] in self._ids]

        return Response()


class FakeServiceClient:
    def __init__(self, vendor_locations: list[dict[str, Any]]) -> None:
        self.client = self
        self._vendor_locations = vendor_locations

    def table(self, name: str) -> FakeVendorLocationsQuery:
        assert name == "vendor_locations"
        return FakeVendorLocationsQuery(self._vendor_locations)


@pytest.fixture
def vendor_locations() -> list[dict[str, Any]]:
    return [
        {"id": ACTIVE_BRANCH, "landmark": "East Park Mall"},
        {"id": INACTIVE_BRANCH, "landmark": "Closed Branch"},
    ]


@pytest.fixture
def client(vendor_locations: list[dict[str, Any]]) -> Generator[TestClient, None, None]:
    app: FastAPI = create_app()
    fake = FakeServiceClient(vendor_locations)
    with (
        patch("app.deps.get_supabase_service_client", return_value=fake),
        patch("app.supabase_client.get_supabase_service_client", return_value=fake),
    ):
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client


class TestPickupLocationsEndpoint:
    def test_not_branch_tracked_returns_empty_locations(self, client: TestClient) -> None:
        with (
            patch("app.routers.products.fetch_listing", return_value={"id": LISTING_ID}),
            patch("app.routers.products.is_branch_tracked", return_value=False),
        ):
            response = client.get(f"/products/listings/{LISTING_ID}/pickup-locations")
        assert response.status_code == 200
        body = response.json()
        assert body["branch_tracked"] is False
        assert body["locations"] == []

    def test_branch_tracked_returns_only_active_branches_with_landmark(
        self, client: TestClient
    ) -> None:
        rows = (
            BranchStockRow(
                location_id=ACTIVE_BRANCH, stock_qty=5, lat=-15.4, lng=28.3, status="active"
            ),
            BranchStockRow(
                location_id=INACTIVE_BRANCH, stock_qty=2, lat=-15.5, lng=28.4, status="inactive"
            ),
        )
        with (
            patch("app.routers.products.fetch_listing", return_value={"id": LISTING_ID}),
            patch("app.routers.products.is_branch_tracked", return_value=True),
            patch("app.routers.products.fetch_branch_stock_rows", return_value=rows),
        ):
            response = client.get(f"/products/listings/{LISTING_ID}/pickup-locations")
        assert response.status_code == 200
        body = response.json()
        assert body["branch_tracked"] is True
        assert len(body["locations"]) == 1
        assert body["locations"][0]["id"] == ACTIVE_BRANCH
        assert body["locations"][0]["landmark"] == "East Park Mall"
        assert body["locations"][0]["lat"] == -15.4
        assert body["locations"][0]["lng"] == 28.3
        # The inactive branch never appears — never selectable if inactive.
        assert all(loc["id"] != INACTIVE_BRANCH for loc in body["locations"])

    def test_branch_tracked_with_zero_active_branches_is_honest_not_fabricated(
        self, client: TestClient
    ) -> None:
        rows = (
            BranchStockRow(
                location_id=INACTIVE_BRANCH, stock_qty=2, lat=-15.5, lng=28.4, status="inactive"
            ),
        )
        with (
            patch("app.routers.products.fetch_listing", return_value={"id": LISTING_ID}),
            patch("app.routers.products.is_branch_tracked", return_value=True),
            patch("app.routers.products.fetch_branch_stock_rows", return_value=rows),
        ):
            response = client.get(f"/products/listings/{LISTING_ID}/pickup-locations")
        assert response.status_code == 200
        body = response.json()
        assert body["branch_tracked"] is True
        assert body["locations"] == []

    def test_unknown_listing_returns_404_before_any_branch_lookup(
        self, client: TestClient
    ) -> None:
        def _not_found(*_args: Any, **_kwargs: Any) -> None:
            raise AppError(
                code="cart.listing_not_found",
                message="Listing not found",
                http_status=404,
                details={"listing_id": LISTING_ID},
            )

        with (
            patch("app.routers.products.fetch_listing", side_effect=_not_found),
            patch("app.routers.products.is_branch_tracked") as tracked_mock,
        ):
            response = client.get(f"/products/listings/{LISTING_ID}/pickup-locations")
            tracked_mock.assert_not_called()
        assert response.status_code == 404

    def test_wholesale_gated_listing_answered_as_not_found_for_ineligible_caller(
        self, client: TestClient
    ) -> None:
        """Same D36 rule fetch_listing already enforces for cart mutations — a listing
        an ineligible caller can't see must not leak location data either."""

        def _wholesale_forbidden(listing_id: str, *, business_eligible: bool) -> dict[str, Any]:
            assert business_eligible is False
            raise AppError(
                code="cart.listing_not_found",
                message="Listing not found",
                http_status=404,
                details={"listing_id": listing_id},
            )

        with patch("app.routers.products.fetch_listing", side_effect=_wholesale_forbidden):
            response = client.get(f"/products/listings/{BUSINESS_LISTING_ID}/pickup-locations")
        assert response.status_code == 404
