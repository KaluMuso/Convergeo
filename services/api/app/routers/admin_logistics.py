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
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.schemas.base import StrictModel
from app.services.dispatch.state import json_rows
from app.services.logistics import custody, reports
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


admin_router.include_router(logistics_router)
