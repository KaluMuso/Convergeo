"""Vendor payouts view — ledger-derived balances, history, statements, method change."""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.privacy import verify_reauth_otp
from app.routers.vendor_orders import _load_vendor_for_owner
from app.schemas.base import StrictModel
from app.services.kyc.name_match import MomoOperator, resolve_and_score_momo_name
from app.services.ledger.engine import account_balance_ngwee, resolve_account_id
from app.services.ledger.templates import AccountRef
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.orders.audit import run_sql_script
from app.services.payouts.eligibility import compute_eligibility
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field, field_validator

router = APIRouter(prefix="/vendor/payouts", tags=["vendor-payouts"])

PAYOUT_RAILS = frozenset({"mtn", "airtel", "zamtel"})
METHOD_CHANGE_LIMIT_PER_DAY = 5
VENDOR_READ_LIMIT_PER_MINUTE = 120
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class PayoutBalances(StrictModel):
    escrow_held_ngwee: int
    released_available_ngwee: int
    paid_out_ngwee: int
    payouts_blocked: bool
    payout_hold_until: str | None
    payout_msisdn: str | None
    payout_rail: str | None


class PayoutHistoryItem(StrictModel):
    id: str
    amount_ngwee: int
    rail: str
    status: str
    lenco_reference: str
    created_at: str


class PayoutHistoryResponse(StrictModel):
    items: list[PayoutHistoryItem]


class PayoutMethodChangeRequest(StrictModel):
    payout_msisdn: str = Field(min_length=9, max_length=20)
    payout_rail: MomoOperator
    otp: str = Field(min_length=6, max_length=6)

    @field_validator("otp")
    @classmethod
    def validate_otp_digits(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("otp must contain digits only")
        return value


class PayoutMethodChangeResponse(StrictModel):
    payout_msisdn: str
    payout_rail: str
    payout_hold_until: str
    resolved_name: str | None
    match_score: float
    matched: bool


def _sql_uuid(value: str, field: str) -> str:
    return f"'{value}'::uuid"


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    normalized = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_msisdn(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("260"):
        return f"0{digits[3:]}"
    if digits.startswith("0"):
        return digits
    if len(digits) == 9:
        return f"0{digits}"
    return digits


def _bump_vendor_scope_limit(
    *,
    request: Request,
    service_client: _ServiceRoleClient,
    scope: str,
    vendor_id: str,
    limit: int,
    window_seconds: int,
    message_key: str,
) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=scope,
        key=f"{vendor_id}:{request.client.host if request.client else 'unknown'}",
        window=timedelta(seconds=window_seconds),
        limit=limit,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key=message_key,
            message="Too many payout requests",
        )


def vendor_escrow_held_ngwee(vendor_id: str) -> int:
    """Ledger-derived escrow still held for this vendor's orders (per-order net escrow credits)."""
    vendor_sql = _sql_uuid(vendor_id, "vendor_id")
    script = f"""
SELECT coalesce(sum(greatest(0, -order_net)), 0)::text
FROM (
  SELECT lt.order_id, sum(lp.amount_ngwee) AS order_net
  FROM public.ledger_transactions lt
  JOIN public.ledger_postings lp ON lp.transaction_id = lt.id
  JOIN public.ledger_accounts la ON la.id = lp.account_id AND la.kind = 'escrow'
  JOIN public.orders o ON o.id = lt.order_id
  WHERE o.vendor_id = {vendor_sql}
    AND lt.order_id IS NOT NULL
  GROUP BY lt.order_id
) per_order;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise AppError(
            code="ledger_query_failed",
            message="Failed to derive escrow-held balance",
            http_status=500,
            details={"error": result.error},
        )
    return int(result.rows[0])


def vendor_paid_out_ngwee(vendor_id: str) -> int:
    """Ledger-derived lifetime paid-out total (PAYOUT_EXECUTED debits on vendor_payable)."""
    vendor_sql = _sql_uuid(vendor_id, "vendor_id")
    script = f"""
SELECT coalesce(sum(lp.amount_ngwee), 0)::text
FROM public.ledger_transactions lt
JOIN public.ledger_postings lp ON lp.transaction_id = lt.id
JOIN public.ledger_accounts la ON la.id = lp.account_id
WHERE la.kind = 'vendor_payable'
  AND la.vendor_id = {vendor_sql}
  AND lt.kind = 'payout_executed'
  AND lp.amount_ngwee > 0;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise AppError(
            code="ledger_query_failed",
            message="Failed to derive paid-out balance",
            http_status=500,
            details={"error": result.error},
        )
    return int(result.rows[0])


def compute_vendor_balances(
    service_client: _ServiceRoleClient,
    *,
    vendor_id: str,
    payout_msisdn: str | None,
    payout_rail: str | None,
    payout_hold_until: str | None,
) -> PayoutBalances:
    eligibility = compute_eligibility(service_client, vendor_id)
    hold_until = _parse_timestamp(payout_hold_until)
    payouts_blocked = hold_until is not None and hold_until > datetime.now(UTC)

    return PayoutBalances(
        escrow_held_ngwee=vendor_escrow_held_ngwee(vendor_id),
        released_available_ngwee=eligibility.available_ngwee,
        paid_out_ngwee=vendor_paid_out_ngwee(vendor_id),
        payouts_blocked=payouts_blocked,
        payout_hold_until=payout_hold_until,
        payout_msisdn=payout_msisdn,
        payout_rail=payout_rail,
    )


def _load_vendor_payout_fields(
    service_client: _ServiceRoleClient,
    vendor_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, payout_msisdn, payout_rail, payout_hold_until")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Vendor not found", http_status=404)
    return row


def _load_kyc_legal_name(service_client: _ServiceRoleClient, vendor_id: str) -> str:
    response = (
        service_client.client.table("kyc_records")
        .select("momo_name_match, status")
        .eq("vendor_id", vendor_id)
        .eq("status", "approved")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        raise AppError(
            code="kyc_not_approved",
            message="Approved KYC is required to change payout method",
            http_status=409,
            details={"message_key": "vendor.payouts.errors.kycRequired"},
        )
    momo = rows[0].get("momo_name_match")
    if not isinstance(momo, dict):
        raise AppError(
            code="kyc_incomplete",
            message="Approved KYC is missing momo_name_match",
            http_status=409,
        )
    legal_name = str(momo.get("legal_name", "")).strip()
    if not legal_name:
        raise AppError(
            code="kyc_incomplete",
            message="KYC legal name is required for payout method verification",
            http_status=409,
        )
    return legal_name


def _owner_phone(service_client: _ServiceRoleClient, owner_user_id: str) -> str | None:
    response = (
        service_client.client.table("profiles")
        .select("phone")
        .eq("id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None
    phone = row.get("phone")
    return phone if isinstance(phone, str) and phone.strip() else None


def _parse_month_bounds(month: str) -> tuple[datetime, datetime]:
    if not MONTH_PATTERN.fullmatch(month):
        raise AppError(
            code="invalid_month",
            message="month must be YYYY-MM",
            http_status=400,
        )
    year_str, month_str = month.split("-", 1)
    year = int(year_str)
    mon = int(month_str)
    if mon < 1 or mon > 12:
        raise AppError(
            code="invalid_month",
            message="month must be YYYY-MM",
            http_status=400,
        )
    start = datetime(year, mon, 1, tzinfo=UTC)
    if mon == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(year, mon + 1, 1, tzinfo=UTC)
    return start, end


def generate_vendor_statement_csv(
    *,
    vendor_id: str,
    month: str,
) -> str:
    """Ledger-derived monthly statement (ngwee-exact vendor_payable effects)."""
    start, end = _parse_month_bounds(month)
    vendor_sql = _sql_uuid(vendor_id, "vendor_id")
    start_sql = f"'{start.isoformat()}'::timestamptz"
    end_sql = f"'{end.isoformat()}'::timestamptz"
    script = f"""
SELECT
  lt.created_at::text,
  lt.kind,
  coalesce(lt.order_id::text, '') AS order_id,
  coalesce(lt.payout_id::text, '') AS payout_id,
  coalesce(sum(
    CASE
      WHEN la.kind = 'vendor_payable' AND la.vendor_id = {vendor_sql}
      THEN -lp.amount_ngwee
      ELSE 0
    END
  ), 0)::text AS vendor_effect_ngwee
FROM public.ledger_transactions lt
JOIN public.ledger_postings lp ON lp.transaction_id = lt.id
JOIN public.ledger_accounts la ON la.id = lp.account_id
WHERE lt.created_at >= {start_sql}
  AND lt.created_at < {end_sql}
  AND (
    (la.kind = 'vendor_payable' AND la.vendor_id = {vendor_sql})
    OR lt.order_id IN (SELECT id FROM public.orders WHERE vendor_id = {vendor_sql})
  )
GROUP BY lt.id, lt.created_at, lt.kind, lt.order_id, lt.payout_id
HAVING coalesce(sum(
  CASE
    WHEN la.kind = 'vendor_payable' AND la.vendor_id = {vendor_sql}
    THEN -lp.amount_ngwee
    ELSE 0
  END
), 0) <> 0
ORDER BY lt.created_at ASC;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise AppError(
            code="ledger_query_failed",
            message="Failed to generate payout statement",
            http_status=500,
            details={"error": result.error},
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "kind", "order_id", "payout_id", "amount_ngwee"])
    for row in result.rows or []:
        parts = row.split("|")
        if len(parts) < 5:
            continue
        writer.writerow(parts[:5])
    return buffer.getvalue()


def _notify_payout_method_changed(
    service_client: _ServiceRoleClient,
    *,
    vendor_id: str,
    owner_user_id: str,
    payout_msisdn: str,
    payout_rail: str,
    hold_until: datetime,
) -> None:
    enqueue_outbox_row(
        service_client.client,
        event_type="payout_method_changed",
        entity_id=vendor_id,
        channel="email",
        template="payout_method_changed",
        payload={
            "recipient_id": owner_user_id,
            "vendor_id": vendor_id,
            "payout_msisdn": payout_msisdn,
            "payout_rail": payout_rail,
            "payout_hold_until": hold_until.isoformat(),
        },
    )


@router.get("", response_model=PayoutBalances)
def get_vendor_payouts(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> PayoutBalances:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    _bump_vendor_scope_limit(
        request=request,
        service_client=service_client,
        scope="vendor_payouts_read",
        vendor_id=vendor_id,
        limit=VENDOR_READ_LIMIT_PER_MINUTE,
        window_seconds=60,
        message_key="vendor.payouts.errors.rateLimited",
    )
    fields = _load_vendor_payout_fields(service_client, vendor_id)
    payout_msisdn = fields.get("payout_msisdn")
    payout_rail = fields.get("payout_rail")
    return compute_vendor_balances(
        service_client,
        vendor_id=vendor_id,
        payout_msisdn=payout_msisdn if isinstance(payout_msisdn, str) else None,
        payout_rail=payout_rail if isinstance(payout_rail, str) else None,
        payout_hold_until=(
            str(fields["payout_hold_until"])
            if fields.get("payout_hold_until") is not None
            else None
        ),
    )


@router.get("/history", response_model=PayoutHistoryResponse)
def get_payout_history(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PayoutHistoryResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    _bump_vendor_scope_limit(
        request=request,
        service_client=service_client,
        scope="vendor_payouts_read",
        vendor_id=vendor_id,
        limit=VENDOR_READ_LIMIT_PER_MINUTE,
        window_seconds=60,
        message_key="vendor.payouts.errors.rateLimited",
    )
    response = (
        service_client.client.table("payouts")
        .select("id, amount_ngwee, rail, status, lenco_reference, created_at")
        .eq("vendor_id", vendor_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    items = [
        PayoutHistoryItem(
            id=str(row["id"]),
            amount_ngwee=int(row["amount_ngwee"]),
            rail=str(row["rail"]),
            status=str(row["status"]),
            lenco_reference=str(row["lenco_reference"]),
            created_at=str(row["created_at"]),
        )
        for row in _rows(response)
    ]
    return PayoutHistoryResponse(items=items)


@router.get("/statement")
def download_payout_statement(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    month: Annotated[str, Query(min_length=7, max_length=7, pattern=r"^\d{4}-\d{2}$")],
) -> Response:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    _bump_vendor_scope_limit(
        request=request,
        service_client=service_client,
        scope="vendor_payouts_read",
        vendor_id=vendor_id,
        limit=VENDOR_READ_LIMIT_PER_MINUTE,
        window_seconds=60,
        message_key="vendor.payouts.errors.rateLimited",
    )
    csv_body = generate_vendor_statement_csv(vendor_id=vendor_id, month=month)
    filename = f"payout-statement-{month}.csv"
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/method", response_model=PayoutMethodChangeResponse)
async def change_payout_method(
    request: Request,
    body: PayoutMethodChangeRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PayoutMethodChangeResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    owner_user_id = str(vendor["owner_user_id"])

    _bump_vendor_scope_limit(
        request=request,
        service_client=service_client,
        scope="vendor_payout_method_change",
        vendor_id=vendor_id,
        limit=METHOD_CHANGE_LIMIT_PER_DAY,
        window_seconds=86_400,
        message_key="vendor.payouts.errors.methodChangeLimit",
    )

    normalized_msisdn = _normalize_msisdn(body.payout_msisdn)
    if body.payout_rail not in PAYOUT_RAILS:
        raise AppError(
            code="invalid_rail",
            message="payout_rail must be mtn, airtel, or zamtel",
            http_status=400,
        )

    phone = _owner_phone(service_client, owner_user_id)
    verify_reauth_otp(phone=phone, otp=body.otp, settings=settings)

    legal_name = _load_kyc_legal_name(service_client, vendor_id)
    resolve_result = await resolve_and_score_momo_name(
        phone=normalized_msisdn,
        legal_name=legal_name,
        operator=body.payout_rail,
    )
    if not resolve_result.matched:
        raise AppError(
            code="payout_method_name_mismatch",
            message="MoMo account name does not match your verified legal name",
            http_status=409,
            details={
                "message_key": "vendor.payouts.errors.nameMismatch",
                "resolved_name": resolve_result.resolved_name,
                "legal_name": legal_name,
                "match_score": resolve_result.match_score,
            },
        )

    hold_until = datetime.now(UTC) + timedelta(hours=24)
    update_payload = {
        "payout_msisdn": normalized_msisdn,
        "payout_rail": body.payout_rail,
        "payout_hold_until": hold_until.isoformat(),
    }
    response = (
        service_client.client.table("vendors")
        .update(update_payload)
        .eq("id", vendor_id)
        .execute()
    )
    updated = _single_row(response)
    if updated is None and not _rows(response):
        raise AppError(
            code="payout_method_update_failed",
            message="Failed to update payout method",
            http_status=500,
        )

    _notify_payout_method_changed(
        service_client,
        vendor_id=vendor_id,
        owner_user_id=owner_user_id,
        payout_msisdn=normalized_msisdn,
        payout_rail=body.payout_rail,
        hold_until=hold_until,
    )

    return PayoutMethodChangeResponse(
        payout_msisdn=normalized_msisdn,
        payout_rail=body.payout_rail,
        payout_hold_until=hold_until.isoformat(),
        resolved_name=resolve_result.resolved_name,
        match_score=resolve_result.match_score,
        matched=resolve_result.matched,
    )


# Exported for tests — property: vendor_payable ledger balance matches released derivation.
def vendor_payable_ledger_balance_ngwee(vendor_id: str) -> int:
    account_id = resolve_account_id(AccountRef("vendor_payable", vendor_id))
    return account_balance_ngwee(account_id)


__all__ = [
    "compute_vendor_balances",
    "generate_vendor_statement_csv",
    "vendor_escrow_held_ngwee",
    "vendor_paid_out_ngwee",
    "vendor_payable_ledger_balance_ngwee",
]
