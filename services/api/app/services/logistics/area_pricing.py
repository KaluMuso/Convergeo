"""Area-pair delivery pricing (founder-approved 2026-11-13; growth blueprint §5).

Customers' delivery prices depend only on a lookup in Convergeo's own tables:

* ``public.areas``           ~60 named Lusaka areas (picker + text aliases + centroid).
* ``public.area_distances``  road km / minutes between every ordered area pair,
                             computed OFFLINE (estimate now, OSRM later). No map API
                             is called on any customer path.

Price for one delivery address (all shops the customer has delivered there):

    route  = best pickup order: shop -> shop -> ... -> customer (area-pair km)
    fee    = round_up_to_K5(base_per_km x route_km x time_band x rain + stop_fee x shops)
    bounds = [min_fee, max_fee], and while ``zone_bounds`` is on (until the table is
             trusted): floor = cheapest active zone fee, cap = dearest zone fee x shops
    multi  = never more than the shops' separate area fees added up (blueprint §6.6)

The consolidated fee is split across the delivered shops in K5 units, in
proportion to each shop's standalone fee, so each vendor order carries its share.

Rollout (``platform_config``): ``area_pricing_shadow`` (default ON) computes and
logs the new fee next to the charged zone fee; ``area_pricing_live`` (default OFF)
charges it. Everything here is integer ngwee / metres / basis points: no float
touches money (distances are converted to whole metres first).
"""

from __future__ import annotations

import itertools
import logging
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

LUSAKA_TZ = ZoneInfo("Africa/Lusaka")
BPS = 10_000
K5_NGWEE = 500
MAX_EXACT_ROUTE_SHOPS = 6

AddressType = Literal["home", "work"]
PromiseDay = Literal["today", "tomorrow", "later"]

SHADOW_KEY = "area_pricing_shadow"
LIVE_KEY = "area_pricing_live"
RAIN_KEY = "delivery_rain_mode"
SETTINGS_KEY = "area_pricing_settings"
BANDS_KEY = "delivery_time_bands"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TimeBand:
    key: str
    start_minute: int  # minutes after Lusaka midnight, inclusive
    end_minute: int  # exclusive
    multiplier_bps: int

    def contains(self, minute: int) -> bool:
        return self.start_minute <= minute < self.end_minute


DEFAULT_TIME_BANDS: tuple[TimeBand, ...] = (
    TimeBand("morning_peak", 7 * 60, 9 * 60, 15_000),
    TimeBand("midday", 9 * 60, 16 * 60 + 30, 10_000),
    TimeBand("evening_peak", 16 * 60 + 30, 18 * 60 + 30, 12_000),
    TimeBand("evening", 18 * 60 + 30, 20 * 60, 11_000),
)
OFF_PEAK_BAND = "off_band"


@dataclass(frozen=True, slots=True)
class AreaPricingSettings:
    base_per_km_ngwee: int = 400
    stop_fee_ngwee: int = 1300
    intra_area_metres: int = 2000
    min_fee_ngwee: int = 2500
    max_fee_ngwee: int = 20_000
    rain_multiplier_bps: int = 12_000
    zone_bounds: bool = True
    quote_ttl_minutes: int = 30
    time_bands: tuple[TimeBand, ...] = DEFAULT_TIME_BANDS

    def __post_init__(self) -> None:
        for name in (
            "base_per_km_ngwee",
            "stop_fee_ngwee",
            "intra_area_metres",
            "min_fee_ngwee",
            "max_fee_ngwee",
            "rain_multiplier_bps",
            "quote_ttl_minutes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.min_fee_ngwee > self.max_fee_ngwee:
            raise ValueError("min_fee_ngwee must not exceed max_fee_ngwee")
        if self.rain_multiplier_bps < BPS:
            raise ValueError("rain_multiplier_bps must be at least 10000 (x1.0)")


@dataclass(frozen=True, slots=True)
class PricingSwitches:
    shadow: bool = True
    live: bool = False
    rain: bool = False


# ---------------------------------------------------------------------------
# Areas and distances
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Area:
    slug: str
    name: str
    zone_key: str
    lat: float
    lng: float
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Leg:
    metres: int
    minutes: int


DistanceTable = Mapping[tuple[str, str], Leg]


def km_to_metres(value: object) -> int | None:
    """``numeric`` road km from PostgREST (str / int / float) -> whole metres."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        km = Decimal(str(value))
    except ArithmeticError:
        return None
    if not km.is_finite() or km < 0:
        return None
    return int((km * 1000).to_integral_value(rounding=ROUND_HALF_UP))


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _normalise(text: str) -> str:
    lowered = text.lower().replace("’", "").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", lowered).split())


def area_terms(area: Area) -> list[str]:
    terms = {_normalise(area.name), *(_normalise(alias) for alias in area.aliases)}
    terms.add(_normalise(area.slug.replace("_", " ")))
    return sorted(term for term in terms if len(term) >= 3)


def match_area_from_text(text: str | None, areas: Iterable[Area]) -> Area | None:
    """Whole-word, longest-name-wins match of free text against area names/aliases."""
    if not text:
        return None
    haystack = f" {_normalise(text)} "
    best: tuple[int, str, Area] | None = None
    for area in areas:
        for term in area_terms(area):
            if f" {term} " in haystack:
                candidate = (len(term), area.slug, area)
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
    return best[2] if best else None


def nearest_area(
    lat: float | None, lng: float | None, areas: Iterable[Area], *, max_km: float = 6.0
) -> Area | None:
    if lat is None or lng is None:
        return None
    ranked = sorted(
        ((haversine_km(lat, lng, a.lat, a.lng), a.slug, a) for a in areas),
        key=lambda item: (item[0], item[1]),
    )
    if not ranked or ranked[0][0] > max_km:
        return None
    return ranked[0][2]


def leg_metres(
    from_area: str, to_area: str, distances: DistanceTable, settings: AreaPricingSettings
) -> int | None:
    if from_area == to_area:
        return settings.intra_area_metres
    leg = distances.get((from_area, to_area))
    return leg.metres if leg is not None else None


def best_route_metres(
    shop_areas: Sequence[str],
    customer_area: str,
    distances: DistanceTable,
    settings: AreaPricingSettings,
) -> int | None:
    """Shortest shop -> ... -> shop -> customer route; None when a leg is unknown.

    Exact over every order for up to six distinct shop areas, nearest-first beyond.
    Shops in the same area are one pickup stop for routing (each still pays a stop fee).
    """
    stops = sorted(set(shop_areas))
    if not stops:
        return None

    def route_cost(order: Sequence[str]) -> int | None:
        total = 0
        legs = list(zip(order, [*order[1:], customer_area], strict=True))
        for a, b in legs:
            metres = leg_metres(a, b, distances, settings)
            if metres is None:
                return None
            total += metres
        return total

    if len(stops) <= MAX_EXACT_ROUTE_SHOPS:
        costs = [c for c in (route_cost(p) for p in itertools.permutations(stops)) if c is not None]
        return min(costs) if costs else None
    # Greedy: end at the shop nearest the customer, build backwards.
    remaining = list(stops)
    order: list[str] = []
    current = customer_area
    while remaining:
        scored = [
            (m, s)
            for s in remaining
            if (m := leg_metres(s, current, distances, settings)) is not None
        ]
        if not scored:
            return None
        _, pick = min(scored)
        order.insert(0, pick)
        remaining.remove(pick)
        current = pick
    return route_cost(order)


# ---------------------------------------------------------------------------
# Fee
# ---------------------------------------------------------------------------


def round_up_to_k5(numerator: int, denominator: int = 1) -> int:
    """ceil(numerator / denominator) rounded UP to the next K5 (500 ngwee)."""
    if numerator < 0 or denominator <= 0:
        raise ValueError("non-negative numerator and positive denominator required")
    unit = denominator * K5_NGWEE
    return -(-numerator // unit) * K5_NGWEE


def time_band_for(minute_of_day: int, bands: Sequence[TimeBand]) -> tuple[str, int]:
    for band in bands:
        if band.contains(minute_of_day):
            return band.key, band.multiplier_bps
    return OFF_PEAK_BAND, BPS


@dataclass(frozen=True, slots=True)
class FeeBounds:
    floor_ngwee: int
    cap_ngwee: int


def fee_bounds(
    settings: AreaPricingSettings, zone_fees: Mapping[str, int], pickups: int
) -> FeeBounds:
    floor, cap = settings.min_fee_ngwee, settings.max_fee_ngwee * max(1, pickups)
    active = [fee for fee in zone_fees.values() if fee > 0]
    if settings.zone_bounds and active:
        floor = max(floor, min(active))
        cap = min(cap, max(active) * max(1, pickups))
    return FeeBounds(floor, max(floor, cap))


def area_fee_ngwee(
    *,
    route_metres: int,
    pickups: int,
    time_multiplier_bps: int,
    rain_multiplier_bps: int,
    settings: AreaPricingSettings,
    bounds: FeeBounds,
) -> int:
    """round_up_to_K5(base_per_km x km x band x rain + stop_fee x pickups), bounded."""
    if route_metres < 0 or pickups < 1:
        raise ValueError("route_metres >= 0 and pickups >= 1 required")
    denominator = 1000 * BPS * BPS
    distance_part = (
        settings.base_per_km_ngwee * route_metres * time_multiplier_bps * rain_multiplier_bps
    )
    stops_part = settings.stop_fee_ngwee * pickups * denominator
    fee = round_up_to_k5(distance_part + stops_part, denominator)
    return min(max(fee, bounds.floor_ngwee), bounds.cap_ngwee)


def split_in_k5_units(total_ngwee: int, weights: Mapping[str, int]) -> dict[str, int]:
    """Split a K5-multiple total across keys in proportion to weights (largest remainder)."""
    keys = sorted(weights)
    if not keys:
        return {}
    units = total_ngwee // K5_NGWEE
    weight_sum = sum(max(0, weights[k]) for k in keys)
    if weight_sum == 0:
        weight_map = {k: 1 for k in keys}
        weight_sum = len(keys)
    else:
        weight_map = {k: max(0, weights[k]) for k in keys}
    base = {k: units * weight_map[k] // weight_sum for k in keys}
    remainders = sorted(keys, key=lambda k: (-(units * weight_map[k] % weight_sum), k))
    for k in remainders[: units - sum(base.values())]:
        base[k] += 1
    shares = {k: base[k] * K5_NGWEE for k in keys}
    shares[keys[0]] += total_ngwee - units * K5_NGWEE  # never happens for K5 totals
    return shares


# ---------------------------------------------------------------------------
# Promise: "Order before 2 pm, get it today"
# ---------------------------------------------------------------------------

ROUND1_CUTOFF = time(11, 0)
ROUND2_CUTOFF = time(14, 0)
SATURDAY_CUTOFF = time(10, 0)
ROUND1_WINDOW = (time(12, 0), time(14, 30))
WORK_ROUND2_WINDOW = (time(15, 0), time(16, 45))
HOME_ROUND2_WINDOW = (time(17, 0), time(19, 30))
SATURDAY_WINDOW = (time(11, 0), time(14, 0))
WORK_LATEST = time(16, 45)
RAIN_WIDEN_MINUTES = 30


@dataclass(frozen=True, slots=True)
class DeliveryPromise:
    day: PromiseDay
    delivery_date: date
    window_start: time
    window_end: time

    @property
    def start_minute(self) -> int:
        return self.window_start.hour * 60 + self.window_start.minute


def _plus_minutes(value: time, minutes: int) -> time:
    total = value.hour * 60 + value.minute + minutes
    total = min(total, 23 * 60 + 59)
    return time(total // 60, total % 60)


def _next_working_window(day: date, address_type: AddressType) -> tuple[date, time, time]:
    candidate = day + timedelta(days=1)
    while True:
        weekday = candidate.weekday()
        if weekday == 6 or (weekday == 5 and address_type == "work"):
            candidate += timedelta(days=1)
            continue
        if weekday == 5:
            return candidate, *SATURDAY_WINDOW
        return candidate, *ROUND1_WINDOW


def delivery_promise(
    now: datetime, address_type: AddressType = "home", *, rain: bool = False
) -> DeliveryPromise:
    """The promised delivery day and window on the Lusaka clock.

    Weekdays: order by 11:00 -> 12:00-14:30 today; by 14:00 -> today 15:00-16:45
    (work) or 17:00-19:30 (home); later -> next working day 12:00-14:30.
    Saturday: one round, order by 10:00 -> 11:00-14:00 (homes only). Sunday:
    collection only. Work addresses are never scheduled after 16:45, nor on a
    weekend. Rain widens the window by 30 minutes (still capped at 16:45 for work).
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(LUSAKA_TZ)
    today, clock, weekday = local.date(), local.time(), local.weekday()

    window: tuple[date, time, time]
    if weekday < 5 and clock < ROUND1_CUTOFF:
        window = (today, *ROUND1_WINDOW)
    elif weekday < 5 and clock < ROUND2_CUTOFF:
        round2 = WORK_ROUND2_WINDOW if address_type == "work" else HOME_ROUND2_WINDOW
        window = (today, *round2)
    elif weekday == 5 and clock < SATURDAY_CUTOFF and address_type == "home":
        window = (today, *SATURDAY_WINDOW)
    else:
        window = _next_working_window(today, address_type)

    delivery_date, start, end = window
    if rain:
        end = _plus_minutes(end, RAIN_WIDEN_MINUTES)
    if address_type == "work" and end > WORK_LATEST:
        end = WORK_LATEST
    gap = (delivery_date - today).days
    day: PromiseDay = "today" if gap == 0 else "tomorrow" if gap == 1 else "later"
    return DeliveryPromise(day, delivery_date, start, end)


# ---------------------------------------------------------------------------
# Quote for one delivery address (all delivered shops)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AreaQuote:
    outcome: str  # "priced" or why not ("no_customer_area", "vendor_area_unknown", ...)
    customer_area: str | None = None
    vendor_areas: dict[str, str] = field(default_factory=dict)
    total_fee_ngwee: int | None = None
    fees_by_vendor: dict[str, int] = field(default_factory=dict)
    route_metres: int | None = None
    time_band: str | None = None
    rain: bool = False
    promise: DeliveryPromise | None = None

    @property
    def priced(self) -> bool:
        return self.outcome == "priced" and self.total_fee_ngwee is not None


def quote_address(
    *,
    customer_area: str | None,
    vendor_areas: Mapping[str, str | None],
    distances: DistanceTable,
    settings: AreaPricingSettings,
    zone_fees: Mapping[str, int],
    rain: bool,
    promise: DeliveryPromise,
) -> AreaQuote:
    """One consolidated fee for every delivered shop going to one address."""
    band, band_bps = time_band_for(promise.start_minute, settings.time_bands)
    rain_bps = settings.rain_multiplier_bps if rain else BPS

    def unpriced(outcome: str, known: dict[str, str] | None = None) -> AreaQuote:
        return AreaQuote(
            outcome,
            customer_area=customer_area,
            vendor_areas=known or {},
            time_band=band,
            rain=rain,
            promise=promise,
        )

    if not vendor_areas:
        return unpriced("no_delivery_groups")
    if customer_area is None:
        return unpriced("no_customer_area")
    known = {v: a for v, a in vendor_areas.items() if a is not None}
    if len(known) != len(vendor_areas):
        return unpriced("vendor_area_unknown", known)

    standalone: dict[str, int] = {}
    for vendor_id, shop_area in known.items():
        metres = best_route_metres([shop_area], customer_area, distances, settings)
        if metres is None:
            return unpriced("distance_missing", known)
        standalone[vendor_id] = area_fee_ngwee(
            route_metres=metres,
            pickups=1,
            time_multiplier_bps=band_bps,
            rain_multiplier_bps=rain_bps,
            settings=settings,
            bounds=fee_bounds(settings, zone_fees, 1),
        )
    route = best_route_metres(list(known.values()), customer_area, distances, settings)
    if route is None:
        return unpriced("distance_missing", known)
    pickups = len(known)
    consolidated = area_fee_ngwee(
        route_metres=route,
        pickups=pickups,
        time_multiplier_bps=band_bps,
        rain_multiplier_bps=rain_bps,
        settings=settings,
        bounds=fee_bounds(settings, zone_fees, pickups),
    )
    total = min(consolidated, sum(standalone.values()))
    return AreaQuote(
        "priced",
        customer_area=customer_area,
        vendor_areas=known,
        total_fee_ngwee=total,
        fees_by_vendor=split_in_k5_units(total, standalone),
        route_metres=route,
        time_band=band,
        rain=rain,
        promise=promise,
    )


# ---------------------------------------------------------------------------
# Loaders (service-role client; tolerant of missing rows -> defaults)
# ---------------------------------------------------------------------------


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _as_bool(raw: object, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        return raw != 0
    if isinstance(raw, str) and raw.strip().lower() in {"true", "false", "1", "0", "on", "off"}:
        return raw.strip().lower() in {"true", "1", "on"}
    return default


def _as_int(raw: object, default: int) -> int:
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int) and raw >= 0:
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return default


def _parse_hhmm(raw: object) -> int | None:
    if not isinstance(raw, str):
        return None
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", raw.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 24 or minute > 59 or (hour == 24 and minute):
        return None
    return hour * 60 + minute


def parse_time_bands(raw: object) -> tuple[TimeBand, ...]:
    if not isinstance(raw, list):
        return DEFAULT_TIME_BANDS
    bands: list[TimeBand] = []
    for item in raw:
        if not isinstance(item, dict):
            return DEFAULT_TIME_BANDS
        start, end = _parse_hhmm(item.get("start")), _parse_hhmm(item.get("end"))
        bps = item.get("multiplier_bps")
        key = item.get("key")
        if (
            start is None
            or end is None
            or end <= start
            or not isinstance(key, str)
            or isinstance(bps, bool)
            or not isinstance(bps, int)
            or not BPS // 2 <= bps <= 3 * BPS
        ):
            return DEFAULT_TIME_BANDS
        bands.append(TimeBand(key, start, end, bps))
    return tuple(bands)


def parse_settings(raw: object, bands_raw: object) -> AreaPricingSettings:
    data = raw if isinstance(raw, dict) else {}
    defaults = AreaPricingSettings()
    intra = km_to_metres(data.get("intra_area_km"))
    try:
        return AreaPricingSettings(
            base_per_km_ngwee=_as_int(data.get("base_per_km_ngwee"), defaults.base_per_km_ngwee),
            stop_fee_ngwee=_as_int(data.get("stop_fee_ngwee"), defaults.stop_fee_ngwee),
            intra_area_metres=intra if intra is not None else defaults.intra_area_metres,
            min_fee_ngwee=_as_int(data.get("min_fee_ngwee"), defaults.min_fee_ngwee),
            max_fee_ngwee=_as_int(data.get("max_fee_ngwee"), defaults.max_fee_ngwee),
            rain_multiplier_bps=_as_int(
                data.get("rain_multiplier_bps"), defaults.rain_multiplier_bps
            ),
            zone_bounds=_as_bool(data.get("zone_bounds"), defaults.zone_bounds),
            quote_ttl_minutes=_as_int(data.get("quote_ttl_minutes"), defaults.quote_ttl_minutes),
            time_bands=parse_time_bands(bands_raw),
        )
    except ValueError:
        logger.warning("area_pricing.settings_invalid", extra={"event": "settings_invalid"})
        return AreaPricingSettings(time_bands=parse_time_bands(bands_raw))


def _config_values(client: Any, keys: Sequence[str]) -> dict[str, object]:
    response = client.table("platform_config").select("key, value").in_("key", list(keys)).execute()
    return {str(r["key"]): r.get("value") for r in _rows(response) if "key" in r}


def load_switches(client: Any) -> PricingSwitches:
    values = _config_values(client, [SHADOW_KEY, LIVE_KEY, RAIN_KEY])
    return PricingSwitches(
        shadow=_as_bool(values.get(SHADOW_KEY), True),
        live=_as_bool(values.get(LIVE_KEY), False),
        rain=_as_bool(values.get(RAIN_KEY), False),
    )


def load_settings(client: Any) -> AreaPricingSettings:
    values = _config_values(client, [SETTINGS_KEY, BANDS_KEY])
    return parse_settings(values.get(SETTINGS_KEY), values.get(BANDS_KEY))


def parse_area_row(row: Mapping[str, Any]) -> Area | None:
    slug, name, zone = row.get("slug"), row.get("name"), row.get("zone_key")
    lat, lng = row.get("lat"), row.get("lng")
    if not (isinstance(slug, str) and isinstance(name, str) and isinstance(zone, str)):
        return None
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return None
    aliases = row.get("aliases")
    return Area(
        slug=slug,
        name=name,
        zone_key=zone,
        lat=float(lat),
        lng=float(lng),
        aliases=tuple(a for a in aliases if isinstance(a, str))
        if isinstance(aliases, list)
        else (),
    )


def load_areas(client: Any) -> dict[str, Area]:
    response = (
        client.table("areas")
        .select("slug, name, zone_key, lat, lng, aliases")
        .eq("active", True)
        .execute()
    )
    areas = (parse_area_row(row) for row in _rows(response))
    return {area.slug: area for area in areas if area is not None}


def load_distances(
    client: Any, from_areas: Iterable[str], to_areas: Iterable[str]
) -> DistanceTable:
    froms, tos = sorted(set(from_areas)), sorted(set(to_areas))
    if not froms or not tos:
        return {}
    response = (
        client.table("area_distances")
        .select("from_area, to_area, road_km, minutes")
        .in_("from_area", froms)
        .in_("to_area", tos)
        .execute()
    )
    table: dict[tuple[str, str], Leg] = {}
    for row in _rows(response):
        metres = km_to_metres(row.get("road_km"))
        minutes = row.get("minutes")
        if metres is None or not isinstance(row.get("from_area"), str):
            continue
        table[(str(row["from_area"]), str(row["to_area"]))] = Leg(
            metres, minutes if isinstance(minutes, int) and not isinstance(minutes, bool) else 0
        )
    return table


def load_vendor_areas(
    client: Any, vendor_ids: Sequence[str], areas: Mapping[str, Area]
) -> dict[str, str | None]:
    """Each shop's area: its primary location's ``area`` text, else nearest centroid."""
    ids = sorted(set(vendor_ids))
    if not ids:
        return {}
    response = (
        client.table("vendor_locations")
        .select("vendor_id, area, landmark, lat, lng, is_primary, created_at")
        .in_("vendor_id", ids)
        .execute()
    )
    by_vendor: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(response):
        if isinstance(row.get("vendor_id"), str):
            by_vendor.setdefault(str(row["vendor_id"]), []).append(row)
    result: dict[str, str | None] = {}
    for vendor_id in ids:
        rows = sorted(
            by_vendor.get(vendor_id, []),
            key=lambda r: (r.get("is_primary") is not True, str(r.get("created_at") or "")),
        )
        found: Area | None = None
        for row in rows:
            found = match_area_from_text(
                row.get("area") if isinstance(row.get("area"), str) else None, areas.values()
            )
            lat, lng = row.get("lat"), row.get("lng")
            if found is None and isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
                found = nearest_area(float(lat), float(lng), areas.values())
            if found is None:
                landmark = row.get("landmark")
                found = match_area_from_text(
                    landmark if isinstance(landmark, str) else None, areas.values()
                )
            if found is not None:
                break
        result[vendor_id] = found.slug if found else None
    return result


def resolve_customer_area(
    areas: Mapping[str, Area],
    *,
    area_slug: str | None,
    landmark: str | None,
    lat: float | None,
    lng: float | None,
) -> Area | None:
    if area_slug and area_slug in areas:
        return areas[area_slug]
    return match_area_from_text(landmark, areas.values()) or nearest_area(
        lat, lng, areas.values(), max_km=3.0
    )


def quote_checkout_delivery(
    client: Any,
    *,
    areas: Mapping[str, Area],
    customer_area: Area | None,
    delivered_vendor_ids: Sequence[str],
    zone_fees: Mapping[str, int],
    switches: PricingSwitches,
    address_type: AddressType,
    now: datetime,
) -> AreaQuote:
    """Load what the quote needs and price one address; never raises on data gaps."""
    settings = load_settings(client)
    promise = delivery_promise(now, address_type, rain=switches.rain)
    vendor_areas = load_vendor_areas(client, delivered_vendor_ids, areas)
    known = [a for a in vendor_areas.values() if a is not None]
    distances: DistanceTable = {}
    if customer_area is not None and known:
        distances = load_distances(client, known, [*known, customer_area.slug])
    return quote_address(
        customer_area=customer_area.slug if customer_area else None,
        vendor_areas=vendor_areas,
        distances=distances,
        settings=settings,
        zone_fees=zone_fees,
        rain=switches.rain,
        promise=promise,
    )


def log_quote(
    client: Any,
    *,
    quote: AreaQuote,
    charged_fee_ngwee: int,
    checkout_group_id: str | None,
    mode: Literal["shadow", "live"],
) -> None:
    """Shadow log: new fee next to the charged one. Best-effort; never blocks checkout."""
    route_km = str(Decimal(quote.route_metres) / 1000) if quote.route_metres is not None else None
    row = {
        "checkout_group_id": checkout_group_id,
        "customer_area": quote.customer_area,
        "vendor_areas": sorted(set(quote.vendor_areas.values())),
        "pickups": len(quote.vendor_areas),
        "route_km": route_km,
        "time_band": quote.time_band,
        "rain_mode": quote.rain,
        "charged_fee_ngwee": charged_fee_ngwee,
        "area_fee_ngwee": quote.total_fee_ngwee,
        "mode": mode,
        "outcome": quote.outcome,
    }
    logger.info(
        "checkout.area_pricing_quote",
        extra={
            "event": "area_pricing_quote",
            **{k: v for k, v in row.items() if k != "vendor_areas"},
        },
    )
    try:
        client.table("delivery_price_shadow_log").insert(row).execute()
    except Exception:  # noqa: BLE001 - logging must never fail a checkout
        logger.warning("area_pricing.shadow_log_failed", extra={"event": "shadow_log_failed"})
