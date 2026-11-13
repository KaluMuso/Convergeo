"""Tiered organiser pre-event advance policy + advance debt recovery/enforcement.

Policy (platform_config, all integer):

* ``event_verified_organiser_advance_bps`` (default 5000, capped 5000) — the share of a
  ticket order bought >14 days ahead that a VERIFIED organiser receives 7 days before
  the event. Everyone else gets 0: 100% held until after the event ends.
* ``event_advance_min_kyc_tier`` (default 2) — minimum approved KYC tier.
* ``event_advance_repayment_days`` (default 14) — repayment window for a recovered
  advance before automatic suspension, blacklisting and a legal follow-up flag.

Verified = vendor ``active`` + approved KYC tier >= min tier (auditable approval only;
orphaned ``vendors.kyc_tier`` stays T1) + an unrevoked advance undertaking at the
current ``ADVANCE_TERMS_VERSION`` + no open or blacklisted advance debt. Any lookup
failure fails closed (no advance).

Undertaking: if the event is cancelled (or fails and is cancelled/refunded), buyers are
refunded in full by the platform and the organiser owes the released advance back.
Ledger (``event_advance_recovery``): the advance becomes an ``organiser_receivable``
and the platform returns the commission/fee it captured, refilling the order's escrow
so the normal event refund job pays the buyer from escrow. The receivable is netted
against later money owed to the organiser (``organiser_receivable_offset``) or settled
by a finance-confirmed cash repayment (``organiser_receivable_repaid``).

Later option (design note only, not built): a small per-ticket "event protection" fee
credited to a platform reserve account would fund refunds for organisers who never
repay, instead of absorbing the loss in platform cash.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.errors import AppError
from app.services.escrow.release_accounting import summarize_order_release_ledger
from app.services.kyc.eligibility import cap_tier_for_quotas
from app.services.ledger.engine import (
    LedgerAccountNotFoundError,
    account_balance_ngwee,
    post_transaction,
    resolve_account_id,
)
from app.services.ledger.templates import AccountRef, LedgerTemplate
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import SYSTEM_ACTOR_ID

logger = logging.getLogger(__name__)

ADVANCE_TERMS_VERSION = "2026-11-v1"
VERIFIED_ADVANCE_BPS_KEY = "event_verified_organiser_advance_bps"
MIN_KYC_TIER_KEY = "event_advance_min_kyc_tier"
REPAYMENT_DAYS_KEY = "event_advance_repayment_days"
DEFAULT_VERIFIED_ADVANCE_BPS = 5_000
MAX_ADVANCE_BPS = 5_000
DEFAULT_MIN_KYC_TIER = 2
DEFAULT_REPAYMENT_DAYS = 14

AUDIT_UNDERTAKING_ACCEPTED = "event_advance.undertaking_accepted"
AUDIT_RECEIVABLE_OPENED = "event_advance.receivable_opened"
AUDIT_RECEIVABLE_OFFSET = "event_advance.receivable_offset"
AUDIT_RECEIVABLE_REPAID = "event_advance.receivable_repaid"
AUDIT_DEBT_OVERDUE = "event_advance.debt_overdue_suspended"


def _uuid_sql(value: str) -> str:
    # sql_literal escapes; ::uuid cast rejects anything that is not a UUID.
    return f"{sql_literal(value)}::uuid"


def _config_int(key: str, default: int) -> int:
    result = run_sql_script(
        f"SELECT value::text FROM public.platform_config WHERE key = {sql_literal(key)} LIMIT 1;"
    )
    if not result.ok or not result.rows:
        return default
    raw = result.rows[0].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return default
    if isinstance(parsed, str) and parsed.strip().lstrip("-").isdigit():
        parsed = int(parsed.strip())
    if isinstance(parsed, bool) or not isinstance(parsed, int):
        return default
    return parsed


def load_verified_advance_bps() -> int:
    value = _config_int(VERIFIED_ADVANCE_BPS_KEY, DEFAULT_VERIFIED_ADVANCE_BPS)
    return max(0, min(value, MAX_ADVANCE_BPS))


def load_min_kyc_tier() -> int:
    value = _config_int(MIN_KYC_TIER_KEY, DEFAULT_MIN_KYC_TIER)
    return value if value >= 1 else DEFAULT_MIN_KYC_TIER


def load_repayment_days() -> int:
    value = _config_int(REPAYMENT_DAYS_KEY, DEFAULT_REPAYMENT_DAYS)
    return value if value >= 1 else DEFAULT_REPAYMENT_DAYS


@dataclass(frozen=True, slots=True)
class AdvanceDecision:
    bps: int
    reason: str


def _organiser_kyc_tier(vendor_id: str) -> tuple[str, int]:
    """(vendor status, auditable effective KYC tier) — via the GMV-cap eligibility math."""
    from app.services.events.gmv_cap import _eligibility_from_sql

    eligibility = _eligibility_from_sql(vendor_id)
    status_result = run_sql_script(
        f"SELECT status FROM public.vendors WHERE id = {_uuid_sql(vendor_id)} LIMIT 1;"
    )
    if not status_result.ok or not status_result.rows:
        raise RuntimeError("organiser status lookup failed")
    return status_result.rows[0].strip(), cap_tier_for_quotas(eligibility)


def has_current_undertaking(vendor_id: str) -> bool:
    result = run_sql_script(
        f"""
SELECT count(*)::text FROM public.organiser_advance_undertakings
WHERE vendor_id = {_uuid_sql(vendor_id)}
  AND revoked_at IS NULL
  AND terms_version = {sql_literal(ADVANCE_TERMS_VERSION)};
"""
    )
    if not result.ok or not result.rows:
        raise RuntimeError(f"undertaking lookup failed: {result.error}")
    return int(result.rows[0]) > 0


def _has_blocking_debt(vendor_id: str) -> bool:
    result = run_sql_script(
        f"""
SELECT count(*)::text FROM public.organiser_advance_debts
WHERE vendor_id = {_uuid_sql(vendor_id)}
  AND (status = 'open' OR blacklisted_at IS NOT NULL);
"""
    )
    if not result.ok or not result.rows:
        raise RuntimeError(f"advance debt lookup failed: {result.error}")
    return int(result.rows[0]) > 0


def organiser_advance_decision(vendor_id: str) -> AdvanceDecision:
    """Pre-event advance share for an organiser right now. Fails closed to 0."""
    configured = load_verified_advance_bps()
    if configured <= 0:
        return AdvanceDecision(0, "advances_disabled")
    try:
        status, tier = _organiser_kyc_tier(vendor_id)
        if status != "active":
            return AdvanceDecision(0, "organiser_not_active")
        if tier < load_min_kyc_tier():
            return AdvanceDecision(0, "organiser_unverified")
        if not has_current_undertaking(vendor_id):
            return AdvanceDecision(0, "undertaking_missing")
        if _has_blocking_debt(vendor_id):
            return AdvanceDecision(0, "advance_debt_outstanding")
    except (RuntimeError, AppError):
        logger.exception("advance policy lookup failed", extra={"vendor_id": vendor_id})
        return AdvanceDecision(0, "policy_lookup_failed")
    return AdvanceDecision(configured, "verified_organiser")


def accept_advance_undertaking(*, vendor_id: str, actor_user_id: str) -> None:
    """Record (or renew) the organiser's advance undertaking, with an audit row."""
    after = json.dumps({"vendor_id": vendor_id, "terms_version": ADVANCE_TERMS_VERSION})
    result = run_sql_script(
        f"""
BEGIN;
INSERT INTO public.organiser_advance_undertakings (vendor_id, terms_version, accepted_by)
VALUES ({_uuid_sql(vendor_id)}, {sql_literal(ADVANCE_TERMS_VERSION)}, {_uuid_sql(actor_user_id)})
ON CONFLICT (vendor_id) DO UPDATE
  SET terms_version = EXCLUDED.terms_version,
      accepted_by = EXCLUDED.accepted_by,
      accepted_at = timezone('utc', now()),
      revoked_at = NULL;
INSERT INTO public.audit_log (actor, action, entity_type, entity_id, before, after)
VALUES ({_uuid_sql(actor_user_id)}, {sql_literal(AUDIT_UNDERTAKING_ACCEPTED)}, 'vendor',
        {_uuid_sql(vendor_id)}, NULL, {sql_literal(after)}::jsonb);
COMMIT;
"""
    )
    if not result.ok:
        raise RuntimeError(f"accept advance undertaking failed: {result.error}")


def _ensure_receivable_account(vendor_id: str) -> None:
    result = run_sql_script(
        f"""
INSERT INTO public.ledger_accounts (kind, vendor_id)
VALUES ('organiser_receivable', {_uuid_sql(vendor_id)})
ON CONFLICT (kind, vendor_id) WHERE vendor_id IS NOT NULL DO NOTHING;
"""
    )
    if not result.ok:
        raise RuntimeError(f"organiser receivable account provisioning failed: {result.error}")


def advance_recovery_key(order_id: str) -> str:
    return f"event-advance-recovery-{order_id}"


@dataclass(frozen=True, slots=True)
class AdvanceRecoveryResult:
    order_id: str
    advance_ngwee: int
    platform_restore_ngwee: int
    posted: bool


def recover_event_advance(
    *, order_id: str, vendor_id: str, event_id: str, now: datetime | None = None
) -> AdvanceRecoveryResult:
    """Cancelled event: turn an already-released advance into an organiser receivable.

    Idempotent per order (ledger key + unique debt row). No-op when nothing was
    released to the organiser for this order.
    """
    summary = summarize_order_release_ledger(order_id)
    created = False
    if summary.advance_recovered_ngwee > 0:
        # Ledger already posted (e.g. a crash before the debt row): re-derive the
        # organiser's share from the recovery transaction and finish idempotently.
        advance = _recovered_advance_ngwee(order_id)
        restore = summary.advance_recovered_ngwee - advance
    else:
        advance = summary.vendor_released_ngwee
        restore = summary.commission_captured_ngwee
        if advance <= 0:
            return AdvanceRecoveryResult(order_id, 0, 0, posted=False)
        _ensure_receivable_account(vendor_id)
        created = post_transaction(
            idempotency_key=advance_recovery_key(order_id),
            template=LedgerTemplate.EVENT_ADVANCE_RECOVERY,
            order_id=order_id,
            advance_ngwee=advance,
            platform_restore_ngwee=restore,
            vendor_id=vendor_id,
        ).created
    if advance <= 0:
        return AdvanceRecoveryResult(order_id, 0, 0, posted=False)
    instant = (now or datetime.now(UTC)).astimezone(UTC)
    due_at = instant + timedelta(days=load_repayment_days())
    after = json.dumps(
        {
            "event_id": event_id,
            "order_id": order_id,
            "advance_ngwee": advance,
            "platform_restore_ngwee": restore,
            "due_at": due_at.isoformat(),
        }
    )
    result = run_sql_script(
        f"""
BEGIN;
WITH ins AS (
  INSERT INTO public.organiser_advance_debts (vendor_id, event_id, order_id, amount_ngwee, due_at)
  VALUES ({_uuid_sql(vendor_id)}, {_uuid_sql(event_id)}, {_uuid_sql(order_id)}, {int(advance)},
          {sql_literal(due_at.isoformat())}::timestamptz)
  ON CONFLICT (order_id) DO NOTHING
  RETURNING id
)
INSERT INTO public.audit_log (actor, action, entity_type, entity_id, before, after)
SELECT {_uuid_sql(SYSTEM_ACTOR_ID)}, {sql_literal(AUDIT_RECEIVABLE_OPENED)}, 'vendor',
       {_uuid_sql(vendor_id)}, NULL, {sql_literal(after)}::jsonb
FROM ins;
COMMIT;
"""
    )
    if not result.ok:
        raise RuntimeError(f"record advance debt failed: {result.error}")
    offset_organiser_receivable(vendor_id)
    return AdvanceRecoveryResult(order_id, advance, restore, posted=created)


def _recovered_advance_ngwee(order_id: str) -> int:
    result = run_sql_script(
        f"""
SELECT coalesce(sum(lp.amount_ngwee), 0)::text
FROM public.ledger_transactions lt
JOIN public.ledger_postings lp ON lp.transaction_id = lt.id
JOIN public.ledger_accounts la ON la.id = lp.account_id
WHERE lt.idempotency_key = {sql_literal(advance_recovery_key(order_id))}
  AND la.kind = 'organiser_receivable';
"""
    )
    if not result.ok or not result.rows:
        raise RuntimeError(f"advance recovery lookup failed: {result.error}")
    return int(result.rows[0])


def organiser_receivable_balance_ngwee(vendor_id: str) -> int:
    """Positive = organiser owes the platform."""
    try:
        account_id = resolve_account_id(AccountRef("organiser_receivable", vendor_id))
    except LedgerAccountNotFoundError:
        return 0
    return account_balance_ngwee(account_id)


def _vendor_payable_available_ngwee(vendor_id: str) -> int:
    """Credit owed to the organiser not already reserved by an in-flight payout."""
    try:
        payable_id = resolve_account_id(AccountRef("vendor_payable", vendor_id))
    except LedgerAccountNotFoundError:
        return 0
    owed = max(0, -account_balance_ngwee(payable_id))
    reserved = run_sql_script(
        f"""
SELECT coalesce(sum(amount_ngwee), 0)::text FROM public.payouts
WHERE vendor_id = {_uuid_sql(vendor_id)}
  AND status IN ('pending', 'processing')
  AND coalesce(resolve_snapshot ->> 'kind', '') <> 'customer_refund'
  AND coalesce((resolve_snapshot ->> 'deferred')::boolean, false) = false;
"""
    )
    if not reserved.ok or not reserved.rows:
        return 0  # fail closed: never offset against money we cannot see
    return max(0, owed - int(reserved.rows[0]))


def _apply_recovered_to_debts(vendor_id: str, amount_ngwee: int) -> None:
    """FIFO-allocate a recovered amount across the organiser's open debts."""
    vendor_sql = _uuid_sql(vendor_id)
    result = run_sql_script(
        f"""
BEGIN;
SELECT id FROM public.organiser_advance_debts
WHERE vendor_id = {vendor_sql} AND status = 'open'
FOR UPDATE;
WITH open_debts AS (
  SELECT id, amount_ngwee - recovered_ngwee AS outstanding,
         sum(amount_ngwee - recovered_ngwee) OVER (ORDER BY created_at, id) AS running
  FROM public.organiser_advance_debts
  WHERE vendor_id = {vendor_sql} AND status = 'open'
),
alloc AS (
  SELECT id,
         least(outstanding, greatest(0, {int(amount_ngwee)} - (running - outstanding)))
           AS take
  FROM open_debts
)
UPDATE public.organiser_advance_debts d
SET recovered_ngwee = d.recovered_ngwee + a.take,
    status = CASE WHEN d.recovered_ngwee + a.take = d.amount_ngwee
                  THEN 'settled' ELSE d.status END
FROM alloc a
WHERE d.id = a.id AND a.take > 0;
COMMIT;
"""
    )
    if not result.ok:
        raise RuntimeError(f"advance debt allocation failed: {result.error}")


def _ledger_state_tag(vendor_id: str) -> str:
    result = run_sql_script(
        f"""
SELECT la.kind || ':' || count(lp.id)::text
FROM public.ledger_accounts la
LEFT JOIN public.ledger_postings lp ON lp.account_id = la.id
WHERE la.vendor_id = {_uuid_sql(vendor_id)}
  AND la.kind IN ('organiser_receivable', 'vendor_payable')
GROUP BY la.kind
ORDER BY la.kind;
"""
    )
    if not result.ok:
        raise RuntimeError(f"ledger state lookup failed: {result.error}")
    return "-".join(row.replace(":", "") for row in result.rows)


def offset_organiser_receivable(vendor_id: str) -> int:
    """Net the organiser's receivable against unreserved money owed to them."""
    receivable = organiser_receivable_balance_ngwee(vendor_id)
    if receivable <= 0:
        return 0
    available = _vendor_payable_available_ngwee(vendor_id)
    amount = min(receivable, available)
    if amount <= 0:
        return 0
    # Key binds to the observed ledger state (posting counts on both accounts): a
    # concurrent run on the same state dedupes, any later state gets a fresh key.
    posted = post_transaction(
        idempotency_key=f"organiser-receivable-offset-{vendor_id}-{_ledger_state_tag(vendor_id)}",
        template=LedgerTemplate.ORGANISER_RECEIVABLE_OFFSET,
        amount_ngwee=amount,
        vendor_id=vendor_id,
    )
    if not posted.created:
        return 0
    _apply_recovered_to_debts(vendor_id, amount)
    _audit(vendor_id, AUDIT_RECEIVABLE_OFFSET, {"amount_ngwee": amount, "txn_id": posted.id})
    return amount


def record_organiser_repayment(
    *, vendor_id: str, amount_ngwee: int, actor_user_id: str, reference: str
) -> str:
    """Finance-confirmed cash repayment of an advance debt (ledger + debts + audit)."""
    if isinstance(amount_ngwee, bool) or not isinstance(amount_ngwee, int) or amount_ngwee <= 0:
        raise AppError(
            code="validation_error", message="amount_ngwee must be positive", http_status=422
        )
    receivable = organiser_receivable_balance_ngwee(vendor_id)
    if amount_ngwee > receivable:
        raise AppError(
            code="repayment_exceeds_receivable",
            message="Repayment exceeds what the organiser owes",
            http_status=409,
            details={"receivable_ngwee": receivable},
        )
    ref = reference.strip()
    if not ref:
        raise AppError(code="validation_error", message="reference is required", http_status=422)
    posted = post_transaction(
        idempotency_key=f"organiser-receivable-repaid-{vendor_id}-{ref}",
        template=LedgerTemplate.ORGANISER_RECEIVABLE_REPAID,
        amount_ngwee=amount_ngwee,
        vendor_id=vendor_id,
    )
    if posted.created:
        _apply_recovered_to_debts(vendor_id, amount_ngwee)
        _audit(
            vendor_id,
            AUDIT_RECEIVABLE_REPAID,
            {"amount_ngwee": amount_ngwee, "reference": ref, "txn_id": posted.id},
            actor=actor_user_id,
        )
    return posted.id


def _audit(
    vendor_id: str, action: str, after: dict[str, object], *, actor: str = SYSTEM_ACTOR_ID
) -> None:
    result = run_sql_script(
        f"""
INSERT INTO public.audit_log (actor, action, entity_type, entity_id, before, after)
VALUES ({_uuid_sql(actor)}, {sql_literal(action)}, 'vendor', {_uuid_sql(vendor_id)}, NULL,
        {sql_literal(json.dumps(after))}::jsonb);
"""
    )
    if not result.ok:
        raise RuntimeError(f"advance audit failed: {result.error}")


@dataclass(frozen=True, slots=True)
class OverdueEnforcementResult:
    debts_flagged: int
    vendors_suspended: int


def enforce_overdue_advance_debts(*, now: datetime | None = None) -> OverdueEnforcementResult:
    """Unpaid past due: suspend the organiser, blacklist the debt, flag legal follow-up.

    One transaction: flag debts, suspend the vendor (active -> suspended, so no new
    publishing or sales), and write one audit row per vendor. Idempotent (already
    flagged debts are skipped).
    """
    instant = (now or datetime.now(UTC)).astimezone(UTC)
    now_sql = f"{sql_literal(instant.isoformat())}::timestamptz"
    actor_sql = _uuid_sql(SYSTEM_ACTOR_ID)
    result = run_sql_script(
        f"""
BEGIN;
WITH overdue AS (
  UPDATE public.organiser_advance_debts
  SET suspended_at = {now_sql},
      blacklisted_at = {now_sql},
      legal_followup_at = {now_sql}
  WHERE status = 'open'
    AND due_at <= {now_sql}
    AND blacklisted_at IS NULL
  RETURNING vendor_id, id, amount_ngwee - recovered_ngwee AS outstanding
),
per_vendor AS (
  SELECT vendor_id, sum(outstanding)::bigint AS outstanding,
         array_agg(id::text ORDER BY id) AS debt_ids
  FROM overdue GROUP BY vendor_id
),
suspended AS (
  UPDATE public.vendors v
  SET status = 'suspended', updated_at = timezone('utc', now())
  FROM per_vendor p
  WHERE v.id = p.vendor_id AND v.status = 'active'
  RETURNING v.id
),
audited AS (
  INSERT INTO public.audit_log (actor, action, entity_type, entity_id, before, after)
  SELECT {actor_sql}, {sql_literal(AUDIT_DEBT_OVERDUE)}, 'vendor', p.vendor_id,
         NULL,
         jsonb_build_object(
           'outstanding_ngwee', p.outstanding,
           'debt_ids', to_jsonb(p.debt_ids),
           'suspended', EXISTS (SELECT 1 FROM suspended s WHERE s.id = p.vendor_id),
           'blacklisted', true,
           'legal_followup', true
         )
  FROM per_vendor p
  RETURNING id
)
SELECT (SELECT count(*) FROM overdue)::text || '|' || (SELECT count(*) FROM suspended)::text
  || '|' || (SELECT count(*) FROM audited)::text;
COMMIT;
"""
    )
    if not result.ok or not result.rows:
        raise RuntimeError(f"overdue advance enforcement failed: {result.error}")
    parts = result.rows[-1].split("|")
    return OverdueEnforcementResult(debts_flagged=int(parts[0]), vendors_suspended=int(parts[1]))
