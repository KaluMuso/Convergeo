"""Automated enforcement when regulator licences expire."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import SYSTEM_ACTOR_ID

logger = logging.getLogger(__name__)

AUDIT_ACTION = "compliance.license_expired_suspend"
LISTING_ACTIVE_STATUSES = ("active", "paused")


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class ExpiredLicenceTarget:
    vendor_id: str
    licence_id: str
    regulated_class: str
    expiry_date: str
    license_body: str | None


@dataclass(frozen=True, slots=True)
class LicenseEnforcementResult:
    vendor_id: str
    licence_id: str
    vendor_suspended: bool
    listings_removed: int
    audited: bool


def list_expired_licence_targets(*, today: date) -> list[ExpiredLicenceTarget]:
    """Vendors with verified licences whose expiry_date is before *today*."""
    today_sql = sql_literal(today.isoformat())
    script = f"""
SELECT
  l.vendor_id::text,
  l.id::text,
  l.regulated_class,
  l.expiry_date::text,
  coalesce(l.license_body::text, l.regulator)
FROM public.vendor_licences l
INNER JOIN public.vendors v ON v.id = l.vendor_id
WHERE l.status = 'verified'
  AND l.expiry_date < {today_sql}::date
  AND v.status = 'active'
ORDER BY l.expiry_date ASC, l.vendor_id ASC;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"list expired licence targets failed: {result.error}")

    targets: list[ExpiredLicenceTarget] = []
    for row in result.rows:
        parts = row.split("|")
        if len(parts) < 5:
            continue
        targets.append(
            ExpiredLicenceTarget(
                vendor_id=parts[0],
                licence_id=parts[1],
                regulated_class=parts[2],
                expiry_date=parts[3],
                license_body=parts[4] if parts[4] else None,
            )
        )
    return targets


def enforce_expired_licence(
    target: ExpiredLicenceTarget,
    *,
    today: date,
) -> LicenseEnforcementResult:
    """Suspend vendor for compliance and hide active listings; write audit log."""
    vendor_sql = sql_literal(target.vendor_id)
    actor_sql = sql_literal(SYSTEM_ACTOR_ID)
    action_sql = sql_literal(AUDIT_ACTION)

    before_payload = json.dumps(
        {
            "vendor": {"id": target.vendor_id, "status": "active"},
            "licence": {
                "id": target.licence_id,
                "regulated_class": target.regulated_class,
                "expiry_date": target.expiry_date,
                "license_body": target.license_body,
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    ).replace("'", "''")

    after_payload = json.dumps(
        {
            "vendor": {"id": target.vendor_id, "status": "suspended_compliance"},
            "licence": {
                "id": target.licence_id,
                "expiry_date": target.expiry_date,
                "enforced_on": today.isoformat(),
            },
            "listings_hidden": True,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).replace("'", "''")

    script = f"""
BEGIN;
SET LOCAL role service_role;

WITH vendor_update AS (
  UPDATE public.vendors
  SET status = 'suspended_compliance',
      updated_at = timezone('utc', now())
  WHERE id = {vendor_sql}::uuid
    AND status = 'active'
  RETURNING id
),
listing_update AS (
  UPDATE public.vendor_listings
  SET status = 'removed',
      updated_at = timezone('utc', now())
  WHERE vendor_id = {vendor_sql}::uuid
    AND status IN ('active', 'paused')
  RETURNING id
),
audit_insert AS (
  INSERT INTO public.audit_log (actor, action, entity_type, entity_id, before, after)
  SELECT
    {actor_sql}::uuid,
    {action_sql},
    'vendor',
    {vendor_sql}::uuid,
    '{before_payload}'::jsonb,
    '{after_payload}'::jsonb
  FROM vendor_update
  RETURNING id
)
SELECT
  (SELECT count(*)::text FROM vendor_update),
  (SELECT count(*)::text FROM listing_update),
  (SELECT count(*)::text FROM audit_insert);
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise RuntimeError(f"enforce expired licence failed: {result.error}")

    parts = result.rows[0].split("|")
    vendor_suspended = int(parts[0]) > 0 if parts else False
    listings_removed = int(parts[1]) if len(parts) > 1 else 0
    audited = int(parts[2]) > 0 if len(parts) > 2 else False

    return LicenseEnforcementResult(
        vendor_id=target.vendor_id,
        licence_id=target.licence_id,
        vendor_suspended=vendor_suspended,
        listings_removed=listings_removed,
        audited=audited,
    )
