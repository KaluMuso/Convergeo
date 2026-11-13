"""Immutable settlement schedule snapshots at ticket sale (EVT-SETTLEMENT-SNAPSHOT).

Paid ticket orders persist purchase-time instance timing and branch decision in
``event_settlement_snapshots`` so escrow release does not follow live reschedules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.services.events.timing import instance_settlement_end
from app.services.events.type_policy import normalize_event_type, policy_for
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.stock.claim import sql_uuid

SettlementSnapshotStatus = Literal[
    "active", "held_for_reschedule", "released", "cancelled"
]
SettlementBranch = Literal["full", "phased"]

PHASED_THRESHOLD_DAYS = 14


@dataclass(frozen=True, slots=True)
class SettlementSchedule:
    starts_at: datetime
    ends_at: datetime | None
    event_type: str
    purchased_at: datetime
    branch: SettlementBranch
    settlement_rule: str
    settlement_end: datetime

    def to_json(self) -> dict[str, Any]:
        return {
            "starts_at": self.starts_at.isoformat(),
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "event_type": self.event_type,
            "purchased_at": self.purchased_at.isoformat(),
            "branch": self.branch,
            "settlement_rule": self.settlement_rule,
            "settlement_end": self.settlement_end.isoformat(),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> SettlementSchedule | None:
        starts_at = _parse_timestamp(payload.get("starts_at"))
        purchased_at = _parse_timestamp(payload.get("purchased_at"))
        settlement_end = _parse_timestamp(payload.get("settlement_end"))
        if starts_at is None or purchased_at is None or settlement_end is None:
            return None
        ends_raw = payload.get("ends_at")
        ends_at = _parse_timestamp(ends_raw) if ends_raw else None
        branch = payload.get("branch")
        if branch not in ("full", "phased"):
            return None
        event_type = normalize_event_type(
            payload.get("event_type") if isinstance(payload.get("event_type"), str) else None
        )
        settlement_rule = payload.get("settlement_rule")
        if settlement_rule not in ("timing_default", "full_only"):
            settlement_rule = policy_for(event_type).settlement_rule
        return cls(
            starts_at=starts_at,
            ends_at=ends_at,
            event_type=event_type,
            purchased_at=purchased_at,
            branch=branch,
            settlement_rule=settlement_rule,
            settlement_end=settlement_end,
        )


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def compute_settlement_branch(
    *, purchased_at: datetime, starts_at: datetime, event_type: str | None
) -> SettlementBranch:
    """Purchase-time branch decision (mirrors event_release.determine_branch)."""
    if policy_for(event_type).settlement_rule == "full_only":
        return "full"
    from datetime import timedelta

    lead = starts_at - purchased_at
    if lead <= timedelta(days=PHASED_THRESHOLD_DAYS):
        return "full"
    return "phased"


def build_settlement_schedule(
    *,
    starts_at: datetime,
    ends_at: datetime | None,
    event_type: str,
    purchased_at: datetime,
) -> SettlementSchedule:
    normalized_type = normalize_event_type(event_type)
    rule = policy_for(normalized_type).settlement_rule
    branch = compute_settlement_branch(
        purchased_at=purchased_at, starts_at=starts_at, event_type=normalized_type
    )
    settlement_end = instance_settlement_end(starts_at, ends_at)
    return SettlementSchedule(
        starts_at=starts_at,
        ends_at=ends_at,
        event_type=normalized_type,
        purchased_at=purchased_at,
        branch=branch,
        settlement_rule=rule,
        settlement_end=settlement_end,
    )


def load_settlement_schedule(order_id: str) -> SettlementSchedule | None:
    order_sql = sql_uuid(order_id, "order_id")
    script = f"""
SELECT schedule::text
FROM public.event_settlement_snapshots
WHERE order_id = {order_sql}
  AND status IN ('active', 'held_for_reschedule', 'released');
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None
    raw = result.rows[0].strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return SettlementSchedule.from_json(payload)


def create_settlement_snapshot(order_id: str) -> bool:
    """Idempotently persist purchase-time settlement terms for a paid ticket order."""
    order_sql = sql_uuid(order_id, "order_id")
    load_script = f"""
SELECT
  o.created_at::text,
  ei.starts_at::text,
  coalesce(ei.ends_at::text, ''),
  e.id::text,
  ei.id::text,
  e.event_type
FROM public.orders o
INNER JOIN public.order_items oi
  ON oi.order_id = o.id AND oi.item_kind = 'ticket'
INNER JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id
INNER JOIN public.event_instances ei ON ei.id = oit.instance_id
INNER JOIN public.events e ON e.id = ei.event_id
WHERE o.id = {order_sql}
LIMIT 1;
"""
    loaded = run_sql_script(load_script)
    if not loaded.ok or not loaded.rows:
        return False

    parts = loaded.rows[0].split("|", 5)
    if len(parts) != 6:
        return False

    (
        created_at_raw,
        starts_at_raw,
        ends_at_raw,
        event_id,
        instance_id,
        event_type,
    ) = parts

    purchased_at = _parse_timestamp(created_at_raw)
    starts_at = _parse_timestamp(starts_at_raw)
    ends_at = _parse_timestamp(ends_at_raw) if ends_at_raw.strip() else None
    if purchased_at is None or starts_at is None:
        return False

    schedule = build_settlement_schedule(
        starts_at=starts_at,
        ends_at=ends_at,
        event_type=event_type,
        purchased_at=purchased_at,
    )
    schedule_json = json.dumps(schedule.to_json(), separators=(",", ":"))
    schedule_sql = sql_literal(schedule_json) + "::jsonb"
    event_sql = sql_uuid(event_id, "event_id")
    instance_sql = sql_uuid(instance_id, "instance_id")

    insert_script = f"""
INSERT INTO public.event_settlement_snapshots (
  order_id, event_id, instance_id, schedule, status
)
VALUES (
  {order_sql}, {event_sql}, {instance_sql}, {schedule_sql}, 'active'
)
ON CONFLICT (order_id) DO NOTHING
RETURNING order_id::text;
"""
    inserted = run_sql_script(insert_script)
    if not inserted.ok:
        raise RuntimeError(f"create settlement snapshot failed: {inserted.error}")
    return bool(inserted.rows)


def mark_settlement_snapshot_released(order_id: str) -> None:
    """Mark snapshot released after escrow payout completes (best-effort)."""
    order_sql = sql_uuid(order_id, "order_id")
    script = f"""
UPDATE public.event_settlement_snapshots
SET status = 'released',
    updated_at = timezone('utc', now())
WHERE order_id = {order_sql}
  AND status = 'active';
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"mark settlement snapshot released failed: {result.error}")
