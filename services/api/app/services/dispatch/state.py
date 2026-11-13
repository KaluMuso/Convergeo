"""Courier dispatch state machine — single authority for dispatch transitions.

Mirrors ``app.services.orders.state``: a pure transition table (unit-testable
without a database) plus a service-role, row-locked SQL write path. The same
transition set is enforced again by the ``guard_dispatch_requests_update``
trigger (migration 20261109100000), so a bypass of this module still cannot
produce an illegal status, and every status change is audited by
``audit_dispatch_requests_status`` into ``dispatch_request_events``.

    requested → accepted → picked_up → delivered
    requested | accepted → cancelled
    requested | accepted | picked_up → failed

Coupling to the ORDER state machine (never raw order UPDATEs):

* ``picked_up``  → order ``SHIP`` (processing → shipped) when the order is still
  ``processing``; a vendor-shipped order is left alone.
* ``delivered``  → order ``MARK_DELIVERED`` (shipped → delivered) via
  ``transition_order``; the order transition is pre-flighted with
  ``check_order_transition`` BEFORE the dispatch row changes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.errors import AppError
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import sql_uuid

DISPATCH_ACTOR_GUC = "app.dispatch_actor"
DISPATCH_NOTE_GUC = "app.dispatch_note"

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_POD_PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9_/.-]{1,255}$")


class DispatchStatus(StrEnum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    PICKED_UP = "picked_up"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_STATUSES: frozenset[DispatchStatus] = frozenset(
    {DispatchStatus.REQUESTED, DispatchStatus.ACCEPTED, DispatchStatus.PICKED_UP}
)
TERMINAL_STATUSES: frozenset[DispatchStatus] = frozenset(
    {DispatchStatus.DELIVERED, DispatchStatus.FAILED, DispatchStatus.CANCELLED}
)

# (from, to) pairs. Kept byte-identical to the SQL guard trigger's list.
TRANSITIONS: frozenset[tuple[DispatchStatus, DispatchStatus]] = frozenset(
    {
        (DispatchStatus.REQUESTED, DispatchStatus.ACCEPTED),
        (DispatchStatus.REQUESTED, DispatchStatus.CANCELLED),
        (DispatchStatus.REQUESTED, DispatchStatus.FAILED),
        (DispatchStatus.ACCEPTED, DispatchStatus.PICKED_UP),
        (DispatchStatus.ACCEPTED, DispatchStatus.CANCELLED),
        (DispatchStatus.ACCEPTED, DispatchStatus.FAILED),
        (DispatchStatus.PICKED_UP, DispatchStatus.DELIVERED),
        (DispatchStatus.PICKED_UP, DispatchStatus.FAILED),
    }
)


class DispatchTransitionError(AppError):
    def __init__(self, message: str, *, from_status: str, to_status: str) -> None:
        super().__init__(
            code="dispatch_invalid_transition",
            message=message,
            http_status=409,
            details={
                "from_status": from_status,
                "to_status": to_status,
                "message_key": "admin.dispatch.errors.invalidTransition",
            },
        )


def is_transition_allowed(from_status: DispatchStatus, to_status: DispatchStatus) -> bool:
    return (from_status, to_status) in TRANSITIONS


def allowed_next_statuses(from_status: DispatchStatus) -> list[DispatchStatus]:
    return sorted(
        (to for (frm, to) in TRANSITIONS if frm == from_status),
        key=lambda status: list(DispatchStatus).index(status),
    )


def assert_transition(from_status: DispatchStatus, to_status: DispatchStatus) -> None:
    if not is_transition_allowed(from_status, to_status):
        raise DispatchTransitionError(
            f"Dispatch cannot move from {from_status.value} to {to_status.value}",
            from_status=from_status.value,
            to_status=to_status.value,
        )


def validate_pod_public_id(value: str) -> str:
    cleaned = value.strip()
    if not _POD_PUBLIC_ID_RE.match(cleaned) or "://" in cleaned:
        raise AppError(
            code="validation_error",
            message="pod_photo_public_id must be a Cloudinary public_id, not a URL",
            http_status=422,
        )
    return cleaned


# ---------------------------------------------------------------------------
# SQL helpers (JSON-projected rows so free text with '|' never breaks parsing)
# ---------------------------------------------------------------------------


def json_rows(script: str, *, context: str) -> list[dict[str, Any]]:
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"{context} failed: {result.error}")
    rows: list[dict[str, Any]] = []
    for raw in result.rows:
        # Scripts also emit set_config(...) rows (GUC values); only the
        # json_build_object projections are data rows.
        if not raw.lstrip().startswith("{"):
            continue
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def audit_context_sql(*, actor_id: str, note: str) -> str:
    if not _UUID_RE.match(actor_id):
        raise ValueError("actor_id must be a UUID")
    return (
        f"SELECT set_config('{DISPATCH_ACTOR_GUC}', {sql_literal(actor_id)}, true);\n"
        f"SELECT set_config('{DISPATCH_NOTE_GUC}', {sql_literal(note[:500])}, true);\n"
    )


@dataclass(frozen=True, slots=True)
class DispatchRow:
    id: str
    order_id: str
    courier_partner_id: str
    status: DispatchStatus
    courier_reference: str | None
    cod_amount_ngwee: int
    quoted_price_ngwee: int | None
    pod_photo_public_id: str | None
    delivered_via: str | None
    failure_reason: str | None
    notify_count: int
    last_notified_at: str | None
    requested_at: str
    accepted_at: str | None
    picked_up_at: str | None
    delivered_at: str | None
    failed_at: str | None
    cancelled_at: str | None
    # Logistics phase 1 (migration 20261113150000).
    direction: str = "delivery"
    attempt_no: int = 1
    failure_code: str | None = None
    pickup_location_id: str | None = None
    actual_cost_ngwee: int | None = None
    cod_collected_ngwee: int | None = None
    cod_collected_method: str | None = None
    cod_collected_at: str | None = None
    remittance_id: str | None = None


_DISPATCH_JSON = """json_build_object(
  'id', d.id,
  'order_id', d.order_id,
  'courier_partner_id', d.courier_partner_id,
  'status', d.status,
  'courier_reference', d.courier_reference,
  'cod_amount_ngwee', d.cod_amount_ngwee,
  'quoted_price_ngwee', d.quoted_price_ngwee,
  'pod_photo_public_id', d.pod_photo_public_id,
  'delivered_via', d.delivered_via,
  'failure_reason', d.failure_reason,
  'notify_count', d.notify_count,
  'last_notified_at', d.last_notified_at,
  'requested_at', d.requested_at,
  'accepted_at', d.accepted_at,
  'picked_up_at', d.picked_up_at,
  'delivered_at', d.delivered_at,
  'failed_at', d.failed_at,
  'cancelled_at', d.cancelled_at,
  'direction', d.direction,
  'attempt_no', d.attempt_no,
  'failure_code', d.failure_code,
  'pickup_location_id', d.pickup_location_id,
  'actual_cost_ngwee', d.actual_cost_ngwee,
  'cod_collected_ngwee', d.cod_collected_ngwee,
  'cod_collected_method', d.cod_collected_method,
  'cod_collected_at', d.cod_collected_at,
  'remittance_id', d.remittance_id
)"""


def _opt_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError("expected integer ngwee from dispatch_requests")
    return value


def dispatch_row_from_json(row: dict[str, Any]) -> DispatchRow:
    cod = _opt_int(row.get("cod_amount_ngwee"))
    return DispatchRow(
        id=str(row["id"]),
        order_id=str(row["order_id"]),
        courier_partner_id=str(row["courier_partner_id"]),
        status=DispatchStatus(str(row["status"])),
        courier_reference=_opt_str(row.get("courier_reference")),
        cod_amount_ngwee=cod if cod is not None else 0,
        quoted_price_ngwee=_opt_int(row.get("quoted_price_ngwee")),
        pod_photo_public_id=_opt_str(row.get("pod_photo_public_id")),
        delivered_via=_opt_str(row.get("delivered_via")),
        failure_reason=_opt_str(row.get("failure_reason")),
        notify_count=int(row.get("notify_count") or 0),
        last_notified_at=_opt_str(row.get("last_notified_at")),
        requested_at=str(row["requested_at"]),
        accepted_at=_opt_str(row.get("accepted_at")),
        picked_up_at=_opt_str(row.get("picked_up_at")),
        delivered_at=_opt_str(row.get("delivered_at")),
        failed_at=_opt_str(row.get("failed_at")),
        cancelled_at=_opt_str(row.get("cancelled_at")),
        direction=str(row.get("direction") or "delivery"),
        attempt_no=int(row.get("attempt_no") or 1),
        failure_code=_opt_str(row.get("failure_code")),
        pickup_location_id=_opt_str(row.get("pickup_location_id")),
        actual_cost_ngwee=_opt_int(row.get("actual_cost_ngwee")),
        cod_collected_ngwee=_opt_int(row.get("cod_collected_ngwee")),
        cod_collected_method=_opt_str(row.get("cod_collected_method")),
        cod_collected_at=_opt_str(row.get("cod_collected_at")),
        remittance_id=_opt_str(row.get("remittance_id")),
    )


def fetch_dispatch(dispatch_id: str) -> DispatchRow:
    dispatch_sql = sql_uuid(dispatch_id, "dispatch_id")
    rows = json_rows(
        f"SELECT {_DISPATCH_JSON}::text "
        f"FROM public.dispatch_requests d WHERE d.id = {dispatch_sql};",
        context="dispatch lookup",
    )
    if not rows:
        raise AppError(code="not_found", message="Dispatch not found", http_status=404)
    return dispatch_row_from_json(rows[0])


def fetch_latest_dispatch_for_order(order_id: str) -> DispatchRow | None:
    order_sql = sql_uuid(order_id, "order_id")
    rows = json_rows(
        f"""
SELECT {_DISPATCH_JSON}::text
FROM public.dispatch_requests d
WHERE d.order_id = {order_sql}
ORDER BY d.created_at DESC, d.id DESC
LIMIT 1;
""",
        context="order dispatch lookup",
    )
    return dispatch_row_from_json(rows[0]) if rows else None


def fetch_dispatch_events(dispatch_id: str) -> list[dict[str, Any]]:
    dispatch_sql = sql_uuid(dispatch_id, "dispatch_id")
    return json_rows(
        f"""
SELECT json_build_object(
  'id', e.id,
  'actor', e.actor,
  'from_status', e.from_status,
  'to_status', e.to_status,
  'note', e.note,
  'created_at', e.created_at
)::text
FROM public.dispatch_request_events e
WHERE e.dispatch_request_id = {dispatch_sql}
ORDER BY e.created_at ASC, e.id ASC;
""",
        context="dispatch events lookup",
    )


@dataclass(frozen=True, slots=True)
class DispatchTransitionOutcome:
    dispatch_id: str
    order_id: str
    from_status: DispatchStatus
    to_status: DispatchStatus


def apply_dispatch_transition(
    *,
    dispatch_id: str,
    from_status: DispatchStatus,
    to_status: DispatchStatus,
    actor_id: str,
    note: str,
    set_fields: dict[str, str | int | None] | None = None,
) -> DispatchTransitionOutcome:
    """Row-locked compare-and-set of a dispatch status (+ optional fields).

    ``from_status`` is the status the caller validated against; a concurrent
    change makes the CAS match zero rows and raises instead of overwriting.
    """
    assert_transition(from_status, to_status)
    dispatch_sql = sql_uuid(dispatch_id, "dispatch_id")
    assignments = [f"status = {sql_literal(to_status.value)}"]
    for column, value in (set_fields or {}).items():
        if column not in _SETTABLE_COLUMNS:
            raise ValueError(f"column {column!r} is not settable on transition")
        if column == "cod_collected_ngwee":
            # Cash custody is write-once (DB guard) and stamped in the same UPDATE.
            assignments.append("cod_collected_at = timezone('utc', now())")
        if value is None:
            assignments.append(f"{column} = NULL")
        elif isinstance(value, int) and not isinstance(value, bool):
            assignments.append(f"{column} = {value}")
        else:
            assignments.append(f"{column} = {sql_literal(str(value))}")
    script = f"""
BEGIN;
{audit_context_sql(actor_id=actor_id, note=note)}
WITH locked AS (
  SELECT id FROM public.dispatch_requests
  WHERE id = {dispatch_sql} AND status = {sql_literal(from_status.value)}
  FOR UPDATE
)
UPDATE public.dispatch_requests d
SET {", ".join(assignments)}
FROM locked l
WHERE d.id = l.id
RETURNING json_build_object('id', d.id, 'order_id', d.order_id, 'status', d.status)::text;
COMMIT;
"""
    rows = json_rows(script, context="dispatch transition")
    if not rows or rows[-1].get("status") != to_status.value:
        raise DispatchTransitionError(
            "Concurrent change: dispatch is no longer in the expected state",
            from_status=from_status.value,
            to_status=to_status.value,
        )
    return DispatchTransitionOutcome(
        dispatch_id=dispatch_id,
        order_id=str(rows[-1]["order_id"]),
        from_status=from_status,
        to_status=to_status,
    )


_SETTABLE_COLUMNS = frozenset(
    {
        "courier_reference",
        "failure_reason",
        "pod_photo_public_id",
        "delivered_via",
        "failure_code",
        "cod_collected_ngwee",
        "cod_collected_method",
    }
)

FAILURE_CODES = frozenset(
    {
        "customer_unavailable",
        "customer_refused",
        "wrong_address",
        "vendor_not_ready",
        "courier_no_show",
        "damaged",
        "other",
    }
)
