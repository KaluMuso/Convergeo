"""Customer confirm-received and report-problem endpoints (M09-P06)."""

from __future__ import annotations

import importlib
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.orders.state import (
    ActorRole,
    OrderEvent,
    OrderStatus,
    OrderTransitionError,
    transition_order,
)
from fastapi import APIRouter, Depends
from pydantic import Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["order-confirmation"])

ORDER_EVIDENCE_BUCKET = "order-evidence"
MAX_EVIDENCE_BYTES = 10_485_760  # 10 MiB — matches config.toml bucket limit.
REPORT_WINDOW_HOURS = 48

ProblemCategory = Literal["faulty", "wrong", "not_delivered", "other"]
ReportRoute = Literal["lane1", "dispute", "support", "guidance"]

LANE1_INTENT_TEMPLATE = "lane1-return-intent"
SUPPORT_REQUEST_TEMPLATE = "order-support-request"


class _StorageServiceClient(Protocol):
    @property
    def client(self) -> Any: ...


class ConfirmReceivedResponse(StrictModel):
    order_id: str
    status: Literal["completed"]
    already_confirmed: bool


class ReportProblemRequest(StrictModel):
    category: ProblemCategory
    description: str = Field(min_length=1, max_length=2000)
    evidence_paths: list[str] = Field(default_factory=list, max_length=8)


class ReportProblemResponse(StrictModel):
    order_id: str
    route: ReportRoute
    within_window: bool
    dispute_id: str | None = None
    guidance_key: str | None = None


class EvidenceSignRequest(StrictModel):
    file_size_bytes: int = Field(ge=1)
    content_type: Literal[
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    ]


class EvidenceSignResponse(StrictModel):
    bucket: str
    path: str
    token: str
    signed_url: str


def _evaluate_and_release(service_client: Any, order_id: str) -> None:
    """Fire escrow release (M08-P08). No-op if the engine is unmerged; failures are
    swallowed (the M08-P08 hourly release-job sweeper retries buyer-confirmed orders)."""
    try:
        release_module = importlib.import_module("app.services.escrow.release")
    except ModuleNotFoundError:
        return
    evaluate_and_release = getattr(release_module, "evaluate_and_release", None)
    if not callable(evaluate_and_release):
        return
    try:
        # M08-P08 signature: evaluate_and_release(service_client, order_id, *, now).
        evaluate_and_release(service_client, order_id)
    except Exception:
        logger.warning(
            "inline escrow release after confirm-received failed; sweeper will retry",
            extra={"order_id": order_id},
            exc_info=True,
        )


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _load_order_row(service_client: _StorageServiceClient, order_id: str) -> dict[str, Any] | None:
    response = (
        service_client.client.table("orders")
        .select("id, customer_id, status, fulfilment, checkout_group_id")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def _assert_customer_owns_order(
    order_row: dict[str, Any] | None,
    customer_id: str,
) -> dict[str, Any]:
    if order_row is None or str(order_row.get("customer_id")) != customer_id:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    return order_row


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _load_delivered_at(service_client: _StorageServiceClient, order_id: str) -> datetime | None:
    response = (
        service_client.client.table("order_events")
        .select("created_at, to_status")
        .eq("order_id", order_id)
        .eq("to_status", "delivered")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return None
    created_at = str(rows[0].get("created_at") or "")
    return _parse_timestamp(created_at)


def _within_report_window(delivered_at: datetime | None, *, now: datetime | None = None) -> bool:
    if delivered_at is None:
        return False
    reference = now or datetime.now(tz=UTC)
    return reference - delivered_at <= timedelta(hours=REPORT_WINDOW_HOURS)


def _extract_signed_upload(result: Any, *, path: str) -> tuple[str, str]:
    def _get(key_snake: str, key_camel: str) -> str | None:
        if isinstance(result, dict):
            value = result.get(key_snake, result.get(key_camel))
        else:
            value = getattr(result, key_snake, None) or getattr(result, key_camel, None)
        return value if isinstance(value, str) and value else None

    signed_url = _get("signed_url", "signedUrl")
    token = _get("token", "token")
    if not signed_url or not token:
        raise AppError(
            code="storage_error",
            message="Storage did not return a usable signed upload URL",
            http_status=502,
            details={"path": path},
        )
    return signed_url, token


def _content_extension(content_type: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "application/pdf": "pdf",
    }[content_type]


def _assert_evidence_path_owned(path: str, *, customer_id: str, order_id: str) -> None:
    expected_prefix = f"orders/{customer_id}/{order_id}/"
    normalized = path.replace("\\", "/").lstrip("/")
    if not normalized.startswith(expected_prefix) or ".." in normalized:
        raise AppError(
            code="validation_error",
            message="Evidence path must belong to this order",
            http_status=422,
            details={"path": path},
        )


def _record_lane1_intent(
    service_client: _StorageServiceClient,
    *,
    order_id: str,
    customer_id: str,
    category: ProblemCategory,
    description: str,
    evidence_paths: list[str],
) -> None:
    enqueue_outbox_row(
        service_client.client,
        event_type="lane1-return-intent",
        entity_id=order_id,
        channel="whatsapp",
        template=LANE1_INTENT_TEMPLATE,
        payload={
            "order_id": order_id,
            "customer_id": customer_id,
            "category": category,
            "description": description,
            "evidence_paths": evidence_paths,
        },
    )


def _record_support_request(
    service_client: _StorageServiceClient,
    *,
    order_id: str,
    customer_id: str,
    category: ProblemCategory,
    description: str,
    evidence_paths: list[str],
) -> None:
    enqueue_outbox_row(
        service_client.client,
        event_type="order-support-request",
        entity_id=order_id,
        channel="email",
        template=SUPPORT_REQUEST_TEMPLATE,
        payload={
            "order_id": order_id,
            "customer_id": customer_id,
            "category": category,
            "description": description,
            "evidence_paths": evidence_paths,
        },
    )


def _create_dispute(
    service_client: _StorageServiceClient,
    *,
    order_id: str,
    customer_id: str,
    evidence_paths: list[str],
) -> str:
    from app.services.disputes.service import open_dispute

    result = open_dispute(
        service_client,
        order_id=order_id,
        opener_user_id=customer_id,
        evidence_paths=evidence_paths,
        note="Customer reported order not delivered",
    )
    return result.dispute_id


@router.post("/{order_id}/confirm-received", response_model=ConfirmReceivedResponse)
async def confirm_received(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_StorageServiceClient, Depends(get_supabase_client)],
) -> ConfirmReceivedResponse:
    order_row = _assert_customer_owns_order(
        _load_order_row(service_client, order_id),
        current_user.id,
    )
    status = str(order_row["status"])

    if status == OrderStatus.COMPLETED.value:
        return ConfirmReceivedResponse(
            order_id=order_id,
            status="completed",
            already_confirmed=True,
        )

    if status != OrderStatus.DELIVERED.value:
        raise AppError(
            code="order_invalid_transition",
            message="Order cannot be confirmed from its current status",
            http_status=409,
            details={"status": status},
        )

    try:
        transition_order(
            order_id=order_id,
            event=OrderEvent.CONFIRM_RECEIVED,
            actor_role=ActorRole.CUSTOMER,
            actor_id=current_user.id,
            note="Customer confirmed receipt",
        )
    except OrderTransitionError:
        refreshed = _load_order_row(service_client, order_id)
        if refreshed and str(refreshed.get("status")) == OrderStatus.COMPLETED.value:
            return ConfirmReceivedResponse(
                order_id=order_id,
                status="completed",
                already_confirmed=True,
            )
        raise

    _evaluate_and_release(service_client, order_id)
    return ConfirmReceivedResponse(
        order_id=order_id,
        status="completed",
        already_confirmed=False,
    )


@router.post("/{order_id}/report-problem", response_model=ReportProblemResponse)
async def report_problem(
    order_id: str,
    body: ReportProblemRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_StorageServiceClient, Depends(get_supabase_client)],
) -> ReportProblemResponse:
    order_row = _assert_customer_owns_order(
        _load_order_row(service_client, order_id),
        current_user.id,
    )
    status = str(order_row["status"])
    reportable_statuses = {
        OrderStatus.SHIPPED.value,
        OrderStatus.DELIVERED.value,
        OrderStatus.COMPLETED.value,
    }
    if status not in reportable_statuses:
        raise AppError(
            code="validation_error",
            message="Problems can only be reported after the order has shipped",
            http_status=409,
            details={"status": status},
        )

    for path in body.evidence_paths:
        _assert_evidence_path_owned(path, customer_id=current_user.id, order_id=order_id)

    delivered_at = _load_delivered_at(service_client, order_id)
    within_window = _within_report_window(delivered_at)

    if body.category == "not_delivered":
        dispute_id = _create_dispute(
            service_client,
            order_id=order_id,
            customer_id=current_user.id,
            evidence_paths=body.evidence_paths,
        )
        return ReportProblemResponse(
            order_id=order_id,
            route="dispute",
            within_window=within_window,
            dispute_id=dispute_id,
        )

    if body.category == "other":
        _record_support_request(
            service_client,
            order_id=order_id,
            customer_id=current_user.id,
            category=body.category,
            description=body.description,
            evidence_paths=body.evidence_paths,
        )
        return ReportProblemResponse(
            order_id=order_id,
            route="support",
            within_window=within_window,
        )

    # faulty / wrong — lane-1 only inside the 48h post-delivery window.
    if within_window:
        _record_lane1_intent(
            service_client,
            order_id=order_id,
            customer_id=current_user.id,
            category=body.category,
            description=body.description,
            evidence_paths=body.evidence_paths,
        )
        return ReportProblemResponse(
            order_id=order_id,
            route="lane1",
            within_window=True,
            guidance_key="report.guidance.lane1",
        )

    return ReportProblemResponse(
        order_id=order_id,
        route="guidance",
        within_window=False,
        guidance_key="report.guidance.expired",
    )


@router.post("/{order_id}/evidence/sign", response_model=EvidenceSignResponse)
async def sign_order_evidence_upload(
    order_id: str,
    body: EvidenceSignRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_StorageServiceClient, Depends(get_supabase_client)],
) -> EvidenceSignResponse:
    _assert_customer_owns_order(_load_order_row(service_client, order_id), current_user.id)

    if body.file_size_bytes > MAX_EVIDENCE_BYTES:
        raise AppError(
            code="file_too_large",
            message="Evidence file exceeds the maximum allowed upload size",
            http_status=400,
            details={"file_size_bytes": body.file_size_bytes, "max_bytes": MAX_EVIDENCE_BYTES},
        )

    extension = _content_extension(body.content_type)
    path = f"orders/{current_user.id}/{order_id}/evidence-{int(time.time())}.{extension}"

    try:
        result = (
            service_client.client.storage.from_(ORDER_EVIDENCE_BUCKET).create_signed_upload_url(path)
        )
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            code="storage_error",
            message="Could not create a signed upload URL",
            http_status=502,
            details={"path": path},
        ) from exc

    signed_url, token = _extract_signed_upload(result, path=path)
    return EvidenceSignResponse(
        bucket=ORDER_EVIDENCE_BUCKET,
        path=path,
        token=token,
        signed_url=signed_url,
    )
