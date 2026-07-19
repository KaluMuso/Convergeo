"""Atomic payout row reservation under a cross-worker Postgres advisory lock.

``threading.Lock`` in eligibility only serialises within one API worker. Production
runs multiple uvicorn workers, so balance check + ``payouts`` insert must happen in
one DB transaction with ``pg_advisory_xact_lock`` keyed by vendor id.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.errors import AppError
from app.services.orders.audit import run_sql_script, sql_literal

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_PENDING_RESERVE_STATUSES = ("pending", "processing")


def _sql_uuid(value: str, field: str) -> str:
    if not _UUID_RE.match(value):
        msg = f"{field} must be a valid UUID"
        raise ValueError(msg)
    return f"'{value}'::uuid"


def reserve_payout_row(
    *,
    payout_id: str,
    vendor_id: str,
    amount_ngwee: int,
    rail: str,
    lenco_reference: str,
    resolve_snapshot: dict[str, Any],
    status: str = "processing",
) -> None:
    """Reserve vendor balance by inserting a payout row under an advisory xact lock.

    Raises ``AppError`` with code ``insufficient_released_balance`` when the vendor
  does not have enough released balance net of pending/processing payouts.
    """
    if amount_ngwee <= 0:
        raise AppError(
            code="invalid_amount",
            message="Payout amount must be positive",
            http_status=400,
        )

    vendor_sql = _sql_uuid(vendor_id, "vendor_id")
    payout_sql = _sql_uuid(payout_id, "payout_id")
    rail_sql = sql_literal(rail)
    ref_sql = sql_literal(lenco_reference)
    status_sql = sql_literal(status)
    snapshot_sql = sql_literal(
        json.dumps(resolve_snapshot, separators=(",", ":"), ensure_ascii=False)
    )
    statuses_sql = ", ".join(sql_literal(s) for s in _PENDING_RESERVE_STATUSES)

    script = f"""
BEGIN;
SELECT pg_advisory_xact_lock(hashtext('vendor_payout_reserve:' || {vendor_sql}::text));

DO $$
DECLARE
  ledger_balance bigint;
  released_ngwee bigint;
  reserved_ngwee bigint;
  available_ngwee bigint;
BEGIN
  SELECT coalesce(sum(lp.amount_ngwee), 0) INTO ledger_balance
  FROM public.ledger_accounts la
  INNER JOIN public.ledger_postings lp ON lp.account_id = la.id
  WHERE la.kind = 'vendor_payable'
    AND la.vendor_id = {vendor_sql};

  released_ngwee := greatest(0, -ledger_balance);

  SELECT coalesce(sum(p.amount_ngwee), 0) INTO reserved_ngwee
  FROM public.payouts p
  WHERE p.vendor_id = {vendor_sql}
    AND p.status IN ({statuses_sql});

  available_ngwee := released_ngwee - reserved_ngwee;

  IF available_ngwee < {int(amount_ngwee)} THEN
    RAISE EXCEPTION 'insufficient_released_balance'
      USING ERRCODE = 'P0001';
  END IF;
END $$;

INSERT INTO public.payouts (
  id, vendor_id, amount_ngwee, rail, lenco_reference, status, resolve_snapshot
) VALUES (
  {payout_sql},
  {vendor_sql},
  {int(amount_ngwee)},
  {rail_sql},
  {ref_sql},
  {status_sql},
  {snapshot_sql}::jsonb
);
COMMIT;
"""
    result = run_sql_script(script)
    if result.ok:
        return

    error = result.error or "payout reservation failed"
    if "insufficient_released_balance" in error:
        raise AppError(
            code="insufficient_released_balance",
            message="Payout exceeds released vendor balance",
            http_status=409,
            details={"requested_ngwee": amount_ngwee, "vendor_id": vendor_id},
        )
    raise AppError(
        code="payout_reserve_failed",
        message="Could not reserve payout balance",
        http_status=500,
        details={"vendor_id": vendor_id, "error": error},
    )
