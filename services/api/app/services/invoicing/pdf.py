"""Tax-invoice / receipt PDF renderer (stdlib only, VAT-flag-aware).

Renders from ``builder.InvoicePayload.to_snapshot()`` (the assembled invoice dict) so no
extra data assembly lives here. Money is integer ngwee everywhere; ``format_k`` converts
to a K-major display string using integer arithmetic only (never float).

At launch the platform is on the Turnover-Tax posture (VAT off): ``vat_enabled`` defaults
to the snapshot's ``vat_flag`` and, when False, the VAT breakdown block is not rendered.
The VAT layout branch exists so the VSDC seam can flip it on later without a rewrite.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_PAGE_WIDTH = 595
_PAGE_HEIGHT = 842
_MARGIN_LEFT = 40
_TOP_Y = 800
_LEADING = 16

_SERIES_LABEL = {"RCP": "RECEIPT", "TAX": "TAX INVOICE"}
_TPIN_PLACEHOLDER = "—"  # em dash — no real TPIN wired at launch


def format_k(ngwee: int) -> str:
    """Render integer ngwee as ``K1,234.56`` (integer math only — never float)."""
    if not isinstance(ngwee, int) or isinstance(ngwee, bool):
        raise TypeError("ngwee must be an integer")
    sign = "-" if ngwee < 0 else ""
    magnitude = abs(ngwee)
    major, minor = divmod(magnitude, 100)
    return f"{sign}K{major:,}.{minor:02d}"


def _invoice_no_display(series: str, invoice_no: int) -> str:
    return f"{series}-{invoice_no:06d}"


def _invoice_lines(
    snapshot: Mapping[str, Any],
    *,
    vat_enabled: bool,
) -> list[str]:
    series = str(snapshot.get("series", ""))
    invoice_no = int(snapshot.get("invoice_no", 0))
    kind = str(snapshot.get("kind", "tax_invoice"))
    heading = _SERIES_LABEL.get(series, kind.replace("_", " ").upper())
    seller_tpin = snapshot.get("seller_tpin") or _TPIN_PLACEHOLDER

    lines: list[str] = [
        "Vergeo5 Marketplace",
        heading,
        f"Invoice No: {_invoice_no_display(series, invoice_no)}",
        f"Issued: {snapshot.get('issued_at', '')}",
        f"Order: {snapshot.get('order_id', '')}",
        f"Seller TPIN: {seller_tpin}",
        f"Buyer TPIN: {_TPIN_PLACEHOLDER}",
        "",
        "Description                Qty   Unit        Line total",
        "-" * 58,
    ]

    raw_lines: Sequence[Any] = snapshot.get("lines", []) or []
    for item in raw_lines:
        description = str(item.get("description", ""))[:24]
        qty = int(item.get("qty", 0))
        unit = format_k(int(item.get("unit_price_ngwee", 0)))
        line_total = format_k(int(item.get("line_total_ngwee", 0)))
        lines.append(f"{description:<24} {qty:>4}   {unit:<11} {line_total:>12}")

    lines.append("-" * 58)
    lines.append(f"Subtotal: {format_k(int(snapshot.get('subtotal_ngwee', 0)))}")

    if vat_enabled:
        # VAT-on layout branch (kept for the VSDC seam; not exercised at launch).
        vat_ngwee = int(snapshot.get("vat_ngwee", 0))
        lines.append(f"VAT: {format_k(vat_ngwee)}")
        lines.append("VAT breakdown per line included above.")
    else:
        lines.append("Turnover Tax posture — not registered for VAT (no VAT charged).")

    lines.append(f"Total: {format_k(int(snapshot.get('total_ngwee', 0)))}")
    lines.append("")
    lines.append("Fiscalisation: pending VSDC activation (ZRA).")
    return lines


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content_stream(lines: Sequence[str]) -> bytes:
    parts = [
        "BT",
        "/F1 11 Tf",
        f"{_LEADING} TL",
        f"{_MARGIN_LEFT} {_TOP_Y} Td",
    ]
    for line in lines:
        parts.append(f"({_escape_pdf_text(line)}) Tj")
        parts.append("T*")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1", "replace")


def _build_pdf(lines: Sequence[str]) -> bytes:
    content = _content_stream(lines)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
            + f"{_PAGE_WIDTH} {_PAGE_HEIGHT}".encode("ascii")
            + b"] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            b"<< /Length "
            + str(len(content)).encode("ascii")
            + b" >>\nstream\n"
            + content
            + b"\nendstream"
        ),
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

    xref_offset = len(out)
    count = len(objects) + 1
    out += f"xref\n0 {count}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        b"trailer\n<< /Size "
        + str(count).encode("ascii")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode("ascii")
        + b"\n%%EOF\n"
    )
    return bytes(out)


def render_invoice_pdf(
    snapshot: Mapping[str, Any],
    *,
    vat_enabled: bool | None = None,
) -> bytes:
    """Render an invoice/receipt snapshot to PDF bytes.

    ``vat_enabled`` defaults to the snapshot's ``vat_flag`` (False at launch). Passing it
    explicitly lets the VSDC activation path preview the VAT-on layout without a schema change.
    """
    resolved_vat = bool(snapshot.get("vat_flag")) if vat_enabled is None else vat_enabled
    lines = _invoice_lines(snapshot, vat_enabled=resolved_vat)
    return _build_pdf(lines)


def invoice_filename(snapshot: Mapping[str, Any]) -> str:
    series = str(snapshot.get("series", "INV"))
    invoice_no = int(snapshot.get("invoice_no", 0))
    return f"invoice-{_invoice_no_display(series, invoice_no)}.pdf"
