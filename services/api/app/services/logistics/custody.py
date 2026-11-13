"""Rider cash custody: who holds which cash, remittances, daily cash-up.

Cash is recorded against the courier when the delivery is completed
(``dispatch_requests.cod_collected_*``, write-once). It reaches Convergeo when
the courier remits (same day, by mobile money): a remittance must match the
exact sum of the jobs it covers, then each order's COD collection is booked in
the ledger through the existing ``confirm_cod_collection`` (platform_cash in,
commission + delivery fee captured, vendor's net released). A short or
mismatched remittance is never booked by an operator: a person resolves it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from app.errors import AppError
from app.services.dispatch.service import courier_cash_cap_ngwee
from app.services.dispatch.state import json_rows
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import sql_uuid

logger = logging.getLogger(__name__)

RemittanceMethod = Literal["mobile_money", "bank_transfer", "lenco", "cash_deposit"]
MAX_DISPATCHES_PER_REMITTANCE = 50


def custody_summary() -> list[dict[str, Any]]:
    """Per courier: cash held (collected, unremitted), cash on active jobs, cap."""
    cap = courier_cash_cap_ngwee()
    rows = json_rows(
        """
SELECT json_build_object(
  'courier_partner_id', c.id,
  'courier_name', c.name,
  'held_ngwee', coalesce(sum(d.cod_collected_ngwee)
      FILTER (WHERE d.cod_collected_ngwee IS NOT NULL AND d.remittance_id IS NULL), 0),
  'in_flight_ngwee', coalesce(sum(d.cod_amount_ngwee)
      FILTER (WHERE d.status IN ('requested', 'accepted', 'picked_up')), 0),
  'oldest_unremitted_at', min(d.cod_collected_at)
      FILTER (WHERE d.cod_collected_ngwee IS NOT NULL AND d.remittance_id IS NULL),
  'open_jobs', coalesce(json_agg(json_build_object(
        'dispatch_id', d.id, 'order_id', d.order_id,
        'cod_collected_ngwee', d.cod_collected_ngwee,
        'cod_collected_method', d.cod_collected_method,
        'cod_collected_at', d.cod_collected_at)
      ORDER BY d.cod_collected_at)
      FILTER (WHERE d.cod_collected_ngwee IS NOT NULL AND d.remittance_id IS NULL), '[]'::json)
)::text
FROM public.courier_partners c
LEFT JOIN public.dispatch_requests d ON d.courier_partner_id = c.id
GROUP BY c.id, c.name
ORDER BY c.name;
""",
        context="cash custody summary",
    )
    for row in rows:
        row["cap_ngwee"] = cap
        row["over_cap"] = int(row["held_ngwee"]) + int(row["in_flight_ngwee"]) > cap
    return rows


@dataclass(frozen=True, slots=True)
class RemittanceResult:
    remittance_id: str
    courier_partner_id: str
    amount_ngwee: int
    dispatch_ids: tuple[str, ...]
    #: order_id -> "booked" | "already_booked" | error code (ledger booking per order).
    bookings: dict[str, str]


def record_remittance(
    *,
    courier_partner_id: str,
    amount_ngwee: int,
    method: RemittanceMethod,
    reference: str,
    dispatch_ids: list[str],
    actor_id: str,
    note: str | None = None,
) -> RemittanceResult:
    """Record a courier's cash hand-in and match it to the jobs it covers (exact sum)."""
    if isinstance(amount_ngwee, bool) or not isinstance(amount_ngwee, int) or amount_ngwee <= 0:
        raise AppError(
            code="validation_error",
            message="amount must be positive integer ngwee",
            http_status=422,
        )
    ids = sorted({d.lower() for d in dispatch_ids})
    if not ids or len(ids) > MAX_DISPATCHES_PER_REMITTANCE:
        raise AppError(
            code="validation_error",
            message=f"List 1 to {MAX_DISPATCHES_PER_REMITTANCE} delivered cash jobs",
            http_status=422,
        )
    ref = reference.strip()
    if not 3 <= len(ref) <= 120:
        raise AppError(code="validation_error", message="reference is required", http_status=422)
    courier_sql = sql_uuid(courier_partner_id, "courier_partner_id")
    actor_sql = sql_uuid(actor_id, "actor_id")
    ids_sql = ", ".join(sql_uuid(d, "dispatch_id") for d in ids)
    note_sql = sql_literal(note.strip()[:500]) if note and note.strip() else "NULL"
    script = f"""
BEGIN;
DO $remit$
DECLARE
  v_count int;
  v_sum bigint;
BEGIN
  PERFORM 1 FROM public.dispatch_requests
  WHERE id IN ({ids_sql}) ORDER BY id FOR UPDATE;
  SELECT count(*), coalesce(sum(cod_collected_ngwee), 0) INTO v_count, v_sum
  FROM public.dispatch_requests
  WHERE id IN ({ids_sql})
    AND courier_partner_id = {courier_sql}
    AND cod_collected_ngwee IS NOT NULL
    AND remittance_id IS NULL;
  IF v_count <> {len(ids)} THEN
    RAISE EXCEPTION 'REMITTANCE_JOBS_INVALID';
  END IF;
  IF v_sum <> {amount_ngwee} THEN
    RAISE EXCEPTION 'REMITTANCE_MISMATCH:%', v_sum;
  END IF;
END $remit$;
WITH ins AS (
  INSERT INTO public.courier_remittances (
    courier_partner_id, amount_ngwee, method, reference, recorded_by, note
  ) VALUES ({courier_sql}, {amount_ngwee}, {sql_literal(method)}, {sql_literal(ref)},
            {actor_sql}, {note_sql})
  RETURNING id
), linked AS (
  UPDATE public.dispatch_requests d SET remittance_id = ins.id
  FROM ins WHERE d.id IN ({ids_sql})
  RETURNING d.id
)
SELECT json_build_object('id', (SELECT id FROM ins), 'linked', (SELECT count(*) FROM linked))::text;
INSERT INTO public.audit_log (actor, action, entity_type, entity_id, after)
SELECT {actor_sql}, 'cod.remittance.recorded', 'courier_remittance', r.id,
       jsonb_build_object('courier_partner_id', r.courier_partner_id,
                          'amount_ngwee', r.amount_ngwee, 'method', r.method,
                          'dispatch_ids', to_jsonb(ARRAY[{", ".join(sql_literal(d) for d in ids)}]))
FROM public.courier_remittances r
WHERE r.method = {sql_literal(method)} AND lower(btrim(r.reference)) = lower({sql_literal(ref)});
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        error = result.error or ""
        if "REMITTANCE_MISMATCH" in error:
            expected = error.split("REMITTANCE_MISMATCH:", 1)[1].split()[0].strip()
            raise AppError(
                code="remittance_mismatch",
                message="Remitted amount differs from the cash recorded on these jobs",
                http_status=422,
                details={
                    "expected_ngwee": int(expected) if expected.isdigit() else None,
                    "remitted_ngwee": amount_ngwee,
                    "message_key": "admin.cod.errors.remittanceMismatch",
                },
            )
        if "REMITTANCE_JOBS_INVALID" in error:
            raise AppError(
                code="remittance_jobs_invalid",
                message="Each job must be this courier's, hold recorded cash and be unremitted",
                http_status=409,
            )
        if "courier_remittances_method_reference_key" in error:
            raise AppError(
                code="remittance_duplicate",
                message="This remittance reference was already recorded",
                http_status=409,
            )
        raise RuntimeError(f"record remittance failed: {error}")
    created = [json.loads(r) for r in result.rows if r.lstrip().startswith("{")]
    remittance_id = str(created[-1]["id"])
    return RemittanceResult(
        remittance_id=remittance_id,
        courier_partner_id=courier_partner_id,
        amount_ngwee=amount_ngwee,
        dispatch_ids=tuple(ids),
        bookings=book_remitted_orders(remittance_id=remittance_id, actor_id=actor_id),
    )


def book_remitted_orders(*, remittance_id: str, actor_id: str) -> dict[str, str]:
    """Book each remitted order's COD collection in the ledger (idempotent, retryable)."""
    from app.services.payments.cod import CodError, confirm_cod_collection

    remittance_sql = sql_uuid(remittance_id, "remittance_id")
    rows = json_rows(
        f"""
SELECT json_build_object('order_id', d.order_id)::text
FROM public.dispatch_requests d WHERE d.remittance_id = {remittance_sql}
ORDER BY d.order_id;
""",
        context="remitted orders",
    )
    bookings: dict[str, str] = {}
    for row in rows:
        order_id = str(row["order_id"])
        try:
            result = confirm_cod_collection(
                order_id=order_id,
                actor_id=actor_id,
                note=f"[cod] courier remittance {remittance_id}",
            )
            bookings[order_id] = "booked" if result.created else "already_booked"
        except CodError as exc:
            bookings[order_id] = exc.code
        except Exception:
            logger.exception("COD booking after remittance failed", extra={"order_id": order_id})
            bookings[order_id] = "booking_failed"
    return bookings


def daily_cash_up(day: date) -> dict[str, Any]:
    """Per courier for one Lusaka calendar day: cash collected, remitted, outstanding."""
    day_sql = sql_literal(day.isoformat())
    rows = json_rows(
        f"""
WITH bounds AS (
  SELECT ({day_sql}::date::timestamp AT TIME ZONE 'Africa/Lusaka') AS start_at,
         (({day_sql}::date + 1)::timestamp AT TIME ZONE 'Africa/Lusaka') AS end_at
)
SELECT json_build_object(
  'courier_partner_id', c.id,
  'courier_name', c.name,
  'collected_ngwee', coalesce((
    SELECT sum(d.cod_collected_ngwee) FROM public.dispatch_requests d, bounds b
    WHERE d.courier_partner_id = c.id AND d.cod_collected_at >= b.start_at
      AND d.cod_collected_at < b.end_at), 0),
  'remitted_ngwee', coalesce((
    SELECT sum(r.amount_ngwee) FROM public.courier_remittances r, bounds b
    WHERE r.courier_partner_id = c.id AND r.received_at >= b.start_at
      AND r.received_at < b.end_at), 0),
  'outstanding_ngwee', coalesce((
    SELECT sum(d.cod_collected_ngwee) FROM public.dispatch_requests d, bounds b
    WHERE d.courier_partner_id = c.id AND d.remittance_id IS NULL
      AND d.cod_collected_ngwee IS NOT NULL AND d.cod_collected_at < b.end_at), 0)
)::text
FROM public.courier_partners c
ORDER BY c.name;
""",
        context="daily cash-up",
    )
    couriers = [
        r for r in rows if r["collected_ngwee"] or r["remitted_ngwee"] or r["outstanding_ngwee"]
    ]
    return {
        "date": day.isoformat(),
        "couriers": couriers,
        "total_outstanding_ngwee": sum(int(r["outstanding_ngwee"]) for r in couriers),
        "difference_is_zero": all(int(r["outstanding_ngwee"]) == 0 for r in couriers),
    }
