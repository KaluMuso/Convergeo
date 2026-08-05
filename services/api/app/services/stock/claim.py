from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.services.db import SqlResult as SqlResult
from app.services.db import resolve_db_url as resolve_db_url
from app.services.db import run_sql_script as run_sql_script

_DEFAULT_TTL_MIN = 15
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def sql_uuid(value: str, field: str) -> str:
    if not _UUID_RE.match(value):
        raise ValueError(f"Invalid UUID for {field}")
    UUID(value)
    return f"'{value}'::uuid"


def sql_int(value: int, field: str) -> str:
    if value <= 0:
        raise ValueError(f"{field} must be positive")
    return str(value)


def _service_client() -> Any:
    return importlib.import_module("app.supabase_client").get_supabase_service_client()


@dataclass(frozen=True, slots=True)
class ClaimResult:
    claimed: bool
    listing_id: str
    checkout_group_id: str
    qty: int
    skipped: bool = False
    remaining_stock_qty: int | None = None
    location_id: str | None = None


def get_reservation_ttl_minutes() -> int:
    service = _service_client()
    response = (
        service.client.table("platform_config")
        .select("value")
        .eq("key", "reservation_ttl_min")
        .maybe_single()
        .execute()
    )
    data = response.data
    if isinstance(data, dict) and data.get("value") is not None:
        raw = data["value"]
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
    return _DEFAULT_TTL_MIN


def _fetch_listing_stock_mode(listing_id: str) -> tuple[str | None, bool]:
    listing_sql = sql_uuid(listing_id, "listing_id")
    result = run_sql_script(
        f"SELECT stock_mode, product_class, fulfilment_mode "
        f"FROM public.vendor_listings WHERE id = {listing_sql};"
    )
    if not result.ok or not result.rows:
        return None, False
    parts = result.rows[0].split("|")
    if len(parts) != 3:
        return None, False
    stock_mode, product_class, fulfilment_mode = parts
    made_to_order = product_class == "E" or fulfilment_mode == "made_to_order"
    return stock_mode, made_to_order


def _branch_claim_script(
    *,
    listing_sql: str,
    group_sql: str,
    qty_sql: str,
    location_sql: str,
    expires_literal: str,
) -> str:
    return f"""
BEGIN;
WITH claimed AS (
  UPDATE public.listing_location_stock
  SET stock_qty = stock_qty - {qty_sql}
  WHERE listing_id = {listing_sql}
    AND location_id = {location_sql}
    AND stock_qty >= {qty_sql}
  RETURNING stock_qty
),
upserted AS (
  INSERT INTO public.stock_reservations (
    listing_id, checkout_group_id, qty, expires_at, location_id
  )
  SELECT {listing_sql}, {group_sql}, {qty_sql}, '{expires_literal}'::timestamptz, {location_sql}
  FROM claimed
  ON CONFLICT (listing_id, checkout_group_id) DO UPDATE
    SET qty = EXCLUDED.qty,
        expires_at = EXCLUDED.expires_at,
        location_id = EXCLUDED.location_id
  RETURNING 1
)
SELECT stock_qty::text FROM claimed;
COMMIT;
"""


def _legacy_claim_script(
    *,
    listing_sql: str,
    group_sql: str,
    qty_sql: str,
    expires_literal: str,
) -> str:
    return f"""
BEGIN;
WITH claimed AS (
  UPDATE public.vendor_listings
  SET stock_qty = stock_qty - {qty_sql}
  WHERE id = {listing_sql}
    AND stock_mode = 'tracked'
    AND stock_qty >= {qty_sql}
  RETURNING stock_qty
),
upserted AS (
  INSERT INTO public.stock_reservations (
    listing_id, checkout_group_id, qty, expires_at
  )
  SELECT {listing_sql}, {group_sql}, {qty_sql}, '{expires_literal}'::timestamptz
  FROM claimed
  ON CONFLICT (listing_id, checkout_group_id) DO UPDATE
    SET qty = EXCLUDED.qty,
        expires_at = EXCLUDED.expires_at
  RETURNING 1
)
SELECT stock_qty::text FROM claimed;
COMMIT;
"""


def claim_reservation(
    *,
    listing_id: str,
    checkout_group_id: str,
    qty: int,
    ttl_minutes: int | None = None,
    location_id: str | None = None,
) -> ClaimResult:
    if not _UUID_RE.match(listing_id) or not _UUID_RE.match(checkout_group_id):
        raise ValueError("listing_id and checkout_group_id must be valid UUIDs")
    if qty <= 0:
        raise ValueError("qty must be positive")
    if location_id is not None and not _UUID_RE.match(location_id):
        raise ValueError("location_id must be a valid UUID")

    stock_mode, made_to_order = _fetch_listing_stock_mode(listing_id)
    if stock_mode is None:
        return ClaimResult(
            claimed=False,
            listing_id=listing_id,
            checkout_group_id=checkout_group_id,
            qty=qty,
        )
    if stock_mode == "always_available" or made_to_order:
        return ClaimResult(
            claimed=True,
            listing_id=listing_id,
            checkout_group_id=checkout_group_id,
            qty=qty,
            skipped=True,
        )

    branch_tracked = importlib.import_module(
        "app.services.inventory.location_stock"
    ).is_branch_tracked(listing_id)
    if branch_tracked and location_id is None:
        return ClaimResult(
            claimed=False,
            listing_id=listing_id,
            checkout_group_id=checkout_group_id,
            qty=qty,
        )

    ttl = ttl_minutes if ttl_minutes is not None else get_reservation_ttl_minutes()
    expires_at = datetime.now(UTC) + timedelta(minutes=ttl)
    expires_literal = expires_at.isoformat()

    listing_sql = sql_uuid(listing_id, "listing_id")
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    qty_sql = sql_int(qty, "qty")

    if branch_tracked and location_id is not None:
        location_sql = sql_uuid(location_id, "location_id")
        script = _branch_claim_script(
            listing_sql=listing_sql,
            group_sql=group_sql,
            qty_sql=qty_sql,
            location_sql=location_sql,
            expires_literal=expires_literal,
        )
        claim_location_id = location_id
    else:
        script = _legacy_claim_script(
            listing_sql=listing_sql,
            group_sql=group_sql,
            qty_sql=qty_sql,
            expires_literal=expires_literal,
        )
        claim_location_id = None

    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"claim_reservation failed: {result.error}")

    if not result.rows:
        return ClaimResult(
            claimed=False,
            listing_id=listing_id,
            checkout_group_id=checkout_group_id,
            qty=qty,
            location_id=claim_location_id,
        )

    remaining = int(result.rows[-1])
    return ClaimResult(
        claimed=True,
        listing_id=listing_id,
        checkout_group_id=checkout_group_id,
        qty=qty,
        remaining_stock_qty=remaining,
        location_id=claim_location_id,
    )
