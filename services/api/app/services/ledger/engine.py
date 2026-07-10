"""Ledger posting engine — templates are the only write path."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.services.ledger.templates import (
    TEMPLATE_REGISTRY,
    AccountRef,
    LedgerTemplate,
    PostingLeg,
    TemplateResult,
)
from app.services.orders.audit import resolve_db_url, run_sql_script, sql_literal

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class LedgerError(RuntimeError):
    """Base ledger engine error."""


class LedgerAccountNotFoundError(LedgerError):
    """Referenced chart-of-accounts row does not exist."""


class LedgerImbalanceError(LedgerError):
    """Posting legs do not zero-sum before write."""


@dataclass(frozen=True, slots=True)
class PostedTransaction:
    id: str
    kind: str
    idempotency_key: str
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


def assert_postings_balanced(legs: tuple[PostingLeg, ...]) -> None:
    total = sum(leg.amount_ngwee for leg in legs)
    if total != 0:
        raise LedgerImbalanceError(f"postings must sum to zero (got {total} ngwee)")


def resolve_account_id(account: AccountRef) -> str:
    """Resolve a chart-of-accounts reference to a ledger_accounts.id."""
    kind_sql = sql_literal(account.kind)
    if account.vendor_id is None:
        script = f"""
SELECT id::text
FROM public.ledger_accounts
WHERE kind = {kind_sql}
  AND vendor_id IS NULL
LIMIT 1;
"""
    else:
        vendor_sql = _sql_uuid(account.vendor_id, "vendor_id")
        script = f"""
SELECT id::text
FROM public.ledger_accounts
WHERE kind = {kind_sql}
  AND vendor_id = {vendor_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise LedgerError(f"account lookup failed: {result.error}")
    if not result.rows:
        raise LedgerAccountNotFoundError(
            f"ledger account not found: kind={account.kind!r} vendor_id={account.vendor_id!r}"
        )
    return result.rows[0]


def resolve_posting_account_ids(legs: tuple[PostingLeg, ...]) -> list[tuple[str, int]]:
    """Map template legs to (account_id, signed_ngwee) rows for insert."""
    assert_postings_balanced(legs)
    resolved: list[tuple[str, int]] = []
    for leg in legs:
        account_id = resolve_account_id(leg.account)
        resolved.append((account_id, leg.amount_ngwee))
    return resolved


def account_balance_ngwee(account_id: str) -> int:
    """Derive account balance as the sum of signed postings."""
    account_sql = _sql_uuid(account_id, "account_id")
    script = f"""
SELECT coalesce(sum(amount_ngwee), 0)::text
FROM public.ledger_postings
WHERE account_id = {account_sql};
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise LedgerError(f"balance query failed: {result.error}")
    return int(result.rows[0])


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


def _build_template_result(
    template: LedgerTemplate,
    *,
    checkout_group_id: str | None = None,
    order_id: str | None = None,
    payment_id: str | None = None,
    payout_id: str | None = None,
    refund_id: str | None = None,
    **event_args: Any,
) -> TemplateResult:
    builder = TEMPLATE_REGISTRY[template]
    built = builder(**event_args)
    return TemplateResult(
        kind=built.kind,
        legs=built.legs,
        checkout_group_id=checkout_group_id or built.checkout_group_id,
        order_id=order_id or built.order_id,
        payment_id=payment_id or built.payment_id,
        payout_id=payout_id or built.payout_id,
        refund_id=refund_id or built.refund_id,
    )


def post_transaction(
    *,
    idempotency_key: str,
    template: LedgerTemplate,
    checkout_group_id: str | None = None,
    order_id: str | None = None,
    payment_id: str | None = None,
    payout_id: str | None = None,
    refund_id: str | None = None,
    **event_args: Any,
) -> PostedTransaction:
    """Post a balanced ledger transaction from a template (sole write path).

    Same idempotency_key returns the existing transaction without double-posting.
    """
    key = idempotency_key.strip()
    if not key:
        raise ValueError("idempotency_key must not be empty")

    existing = _fetch_transaction_by_idempotency_key(key)
    if existing is not None:
        txn_sql = _sql_uuid(existing, "id")
        kind_script = f"SELECT kind FROM public.ledger_transactions WHERE id = {txn_sql};"
        kind_result = run_sql_script(kind_script)
        kind = kind_result.rows[0] if kind_result.ok and kind_result.rows else template.value
        return PostedTransaction(
            id=existing,
            kind=kind,
            idempotency_key=key,
            created=False,
        )

    template_result = _build_template_result(
        template,
        checkout_group_id=checkout_group_id,
        order_id=order_id,
        payment_id=payment_id,
        payout_id=payout_id,
        refund_id=refund_id,
        **event_args,
    )
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
    {_sql_nullable_uuid(template_result.checkout_group_id, "checkout_group_id")},
    {_sql_nullable_uuid(template_result.order_id, "order_id")},
    {_sql_nullable_uuid(template_result.payment_id, "payment_id")},
    {_sql_nullable_uuid(template_result.payout_id, "payout_id")},
    {_sql_nullable_uuid(template_result.refund_id, "refund_id")}
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
        return PostedTransaction(
            id=insert_result.rows[-1],
            kind=template_result.kind,
            idempotency_key=key,
            created=True,
        )

    existing = _fetch_transaction_by_idempotency_key(key)
    if existing is None:
        raise LedgerError("idempotent insert race lost but transaction not found")
    txn_sql = _sql_uuid(existing, "id")
    kind_script = f"SELECT kind FROM public.ledger_transactions WHERE id = {txn_sql};"
    kind_result = run_sql_script(kind_script)
    kind = kind_result.rows[0] if kind_result.ok and kind_result.rows else template_result.kind
    return PostedTransaction(
        id=existing,
        kind=kind,
        idempotency_key=key,
        created=False,
    )


def db_url() -> str:
    """Expose resolved DB URL for tests."""
    return resolve_db_url()
