"""Weekly delivery margin report: fee booked vs actual courier cost (ngwee)."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.services.dispatch.state import json_rows
from app.services.orders.audit import sql_literal


def margin_report(*, start: date, end: date) -> dict[str, Any]:
    """Delivered and failed jobs in [start, end) (Lusaka days), by zone and courier.

    Revenue per order is what delivery_revenue receives: the customer's fee, or
    the vendor/platform-funded amount. Cost is the actual courier cost entered
    per job (every attempt counts, including failed ones and returns). Jobs
    without a cost are listed so the report never looks better than it is.
    """
    start_sql = sql_literal(start.isoformat())
    end_sql = sql_literal(end.isoformat())
    window = f"""
WITH bounds AS (
  SELECT ({start_sql}::date::timestamp AT TIME ZONE 'Africa/Lusaka') AS start_at,
         ({end_sql}::date::timestamp AT TIME ZONE 'Africa/Lusaka') AS end_at
), jobs AS (
  SELECT d.id, d.order_id, d.courier_partner_id, d.status, d.direction, d.actual_cost_ngwee,
         o.delivery_zone, o.delivery_fee_ngwee + o.delivery_funded_ngwee AS revenue_ngwee,
         o.delivery_funding,
         -- Revenue counts once per order: on its delivered delivery job.
         (d.status = 'delivered' AND d.direction = 'delivery') AS counts_revenue
  FROM public.dispatch_requests d
  JOIN public.orders o ON o.id = d.order_id, bounds b
  WHERE coalesce(d.delivered_at, d.failed_at, d.cancelled_at) >= b.start_at
    AND coalesce(d.delivered_at, d.failed_at, d.cancelled_at) < b.end_at
    AND d.status IN ('delivered', 'failed', 'cancelled')
)
"""

    def grouped(key_sql: str, label: str) -> list[dict[str, Any]]:
        return json_rows(
            window
            + f"""
SELECT json_build_object(
  '{label}', {key_sql},
  'jobs', count(*),
  'delivered', count(*) FILTER (WHERE counts_revenue),
  'failed', count(*) FILTER (WHERE status = 'failed'),
  'revenue_ngwee', coalesce(sum(revenue_ngwee) FILTER (WHERE counts_revenue), 0),
  'cost_ngwee', coalesce(sum(actual_cost_ngwee), 0),
  'missing_cost', count(*) FILTER (WHERE actual_cost_ngwee IS NULL AND status <> 'cancelled'),
  'margin_ngwee', coalesce(sum(revenue_ngwee) FILTER (WHERE counts_revenue), 0)
                  - coalesce(sum(actual_cost_ngwee), 0)
)::text
FROM jobs j
LEFT JOIN public.courier_partners c ON c.id = j.courier_partner_id
GROUP BY {key_sql}
ORDER BY {key_sql} NULLS LAST;
""",
            context=f"margin report by {label}",
        )

    by_zone = grouped("j.delivery_zone", "zone")
    by_courier = grouped("c.name", "courier")
    by_funding = grouped("j.delivery_funding", "funding")
    missing = json_rows(
        window
        + """
SELECT json_build_object('dispatch_id', id, 'order_id', order_id, 'status', status)::text
FROM jobs WHERE actual_cost_ngwee IS NULL AND status <> 'cancelled'
ORDER BY id LIMIT 200;
""",
        context="margin report missing costs",
    )
    revenue = sum(int(r["revenue_ngwee"]) for r in by_zone)
    cost = sum(int(r["cost_ngwee"]) for r in by_zone)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "revenue_ngwee": revenue,
        "cost_ngwee": cost,
        "margin_ngwee": revenue - cost,
        "by_zone": by_zone,
        "by_courier": by_courier,
        "by_funding": by_funding,
        "missing_cost": missing,
    }
