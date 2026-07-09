from __future__ import annotations

import importlib
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

_DEFAULT_TTL_MIN = 15
_DEFAULT_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SqlResult:
    ok: bool
    rows: list[str]
    error: str | None = None


def resolve_db_url() -> str:
    return os.environ.get("SUPABASE_DB_URL", _DEFAULT_DB_URL)


def sql_uuid(value: str, field: str) -> str:
    if not _UUID_RE.match(value):
        raise ValueError(f"Invalid UUID for {field}")
    UUID(value)
    return f"'{value}'::uuid"


def sql_int(value: int, field: str) -> str:
    if value <= 0:
        raise ValueError(f"{field} must be positive")
    return str(value)


def run_sql_script(script: str) -> SqlResult:
    proc = subprocess.run(
        ["psql", resolve_db_url(), "-v", "ON_ERROR_STOP=1", "-At"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return SqlResult(ok=False, rows=[], error=proc.stderr.strip())
    rows = [line for line in proc.stdout.splitlines() if line]
    noise = {"BEGIN", "COMMIT", "ROLLBACK", "DO"}
    data = [
        row
        for row in rows
        if row not in noise and not re.match(r"^(?:INSERT|UPDATE|DELETE) \d+$", row)
    ]
    return SqlResult(ok=True, rows=data)


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


def _fetch_listing_mode(listing_id: str) -> str | None:
    listing_sql = sql_uuid(listing_id, "listing_id")
    result = run_sql_script(
        f"SELECT stock_mode FROM public.vendor_listings WHERE id = {listing_sql};"
    )
    if not result.ok or not result.rows:
        return None
    return result.rows[0]


def claim_reservation(
    *,
    listing_id: str,
    checkout_group_id: str,
    qty: int,
    ttl_minutes: int | None = None,
) -> ClaimResult:
    if not _UUID_RE.match(listing_id) or not _UUID_RE.match(checkout_group_id):
        raise ValueError("listing_id and checkout_group_id must be valid UUIDs")
    if qty <= 0:
        raise ValueError("qty must be positive")

    stock_mode = _fetch_listing_mode(listing_id)
    if stock_mode is None:
        return ClaimResult(
            claimed=False,
            listing_id=listing_id,
            checkout_group_id=checkout_group_id,
            qty=qty,
        )
    if stock_mode == "always_available":
        return ClaimResult(
            claimed=True,
            listing_id=listing_id,
            checkout_group_id=checkout_group_id,
            qty=qty,
            skipped=True,
        )

    ttl = ttl_minutes if ttl_minutes is not None else get_reservation_ttl_minutes()
    expires_at = datetime.now(UTC) + timedelta(minutes=ttl)
    expires_literal = expires_at.isoformat()

    listing_sql = sql_uuid(listing_id, "listing_id")
    group_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    qty_sql = sql_int(qty, "qty")

    script = f"""
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
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"claim_reservation failed: {result.error}")

    if not result.rows:
        return ClaimResult(
            claimed=False,
            listing_id=listing_id,
            checkout_group_id=checkout_group_id,
            qty=qty,
        )

    remaining = int(result.rows[-1])
    return ClaimResult(
        claimed=True,
        listing_id=listing_id,
        checkout_group_id=checkout_group_id,
        qty=qty,
        remaining_stock_qty=remaining,
    )
