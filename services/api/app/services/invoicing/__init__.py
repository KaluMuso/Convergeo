"""Sequential invoicing — gapless numbering, ZRA-ready payloads, VAT-off at launch."""

from app.services.invoicing.allocation import allocate_invoice_number
from app.services.invoicing.builder import (
    RECEIPT_SERIES,
    TAX_INVOICE_SERIES,
    VAT_ENABLED_AT_LAUNCH,
    InvoiceInputLine,
    InvoicePayload,
    issue_receipt,
    issue_tax_invoice,
)
from app.services.invoicing.vsdc import VsdcSubmissionResult, submit_to_vsdc_stub

__all__ = [
    "RECEIPT_SERIES",
    "TAX_INVOICE_SERIES",
    "VAT_ENABLED_AT_LAUNCH",
    "InvoiceInputLine",
    "InvoicePayload",
    "VsdcSubmissionResult",
    "allocate_invoice_number",
    "issue_receipt",
    "issue_tax_invoice",
    "submit_to_vsdc_stub",
]
