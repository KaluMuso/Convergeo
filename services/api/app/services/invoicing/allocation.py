"""Gapless invoice number allocation via ``public.next_invoice_no``."""

from __future__ import annotations

import json
from typing import Any

from app.services.orders.audit import run_sql_script, sql_literal


class InvoiceAllocationError(RuntimeError):
    """Failed to allocate a sequential invoice number."""


def allocate_invoice_number(series: str) -> int:
    """Allocate the next gapless invoice number for ``series`` (FOR UPDATE serialized).

    Standalone allocation (no row persisted). Prefer
    :func:`allocate_and_persist_invoice` when issuing an invoice: it consumes the
    number and inserts the row in ONE transaction so a persist failure rolls the
    number back and no gap appears in the series.
    """
    normalized = series.strip()
    if not normalized:
        raise ValueError("series must not be empty")

    series_sql = sql_literal(normalized)
    result = run_sql_script(f"SELECT public.next_invoice_no({series_sql})::text;")
    if not result.ok or not result.rows:
        raise InvoiceAllocationError(
            f"next_invoice_no failed for series {normalized!r}: {result.error}"
        )
    allocated = _last_int(result.rows)
    if allocated is None or allocated < 1:
        raise InvoiceAllocationError(f"invalid invoice number allocated: {allocated}")
    return allocated


def allocate_and_persist_invoice(
    *,
    series: str,
    invoice_id: str,
    order_id: str,
    snapshot: dict[str, Any],
    vat_flag: bool,
    vat_ngwee: int,
) -> int:
    """Allocate the next gapless number AND insert the invoice row in ONE transaction.

    ``SELECT public.next_invoice_no(series)`` and ``INSERT INTO public.invoices``
    run inside a single psql ``BEGIN … COMMIT`` block. ``next_invoice_no`` holds
    the counter row lock (``SELECT … FOR UPDATE``) for the whole transaction, so
    the number is consumed **iff** the row persists: if the INSERT fails,
    ``ON_ERROR_STOP`` aborts the transaction before COMMIT and the counter
    increment rolls back — no gap in the series (ZRA gapless requirement).

    The allocated number is stamped into the persisted snapshot's ``invoice_no``
    via ``jsonb_set`` and returned so the caller can rebuild its payload.
    """
    normalized = series.strip()
    if not normalized:
        raise ValueError("series must not be empty")
    if vat_ngwee < 0:
        raise ValueError("vat_ngwee must be non-negative")

    series_sql = sql_literal(normalized)
    id_sql = sql_literal(invoice_id)
    order_sql = sql_literal(order_id)
    snapshot_sql = sql_literal(json.dumps(snapshot, separators=(",", ":")))
    vat_flag_sql = "true" if vat_flag else "false"
    # One transaction: consume the number, persist the row, echo the number.
    # ``\gset`` captures the allocation into :alloc_no without printing it; the
    # trailing SELECT emits it as the single clean numeric line for parsing.
    script = f"""BEGIN;
SELECT public.next_invoice_no({series_sql})::bigint AS alloc_no
\\gset
INSERT INTO public.invoices (id, series, no, order_id, snapshot, vat_flag, vat_ngwee)
VALUES (
  {id_sql}::uuid,
  {series_sql},
  :alloc_no,
  {order_sql}::uuid,
  jsonb_set({snapshot_sql}::jsonb, '{{invoice_no}}', to_jsonb(:alloc_no::bigint)),
  {vat_flag_sql},
  {vat_ngwee}
);
SELECT :alloc_no AS invoice_no;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise InvoiceAllocationError(
            f"gapless allocate+persist failed for series {normalized!r}: {result.error}"
        )
    allocated = _last_int(result.rows)
    if allocated is None or allocated < 1:
        raise InvoiceAllocationError(f"invalid invoice number allocated: {allocated}")
    return allocated


def _last_int(rows: list[str]) -> int | None:
    """Return the last purely-numeric row, ignoring psql status tags (``INSERT 0 1``)."""
    numeric = [row for row in rows if row.strip().lstrip("-").isdigit()]
    return int(numeric[-1]) if numeric else None
