"""Deterministic trending listings from recent PDP views with recency decay."""

from __future__ import annotations

from typing import Any

from app.schemas.base import NgweeInt, StrictModel
from app.services.listings.demo import fetch_demo_listing_ids
from app.services.orders.audit import run_sql_script

# Exponential half-life ~4 days — recent views matter more; raw totals cannot dominate.
_DECAY_PER_DAY = 0.85
_WINDOW_DAYS = 7


class TrendingListing(StrictModel):
    listing_id: str
    title: str
    product_slug: str | None
    vendor_name: str
    price_ngwee: NgweeInt
    image_public_id: str | None = None
    score: float


_TRENDING_SQL = f"""
WITH scored AS (
  SELECT
    la.listing_id,
    sum(
      la.pdp_views::float * power({_DECAY_PER_DAY}::float, greatest(0, current_date - la.day))
    ) AS trend_score
  FROM public.listing_analytics la
  WHERE la.day >= current_date - interval '{_WINDOW_DAYS} days'
    AND la.pdp_views > 0
  GROUP BY la.listing_id
  HAVING sum(la.pdp_views) >= 2
)
SELECT
  vl.id::text,
  coalesce(sd.title, vl.title, 'Listing') AS title,
  p.slug AS product_slug,
  v.display_name AS vendor_name,
  coalesce(vl.price_ngwee, 0)::text AS price_ngwee,
  (
    SELECT li.public_id
    FROM public.listing_images li
    WHERE li.listing_id = vl.id
    ORDER BY li.position ASC
    LIMIT 1
  ) AS image_public_id,
  scored.trend_score::text
FROM scored
JOIN public.vendor_listings vl ON vl.id = scored.listing_id
JOIN public.vendors v ON v.id = vl.vendor_id
LEFT JOIN public.products p ON p.id = vl.product_id
LEFT JOIN public.search_documents sd ON sd.entity_kind = 'listing' AND sd.entity_id = vl.id::text
WHERE vl.status = 'active'
  AND v.status = 'active'
  AND coalesce(vl.wholesale, false) = false
ORDER BY scored.trend_score DESC, vl.updated_at DESC
LIMIT %s;
"""


def fetch_trending_listings(client: Any, *, limit: int = 8) -> list[TrendingListing]:
    safe_limit = max(1, min(int(limit), 24))
    result = run_sql_script(_TRENDING_SQL.replace("%s", str(safe_limit)))
    if not result.ok:
        return []

    parsed_rows: list[tuple[str, ...]] = []
    listing_ids: list[str] = []
    for line in result.rows:
        parts = line.split("|")
        if len(parts) < 7:
            continue
        parsed_rows.append(tuple(parts[:7]))
        listing_ids.append(parts[0])

    demo_ids = fetch_demo_listing_ids(client, listing_ids)

    items: list[TrendingListing] = []
    for parts in parsed_rows:
        listing_id, title, product_slug, vendor_name, price_raw, image_public_id, score_raw = parts
        if listing_id in demo_ids:
            continue
        try:
            price_ngwee = int(price_raw)
            score = float(score_raw)
        except ValueError:
            continue
        items.append(
            TrendingListing(
                listing_id=listing_id,
                title=title,
                product_slug=product_slug or None,
                vendor_name=vendor_name,
                price_ngwee=price_ngwee,
                image_public_id=image_public_id or None,
                score=round(score, 3),
            )
        )
    return items
