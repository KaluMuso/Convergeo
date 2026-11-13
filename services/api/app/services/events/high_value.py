"""K100,000 pre-event verification gate (strategy §7.2).

Publish is blocked when projected paid GMV meets the configured threshold and
an admin has not set ``events.high_value_verified_at``. This never auto-calls
anyone; it is a human gate.
"""

from __future__ import annotations

import json
from typing import Any

from app.errors import AppError
from app.services.stock.claim import run_sql_script, sql_uuid

HIGH_VALUE_CONFIG_KEY = "event_high_value_gmv_ngwee"
DEFAULT_HIGH_VALUE_GMV_NGWEE = 10_000_000  # K100,000
ID_CHECK_THRESHOLD_NGWEE = 50_000  # K500


def load_high_value_gmv_ngwee() -> int:
    key_sql = "'" + HIGH_VALUE_CONFIG_KEY.replace("'", "''") + "'"
    result = run_sql_script(
        f"""
SELECT value::text
FROM public.platform_config
WHERE key = {key_sql}
LIMIT 1;
"""
    )
    if not result.ok or not result.rows:
        return DEFAULT_HIGH_VALUE_GMV_NGWEE
    raw = result.rows[0].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw
    if isinstance(parsed, int) and parsed > 0:
        return parsed
    if isinstance(parsed, str) and parsed.strip().isdigit():
        value = int(parsed.strip())
        return value if value > 0 else DEFAULT_HIGH_VALUE_GMV_NGWEE
    return DEFAULT_HIGH_VALUE_GMV_NGWEE


def projected_paid_gmv_ngwee(event_id: str) -> int:
    """Upper bound: each instance capacity × cheapest paid ticket on the event."""
    event_sql = sql_uuid(event_id, "event_id")
    result = run_sql_script(
        f"""
SELECT coalesce(
  (
    SELECT min(tt.price_ngwee)::bigint
    FROM public.ticket_types tt
    WHERE tt.event_id = {event_sql}
      AND tt.kind <> 'free_rsvp'
      AND tt.price_ngwee > 0
  ),
  0
)::text;
"""
    )
    if not result.ok or not result.rows:
        return 0
    min_price = int(result.rows[0])
    if min_price <= 0:
        return 0
    cap_result = run_sql_script(
        f"""
SELECT coalesce(sum(ei.capacity), 0)::text
FROM public.event_instances ei
WHERE ei.event_id = {event_sql};
"""
    )
    if not cap_result.ok or not cap_result.rows:
        return 0
    return min_price * int(cap_result.rows[0])


def assert_high_value_publish_allowed(event_row: dict[str, Any]) -> None:
    event_id = str(event_row["id"])
    if event_row.get("high_value_verified_at"):
        return
    threshold = load_high_value_gmv_ngwee()
    projected = projected_paid_gmv_ngwee(event_id)
    if projected < threshold:
        return
    raise AppError(
        code="event_high_value_verification_required",
        message="Events projecting K100,000+ in ticket GMV need a verification call before publish",
        http_status=422,
        details={
            "message_key": "vendor.events.errors.highValueVerificationRequired",
            "event_id": event_id,
            "projected_gmv_ngwee": projected,
            "threshold_ngwee": threshold,
        },
    )


def count_upheld_event_disputes(organiser_vendor_id: str) -> int:
    vendor_sql = sql_uuid(organiser_vendor_id, "organiser_vendor_id")
    result = run_sql_script(
        f"""
SELECT count(*)::text
FROM public.disputes d
INNER JOIN public.events e ON e.id = d.event_id
WHERE e.organiser_vendor_id = {vendor_sql}
  AND d.kind = 'event_misrepresentation'
  AND d.status = 'resolved_refund';
"""
    )
    if not result.ok or not result.rows:
        return 0
    return int(result.rows[0])
