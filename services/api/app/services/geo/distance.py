"""Great-circle distance helpers for Zambia-frugal geo discovery (no Map SDK).

PostGIS is not installed on the Supabase stack (see ADR-R02-04-B), so nearby
queries use a bounding-box prefilter on indexed ``lat``/``lng`` columns plus
exact haversine on the survivors.
"""

from __future__ import annotations

import math
from typing import Final

# Lusaka CBD — default when the browser denies geolocation.
LUSAKA_CENTER_LAT: Final = -15.4167
LUSAKA_CENTER_LNG: Final = 28.2833

_EARTH_RADIUS_KM: Final = 6371.0088
_EARTH_RADIUS_M: Final = _EARTH_RADIUS_KM * 1000.0

# Public responses coarsen coordinates to ~1.1 km (privacy + matches the
# customer NearMeToggle 2dp rounding).
COORD_PRECISION: Final = 2


def round_coord(value: float, *, precision: int = COORD_PRECISION) -> float:
    factor = 10**precision
    return float(round(value * factor) / factor)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return haversine_km(lat1, lng1, lat2, lng2) * 1000.0


def bounding_box(
    lat: float, lng: float, radius_km: float
) -> tuple[float, float, float, float]:
    """Return ``(min_lat, max_lat, min_lng, max_lng)`` for a square prefilter."""
    if radius_km <= 0:
        raise ValueError("radius_km must be positive")
    # 1° latitude ≈ 111 km everywhere; longitude shrinks toward the poles.
    lat_delta = radius_km / 111.0
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    lng_delta = radius_km / (111.0 * cos_lat)
    return (
        max(-90.0, lat - lat_delta),
        min(90.0, lat + lat_delta),
        max(-180.0, lng - lng_delta),
        min(180.0, lng + lng_delta),
    )
