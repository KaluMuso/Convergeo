from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.stock.claim import run_sql_script, sql_uuid

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ReleaseResult:
    released: bool
    listing_id: str
    checkout_group_id: str
    qty: int
    restocked: bool = False


def release_reservation(
    *,
    listing_id: str,
    checkout_group_id: str,
) -> ReleaseResult:
    if not _UUID_RE.match(listing_id) or not _UUID_RE.match(checkout_group_id):
        raise ValueError("listing_id and checkout_group_id must be valid UUIDs")

    listing_sql = sql_uuid(listing_id, "listing_id")
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")

    script = f"""
BEGIN;
WITH deleted AS (
  DELETE FROM public.stock_reservations
  WHERE listing_id = {listing_sql}
    AND checkout_group_id = {group_sql}
  RETURNING listing_id, checkout_group_id, qty
)
UPDATE public.vendor_listings vl
SET stock_qty = vl.stock_qty + deleted.qty
FROM deleted
WHERE vl.id = deleted.listing_id
  AND vl.stock_mode = 'tracked'
    RETURNING deleted.listing_id::text, deleted.checkout_group_id::text, deleted.qty::text;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"release_reservation failed: {result.error}")

    if not result.rows:
        return ReleaseResult(
            released=False,
            listing_id=listing_id,
            checkout_group_id=checkout_group_id,
            qty=0,
            restocked=False,
        )

    parts = result.rows[-1].split("|")
    if len(parts) != 3:
        raise RuntimeError("release_reservation returned unexpected row shape")

    return ReleaseResult(
        released=True,
        listing_id=parts[0],
        checkout_group_id=parts[1],
        qty=int(parts[2]),
        restocked=True,
    )
