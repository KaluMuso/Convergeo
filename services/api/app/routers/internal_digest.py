"""Internal founder daily-digest data endpoint (M13-P11).

Internal-token guarded, read-only aggregates for the n8n `admin-digest` workflow.
Numbers reuse the admin-dashboard truth (GMV, orders-by-status, reconciliation)
and add payouts-due, KYC queue depth, and flags-pending for the founder morning
view. No money mutations; no new ledger logic.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, cast

from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_dashboards import (
    OrdersByStatusOut,
    ReconciliationTileOut,
    ServiceRoleClient,
    _latest_reconciliation,
    _orders_by_status,
    compute_gmv_ngwee,
)
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

router = APIRouter(prefix="/internal/digest", tags=["internal-digest"])

_INTERNAL_TOKEN_ENV = "INTERNAL_DIGEST_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-digest"

PENDING_PAYOUT_STATUS = "pending"
PENDING_KYC_STATUS = "pending"
OPEN_FLAG_STATUS = "open"


class PayoutsDueOut(BaseModel):
    count: int
    amount_ngwee: int


class OrdersDigestOut(BaseModel):
    total: int
    by_status: OrdersByStatusOut


class DigestOut(BaseModel):
    generated_at: datetime
    gmv_ngwee: int
    orders: OrdersDigestOut
    payouts_due: PayoutsDueOut
    reconciliation: ReconciliationTileOut
    kyc_queue_depth: int
    flags_pending: int


def _expected_internal_token() -> str:
    return os.environ.get(_INTERNAL_TOKEN_ENV, _DEFAULT_INTERNAL_TOKEN)


async def require_internal_digest_token(request: Request) -> None:
    """Guard the digest tick — not publicly callable without the shared internal token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal digest token",
            http_status=401,
        )


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _count_with_status(service_client: ServiceRoleClient, table: str, status: str) -> int:
    response = (
        service_client.client.table(table)
        .select("id", count="exact")
        .eq("status", status)
        .limit(0)
        .execute()
    )
    count = getattr(response, "count", None)
    if isinstance(count, int):
        return count
    return len(_rows(response))


def _payouts_due(service_client: ServiceRoleClient) -> PayoutsDueOut:
    response = (
        service_client.client.table("payouts")
        .select("amount_ngwee, status")
        .eq("status", PENDING_PAYOUT_STATUS)
        .execute()
    )
    rows = _rows(response)
    amount = sum(int(row.get("amount_ngwee", 0)) for row in rows)
    return PayoutsDueOut(count=len(rows), amount_ngwee=amount)


def _orders_digest(service_client: ServiceRoleClient) -> OrdersDigestOut:
    by_status = _orders_by_status(service_client)
    total = sum(int(getattr(by_status, field)) for field in OrdersByStatusOut.model_fields)
    return OrdersDigestOut(total=total, by_status=by_status)


def build_digest(service_client: ServiceRoleClient) -> DigestOut:
    return DigestOut(
        generated_at=datetime.now(UTC),
        gmv_ngwee=compute_gmv_ngwee(),
        orders=_orders_digest(service_client),
        payouts_due=_payouts_due(service_client),
        reconciliation=_latest_reconciliation(service_client),
        kyc_queue_depth=_count_with_status(service_client, "kyc_records", PENDING_KYC_STATUS),
        flags_pending=_count_with_status(service_client, "flags", OPEN_FLAG_STATUS),
    )


@router.post(
    "",
    response_model=DigestOut,
    dependencies=[Depends(require_internal_digest_token)],
)
async def get_daily_digest() -> DigestOut:
    service = next(get_supabase_client())
    return build_digest(service)
