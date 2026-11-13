"""Admin: organiser advance debts — list (status / organiser filters) and cash repayments.

Admin/superadmin only (deliberately absent from the delegated admin permission map).
A repayment posts ``organiser_receivable_repaid`` through
``advance_policy.record_organiser_repayment`` (balanced ledger entry, FIFO allocation
across the organiser's open debts, ``event_advance.receivable_repaid`` audit row) and
the admin audit recorder logs the request. A debt fully repaid becomes ``settled``, so
the overdue sweep never suspends or blacklists the organiser for it.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.routers.admin_base import router
from app.schemas.base import StrictModel
from app.services.events.advance_policy import (
    AdvanceDebtRow,
    list_advance_debts,
    organiser_receivable_balance_ngwee,
    record_organiser_repayment,
)
from fastapi import Depends, Query
from pydantic import Field

DebtStatus = Literal["open", "settled", "written_off"]

# Largest single repayment accepted: K10,000,000 (integer ngwee).
MAX_REPAYMENT_NGWEE = 1_000_000_000


class AdvanceDebtOut(StrictModel):
    id: UUID
    vendor_id: UUID
    vendor_name: str
    event_id: UUID
    event_title: str
    order_id: UUID
    amount_ngwee: int
    recovered_ngwee: int
    outstanding_ngwee: int
    status: str
    due_at: str
    suspended_at: str | None
    blacklisted_at: str | None
    legal_followup_at: str | None
    created_at: str


class AdvanceDebtListOut(StrictModel):
    items: list[AdvanceDebtOut]


class RepaymentIn(StrictModel):
    # JSON carries UUIDs as strings; still parsed and rejected unless a valid UUID.
    vendor_id: UUID = Field(strict=False)
    amount_ngwee: int = Field(gt=0, le=MAX_REPAYMENT_NGWEE)
    # Finance's receipt / bank / MoMo reference; part of the ledger idempotency key.
    reference: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._\-]+$")


class RepaymentOut(StrictModel):
    vendor_id: UUID
    transaction_id: str
    amount_ngwee: int
    receivable_ngwee: int
    debts: list[AdvanceDebtOut]


def _debt_out(row: AdvanceDebtRow) -> AdvanceDebtOut:
    return AdvanceDebtOut(
        id=UUID(row.id),
        vendor_id=UUID(row.vendor_id),
        vendor_name=row.vendor_name,
        event_id=UUID(row.event_id),
        event_title=row.event_title,
        order_id=UUID(row.order_id),
        amount_ngwee=row.amount_ngwee,
        recovered_ngwee=row.recovered_ngwee,
        outstanding_ngwee=row.outstanding_ngwee,
        status=row.status,
        due_at=row.due_at,
        suspended_at=row.suspended_at,
        blacklisted_at=row.blacklisted_at,
        legal_followup_at=row.legal_followup_at,
        created_at=row.created_at,
    )


@router.get("/event-advance-debts", response_model=AdvanceDebtListOut)
def get_event_advance_debts(
    current_user: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    status: Annotated[DebtStatus | None, Query()] = None,
    vendor_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> AdvanceDebtListOut:
    del current_user
    rows = list_advance_debts(
        status=status, vendor_id=str(vendor_id) if vendor_id else None, limit=limit
    )
    return AdvanceDebtListOut(items=[_debt_out(row) for row in rows])


@router.post("/event-advance-debts/repayments", response_model=RepaymentOut)
def post_event_advance_repayment(
    body: RepaymentIn,
    current_user: Annotated[CurrentUser, Depends(require_role("admin", "superadmin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> RepaymentOut:
    vendor_id = str(body.vendor_id)
    before = organiser_receivable_balance_ngwee(vendor_id)
    transaction_id = record_organiser_repayment(
        vendor_id=vendor_id,
        amount_ngwee=body.amount_ngwee,
        actor_user_id=current_user.id,
        reference=body.reference,
    )
    after = organiser_receivable_balance_ngwee(vendor_id)
    recorder.record(
        action="admin.event_advance.repayment_recorded",
        entity_type="vendor",
        entity_id=vendor_id,
        before={"receivable_ngwee": before},
        after={
            "receivable_ngwee": after,
            "amount_ngwee": body.amount_ngwee,
            "reference": body.reference,
            "transaction_id": transaction_id,
        },
    )
    debts = list_advance_debts(vendor_id=vendor_id, limit=200)
    return RepaymentOut(
        vendor_id=body.vendor_id,
        transaction_id=transaction_id,
        amount_ngwee=body.amount_ngwee,
        receivable_ngwee=max(0, after),
        debts=[_debt_out(row) for row in debts],
    )
