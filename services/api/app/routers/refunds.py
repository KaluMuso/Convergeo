from __future__ import annotations

from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from app.services.refunds.execute import RefundExecutionResult, execute_refund
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

Lane = Literal[1, 2]
CustomerRail = Literal["mtn", "airtel", "zamtel"]


class ServiceRoleClient(Protocol):
    client: Any


refunds_router = APIRouter(prefix="/refunds", tags=["admin-refunds"])


class ExecuteRefundRequest(BaseModel):
    order_id: UUID
    lane: Lane
    return_transport_ngwee: int = Field(default=0, ge=0)
    customer_rail: CustomerRail = "mtn"
    customer_momo: str = Field(min_length=8, max_length=20)
    dispute_id: UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def lane2_requires_return_transport_field(self) -> ExecuteRefundRequest:
        if self.lane == 2 and self.return_transport_ngwee < 0:
            raise ValueError("return_transport_ngwee must be non-negative")
        return self


class ExecuteRefundResponse(BaseModel):
    refund_id: UUID
    order_id: UUID
    lane: Lane
    phase: str
    amount_ngwee: int
    payout_id: UUID | None = None
    lenco_reference: str
    ledger_transaction_ids: list[str]
    breakdown: dict[str, Any]
    created: bool


def _to_response(result: RefundExecutionResult) -> ExecuteRefundResponse:
    payout_id: UUID | None = None
    if result.payout_id:
        payout_id = UUID(result.payout_id)
    return ExecuteRefundResponse(
        refund_id=UUID(result.refund_id),
        order_id=UUID(result.order_id),
        lane=result.lane,
        phase=result.phase.value,
        amount_ngwee=result.amount_ngwee,
        payout_id=payout_id,
        lenco_reference=result.lenco_reference,
        ledger_transaction_ids=list(result.ledger_transaction_ids),
        breakdown=result.breakdown,
        created=result.created,
    )


@refunds_router.post("/execute", response_model=ExecuteRefundResponse)
async def admin_execute_refund(
    body: ExecuteRefundRequest,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> ExecuteRefundResponse:
    """Admin/dispute-triggered refund execution."""
    try:
        result = execute_refund(
            service_client=service_client,
            order_id=str(body.order_id),
            lane=body.lane,
            return_transport_ngwee=body.return_transport_ngwee,
            customer_rail=body.customer_rail,
            customer_momo=body.customer_momo,
            dispute_id=str(body.dispute_id) if body.dispute_id else None,
            idempotency_key=body.idempotency_key,
        )
    except AppError:
        raise
    except ValueError as exc:
        raise AppError("refund_invalid", str(exc), 422) from exc

    recorder.record(
        action="admin.refunds.execute",
        entity_type="refund",
        entity_id=UUID(result.refund_id),
        before=None,
        after={
            "order_id": result.order_id,
            "lane": result.lane,
            "phase": result.phase.value,
            "amount_ngwee": result.amount_ngwee,
            "created": result.created,
        },
    )
    return _to_response(result)


admin_router.include_router(refunds_router)

router = refunds_router
