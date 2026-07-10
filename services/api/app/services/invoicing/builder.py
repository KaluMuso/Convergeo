"""Receipt and tax-invoice payload builders (VAT-off compliant at launch)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.services.invoicing.allocation import allocate_invoice_number
from app.services.orders.audit import run_sql_script, sql_literal

RECEIPT_SERIES = "RCP"
TAX_INVOICE_SERIES = "TAX"
VAT_ENABLED_AT_LAUNCH = False
VAT_RATE_BPS_AT_LAUNCH = 0


@dataclass(frozen=True, slots=True)
class InvoiceInputLine:
    description: str
    qty: int
    unit_price_ngwee: int


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    description: str
    qty: int
    unit_price_ngwee: int
    line_total_ngwee: int
    vat_rate_bps: int
    vat_ngwee: int


@dataclass(frozen=True, slots=True)
class InvoicePayload:
    kind: Literal["receipt", "tax_invoice"]
    series: str
    invoice_no: int
    invoice_id: str
    order_id: str
    payment_id: str | None
    issued_at: datetime
    seller_tpin: str | None
    vat_flag: bool
    subtotal_ngwee: int
    vat_ngwee: int
    total_ngwee: int
    lines: tuple[InvoiceLine, ...]

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "series": self.series,
            "invoice_no": self.invoice_no,
            "order_id": self.order_id,
            "payment_id": self.payment_id,
            "issued_at": self.issued_at.isoformat(),
            "seller_tpin": self.seller_tpin,
            "vat_flag": self.vat_flag,
            "subtotal_ngwee": self.subtotal_ngwee,
            "vat_ngwee": self.vat_ngwee,
            "total_ngwee": self.total_ngwee,
            "lines": [
                {
                    "description": line.description,
                    "qty": line.qty,
                    "unit_price_ngwee": line.unit_price_ngwee,
                    "line_total_ngwee": line.line_total_ngwee,
                    "vat_rate_bps": line.vat_rate_bps,
                    "vat_ngwee": line.vat_ngwee,
                }
                for line in self.lines
            ],
        }


def _line_total_ngwee(qty: int, unit_price_ngwee: int) -> int:
    if qty < 1:
        raise ValueError("qty must be at least 1")
    if unit_price_ngwee < 0:
        raise ValueError("unit_price_ngwee must be non-negative")
    return qty * unit_price_ngwee


def _build_lines(
    input_lines: tuple[InvoiceInputLine, ...],
    *,
    vat_flag: bool,
) -> tuple[InvoiceLine, ...]:
    vat_rate_bps = VAT_RATE_BPS_AT_LAUNCH if vat_flag else 0
    built: list[InvoiceLine] = []
    for item in input_lines:
        line_total = _line_total_ngwee(item.qty, item.unit_price_ngwee)
        line_vat = (line_total * vat_rate_bps) // 10_000 if vat_flag else 0
        built.append(
            InvoiceLine(
                description=item.description,
                qty=item.qty,
                unit_price_ngwee=item.unit_price_ngwee,
                line_total_ngwee=line_total,
                vat_rate_bps=vat_rate_bps,
                vat_ngwee=line_vat,
            )
        )
    return tuple(built)


def build_invoice_payload(
    *,
    kind: Literal["receipt", "tax_invoice"],
    series: str,
    invoice_no: int,
    order_id: str,
    lines: tuple[InvoiceInputLine, ...],
    payment_id: str | None = None,
    seller_tpin: str | None = None,
    issued_at: datetime | None = None,
    vat_flag: bool = VAT_ENABLED_AT_LAUNCH,
) -> InvoicePayload:
    """Build a ZRA-ready invoice payload (VAT columns present; zeroed when VAT off)."""
    invoice_lines = _build_lines(lines, vat_flag=vat_flag)
    subtotal = sum(line.line_total_ngwee for line in invoice_lines)
    vat_total = sum(line.vat_ngwee for line in invoice_lines)
    return InvoicePayload(
        kind=kind,
        series=series,
        invoice_no=invoice_no,
        invoice_id=str(uuid.uuid4()),
        order_id=order_id,
        payment_id=payment_id,
        issued_at=issued_at or datetime.now(tz=UTC),
        seller_tpin=seller_tpin,
        vat_flag=vat_flag,
        subtotal_ngwee=subtotal,
        vat_ngwee=vat_total,
        total_ngwee=subtotal + vat_total,
        lines=invoice_lines,
    )


def _persist_invoice(payload: InvoicePayload) -> None:
    snapshot_sql = sql_literal(json.dumps(payload.to_snapshot(), separators=(",", ":")))
    order_sql = sql_literal(payload.order_id)
    series_sql = sql_literal(payload.series)
    script = f"""
INSERT INTO public.invoices (
  id, series, no, order_id, snapshot, vat_flag, vat_ngwee
)
VALUES (
  '{payload.invoice_id}'::uuid,
  {series_sql},
  {payload.invoice_no},
  {order_sql}::uuid,
  {snapshot_sql}::jsonb,
  {'true' if payload.vat_flag else 'false'},
  {payload.vat_ngwee}
);
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"invoice persist failed: {result.error}")


def issue_receipt(
    *,
    order_id: str,
    lines: tuple[InvoiceInputLine, ...],
    payment_id: str,
    seller_tpin: str | None = None,
) -> InvoicePayload:
    """Issue a payment-success receipt with a gapless sequential number."""
    invoice_no = allocate_invoice_number(RECEIPT_SERIES)
    payload = build_invoice_payload(
        kind="receipt",
        series=RECEIPT_SERIES,
        invoice_no=invoice_no,
        order_id=order_id,
        lines=lines,
        payment_id=payment_id,
        seller_tpin=seller_tpin,
        vat_flag=VAT_ENABLED_AT_LAUNCH,
    )
    _persist_invoice(payload)
    return payload


def issue_tax_invoice(
    *,
    order_id: str,
    lines: tuple[InvoiceInputLine, ...],
    seller_tpin: str | None = None,
) -> InvoicePayload:
    """Issue order-completion tax-invoice data with a gapless sequential number."""
    invoice_no = allocate_invoice_number(TAX_INVOICE_SERIES)
    payload = build_invoice_payload(
        kind="tax_invoice",
        series=TAX_INVOICE_SERIES,
        invoice_no=invoice_no,
        order_id=order_id,
        lines=lines,
        seller_tpin=seller_tpin,
        vat_flag=VAT_ENABLED_AT_LAUNCH,
    )
    _persist_invoice(payload)
    return payload
