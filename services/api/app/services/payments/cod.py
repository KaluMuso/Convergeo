"""COD ledger lifecycle — receivable, collection, reversal.

Cash model (platform-collect):
  Delivery agents remit collected cash to the platform. ``cod_collected`` credits
  ``platform_cash``; the vendor's net share is credited to ``vendor_payable`` for
  later payout. Commission is captured from the escrow pipeline opened at order time.

Vendor-remit (not the default path here):
  If the vendor keeps physical cash, only the commission portion would sit in
  ``cod_receivable``; reconciliation would net commission owed via vendor payable
  debits instead of a full collectable receivable. Zambia launch uses platform-collect.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.errors import AppError
from app.services.commissions.engine import (
    capture_order_commission,
    compute_order_commission,
)
from app.services.ledger.engine import (
    LedgerError,
    assert_postings_balanced,
    post_transaction,
    resolve_posting_account_ids,
)
from app.services.ledger.templates import (
    AccountRef,
    LedgerTemplate,
    PostingLeg,
    TemplateResult,
    commission_ngwee_from_bps,
)
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import (
    SYSTEM_ACTOR_ID,
    ActorRole,
    OrderEvent,
    OrderStatus,
    transition_order,
)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

COD_RECEIVABLE_OPENED = "cod_receivable_opened"
COD_RECEIVABLE_REVERSED = "cod_receivable_reversed"

_COLLECTABLE_STATUSES = frozenset({OrderStatus.DELIVERED.value})
_REFUSAL_STATUSES = frozenset({OrderStatus.SHIPPED.value})


class CodError(AppError):
    """COD lifecycle domain error."""


@dataclass(frozen=True, slots=True)
class CodOrderContext:
    order_id: str
    vendor_id: str
    status: str
    cod: bool
    fulfilment: str
    collectable_ngwee: int
    commission_snapshot: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CodReceivableResult:
    order_id: str
    collectable_ngwee: int
    transaction_id: str
    created: bool


@dataclass(frozen=True, slots=True)
class CodCollectionResult:
    order_id: str
    collectable_ngwee: int
    commission_ngwee: int
    net_vendor_ngwee: int
    transaction_ids: tuple[str, ...]
    created: bool


@dataclass(frozen=True, slots=True)
class CodRefusalResult:
    order_id: str
    collectable_ngwee: int
    reversal_transaction_id: str
    from_status: str
    to_status: str
    created: bool


def _sql_uuid(value: str, field: str) -> str:
    if not _UUID_RE.match(value):
        msg = f"Invalid UUID for {field}"
        raise ValueError(msg)
    UUID(value)
    return f"'{value}'::uuid"


def _sql_nullable_uuid(value: str | None, field: str) -> str:
    if value is None:
        return "NULL"
    return _sql_uuid(value, field)


def _fetch_transaction_by_idempotency_key(idempotency_key: str) -> str | None:
    key_sql = sql_literal(idempotency_key)
    script = f"""
SELECT id::text
FROM public.ledger_transactions
WHERE idempotency_key = {key_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise LedgerError(f"idempotency lookup failed: {result.error}")
    if not result.rows:
        return None
    return result.rows[0]


def _cod_receivable_opened_template(
    *, receivable_ngwee: int, vendor_id: str
) -> TemplateResult:
    """Order-time COD receivable paired with escrow (prepaid pipeline without Lenco).

    Debit cod_receivable (vendor) (+receivable).
    Credit escrow (−receivable).
    """
    if receivable_ngwee <= 0:
        raise ValueError("receivable_ngwee must be positive")
    legs = (
        PostingLeg(AccountRef("cod_receivable", vendor_id), receivable_ngwee),
        PostingLeg(AccountRef("escrow"), -receivable_ngwee),
    )
    assert_postings_balanced(legs)
    return TemplateResult(kind=COD_RECEIVABLE_OPENED, legs=legs)


def _cod_receivable_reversed_template(
    *, receivable_ngwee: int, vendor_id: str
) -> TemplateResult:
    """Reverse an open COD receivable on refused/uncollected delivery.

    Debit escrow (+receivable).
    Credit cod_receivable (vendor) (−receivable).
    """
    if receivable_ngwee <= 0:
        raise ValueError("receivable_ngwee must be positive")
    legs = (
        PostingLeg(AccountRef("escrow"), receivable_ngwee),
        PostingLeg(AccountRef("cod_receivable", vendor_id), -receivable_ngwee),
    )
    assert_postings_balanced(legs)
    return TemplateResult(kind=COD_RECEIVABLE_REVERSED, legs=legs)


def _post_template_result(
    *,
    idempotency_key: str,
    template_result: TemplateResult,
    order_id: str | None = None,
) -> tuple[str, bool]:
    """Post balanced legs with idempotency (local templates not in M08-P05 registry)."""
    key = idempotency_key.strip()
    if not key:
        raise ValueError("idempotency_key must not be empty")

    existing = _fetch_transaction_by_idempotency_key(key)
    if existing is not None:
        return existing, False

    assert_postings_balanced(template_result.legs)
    resolved_postings = resolve_posting_account_ids(template_result.legs)

    txn_id = str(uuid.uuid4())
    txn_sql = _sql_uuid(txn_id, "transaction_id")
    key_sql = sql_literal(key)
    kind_sql = sql_literal(template_result.kind)

    posting_rows = ",\n".join(
        f"({_sql_uuid(account_id, 'account_id')}, {amount})"
        for account_id, amount in resolved_postings
    )

    script = f"""
BEGIN;
WITH ins AS (
  INSERT INTO public.ledger_transactions (
    id,
    kind,
    idempotency_key,
    checkout_group_id,
    order_id,
    payment_id,
    payout_id,
    refund_id
  )
  VALUES (
    {txn_sql},
    {kind_sql},
    {key_sql},
    NULL,
    {_sql_nullable_uuid(order_id, "order_id")},
    NULL,
    NULL,
    NULL
  )
  ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING
  RETURNING id
),
posted AS (
  INSERT INTO public.ledger_postings (transaction_id, account_id, amount_ngwee)
  SELECT ins.id, vals.account_id, vals.amount_ngwee
  FROM ins
  CROSS JOIN (
    VALUES
      {posting_rows}
  ) AS vals(account_id, amount_ngwee)
  RETURNING transaction_id
)
SELECT id::text FROM ins;
COMMIT;
"""
    insert_result = run_sql_script(script)
    if not insert_result.ok:
        raise LedgerError(f"ledger post failed: {insert_result.error}")

    if insert_result.rows:
        return insert_result.rows[-1], True

    existing = _fetch_transaction_by_idempotency_key(key)
    if existing is None:
        raise LedgerError("idempotent insert race lost but transaction not found")
    return existing, False


def _load_cod_order(order_id: str) -> CodOrderContext:
    order_sql = _sql_uuid(order_id, "order_id")
    script = f"""
SELECT
  o.id::text,
  o.vendor_id::text,
  o.status,
  o.cod::text,
  o.fulfilment,
  o.delivery_fee_ngwee::text,
  o.commission_snapshot::text,
  coalesce((
    SELECT sum(oi.qty * oi.unit_price_ngwee)::text
    FROM public.order_items oi
    WHERE oi.order_id = o.id
  ), '0')
FROM public.orders o
WHERE o.id = {order_sql};
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise CodError(
            code="not_found",
            message="Order not found",
            http_status=404,
        )
    parts = result.rows[0].split("|")
    if len(parts) != 8:
        raise CodError(
            code="internal_error",
            message="Unexpected order row shape",
            http_status=500,
        )
    snapshot_raw = parts[6]
    snapshot: dict[str, Any] = json.loads(snapshot_raw) if snapshot_raw else {}
    subtotal = int(parts[7])
    delivery_fee = int(parts[5])
    return CodOrderContext(
        order_id=parts[0],
        vendor_id=parts[1],
        status=parts[2],
        cod=parts[3].lower() in {"t", "true"},
        fulfilment=parts[4],
        collectable_ngwee=subtotal + delivery_fee,
        commission_snapshot=snapshot,
    )


def _assert_cod_order(ctx: CodOrderContext) -> None:
    if not ctx.cod:
        raise CodError(
            code="cod_not_applicable",
            message="Order is not cash-on-delivery",
            http_status=409,
        )
    if ctx.collectable_ngwee <= 0:
        raise CodError(
            code="validation_error",
            message="COD collectable amount must be positive",
            http_status=422,
        )


def receivable_idempotency_key(order_id: str) -> str:
    return f"cod-receivable-{order_id}"


def collection_idempotency_key(order_id: str) -> str:
    return f"cod-collect-{order_id}"


def reversal_idempotency_key(order_id: str) -> str:
    return f"cod-reversal-{order_id}"


def record_cod_receivable(*, order_id: str) -> CodReceivableResult:
    """Post order-time COD receivable (paired with escrow for commission pipeline)."""
    ctx = _load_cod_order(order_id)
    _assert_cod_order(ctx)

    template = _cod_receivable_opened_template(
        receivable_ngwee=ctx.collectable_ngwee,
        vendor_id=ctx.vendor_id,
    )
    txn_id, created = _post_template_result(
        idempotency_key=receivable_idempotency_key(order_id),
        template_result=template,
        order_id=order_id,
    )
    return CodReceivableResult(
        order_id=order_id,
        collectable_ngwee=ctx.collectable_ngwee,
        transaction_id=txn_id,
        created=created,
    )


def confirm_cod_collection(
    *,
    order_id: str,
    actor_id: str,
    note: str,
) -> CodCollectionResult:
    """Confirm COD cash collected at delivery — ledger + commission + vendor net.

    Retries heal a partial prior run: if ``cod-collect-*`` already exists but
    commission/release were skipped, idempotent posts finish the drain. D17
    ``claim_release_gate`` blocks release when a refund owns the escrow drain.
    """
    from app.services.escrow.order_money_gate import (
        OrderMoneyGateError,
        claim_release_gate,
    )
    from app.services.escrow.release_accounting import (
        ReleaseAccountingError,
        compute_release_amounts,
        release_blocked_reason,
    )

    _ = actor_id
    ctx = _load_cod_order(order_id)
    _assert_cod_order(ctx)

    collect_key = collection_idempotency_key(order_id)
    existing_collect = _fetch_transaction_by_idempotency_key(collect_key)

    if existing_collect is None and ctx.status not in _COLLECTABLE_STATUSES:
        raise CodError(
            code="cod_invalid_status",
            message="COD collection requires a delivered order",
            http_status=409,
            details={"status": ctx.status, "required": sorted(_COLLECTABLE_STATUSES)},
        )

    blocked = release_blocked_reason(status=ctx.status, order_id=order_id)
    if blocked is not None:
        raise CodError(
            code="release_blocked",
            message="COD collection/release is blocked for this order",
            http_status=409,
            details={"reason": blocked},
        )

    try:
        amounts = compute_release_amounts(
            order_id=order_id,
            gross_ngwee=ctx.collectable_ngwee,
            commission_snapshot=ctx.commission_snapshot,
        )
    except ReleaseAccountingError as exc:
        raise CodError(
            code="invalid_commission_snapshot",
            message="COD release requires a usable commission snapshot",
            http_status=409,
            details={"reason": str(exc) if str(exc) else "invalid_commission_snapshot"},
        ) from exc

    try:
        claim_release_gate(order_id)
    except OrderMoneyGateError as exc:
        raise CodError(
            code="release_blocked",
            message="COD release is blocked for this order",
            http_status=409 if exc.code == "order_refunded" else 503,
            details={"reason": exc.code},
        ) from exc

    receivable_key = receivable_idempotency_key(order_id)
    if _fetch_transaction_by_idempotency_key(receivable_key) is None:
        record_cod_receivable(order_id=order_id)

    txn_ids: list[str] = []

    collected = post_transaction(
        idempotency_key=collect_key,
        template=LedgerTemplate.COD_COLLECTED,
        order_id=order_id,
        collected_ngwee=ctx.collectable_ngwee,
        vendor_id=ctx.vendor_id,
    )
    txn_ids.append(collected.id)

    captured = capture_order_commission(
        order_id=order_id,
        commission_snapshot=ctx.commission_snapshot,
        idempotency_key_prefix=f"cod-commission-{order_id}",
    )
    txn_ids.extend(captured.posted_transaction_ids)

    if amounts.net_ngwee > 0:
        released = post_transaction(
            idempotency_key=f"cod-release-{order_id}",
            template=LedgerTemplate.RELEASE_TO_VENDOR,
            order_id=order_id,
            net_ngwee=amounts.net_ngwee,
            vendor_id=ctx.vendor_id,
        )
        txn_ids.append(released.id)

    # Flip delivered→completed when collect books (or heal after a prior crash).
    # Idempotent retries may already be completed — ignore illegal transitions.
    from app.services.orders.state import OrderTransitionError

    try:
        transition_order(
            order_id=order_id,
            event=OrderEvent.AUTO_CONFIRM,
            actor_role=ActorRole.SYSTEM,
            actor_id=SYSTEM_ACTOR_ID,
            note=note,
        )
    except OrderTransitionError:
        pass

    return CodCollectionResult(
        order_id=order_id,
        collectable_ngwee=ctx.collectable_ngwee,
        commission_ngwee=amounts.commission_ngwee,
        net_vendor_ngwee=amounts.net_ngwee,
        transaction_ids=tuple(txn_ids),
        created=collected.created,
    )


def refuse_cod_collection(
    *,
    order_id: str,
    actor_role: ActorRole,
    actor_id: str,
    note: str,
) -> CodRefusalResult:
    """Refused/uncollected delivery — cancel order and reverse COD receivable."""
    ctx = _load_cod_order(order_id)
    _assert_cod_order(ctx)

    reversal_key = reversal_idempotency_key(order_id)
    existing = _fetch_transaction_by_idempotency_key(reversal_key)
    if existing is not None:
        return CodRefusalResult(
            order_id=order_id,
            collectable_ngwee=ctx.collectable_ngwee,
            reversal_transaction_id=existing,
            from_status=ctx.status,
            to_status=OrderStatus.CANCELLED.value,
            created=False,
        )

    if ctx.status not in _REFUSAL_STATUSES:
        raise CodError(
            code="cod_invalid_status",
            message="COD refusal is only allowed for shipped orders",
            http_status=409,
            details={"status": ctx.status, "allowed": sorted(_REFUSAL_STATUSES)},
        )

    receivable_key = receivable_idempotency_key(order_id)
    if _fetch_transaction_by_idempotency_key(receivable_key) is None:
        record_cod_receivable(order_id=order_id)

    template = _cod_receivable_reversed_template(
        receivable_ngwee=ctx.collectable_ngwee,
        vendor_id=ctx.vendor_id,
    )
    txn_id, created = _post_template_result(
        idempotency_key=reversal_key,
        template_result=template,
        order_id=order_id,
    )

    outcome = transition_order(
        order_id=order_id,
        event=OrderEvent.CANCEL,
        actor_role=actor_role,
        actor_id=actor_id,
        note=note,
    )

    return CodRefusalResult(
        order_id=order_id,
        collectable_ngwee=ctx.collectable_ngwee,
        reversal_transaction_id=txn_id,
        from_status=outcome.from_status.value,
        to_status=outcome.to_status.value,
        created=created,
    )


def commission_from_snapshot(snapshot: Mapping[str, Any]) -> int:
    """Expose integer-exact commission for tests and callers."""
    return compute_order_commission(snapshot).commission_ngwee


def commission_ngwee_for_collectable(
    *,
    collectable_ngwee: int,
    commission_snapshot: Mapping[str, Any],
) -> tuple[int, int]:
    """Return (commission_ngwee, net_vendor_ngwee) from a purchase-time snapshot."""
    commission = compute_order_commission(commission_snapshot).commission_ngwee
    return commission, collectable_ngwee - commission


def expected_collection_posting_legs(
    *,
    collectable_ngwee: int,
    commission_bps: int,
    vendor_id: str,
) -> tuple[tuple[str, str | None, int], ...]:
    """Return signed legs for collection confirm (cash + commission + vendor net)."""
    commission = commission_ngwee_from_bps(
        gross_ngwee=collectable_ngwee,
        commission_bps=commission_bps,
    )
    net = collectable_ngwee - commission
    legs: list[tuple[str, str | None, int]] = [
        ("platform_cash", None, collectable_ngwee),
        ("cod_receivable", vendor_id, -collectable_ngwee),
        ("escrow", None, commission),
        ("commission_revenue", None, -commission),
        ("escrow", None, net),
        ("vendor_payable", vendor_id, -net),
    ]
    return tuple(legs)
