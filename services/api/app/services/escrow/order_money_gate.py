"""Exclusive escrow-drain claim per order (D17 single-drain under concurrency).

Refund PRE_RELEASE and RELEASE_TO_VENDOR both drain escrow. Callers must claim
under ``pg_advisory_xact_lock`` before posting those ledger templates. POST_RELEASE
clawback does not claim (release already owns the drain).

Product and event release paths share this gate. Event phased releases re-enter
with ``gate=release`` already set; that is treated as an idempotent re-claim.

Partial item-scoped PRE_RELEASE refunds claim ``gate=refund`` for the returned
slice only. When refund ledger drain leaves remaining escrow, release may promote
the gate to ``release`` and drain the remainder (capped by remaining escrow).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.orders.audit import run_sql_script, sql_literal

RELEASE_LEDGER_KIND = "release_to_vendor"
REFUND_LEDGER_KINDS = frozenset({"refund_lane1", "refund_lane2"})
ACTIVE_REFUND_STATUSES = frozenset({"pending", "processing", "completed"})


class OrderMoneyGateError(Exception):
    """Escrow-drain claim failed (conflict or lookup error)."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class RefundGateDecision:
    """Result of claiming (or observing) escrow state for a refund."""

    phase: Literal["pre_release", "post_release"]
    claimed: bool


def _sql_uuid(value: str) -> str:
    return f"'{value}'::uuid"


def _escrow_remainder_cte(order_sql: str) -> str:
    """SQL fragment: CTE ``escrow_rem`` with charged/commission/released/refunded/remaining."""
    refund_kinds_sql = ", ".join(sql_literal(k) for k in sorted(REFUND_LEDGER_KINDS))
    return f"""
escrow_rem AS (
  SELECT
    coalesce(sum(CASE WHEN lt.kind IN (
        'charge_received', 'escrow_hold', 'cod_receivable_opened'
      ) THEN abs(lp.amount_ngwee) ELSE 0 END), 0) AS charged,
    coalesce(sum(CASE WHEN lt.kind = 'commission_capture'
      THEN abs(lp.amount_ngwee) ELSE 0 END), 0) AS commission,
    coalesce(sum(CASE WHEN lt.kind = '{RELEASE_LEDGER_KIND}'
      THEN abs(lp.amount_ngwee) ELSE 0 END), 0) AS released,
    coalesce(sum(CASE WHEN lt.kind IN ({refund_kinds_sql})
      THEN abs(lp.amount_ngwee) ELSE 0 END), 0) AS refunded
  FROM public.ledger_transactions lt
  INNER JOIN public.ledger_postings lp ON lp.transaction_id = lt.id
  INNER JOIN public.ledger_accounts la ON la.id = lp.account_id
  WHERE lt.order_id = {order_sql}
    AND la.kind = 'escrow'
),
remainder_ok AS (
  SELECT (refunded > 0 AND (charged - commission - released - refunded) > 0) AS ok
  FROM escrow_rem
)
"""


def claim_release_gate(order_id: str) -> None:
    """Claim exclusive release drain for ``order_id``.

    Blocks when a refund already owns the escrow drain **and** no remainder
    remains. Idempotent when this order already holds ``gate=release`` (event
    phase-2 / sweeper retry). Partial item refunds that left escrow promote
    ``gate=refund`` → ``gate=release`` so the remainder can reach the vendor.

    Raises ``OrderMoneyGateError`` with ``order_refunded`` or ``gate_lookup_failed``.
    """
    order_sql = _sql_uuid(order_id)
    statuses_sql = ", ".join(sql_literal(s) for s in sorted(ACTIVE_REFUND_STATUSES))
    refund_kinds_sql = ", ".join(sql_literal(k) for k in sorted(REFUND_LEDGER_KINDS))
    rem_cte = _escrow_remainder_cte(order_sql)
    script = f"""
BEGIN;
SELECT pg_advisory_xact_lock(hashtext('order_escrow:' || {order_sql}::text));

WITH {rem_cte}
UPDATE public.order_money_gates g
SET gate = 'release'
FROM remainder_ok r
WHERE g.order_id = {order_sql}
  AND g.gate = 'refund'
  AND r.ok;

WITH {rem_cte}
INSERT INTO public.order_money_gates (order_id, gate)
SELECT {order_sql}, 'release'
WHERE NOT EXISTS (
  SELECT 1 FROM public.order_money_gates WHERE order_id = {order_sql}
)
AND (
  (
    NOT EXISTS (
      SELECT 1 FROM public.refunds
      WHERE order_id = {order_sql} AND status IN ({statuses_sql})
    )
    AND NOT EXISTS (
      SELECT 1 FROM public.ledger_transactions
      WHERE order_id = {order_sql} AND kind IN ({refund_kinds_sql})
    )
  )
  OR EXISTS (SELECT 1 FROM remainder_ok WHERE ok)
)
ON CONFLICT (order_id) DO NOTHING;

SELECT CASE
  WHEN (
    SELECT gate FROM public.order_money_gates WHERE order_id = {order_sql}
  ) = 'release' THEN 'ok'
  WHEN EXISTS (
    SELECT 1 FROM public.refunds
    WHERE order_id = {order_sql} AND status IN ({statuses_sql})
  ) THEN 'order_refunded'
  WHEN EXISTS (
    SELECT 1 FROM public.ledger_transactions
    WHERE order_id = {order_sql} AND kind IN ({refund_kinds_sql})
  ) THEN 'order_refunded'
  WHEN (
    SELECT gate FROM public.order_money_gates WHERE order_id = {order_sql}
  ) = 'refund' THEN 'order_refunded'
  ELSE 'gate_lookup_failed'
END;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise OrderMoneyGateError("gate_lookup_failed")
    outcome = result.rows[-1]
    if outcome == "ok":
        return
    if outcome == "order_refunded":
        raise OrderMoneyGateError("order_refunded")
    raise OrderMoneyGateError("gate_lookup_failed")


def decide_refund_phase_under_gate(order_id: str) -> RefundGateDecision:
    """Decide refund phase under the order escrow lock; claim refund when pre-release.

    - If RELEASE_TO_VENDOR exists → ``post_release`` (clawback; no gate insert).
    - Else claim ``refund`` gate → ``pre_release``.
    - If ``release`` gate claimed without a release ledger yet → ``release_in_progress``.
    """
    order_sql = _sql_uuid(order_id)
    script = f"""
BEGIN;
SELECT pg_advisory_xact_lock(hashtext('order_escrow:' || {order_sql}::text));

INSERT INTO public.order_money_gates (order_id, gate)
SELECT {order_sql}, 'refund'
WHERE NOT EXISTS (
  SELECT 1 FROM public.ledger_transactions
  WHERE order_id = {order_sql} AND kind = '{RELEASE_LEDGER_KIND}'
)
AND NOT EXISTS (
  SELECT 1 FROM public.order_money_gates WHERE order_id = {order_sql}
)
ON CONFLICT (order_id) DO NOTHING;

SELECT CASE
  WHEN EXISTS (
    SELECT 1 FROM public.ledger_transactions
    WHERE order_id = {order_sql} AND kind = '{RELEASE_LEDGER_KIND}'
  ) THEN 'phase_post_release'
  WHEN (
    SELECT gate FROM public.order_money_gates WHERE order_id = {order_sql}
  ) = 'refund' THEN 'phase_pre_release'
  WHEN (
    SELECT gate FROM public.order_money_gates WHERE order_id = {order_sql}
  ) = 'release' THEN 'release_in_progress'
  ELSE 'gate_lookup_failed'
END;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise OrderMoneyGateError("gate_lookup_failed")
    outcome = result.rows[-1]
    if outcome == "phase_post_release":
        return RefundGateDecision(phase="post_release", claimed=False)
    if outcome == "phase_pre_release":
        return RefundGateDecision(phase="pre_release", claimed=True)
    if outcome == "release_in_progress":
        raise OrderMoneyGateError("release_in_progress")
    raise OrderMoneyGateError("gate_lookup_failed")
