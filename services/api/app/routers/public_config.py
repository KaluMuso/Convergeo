"""Public, read-only platform config surfaces (no auth, cacheable).

Routes (auto-discovered via the module-level ``router``):

* ``GET /public/config/commission-rates`` — D4 category commission percentages for
  marketing/checkout display. Service-role read of ``commission_rates``; safe to
  cache at the edge (``s-maxage=300``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Protocol

from app.deps import get_supabase_client
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends, Response
from pydantic import Field

router = APIRouter(prefix="/public/config", tags=["public-config"])

PUBLIC_COMMISSION_CACHE_CONTROL = "public, s-maxage=300, stale-while-revalidate=60"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class PublicCommissionRate(StrictModel):
    category_key: str
    rate_pct: int | float = Field(description="Percentage from rate_bps (no float drift)")


class PublicCommissionRatesResponse(StrictModel):
    rates: list[PublicCommissionRate]
    updated_at: datetime


def _bps_to_rate_pct(rate_bps: int) -> int | float:
    if rate_bps % 100 == 0:
        return rate_bps // 100
    return float(Decimal(rate_bps) / Decimal(100))


def _parse_updated_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


@router.get("/commission-rates", response_model=PublicCommissionRatesResponse)
async def get_public_commission_rates(
    response: Response,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PublicCommissionRatesResponse:
    db_response = (
        service_client.client.table("commission_rates")
        .select("category_key, rate_bps, updated_at")
        .order("category_key")
        .execute()
    )
    rows = db_response.data if isinstance(db_response.data, list) else []

    rates: list[PublicCommissionRate] = []
    latest_updated_at: datetime | None = None

    for row in rows:
        if not isinstance(row, dict):
            continue
        category_key = row.get("category_key")
        rate_bps = row.get("rate_bps")
        if not isinstance(category_key, str) or not isinstance(rate_bps, int):
            continue

        rates.append(
            PublicCommissionRate(
                category_key=category_key,
                rate_pct=_bps_to_rate_pct(rate_bps),
            )
        )

        row_updated_at = _parse_updated_at(row.get("updated_at"))
        if row_updated_at is not None and (
            latest_updated_at is None or row_updated_at > latest_updated_at
        ):
            latest_updated_at = row_updated_at

    response.headers["Cache-Control"] = PUBLIC_COMMISSION_CACHE_CONTROL

    return PublicCommissionRatesResponse(
        rates=rates,
        updated_at=latest_updated_at or datetime.now(UTC),
    )


class PublicFxRateResponse(StrictModel):
    published: bool
    stale: bool = True
    rate_zmw_per_usd_micros: int | None = None
    vendor_margin_bps: int | None = None
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    source: str | None = None


@router.get("/fx-rate", response_model=PublicFxRateResponse)
async def get_public_fx_rate(
    response: Response,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PublicFxRateResponse:
    from app.services.fx.rates import load_current_usd_zmw_rate

    snapshot = load_current_usd_zmw_rate(service_client.client)
    response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=30"
    if snapshot is None:
        return PublicFxRateResponse(published=False, stale=True)
    return PublicFxRateResponse(
        published=True,
        stale=snapshot.stale,
        rate_zmw_per_usd_micros=snapshot.rate_zmw_per_usd_micros,
        vendor_margin_bps=snapshot.vendor_margin_bps,
        effective_at=snapshot.effective_at,
        expires_at=snapshot.expires_at,
        source=snapshot.source,
    )
