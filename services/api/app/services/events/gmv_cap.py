"""Tier-1 organiser per-event paid GMV fraud cap (VF-P06 / BG-3 / BL-004).

Personal (Tier-1) organisers cannot accumulate more than the configured paid-ticket
GMV on a single event before further paid checkouts are rejected. Tier-2+ organisers
are uncapped. Free RSVP is out of scope (no money / no escrow).

Cap value lives in ``platform_config.organiser_t1_event_gmv_cap_ngwee`` (default
2_000_000 ngwee = K20,000). D9 product first-order caps are intentionally separate —
do not reuse ``first_orders_cap_ngwee``.
"""

from __future__ import annotations

import json
from typing import Any

from app.errors import AppError
from app.services.kyc.eligibility import (
    VendorKycEligibility,
    build_eligibility_from_rows,
    cap_tier_for_quotas,
    resolve_vendor_eligibility,
)
from app.services.orders.state import SYSTEM_ACTOR_ID
from app.services.stock.claim import run_sql_script, sql_uuid

CONFIG_KEY = "organiser_t1_event_gmv_cap_ngwee"
DEFAULT_CAP_NGWEE = 2_000_000
AUDIT_ACTION = "organiser_t1_gmv_cap_exceeded"


def _eligibility_from_sql(organiser_vendor_id: str) -> VendorKycEligibility:
    """Same auditable eligibility math as resolve_vendor_eligibility, via SQL.

    Used when the service-role table client is unavailable (SQL-fixture tests).
    """
    vendor_sql = sql_uuid(organiser_vendor_id, "organiser_vendor_id")
    vendor_result = run_sql_script(
        f"""
SELECT id::text, status, coalesce(kyc_tier::text, ''), coalesce(preferred_badge::text, 'false')
FROM public.vendors
WHERE id = {vendor_sql}
LIMIT 1;
"""
    )
    if not vendor_result.ok:
        raise RuntimeError(f"load organiser vendor failed: {vendor_result.error}")
    if not vendor_result.rows:
        raise AppError(code="not_found", message="Vendor not found", http_status=404)
    parts = vendor_result.rows[0].split("|")
    if len(parts) != 4:
        raise RuntimeError("unexpected vendor row shape for GMV cap eligibility")
    vendor = {
        "id": parts[0],
        "status": parts[1],
        "kyc_tier": int(parts[2]) if parts[2].strip() else None,
        "preferred_badge": parts[3] == "true",
    }

    kyc_result = run_sql_script(
        f"""
SELECT id::text, vendor_id::text, tier::text, status
FROM public.kyc_records
WHERE vendor_id = {vendor_sql}
  AND status = 'approved'
ORDER BY tier DESC
LIMIT 1;
"""
    )
    if not kyc_result.ok:
        raise RuntimeError(f"load organiser KYC failed: {kyc_result.error}")
    approved: dict[str, Any] | None = None
    if kyc_result.rows:
        kyc_parts = kyc_result.rows[0].split("|")
        if len(kyc_parts) == 4:
            approved = {
                "id": kyc_parts[0],
                "vendor_id": kyc_parts[1],
                "tier": int(kyc_parts[2]),
                "status": kyc_parts[3],
            }
    return build_eligibility_from_rows(vendor=vendor, approved_record=approved)


def _resolve_cap_tier(service: Any, organiser_vendor_id: str) -> int:
    """Quota tier via resolve_vendor_eligibility / cap_tier_for_quotas (orphans → T1)."""
    try:
        eligibility = resolve_vendor_eligibility(service, organiser_vendor_id)
    except RuntimeError:
        eligibility = _eligibility_from_sql(organiser_vendor_id)
    return cap_tier_for_quotas(eligibility)


def load_organiser_t1_event_gmv_cap_ngwee() -> int:
    """Read the per-event T1 GMV cap from platform_config (integer ngwee)."""
    key_sql = "'" + CONFIG_KEY.replace("'", "''") + "'"
    result = run_sql_script(
        f"""
SELECT value::text
FROM public.platform_config
WHERE key = {key_sql}
LIMIT 1;
"""
    )
    if not result.ok:
        raise RuntimeError(f"load {CONFIG_KEY} failed: {result.error}")
    if not result.rows:
        return DEFAULT_CAP_NGWEE
    raw = result.rows[0].strip()
    if not raw:
        return DEFAULT_CAP_NGWEE
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw
    if isinstance(parsed, bool):
        return DEFAULT_CAP_NGWEE
    if isinstance(parsed, int):
        return parsed if parsed > 0 else DEFAULT_CAP_NGWEE
    if isinstance(parsed, str) and parsed.strip().isdigit():
        value = int(parsed.strip())
        return value if value > 0 else DEFAULT_CAP_NGWEE
    return DEFAULT_CAP_NGWEE


def event_paid_gmv_ngwee(event_id: str) -> int:
    """Sum paid ticket line GMV for an event (successful payments only).

    Free RSVP lines are excluded (nominal 1 ngwee storage workaround is not money).
    """
    event_sql = sql_uuid(event_id, "event_id")
    result = run_sql_script(
        f"""
SELECT coalesce(sum(oi.qty * oi.unit_price_ngwee), 0)::text
FROM public.order_items oi
INNER JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id
INNER JOIN public.ticket_types tt ON tt.id = oit.ticket_type_id
INNER JOIN public.orders o ON o.id = oi.order_id
WHERE tt.event_id = {event_sql}
  AND oi.item_kind = 'ticket'
  AND tt.kind <> 'free_rsvp'
  AND EXISTS (
    SELECT 1
    FROM public.payments p
    WHERE p.checkout_group_id = o.checkout_group_id
      AND p.status = 'success'
  );
"""
    )
    if not result.ok or not result.rows:
        raise RuntimeError(f"event paid GMV query failed: {result.error}")
    return int(result.rows[0])


def _write_cap_reject_audit(
    service: Any,
    *,
    organiser_vendor_id: str,
    event_id: str,
    current_gmv_ngwee: int,
    additional_ngwee: int,
    cap_ngwee: int,
    cap_tier: int,
) -> None:
    after = {
        "organiser_vendor_id": organiser_vendor_id,
        "event_id": event_id,
        "current_gmv_ngwee": current_gmv_ngwee,
        "additional_ngwee": additional_ngwee,
        "projected_gmv_ngwee": current_gmv_ngwee + additional_ngwee,
        "cap_ngwee": cap_ngwee,
        "cap_tier": cap_tier,
        "config_key": CONFIG_KEY,
    }
    client = getattr(service, "client", None)
    table = getattr(client, "table", None) if client is not None else None
    if callable(table):
        try:
            table("audit_log").insert(
                {
                    "actor": SYSTEM_ACTOR_ID,
                    "action": AUDIT_ACTION,
                    "entity_type": "event",
                    "entity_id": event_id,
                    "before": None,
                    "after": after,
                }
            ).execute()
            return
        except Exception:
            # Fall through to SQL so a stub test client cannot silence the audit.
            pass

    event_sql = sql_uuid(event_id, "event_id")
    actor_sql = sql_uuid(SYSTEM_ACTOR_ID, "actor")
    after_sql = json.dumps(after, separators=(",", ":"), sort_keys=True).replace("'", "''")
    action_sql = "'" + AUDIT_ACTION.replace("'", "''") + "'"
    result = run_sql_script(
        f"""
INSERT INTO public.audit_log (actor, action, entity_type, entity_id, before, after)
VALUES (
  {actor_sql}, {action_sql}, 'event', {event_sql}, NULL, '{after_sql}'::jsonb
);
"""
    )
    if not result.ok:
        raise RuntimeError(f"organiser GMV cap audit_log insert failed: {result.error}")


def enforce_organiser_t1_gmv_cap(
    service: Any,
    organiser_vendor_id: str,
    event_id: str,
    additional_ngwee: int,
) -> None:
    """Reject paid-ticket checkout that would push a T1 organiser over the per-event GMV cap.

    Uses :func:`resolve_vendor_eligibility` + :func:`cap_tier_for_quotas` so orphaned
    ``vendors.kyc_tier`` values cannot unlock an uncapped T2 path. T2+ pass through.
    Over-cap → ``organiser_gmv_cap_exceeded`` (403) + ``audit_log`` row.
    """
    if additional_ngwee < 0:
        raise AppError(
            code="validation_error",
            message="additional_ngwee must be non-negative",
            http_status=422,
            details={"field": "additional_ngwee"},
        )
    if additional_ngwee == 0:
        return

    tier = _resolve_cap_tier(service, organiser_vendor_id)
    if tier >= 2:
        return

    cap_ngwee = load_organiser_t1_event_gmv_cap_ngwee()
    current_gmv_ngwee = event_paid_gmv_ngwee(event_id)
    projected = current_gmv_ngwee + additional_ngwee
    if projected <= cap_ngwee:
        return

    _write_cap_reject_audit(
        service,
        organiser_vendor_id=organiser_vendor_id,
        event_id=event_id,
        current_gmv_ngwee=current_gmv_ngwee,
        additional_ngwee=additional_ngwee,
        cap_ngwee=cap_ngwee,
        cap_tier=tier,
    )
    raise AppError(
        code="organiser_gmv_cap_exceeded",
        message="Tier-1 organiser per-event ticket GMV cap exceeded",
        http_status=403,
        details={
            "message_key": "events.ticketPurchase.errors.organiserGmvCapExceeded",
            "event_id": event_id,
            "organiser_vendor_id": organiser_vendor_id,
            "current_gmv_ngwee": current_gmv_ngwee,
            "additional_ngwee": additional_ngwee,
            "projected_gmv_ngwee": projected,
            "cap_ngwee": cap_ngwee,
            "cap_tier": tier,
            "config_key": CONFIG_KEY,
        },
    )
