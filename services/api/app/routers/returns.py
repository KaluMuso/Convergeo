"""Customer return submission and vendor accept/contest endpoints (M09-P07)."""

from __future__ import annotations

import importlib
import logging
from datetime import timedelta
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user, require_role
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.returns import lane1 as lane1_service
from fastapi import APIRouter, Depends, Request
from pydantic import Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/returns", tags=["returns"])

Lane = Literal[1, 2]
VendorResponse = Literal["accept", "contest"]


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class SubmitReturnRequest(StrictModel):
    order_item_id: str
    lane: Lane
    evidence_paths: list[str] = Field(default_factory=list, max_length=8)
    unused_declaration: bool | None = None


class SubmitReturnResponse(StrictModel):
    id: str
    order_item_id: str
    lane: Lane
    status: str
    fee_breakdown: dict[str, Any]


class ReturnPreviewResponse(StrictModel):
    lane: Lane
    order_item_id: str
    order_id: str
    within_window: bool
    fee_breakdown: dict[str, Any]
    lane2_eligible: bool = False
    lane2_reason: str | None = None


class VendorReturnQueueItem(StrictModel):
    id: str
    order_id: str
    order_item_id: str
    lane: int
    status: str
    fee_breakdown: dict[str, Any]
    evidence_count: int
    item_title: str
    item_qty: int
    created_at: str | None = None
    order_created_at: str | None = None


class VendorRespondRequest(StrictModel):
    action: VendorResponse


class VendorRespondResponse(StrictModel):
    id: str
    status: str
    dispute_id: str | None = None
    refund_id: str | None = None


def _rate_limit_returns(request: Request, user_id: str, service_client: _ServiceRoleClient) -> None:
    ip = get_client_ip(request)
    allowed, retry_after = bump_rate_counter(
        scope="returns_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=30,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="orders.return.errors.rateLimited",
            message="Too many return requests",
        )
    allowed_user, user_retry = bump_rate_counter(
        scope="returns_user",
        key=user_id,
        window=timedelta(minutes=1),
        limit=10,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=user_retry,
            message_key="orders.return.errors.rateLimited",
            message="Too many return requests",
        )


def _try_import_lane2() -> Any | None:
    try:
        return importlib.import_module("app.services.returns.lane2")
    except ModuleNotFoundError:
        return None


@router.get("/preview", response_model=ReturnPreviewResponse)
async def preview_return(
    order_item_id: str,
    lane: Lane,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> ReturnPreviewResponse:
    if lane == 1:
        preview = lane1_service.preview_lane1_breakdown(
            service_client,
            order_item_id=order_item_id,
            customer_id=current_user.id,
        )
        return ReturnPreviewResponse(
            lane=1,
            order_item_id=order_item_id,
            order_id=str(preview["order_id"]),
            within_window=bool(preview["within_window"]),
            fee_breakdown=preview["fee_breakdown"],
            lane2_eligible=False,
        )

    lane2 = _try_import_lane2()
    if lane2 is None:
        return ReturnPreviewResponse(
            lane=2,
            order_item_id=order_item_id,
            order_id="",
            within_window=False,
            fee_breakdown={},
            lane2_eligible=False,
            lane2_reason="lane2_unavailable",
        )

    check_eligibility = getattr(lane2, "check_eligibility", None)
    if not callable(check_eligibility):
        return ReturnPreviewResponse(
            lane=2,
            order_item_id=order_item_id,
            order_id="",
            within_window=False,
            fee_breakdown={},
            lane2_eligible=False,
            lane2_reason="lane2_unavailable",
        )

    try:
        result = check_eligibility(
            service_client,
            order_item_id=order_item_id,
            customer_id=current_user.id,
        )
    except AppError:
        return ReturnPreviewResponse(
            lane=2,
            order_item_id=order_item_id,
            order_id="",
            within_window=False,
            fee_breakdown={},
            lane2_eligible=False,
            lane2_reason="listing_not_returnable",
        )

    order_id = ""
    fee_breakdown: dict[str, Any] = {}
    load_order_item = getattr(lane2, "_load_order_item_context", None)
    if callable(load_order_item):
        try:
            order_item = load_order_item(service_client, order_item_id=order_item_id)
            order_id = str(order_item["order_id"])
            if result.eligible:
                compute_breakdown = getattr(lane2, "compute_lane2_breakdown", None)
                load_order = getattr(lane2, "_load_order", None)
                prorated_delivery = getattr(lane2, "_prorated_outbound_delivery", None)
                item_ngwee = getattr(lane2, "_item_ngwee", None)
                load_restocking = getattr(lane2, "load_restocking_pct", None)
                if all(
                    callable(fn)
                    for fn in (
                        compute_breakdown,
                        load_order,
                        prorated_delivery,
                        item_ngwee,
                        load_restocking,
                    )
                ):
                    order = load_order(service_client, order_id=order_id)
                    breakdown = compute_breakdown(
                        item_ngwee=item_ngwee(order_item),
                        outbound_delivery_ngwee=prorated_delivery(
                            service_client,
                            order_id=order_id,
                            order_item=order_item,
                            delivery_fee_ngwee=int(order.get("delivery_fee_ngwee", 0)),
                        ),
                        return_transport_ngwee=0,
                        restocking_pct=load_restocking(service_client),
                    )
                    fee_breakdown = breakdown.as_dict()
        except AppError:
            pass

    within_window = result.eligible or result.reason not in (
        "return_window_expired",
        "order_not_delivered",
    )
    return ReturnPreviewResponse(
        lane=2,
        order_item_id=order_item_id,
        order_id=order_id,
        within_window=within_window,
        fee_breakdown=fee_breakdown,
        lane2_eligible=result.eligible,
        lane2_reason=result.reason,
    )


@router.post("", response_model=SubmitReturnResponse)
async def submit_return(
    body: SubmitReturnRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> SubmitReturnResponse:
    _rate_limit_returns(request, current_user.id, service_client)

    if body.lane == 1:
        row = lane1_service.create_lane1_return(
            service_client,
            order_item_id=body.order_item_id,
            customer_id=current_user.id,
            evidence_paths=body.evidence_paths,
        )
        return SubmitReturnResponse(
            id=str(row["id"]),
            order_item_id=str(row["order_item_id"]),
            lane=1,
            status=str(row["status"]),
            fee_breakdown=row.get("fee_breakdown", {}),
        )

    lane2 = _try_import_lane2()
    if lane2 is None:
        raise AppError(
            code="not_implemented",
            message="Lane-2 returns are not available yet",
            http_status=501,
            details={"lane": 2, "todo": "M09-P08"},
        )

    create_lane2 = getattr(lane2, "create_lane2_return", None)
    if not callable(create_lane2):
        raise AppError(
            code="not_implemented",
            message="Lane-2 returns are not available yet",
            http_status=501,
            details={"lane": 2, "todo": "M09-P08"},
        )

    record = create_lane2(
        service_client,
        order_item_id=body.order_item_id,
        customer_id=current_user.id,
        unused_declared=bool(body.unused_declaration),
    )
    return SubmitReturnResponse(
        id=record.return_id,
        order_item_id=record.order_item_id,
        lane=2,
        status="requested",
        fee_breakdown=record.fee_breakdown,
    )


@router.get("/vendor", response_model=list[VendorReturnQueueItem])
async def list_vendor_returns(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> list[VendorReturnQueueItem]:
    rows = lane1_service.list_vendor_pending_returns(
        service_client,
        vendor_owner_id=current_user.id,
    )
    return [VendorReturnQueueItem(**row) for row in rows]


@router.post("/{return_id}/respond", response_model=VendorRespondResponse)
async def vendor_respond_to_return(
    return_id: str,
    body: VendorRespondRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorRespondResponse:
    _rate_limit_returns(request, current_user.id, service_client)

    if body.action == "accept":
        row = lane1_service.vendor_accept_lane1_return(
            service_client,
            return_id=return_id,
            vendor_owner_id=current_user.id,
        )
        refund_meta = row.get("_refund", {})
        refund_id = refund_meta.get("refund_id") if isinstance(refund_meta, dict) else None
        return VendorRespondResponse(
            id=str(row["id"]),
            status=str(row["status"]),
            refund_id=str(refund_id) if refund_id else None,
        )

    row = lane1_service.vendor_contest_lane1_return(
        service_client,
        return_id=return_id,
        vendor_owner_id=current_user.id,
    )
    return VendorRespondResponse(
        id=str(row["id"]),
        status=str(row["status"]),
        dispute_id=str(row.get("_dispute_id", "")) or None,
    )
