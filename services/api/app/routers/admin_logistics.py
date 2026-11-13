"""Logistics operations (phase 1): rider cash custody, remittances, cash-up, margin.

Mounted under the shared admin router (``/admin/logistics``). A restricted
operator needs ``cod.reconcile`` for cash routes and ``logistics.manage`` for
the margin report and reference rate cards (``app.core.auth`` route inventory).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
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
from app.schemas.base import StrictModel
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


admin_router.include_router(logistics_router)
