"""Logistics operations (phase 1): rider cash custody, remittances, cash-up, margin.

Mounted under the shared admin router (``/admin/logistics``). A restricted
operator needs ``cod.reconcile`` for cash routes and ``logistics.manage`` for
the margin report and reference rate cards (``app.core.auth`` route inventory).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from app.core.admin_audit import (
    AdminAuditedRoute,
    AdminAuditRecorder,
    get_admin_audit_recorder,
)
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.schemas.base import NgweeInt, StrictModel
from app.services.dispatch.state import json_rows
from app.services.logistics import area_pricing, custody, reports
from fastapi import APIRouter, Depends, Query
from pydantic import Field

logistics_router = APIRouter(
    prefix="/logistics",
    tags=["admin-logistics"],
    route_class=AdminAuditedRoute,
)

_UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class RemittanceIn(StrictModel):
    courier_partner_id: str = Field(pattern=_UUID_PATTERN)
    amount_ngwee: int = Field(gt=0, le=100_000_000)
    method: Literal["mobile_money", "bank_transfer", "lenco", "cash_deposit"] = "mobile_money"
    reference: str = Field(min_length=3, max_length=120)
    dispatch_ids: list[str] = Field(min_length=1, max_length=custody.MAX_DISPATCHES_PER_REMITTANCE)
    note: str | None = Field(default=None, max_length=500)


class RemittanceOut(StrictModel):
    remittance_id: str
    courier_partner_id: str
    amount_ngwee: int
    dispatch_ids: list[str]
    bookings: dict[str, str]


@logistics_router.get("/cash/custody")
def get_custody(
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> dict[str, Any]:
    """Cash each courier holds now, cash on active jobs, and the cap."""
    return {"couriers": custody.custody_summary()}


@logistics_router.post("/cash/remittances", response_model=RemittanceOut, status_code=201)
def post_remittance(
    body: RemittanceIn,
    admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> RemittanceOut:
    """Record a courier's same-day cash hand-in; books each order's cash in the ledger."""
    for dispatch_id in body.dispatch_ids:
        if not re.match(_UUID_PATTERN, dispatch_id):
            raise AppError(code="validation_error", message="Invalid dispatch id", http_status=422)
    result = custody.record_remittance(
        courier_partner_id=body.courier_partner_id.lower(),
        amount_ngwee=body.amount_ngwee,
        method=body.method,
        reference=body.reference,
        dispatch_ids=body.dispatch_ids,
        actor_id=admin.id,
        note=body.note,
    )
    recorder.record(
        action="admin.logistics.remittance.create",
        entity_type="courier_remittance",
        entity_id=result.remittance_id,
        before=None,
        after={
            "courier_partner_id": result.courier_partner_id,
            "amount_ngwee": result.amount_ngwee,
            "method": body.method,
            "dispatch_ids": list(result.dispatch_ids),
            "bookings": result.bookings,
        },
    )
    return RemittanceOut(
        remittance_id=result.remittance_id,
        courier_partner_id=result.courier_partner_id,
        amount_ngwee=result.amount_ngwee,
        dispatch_ids=list(result.dispatch_ids),
        bookings=result.bookings,
    )


@logistics_router.get("/cash/cash-up")
def get_cash_up(
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    day: Annotated[date | None, Query()] = None,
) -> dict[str, Any]:
    """Daily cash-up per courier: collected, remitted, outstanding (target: 0)."""
    return custody.daily_cash_up(day or date.today())


@logistics_router.get("/margin-report")
def get_margin_report(
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
) -> dict[str, Any]:
    """Delivery fee booked vs actual courier cost, by zone, courier and funding."""
    end_day = end or date.today() + timedelta(days=1)
    start_day = start or end_day - timedelta(days=7)
    if start_day >= end_day or (end_day - start_day).days > 93:
        raise AppError(
            code="validation_error",
            message="Choose a window of 1 to 93 days",
            http_status=422,
        )
    return reports.margin_report(start=start_day, end=end_day)


@logistics_router.get("/intercity-rates")
def get_intercity_rates(
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> dict[str, Any]:
    """Reference intercity parcel prices (price-list photos; verify before quoting)."""
    rows = json_rows(
        """
SELECT json_build_object(
  'id', id, 'carrier_name', carrier_name, 'origin_town', origin_town,
  'province', province, 'destination_town', destination_town,
  'small_parcel_ngwee', small_parcel_ngwee, 'medium_parcel_ngwee', medium_parcel_ngwee,
  'large_parcel_ngwee', large_parcel_ngwee, 'large_is_minimum', large_is_minimum,
  'liability_note', liability_note, 'source', source, 'confidence', confidence,
  'effective_from', effective_from
)::text
FROM public.intercity_rate_cards
WHERE active
ORDER BY destination_town, carrier_name;
""",
        context="intercity rate cards",
    )
    return {"rates": rows}


class PricingSwitchesOut(StrictModel):
    rain_mode: bool
    area_pricing_shadow: bool
    area_pricing_live: bool


class RainModeIn(StrictModel):
    enabled: bool


class AreaPricingIn(StrictModel):
    shadow: bool | None = None
    live: bool | None = None


def _switches_out(client: Any) -> PricingSwitchesOut:
    switches = area_pricing.load_switches(client)
    return PricingSwitchesOut(
        rain_mode=switches.rain,
        area_pricing_shadow=switches.shadow,
        area_pricing_live=switches.live,
    )


def _set_config_bool(client: Any, key: str, value: bool) -> None:
    _set_config(client, key, value)


def _set_config(client: Any, key: str, value: object) -> None:
    client.table("platform_config").upsert(
        {"key": key, "value": value}, on_conflict="key"
    ).execute()


@logistics_router.get("/pricing-switches", response_model=PricingSwitchesOut)
def get_pricing_switches(
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    service: Annotated[Any, Depends(get_supabase_client)],
) -> PricingSwitchesOut:
    """Rain mode and the area-pair pricing rollout switches (operations screen)."""
    return _switches_out(service.client)


@logistics_router.patch("/rain-mode", response_model=PricingSwitchesOut)
def patch_rain_mode(
    body: RainModeIn,
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service: Annotated[Any, Depends(get_supabase_client)],
) -> PricingSwitchesOut:
    """Rain switch: multiplies area-pair fees and widens promised windows by 30 min."""
    before = _switches_out(service.client)
    _set_config_bool(service.client, area_pricing.RAIN_KEY, body.enabled)
    recorder.record(
        action="admin.logistics.rain_mode.update",
        entity_type="platform_config",
        entity_id=area_pricing.RAIN_KEY,
        before={"value": before.rain_mode},
        after={"value": body.enabled},
    )
    return _switches_out(service.client)


@logistics_router.patch("/area-pricing", response_model=PricingSwitchesOut)
def patch_area_pricing(
    body: AreaPricingIn,
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service: Annotated[Any, Depends(get_supabase_client)],
) -> PricingSwitchesOut:
    """Full admins only: shadow (log next to the zone fee) and live (charge it)."""
    if body.shadow is None and body.live is None:
        raise AppError(code="validation_error", message="Nothing to change", http_status=422)
    before = _switches_out(service.client)
    if body.shadow is not None:
        _set_config_bool(service.client, area_pricing.SHADOW_KEY, body.shadow)
    if body.live is not None:
        _set_config_bool(service.client, area_pricing.LIVE_KEY, body.live)
    after = _switches_out(service.client)
    recorder.record(
        action="admin.logistics.area_pricing.update",
        entity_type="platform_config",
        entity_id="area_pricing",
        before={"shadow": before.area_pricing_shadow, "live": before.area_pricing_live},
        after={"shadow": after.area_pricing_shadow, "live": after.area_pricing_live},
    )
    return after


# ---------------------------------------------------------------------------
# Area-pair price table: settings, time bands and the distance table (full admins)
# ---------------------------------------------------------------------------

_AREA_SLUG = r"^[a-z0-9_]{2,40}$"
_HHMM = r"^([01][0-9]|2[0-3]):[0-5][0-9]$|^24:00$"
_ROAD_KM = r"^[0-9]{1,3}(\.[0-9]{1,2})?$"
MAX_ROAD_KM = Decimal(500)


class TimeBandIO(StrictModel):
    key: str = Field(pattern=_AREA_SLUG)
    start: str = Field(pattern=_HHMM)
    end: str = Field(pattern=_HHMM)
    multiplier_bps: int = Field(ge=area_pricing.BPS // 2, le=3 * area_pricing.BPS)


class AreaPricingSettingsIO(StrictModel):
    """The price formula, all integer ngwee / metres / basis points (no floats)."""

    base_per_km_ngwee: NgweeInt = Field(le=100_000)
    stop_fee_ngwee: NgweeInt = Field(le=1_000_000)
    intra_area_metres: int = Field(ge=0, le=20_000)
    min_fee_ngwee: NgweeInt = Field(le=1_000_000)
    max_fee_ngwee: NgweeInt = Field(le=1_000_000)
    rain_multiplier_bps: int = Field(ge=area_pricing.BPS, le=3 * area_pricing.BPS)
    zone_bounds: bool
    quote_ttl_minutes: int = Field(ge=5, le=240)
    time_bands: list[TimeBandIO] = Field(max_length=12)


def _data_rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _settings_out(settings: area_pricing.AreaPricingSettings) -> AreaPricingSettingsIO:
    return AreaPricingSettingsIO(
        base_per_km_ngwee=settings.base_per_km_ngwee,
        stop_fee_ngwee=settings.stop_fee_ngwee,
        intra_area_metres=settings.intra_area_metres,
        min_fee_ngwee=settings.min_fee_ngwee,
        max_fee_ngwee=settings.max_fee_ngwee,
        rain_multiplier_bps=settings.rain_multiplier_bps,
        zone_bounds=settings.zone_bounds,
        quote_ttl_minutes=settings.quote_ttl_minutes,
        time_bands=[
            TimeBandIO(
                key=band.key,
                start=_hhmm(band.start_minute),
                end=_hhmm(band.end_minute),
                multiplier_bps=band.multiplier_bps,
            )
            for band in settings.time_bands
        ],
    )


def _invalid(field: str, message: str) -> AppError:
    return AppError(
        code="validation_error", message=message, http_status=422, details={field: message}
    )


def _settings_payload(body: AreaPricingSettingsIO) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if body.min_fee_ngwee > body.max_fee_ngwee:
        raise _invalid("min_fee_ngwee", "must not exceed max_fee_ngwee")
    bands = sorted(body.time_bands, key=lambda band: band.start)
    if len({band.key for band in bands}) != len(bands):
        raise _invalid("time_bands", "band keys must be unique")
    previous_end = ""
    for band in bands:
        if band.end <= band.start:
            raise _invalid("time_bands", f"{band.key}: end must be after start")
        if previous_end and band.start < previous_end:
            raise _invalid("time_bands", f"{band.key}: overlaps the previous band")
        previous_end = band.end
    settings_value: dict[str, Any] = {
        "base_per_km_ngwee": body.base_per_km_ngwee,
        "stop_fee_ngwee": body.stop_fee_ngwee,
        # Stored as a decimal string so no float ever round-trips the config.
        "intra_area_km": str(Decimal(body.intra_area_metres) / 1000),
        "min_fee_ngwee": body.min_fee_ngwee,
        "max_fee_ngwee": body.max_fee_ngwee,
        "rain_multiplier_bps": body.rain_multiplier_bps,
        "zone_bounds": body.zone_bounds,
        "quote_ttl_minutes": body.quote_ttl_minutes,
    }
    bands_value = [band.model_dump() for band in bands]
    # The checkout reads these through parse_settings, which falls back to the
    # defaults on anything it cannot parse; refuse a save that would do that.
    parsed = area_pricing.parse_settings(settings_value, bands_value)
    if (
        _settings_out(parsed).model_dump()
        != body.model_copy(update={"time_bands": bands}).model_dump()
    ):
        raise _invalid("settings", "settings would not be read back as saved")
    return settings_value, bands_value


@logistics_router.get("/area-pricing/settings", response_model=AreaPricingSettingsIO)
def get_area_pricing_settings(
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    service: Annotated[Any, Depends(get_supabase_client)],
) -> AreaPricingSettingsIO:
    """The settings checkout is pricing with right now (defaults if the row is unreadable)."""
    return _settings_out(area_pricing.load_settings(service.client))


@logistics_router.put("/area-pricing/settings", response_model=AreaPricingSettingsIO)
def put_area_pricing_settings(
    body: AreaPricingSettingsIO,
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service: Annotated[Any, Depends(get_supabase_client)],
) -> AreaPricingSettingsIO:
    """Full admins only: per-km rate, stop fee, bounds, rain multiplier, time bands."""
    settings_value, bands_value = _settings_payload(body)
    before = _settings_out(area_pricing.load_settings(service.client))
    _set_config(service.client, area_pricing.SETTINGS_KEY, settings_value)
    _set_config(service.client, area_pricing.BANDS_KEY, bands_value)
    after = _settings_out(area_pricing.load_settings(service.client))
    recorder.record(
        action="admin.logistics.area_pricing_settings.update",
        entity_type="platform_config",
        entity_id=area_pricing.SETTINGS_KEY,
        before=before.model_dump(),
        after=after.model_dump(),
    )
    return after


class AdminAreaOut(StrictModel):
    slug: str
    name: str
    zone_key: str
    active: bool


class AreaDistanceOut(StrictModel):
    from_area: str
    to_area: str
    road_km: str
    minutes: int
    source: str
    manual_override: bool


class AreaDistancesOut(StrictModel):
    from_area: str
    rows: list[AreaDistanceOut]


class AreaDistanceIn(StrictModel):
    #: Decimal string, two places at most (no float on the wire).
    road_km: str = Field(pattern=_ROAD_KM)
    minutes: int = Field(ge=0, le=600)
    #: Also write the same km / minutes for to_area -> from_area.
    both_directions: bool = False


MANUAL_DISTANCE_SOURCE = "manual edit (admin)"


def _km_text(raw: object) -> str:
    metres = area_pricing.km_to_metres(raw)
    if metres is None:
        return "0.00"
    return str((Decimal(metres) / 1000).quantize(Decimal("0.01")))


def _distance_out(row: dict[str, Any]) -> AreaDistanceOut:
    return AreaDistanceOut(
        from_area=str(row.get("from_area")),
        to_area=str(row.get("to_area")),
        road_km=_km_text(row.get("road_km")),
        minutes=int(row.get("minutes") or 0),
        source=str(row.get("source") or ""),
        manual_override=row.get("manual_override") is True,
    )


@logistics_router.get("/areas", response_model=list[AdminAreaOut])
def list_admin_areas(
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    service: Annotated[Any, Depends(get_supabase_client)],
) -> list[AdminAreaOut]:
    rows = _data_rows(
        service.client.table("areas").select("slug, name, zone_key, active").order("name").execute()
    )
    return [
        AdminAreaOut(
            slug=str(row["slug"]),
            name=str(row["name"]),
            zone_key=str(row["zone_key"]),
            active=row.get("active") is True,
        )
        for row in rows
    ]


@logistics_router.get("/area-distances", response_model=AreaDistancesOut)
def list_area_distances(
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    service: Annotated[Any, Depends(get_supabase_client)],
    from_area: Annotated[str, Query(pattern=_AREA_SLUG)],
) -> AreaDistancesOut:
    """Every distance row from one area (the shop side) to the others."""
    rows = _data_rows(
        service.client.table("area_distances")
        .select("from_area, to_area, road_km, minutes, source, manual_override")
        .eq("from_area", from_area)
        .order("to_area")
        .execute()
    )
    return AreaDistancesOut(from_area=from_area, rows=[_distance_out(row) for row in rows])


def _existing_area_slugs(client: Any, slugs: list[str]) -> set[str]:
    rows = _data_rows(client.table("areas").select("slug").in_("slug", slugs).execute())
    return {str(row["slug"]) for row in rows}


def _distance_rows(client: Any, pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for from_area, to_area in pairs:
        found.extend(
            _data_rows(
                client.table("area_distances")
                .select("from_area, to_area, road_km, minutes, source, manual_override")
                .eq("from_area", from_area)
                .eq("to_area", to_area)
                .execute()
            )
        )
    return found


@logistics_router.patch(
    "/area-distances/{from_area}/{to_area}", response_model=list[AreaDistanceOut]
)
def patch_area_distance(
    from_area: str,
    to_area: str,
    body: AreaDistanceIn,
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
    service: Annotated[Any, Depends(get_supabase_client)],
) -> list[AreaDistanceOut]:
    """Correct one area pair by hand; the row is marked manual so a refresh keeps it."""
    if not (re.fullmatch(_AREA_SLUG, from_area) and re.fullmatch(_AREA_SLUG, to_area)):
        raise _invalid("area", "unknown area")
    if from_area == to_area:
        raise _invalid("to_area", "must differ from from_area (same-area trips use intra_area)")
    road_km = Decimal(body.road_km)
    if road_km > MAX_ROAD_KM:
        raise _invalid("road_km", f"must be at most {MAX_ROAD_KM}")
    if _existing_area_slugs(service.client, [from_area, to_area]) != {from_area, to_area}:
        raise AppError(code="not_found", message="Area not found", http_status=404)
    pairs = [(from_area, to_area)]
    if body.both_directions:
        pairs.append((to_area, from_area))
    before = [_distance_out(row) for row in _distance_rows(service.client, pairs)]
    service.client.table("area_distances").upsert(
        [
            {
                "from_area": a,
                "to_area": b,
                "road_km": str(road_km),
                "minutes": body.minutes,
                "source": MANUAL_DISTANCE_SOURCE,
                "manual_override": True,
            }
            for a, b in pairs
        ],
        on_conflict="from_area,to_area",
    ).execute()
    after = [_distance_out(row) for row in _distance_rows(service.client, pairs)]
    recorder.record(
        action="admin.logistics.area_distance.update",
        entity_type="area_distances",
        entity_id=f"{from_area}->{to_area}",
        before={"rows": [row.model_dump() for row in before]},
        after={"rows": [row.model_dump() for row in after]},
    )
    return after


admin_router.include_router(logistics_router)
