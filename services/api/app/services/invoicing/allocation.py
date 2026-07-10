"""Gapless invoice number allocation via ``public.next_invoice_no``."""

from __future__ import annotations

from app.services.orders.audit import run_sql_script, sql_literal


class InvoiceAllocationError(RuntimeError):
    """Failed to allocate a sequential invoice number."""


def allocate_invoice_number(series: str) -> int:
    """Allocate the next gapless invoice number for ``series`` (FOR UPDATE serialized)."""
    normalized = series.strip()
    if not normalized:
        raise ValueError("series must not be empty")

    series_sql = sql_literal(normalized)
    result = run_sql_script(f"SELECT public.next_invoice_no({series_sql})::text;")
    if not result.ok or not result.rows:
        raise InvoiceAllocationError(
            f"next_invoice_no failed for series {normalized!r}: {result.error}"
        )
    allocated = int(result.rows[-1])
    if allocated < 1:
        raise InvoiceAllocationError(f"invalid invoice number allocated: {allocated}")
    return allocated
