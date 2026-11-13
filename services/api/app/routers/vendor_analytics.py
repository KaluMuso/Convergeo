"""Vendor analytics — lightweight, vendor-scoped 7/30-day aggregates.

Numbers reconcile with orders truth: sales/orders are derived from the vendor's
own `orders` + `order_items` rows (cancelled excluded). The "cart activity"
metric (legacy API fields `views_by_day` / `views_total`) counts distinct
add-to-cart / checkout-start `funnel_events` whose cart snapshot references one of
the vendor's listings — buying-intent activity, not raw storefront impressions,
not unique visitors or matched order-producing journeys. The order/activity ratio
compares independent window totals, can exceed 100, and is not a conversion rate.
Legacy fields keep their numeric values; explicit fields describe the same data.
All money is integer ngwee; the client renders via `formatK`.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.vendor_orders import _load_vendor_for_owner
from app.schemas.base import StrictModel
from app.services.orders.audit import run_sql_script
from fastapi import APIRouter, Depends, Query
from pydantic import Field

router = APIRouter(prefix="/vendor/analytics", tags=["vendor-analytics"])

ALLOWED_WINDOWS: frozenset[int] = frozenset({7, 30})
TOP_LISTINGS_LIMIT = 5

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class TopListing(StrictModel):
    listing_id: str
    title: str
    units: int
    revenue_ngwee: int


class ConversionHint(StrictModel):
    """Deprecated field names; values retained for older consumers."""

    orders_total: int
    views_total: int = Field(
        description="Distinct cart_add/checkout_start event rows, not listing views.",
        deprecated=True,
    )
    conversion_pct: float = Field(
        description="Orders per 100 activity events, not conversion; legacy zero if none.",
        deprecated=True,
    )


class OrderActivityRatio(StrictModel):
    """Independent totals in the UTC window, not a matched conversion cohort."""

    orders_total: int = Field(description="Non-cancelled vendor orders created in the window.")
    cart_activity_events_total: int = Field(
        description="Distinct cart_add/checkout_start rows referencing a vendor listing."
    )
    orders_per_100_cart_activity_events: float | None = Field(
        description="100 * orders / activity events; may exceed 100; null if no events."
    )


class VendorAnalyticsResponse(StrictModel):
    window: int
    days: list[str]
    sales_ngwee_by_day: list[int]
    orders_by_day: list[int]
    cart_activity_events_by_day: list[int]
    views_by_day: list[int] = Field(
        description="Legacy alias of cart_activity_events_by_day; not listing views.",
        deprecated=True,
    )
    top_listings: list[TopListing]
    order_activity_ratio: OrderActivityRatio
    conversion_hint: ConversionHint = Field(deprecated=True)


class VendorAnalyticsSummary(StrictModel):
    """Trailing 30-day headline metrics for the vendor dashboard overview."""

    window_days: int = 30
    total_views: int
    total_orders: int
    gmv_ngwee: int
    impressions: int
    pdp_views: int


def _validate_window(window: int) -> int:
    if window not in ALLOWED_WINDOWS:
        raise AppError(
            code="invalid_window",
            message="window must be 7 or 30",
            http_status=400,
            details={"message_key": "vendor.analytics.errors.invalidWindow"},
        )
    return window


def _safe_vendor_uuid(vendor_id: str) -> str:
    # vendor_id is derived server-side from the authed owner, but validate before
    # embedding so a malformed value can never reach the SQL string.
    if not _UUID_RE.match(vendor_id):
        raise AppError(
            code="invalid_vendor",
            message="vendor id is not a valid uuid",
            http_status=400,
        )
    return vendor_id


def _window_start_sql(window: int) -> str:
    return f"(date_trunc('day', timezone('utc', now())) - interval '{window - 1} days')"


def _run(script: str, *, what: str) -> list[str]:
    result = run_sql_script(script)
    if not result.ok:
        raise AppError(
            code="analytics_query_failed",
            message=f"Failed to compute {what}",
            http_status=500,
            details={"error": result.error},
        )
    return result.rows


def _sales_orders_by_day(vendor_sql: str, window: int) -> tuple[list[str], list[int], list[int]]:
    start = _window_start_sql(window)
    script = f"""
WITH days AS (
  SELECT generate_series(
    {start},
    date_trunc('day', timezone('utc', now())),
    interval '1 day'
  )::date AS day
),
vo AS (
  SELECT o.id, (o.created_at AT TIME ZONE 'utc')::date AS day
  FROM public.orders o
  WHERE o.vendor_id = '{vendor_sql}'::uuid
    AND o.status <> 'cancelled'
    AND o.created_at >= {start}
),
agg AS (
  SELECT vo.day,
         count(DISTINCT vo.id) AS orders,
         coalesce(sum(oi.qty * oi.unit_price_ngwee), 0) AS sales
  FROM vo
  LEFT JOIN public.order_items oi ON oi.order_id = vo.id
  GROUP BY vo.day
)
SELECT to_char(d.day, 'YYYY-MM-DD'),
       coalesce(agg.sales, 0)::text,
       coalesce(agg.orders, 0)::text
FROM days d
LEFT JOIN agg ON agg.day = d.day
ORDER BY d.day ASC;
"""
    days: list[str] = []
    sales: list[int] = []
    orders: list[int] = []
    for row in _run(script, what="sales/orders"):
        parts = row.split("|")
        if len(parts) < 3:
            continue
        days.append(parts[0])
        sales.append(int(parts[1]))
        orders.append(int(parts[2]))
    return days, sales, orders


def _cart_activity_events_by_day(vendor_sql: str, window: int) -> list[int]:
    start = _window_start_sql(window)
    script = f"""
WITH days AS (
  SELECT generate_series(
    {start},
    date_trunc('day', timezone('utc', now())),
    interval '1 day'
  )::date AS day
),
vl AS (
  SELECT id FROM public.vendor_listings WHERE vendor_id = '{vendor_sql}'::uuid
),
ev AS (
  SELECT DISTINCT fe.id, (fe.created_at AT TIME ZONE 'utc')::date AS day
  FROM public.funnel_events fe
  CROSS JOIN LATERAL jsonb_array_elements(
    coalesce(fe.snapshot -> 'lines', '[]'::jsonb)
  ) AS line
  JOIN vl ON vl.id::text = line ->> 'listing_id'
  WHERE fe.stage IN ('cart_add', 'checkout_start')
    AND fe.created_at >= {start}
),
agg AS (
  SELECT ev.day, count(*) AS activity_events FROM ev GROUP BY ev.day
)
SELECT to_char(d.day, 'YYYY-MM-DD'), coalesce(agg.activity_events, 0)::text
FROM days d
LEFT JOIN agg ON agg.day = d.day
ORDER BY d.day ASC;
"""
    activity_events: list[int] = []
    for row in _run(script, what="cart/checkout activity events"):
        parts = row.split("|")
        if len(parts) < 2:
            continue
        activity_events.append(int(parts[1]))
    return activity_events


def _top_listings(vendor_sql: str, window: int) -> list[TopListing]:
    start = _window_start_sql(window)
    # title is selected LAST so a pipe inside the title cannot break row parsing.
    script = f"""
SELECT oip.listing_id::text,
       coalesce(sum(oi.qty), 0)::text AS units,
       coalesce(sum(oi.qty * oi.unit_price_ngwee), 0)::text AS revenue,
       coalesce(nullif(vl.title_override, ''), p.name, '') AS title
FROM public.orders o
JOIN public.order_items oi ON oi.order_id = o.id
JOIN public.order_item_products oip ON oip.order_item_id = oi.id
JOIN public.vendor_listings vl ON vl.id = oip.listing_id
LEFT JOIN public.products p ON p.id = vl.product_id
WHERE o.vendor_id = '{vendor_sql}'::uuid
  AND o.status <> 'cancelled'
  AND o.created_at >= {start}
GROUP BY oip.listing_id, vl.title_override, p.name
ORDER BY sum(oi.qty * oi.unit_price_ngwee) DESC, oip.listing_id ASC
LIMIT {TOP_LISTINGS_LIMIT};
"""
    listings: list[TopListing] = []
    for row in _run(script, what="top listings"):
        parts = row.split("|", 3)
        if len(parts) < 4:
            continue
        listings.append(
            TopListing(
                listing_id=parts[0],
                units=int(parts[1]),
                revenue_ngwee=int(parts[2]),
                title=parts[3],
            )
        )
    return listings


def _listing_views_totals(vendor_sql: str, window: int) -> tuple[int, int]:
    start = _window_start_sql(window)
    script = f"""
SELECT coalesce(sum(la.impressions), 0)::text,
       coalesce(sum(la.pdp_views), 0)::text
FROM public.listing_analytics la
JOIN public.vendor_listings vl ON vl.id = la.listing_id
WHERE vl.vendor_id = '{vendor_sql}'::uuid
  AND la.day >= ({start})::date;
"""
    rows = _run(script, what="listing views")
    if not rows:
        return 0, 0
    parts = rows[0].split("|")
    if len(parts) < 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


def compute_vendor_analytics_summary(vendor_id: str) -> VendorAnalyticsSummary:
    """Aggregate views, orders, and GMV over the trailing 30 days."""
    window = 30
    vendor_sql = _safe_vendor_uuid(vendor_id)
    _, sales, orders = _sales_orders_by_day(vendor_sql, window)
    impressions, pdp_views = _listing_views_totals(vendor_sql, window)
    total_views = impressions + pdp_views
    return VendorAnalyticsSummary(
        window_days=window,
        total_views=total_views,
        total_orders=sum(orders),
        gmv_ngwee=sum(sales),
        impressions=impressions,
        pdp_views=pdp_views,
    )


def compute_vendor_analytics(vendor_id: str, window: int) -> VendorAnalyticsResponse:
    """Assemble vendor-scoped analytics; empty history yields zero-filled series."""
    vendor_sql = _safe_vendor_uuid(vendor_id)
    days, sales, orders = _sales_orders_by_day(vendor_sql, window)
    activity_events = _cart_activity_events_by_day(vendor_sql, window)
    top = _top_listings(vendor_sql, window)

    orders_total = sum(orders)
    activity_events_total = sum(activity_events)
    orders_per_100_events = (
        round(100.0 * orders_total / activity_events_total, 1) if activity_events_total else None
    )

    return VendorAnalyticsResponse(
        window=window,
        days=days,
        sales_ngwee_by_day=sales,
        orders_by_day=orders,
        cart_activity_events_by_day=activity_events,
        views_by_day=activity_events,
        top_listings=top,
        order_activity_ratio=OrderActivityRatio(
            orders_total=orders_total,
            cart_activity_events_total=activity_events_total,
            orders_per_100_cart_activity_events=orders_per_100_events,
        ),
        conversion_hint=ConversionHint(
            orders_total=orders_total,
            views_total=activity_events_total,
            conversion_pct=orders_per_100_events if orders_per_100_events is not None else 0.0,
        ),
    )


@router.get("/summary", response_model=VendorAnalyticsSummary)
def get_vendor_analytics_summary(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorAnalyticsSummary:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    return compute_vendor_analytics_summary(str(vendor["id"]))


@router.get("", response_model=VendorAnalyticsResponse)
def get_vendor_analytics(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    window: Annotated[int, Query(description="Trailing window in days (7 or 30)")] = 7,
) -> VendorAnalyticsResponse:
    validated = _validate_window(window)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    return compute_vendor_analytics(vendor_id, validated)


__all__ = [
    "ConversionHint",
    "OrderActivityRatio",
    "TopListing",
    "VendorAnalyticsResponse",
    "VendorAnalyticsSummary",
    "compute_vendor_analytics",
    "compute_vendor_analytics_summary",
]
