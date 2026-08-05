"""Query-less nearby vendor-branch discovery (R02 §3.6 / G-D8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from app.schemas.base import StrictModel
from app.services.geo.distance import (
    bounding_box,
    haversine_km,
    round_coord,
)
from app.services.listings.demo import fetch_demo_only_vendor_ids
from app.services.search.query_builder import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, paginate
from app.services.vendors.hours import LUSAKA_TZ, is_open_at
from pydantic import Field

DEFAULT_RADIUS_KM = 25.0
MAX_RADIUS_KM = 50.0


class NearbyBranch(StrictModel):
    location_id: str
    vendor_id: str
    vendor_slug: str
    vendor_name: str
    label: str | None = None
    landmark: str
    lat: float
    lng: float
    distance_km: float
    is_open_now: bool | None = None


class NearbyResponse(StrictModel):
    lat: float
    lng: float
    radius_km: float
    page: int
    page_size: int
    total: int
    results: list[NearbyBranch] = Field(default_factory=list)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _branch_open_now(hours: Any, *, now: datetime) -> bool | None:
    if not isinstance(hours, dict) or not hours:
        return None
    return is_open_at(hours, now)


def run_nearby(
    client: Any,
    *,
    lat: float,
    lng: float,
    radius_km: float = DEFAULT_RADIUS_KM,
    open_now: bool = False,
    page: int = DEFAULT_PAGE,
    page_size: int = DEFAULT_PAGE_SIZE,
    now: datetime | None = None,
) -> NearbyResponse:
    """Return active vendor branches within ``radius_km``, sorted nearest-first."""
    at = now or datetime.now(LUSAKA_TZ)
    min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius_km)

    response = (
        client.table("vendor_locations")
        .select(
            "id, vendor_id, label, landmark, lat, lng, hours, status, "
            "vendors!inner(id, slug, display_name, status)"
        )
        .eq("status", "active")
        .eq("vendors.status", "active")
        .gte("lat", min_lat)
        .lte("lat", max_lat)
        .gte("lng", min_lng)
        .lte("lng", max_lng)
        .execute()
    )

    candidates: list[tuple[float, NearbyBranch]] = []
    vendor_ids: list[str] = []

    for row in _rows(response):
        row_lat = row.get("lat")
        row_lng = row.get("lng")
        location_id = row.get("id")
        vendor_id = row.get("vendor_id")
        if row_lat is None or row_lng is None or not location_id or not vendor_id:
            continue

        distance = haversine_km(lat, lng, float(row_lat), float(row_lng))
        if distance > radius_km:
            continue

        vendor = row.get("vendors")
        if isinstance(vendor, list):
            vendor = vendor[0] if vendor else None
        if not isinstance(vendor, dict):
            continue

        hours = row.get("hours")
        branch_open = _branch_open_now(hours, now=at)
        if open_now and branch_open is not True:
            continue

        vendor_id_str = str(vendor_id)
        vendor_ids.append(vendor_id_str)
        candidates.append(
            (
                distance,
                NearbyBranch(
                    location_id=str(location_id),
                    vendor_id=vendor_id_str,
                    vendor_slug=str(vendor.get("slug") or ""),
                    vendor_name=str(vendor.get("display_name") or ""),
                    label=str(row["label"]).strip() if row.get("label") else None,
                    landmark=str(row.get("landmark") or ""),
                    lat=round_coord(float(row_lat)),
                    lng=round_coord(float(row_lng)),
                    distance_km=round(distance, 3),
                    is_open_now=branch_open,
                ),
            )
        )

    demo_only = fetch_demo_only_vendor_ids(client, list(dict.fromkeys(vendor_ids)))
    if demo_only:
        candidates = [
            (distance, branch)
            for distance, branch in candidates
            if branch.vendor_id not in demo_only
        ]

    candidates.sort(key=lambda item: (item[0], item[1].vendor_name.lower()))
    branches = [branch for _distance, branch in candidates]
    page_items, total = paginate(branches, page=page, page_size=page_size)

    return NearbyResponse(
        lat=round_coord(lat),
        lng=round_coord(lng),
        radius_km=radius_km,
        page=page,
        page_size=page_size,
        total=total,
        results=page_items,
    )
