"""VSDC (ZRA fiscal device) integration seam — stub only at launch."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VsdcSubmissionResult:
    """Result of a (stubbed) VSDC fiscalisation attempt."""

    submitted: bool
    fiscal_code: str | None
    message: str


def submit_to_vsdc_stub(payload: Mapping[str, Any]) -> VsdcSubmissionResult:
    """Documented VSDC seam — no live ZRA integration until VSDC credentials land (F-series).

    Callers pass the tax-invoice payload; at launch this records intent only and returns a
    deterministic placeholder fiscal code for downstream wiring tests.
    """
    series = str(payload.get("series", ""))
    invoice_no = payload.get("invoice_no")
    if not series or invoice_no is None:
        return VsdcSubmissionResult(
            submitted=False,
            fiscal_code=None,
            message="VSDC stub: missing series or invoice_no",
        )
    return VsdcSubmissionResult(
        submitted=False,
        fiscal_code=f"VSDC-STUB-{series}-{invoice_no}",
        message="VSDC integration disabled at launch (VAT-off); seam records payload only",
    )
