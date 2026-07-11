"""Signed, owner-scoped invoice/receipt download (customer + vendor) — M15-P07.

Reuses the persisted invoice snapshot (``public.invoices.snapshot``, assembled by
``services.invoicing.builder``) and renders it via ``services.invoicing.pdf``. No new
invoice number is allocated on download — the gapless sequence is reused as-is.

Two access paths, both owner-scoped:
  * ``GET /invoices/{order_id}`` — bearer-authenticated; customer sees only their own
    orders, a vendor only their own sales. Non-owner => 404 (no IDOR leak). Streams PDF.
  * ``GET /invoices/{order_id}/signed-url`` mints a short-lived HMAC-signed link that
    ``GET /invoices/download`` verifies, so a plain browser link can fetch without a
    bearer header. Tampered/expired tokens => 403.

VAT is off at launch (Turnover-Tax posture); the renderer stays VAT-flag-aware.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from datetime import timedelta
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.invoicing.pdf import invoice_filename, render_invoice_pdf
from fastapi import APIRouter, Depends, Response

router = APIRouter(prefix="/invoices", tags=["invoices"])

_KIND_TO_SERIES = {"receipt": "RCP", "tax_invoice": "TAX"}
_RATE_LIMIT_PER_HOUR = 40
_SIGNED_URL_TTL_SECONDS = 600
_TOKEN_PARTS = 2


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _not_found() -> AppError:
    # Uniform 404 for missing OR non-owned invoices — never distinguishes the two (no IDOR leak).
    return AppError(code="not_found", message="Invoice not found", http_status=404)


def _signing_secret() -> str:
    secret = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not secret:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for invoice link signing")
    return secret


def sign_invoice_token(*, order_id: str, subject_id: str, role: str, expires_at: int) -> str:
    """HMAC-sign a short-lived download grant (order + principal + expiry)."""
    payload = f"{order_id}:{subject_id}:{role}:{expires_at}"
    signature = hmac.new(
        _signing_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{encoded}.{signature}"


def verify_invoice_token(token: str, *, order_id: str) -> tuple[str, str]:
    """Return ``(subject_id, role)`` for a valid, unexpired token bound to ``order_id``.

    Raises ``AppError`` (403) for tampered, malformed, expired, or order-mismatched tokens.
    """
    parts = token.split(".")
    if len(parts) != _TOKEN_PARTS:
        raise AppError(code="forbidden", message="Invalid download token", http_status=403)
    encoded, signature = parts
    padding = "=" * (-len(encoded) % 4)
    try:
        payload = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError(
            code="forbidden", message="Invalid download token", http_status=403
        ) from exc
    expected = hmac.new(
        _signing_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise AppError(code="forbidden", message="Invalid download token", http_status=403)
    fields = payload.split(":")
    if len(fields) != 4:
        raise AppError(code="forbidden", message="Invalid download token", http_status=403)
    token_order, subject_id, role, expires_raw = fields
    if token_order != order_id:
        raise AppError(code="forbidden", message="Invalid download token", http_status=403)
    try:
        expires_at = int(expires_raw)
    except ValueError as exc:
        raise AppError(
            code="forbidden", message="Invalid download token", http_status=403
        ) from exc
    if expires_at < int(time.time()):
        raise AppError(code="forbidden", message="Download link expired", http_status=403)
    return subject_id, role


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _load_order(service: _ServiceRoleClient, order_id: str) -> dict[str, Any] | None:
    response = (
        service.client.table("orders")
        .select("id, customer_id, vendor_id")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def _vendor_id_for_owner(service: _ServiceRoleClient, owner_user_id: str) -> str | None:
    response = (
        service.client.table("vendors")
        .select("id, owner_user_id")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    return str(row["id"]) if row and row.get("id") is not None else None


def authorize_invoice_access(
    service: _ServiceRoleClient,
    *,
    order_id: str,
    subject_id: str,
) -> str:
    """Return the requester's role (``customer``/``vendor``) or raise 404 (no IDOR leak)."""
    order_row = _load_order(service, order_id)
    if order_row is None:
        raise _not_found()
    if str(order_row.get("customer_id")) == subject_id:
        return "customer"
    vendor_id = _vendor_id_for_owner(service, subject_id)
    if vendor_id is not None and vendor_id == str(order_row.get("vendor_id")):
        return "vendor"
    raise _not_found()


def _load_invoice_snapshot(
    service: _ServiceRoleClient,
    *,
    order_id: str,
    kind: str | None,
) -> dict[str, Any]:
    query = (
        service.client.table("invoices")
        .select("id, series, no, snapshot")
        .eq("order_id", order_id)
    )
    if kind is not None:
        series = _KIND_TO_SERIES.get(kind)
        if series is None:
            raise AppError(code="invalid_request", message="Unknown invoice kind", http_status=400)
        query = query.eq("series", series)
    rows = _rows(query.order("created_at", desc=True).limit(1).execute())
    if not rows:
        raise _not_found()
    snapshot = rows[0].get("snapshot")
    if not isinstance(snapshot, dict):
        raise _not_found()
    return snapshot


def _rate_limit(service: _ServiceRoleClient, subject_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope="invoice_download",
        key=subject_id,
        window=timedelta(hours=1),
        limit=_RATE_LIMIT_PER_HOUR,
        client=service.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="account.orders.invoice.errors.rateLimited",
            message="Too many invoice downloads, please wait",
        )


def _pdf_response(snapshot: dict[str, Any]) -> Response:
    pdf_bytes = render_invoice_pdf(snapshot)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{invoice_filename(snapshot)}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{order_id}/signed-url")
def create_signed_invoice_url(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    kind: str | None = None,
) -> dict[str, Any]:
    """Owner-scoped: mint a short-lived signed link a browser can follow without a bearer."""
    role = authorize_invoice_access(service, order_id=order_id, subject_id=current_user.id)
    _load_invoice_snapshot(service, order_id=order_id, kind=kind)  # 404 if not issued yet
    _rate_limit(service, current_user.id)
    expires_at = int(time.time()) + _SIGNED_URL_TTL_SECONDS
    token = sign_invoice_token(
        order_id=order_id,
        subject_id=current_user.id,
        role=role,
        expires_at=expires_at,
    )
    suffix = f"&kind={kind}" if kind is not None else ""
    return {
        "download_url": f"/invoices/download?order_id={order_id}&token={token}{suffix}",
        "expires_at": expires_at,
    }


@router.get("/download")
def download_signed_invoice(
    order_id: str,
    token: str,
    service: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    kind: str | None = None,
) -> Response:
    """Public route guarded by an HMAC-signed, short-lived, order-bound token."""
    subject_id, _role = verify_invoice_token(token, order_id=order_id)
    # Re-check ownership against live data (defence in depth beyond the signature).
    authorize_invoice_access(service, order_id=order_id, subject_id=subject_id)
    snapshot = _load_invoice_snapshot(service, order_id=order_id, kind=kind)
    return _pdf_response(snapshot)


@router.get("/{order_id}")
def download_invoice(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    kind: str | None = None,
) -> Response:
    """Bearer-authenticated owner-scoped invoice/receipt PDF stream. Non-owner => 404."""
    authorize_invoice_access(service, order_id=order_id, subject_id=current_user.id)
    snapshot = _load_invoice_snapshot(service, order_id=order_id, kind=kind)
    _rate_limit(service, current_user.id)
    return _pdf_response(snapshot)
