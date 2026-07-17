"""Verified-engagement service reviews — customer submit/edit and vendor replies.

An accepted RFQ quote creates a service order (order_item_services → job → quote).
RFQ jobs are category-based, not tied to a specific `services` listing, so a
review attributes to the PROVIDER VENDOR of the completed job. A review is
allowed once the service order is completed (job done AND vendor paid) and only
by the job's customer — mirroring the product verified-purchase pattern.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

router = APIRouter(prefix="/service-reviews", tags=["service-reviews"])

REVIEW_SELECT_COLUMNS = (
    "id, job_id, provider_vendor_id, customer_id, rating, body, vendor_reply, "
    "vendor_reply_at, status, created_at, updated_at"
)

REVIEW_EDIT_DAYS = 7
REPLY_EDIT_HOURS = 24
COMPLETED_ORDER_STATUS = "completed"


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class SubmitServiceReviewRequest(StrictModel):
    job_id: str
    rating: int = Field(ge=1, le=5)
    body: str | None = Field(default=None, max_length=4000)


class ServiceVendorReplyRequest(StrictModel):
    reply: str = Field(min_length=1, max_length=4000)


class ServiceReviewResponse(StrictModel):
    id: str
    job_id: str
    provider_vendor_id: str
    rating: int
    body: str | None
    vendor_reply: str | None
    vendor_reply_at: str | None
    status: str
    created_at: str
    updated_at: str
    editable_until: str | None = None
    reply_editable_until: str | None = None


class ServiceReviewsResponse(StrictModel):
    items: list[ServiceReviewResponse]
    rating_avg: float | None = None
    rating_count: int = 0


class ServiceReviewEligibility(StrictModel):
    job_id: str
    can_review: bool
    completed: bool
    review: ServiceReviewResponse | None = None


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


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _review_edit_deadline(created_at: object) -> datetime | None:
    created = _parse_ts(created_at)
    if created is None:
        return None
    return created + timedelta(days=REVIEW_EDIT_DAYS)


def _reply_edit_deadline(vendor_reply_at: object) -> datetime | None:
    replied = _parse_ts(vendor_reply_at)
    if replied is None:
        return None
    return replied + timedelta(hours=REPLY_EDIT_HOURS)


def _to_service_review_response(row: dict[str, Any]) -> ServiceReviewResponse:
    edit_deadline = _review_edit_deadline(row.get("created_at"))
    reply_deadline = _reply_edit_deadline(row.get("vendor_reply_at"))
    return ServiceReviewResponse(
        id=str(row["id"]),
        job_id=str(row["job_id"]),
        provider_vendor_id=str(row["provider_vendor_id"]),
        rating=int(row["rating"]),
        body=row.get("body"),
        vendor_reply=row.get("vendor_reply"),
        vendor_reply_at=row.get("vendor_reply_at"),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        editable_until=_iso(edit_deadline) if edit_deadline else None,
        reply_editable_until=_iso(reply_deadline) if reply_deadline else None,
    )


def _rate_limit(
    request: Request,
    user_id: str,
    service_client: _ServiceRoleClient,
    *,
    scope_suffix: str,
) -> None:
    ip = get_client_ip(request)
    allowed, retry_after = bump_rate_counter(
        scope=f"service_reviews_ip_{scope_suffix}",
        key=ip,
        window=timedelta(minutes=1),
        limit=30,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="services.reviews.errors.rateLimited",
            message="Too many review requests",
        )
    allowed_user, user_retry = bump_rate_counter(
        scope=f"service_reviews_user_{scope_suffix}",
        key=user_id,
        window=timedelta(minutes=1),
        limit=10,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=user_retry,
            message_key="services.reviews.errors.rateLimited",
            message="Too many review requests",
        )


def _load_job(client: _ServiceRoleClient, job_id: str) -> dict[str, Any] | None:
    response = (
        client.client.table("jobs")
        .select("id, customer_id, status")
        .eq("id", job_id)
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def _accepted_provider_vendor_id(client: _ServiceRoleClient, job_id: str) -> str | None:
    response = (
        client.client.table("job_quotes")
        .select("provider_vendor_id, status")
        .eq("job_id", job_id)
        .eq("status", "accepted")
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None
    provider = row.get("provider_vendor_id")
    return str(provider) if provider else None


def _service_order_completed(client: _ServiceRoleClient, job_id: str) -> bool:
    """True once the service order for this job is completed (done AND paid)."""
    links = (
        client.client.table("order_item_services")
        .select("order_item_id")
        .eq("job_id", job_id)
        .execute()
    )
    order_item_ids = [
        str(row["order_item_id"])
        for row in _rows(links)
        if row.get("order_item_id")
    ]
    if not order_item_ids:
        return False
    items = (
        client.client.table("order_items")
        .select("order_id")
        .in_("id", order_item_ids)
        .execute()
    )
    order_ids = [str(row["order_id"]) for row in _rows(items) if row.get("order_id")]
    if not order_ids:
        return False
    orders = (
        client.client.table("orders")
        .select("id, status")
        .in_("id", order_ids)
        .eq("status", COMPLETED_ORDER_STATUS)
        .execute()
    )
    return len(_rows(orders)) > 0


def _existing_review(
    client: _ServiceRoleClient, job_id: str
) -> dict[str, Any] | None:
    response = (
        client.client.table("service_reviews")
        .select(REVIEW_SELECT_COLUMNS)
        .eq("job_id", job_id)
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def _is_unique_violation(exc: Exception) -> bool:
    text = str(exc).lower()
    return "duplicate key" in text or "unique" in text or "23505" in text


@router.post("", response_model=ServiceReviewResponse)
async def submit_service_review(
    body: SubmitServiceReviewRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> ServiceReviewResponse:
    _rate_limit(request, current_user.id, service_client, scope_suffix="submit")

    job = _load_job(service_client, body.job_id)
    if job is None:
        raise AppError(code="not_found", message="Job not found", http_status=404)
    if str(job.get("customer_id")) != current_user.id:
        raise AppError(
            code="forbidden",
            message="Only the job customer may review this service",
            http_status=403,
            details={"job_id": body.job_id},
        )

    provider_vendor_id = _accepted_provider_vendor_id(service_client, body.job_id)
    if provider_vendor_id is None:
        raise AppError(
            code="conflict",
            message="This job has no accepted provider to review",
            http_status=409,
            details={"job_id": body.job_id},
        )
    if not _service_order_completed(service_client, body.job_id):
        raise AppError(
            code="forbidden",
            message="Reviews are only allowed after the job is completed",
            http_status=403,
            details={"job_id": body.job_id},
        )

    payload = {"rating": body.rating, "body": body.body, "status": "published"}
    existing = _existing_review(service_client, body.job_id)

    if existing is not None:
        deadline = _review_edit_deadline(existing.get("created_at"))
        if deadline is None or datetime.now(tz=UTC) > deadline:
            raise AppError(
                code="forbidden",
                message="Review edit window has expired",
                http_status=403,
                details={"job_id": body.job_id},
            )
        update_response = (
            service_client.client.table("service_reviews")
            .update(payload)
            .eq("id", existing["id"])
            .execute()
        )
        updated = _rows(update_response)
        if not updated:
            raise AppError(
                code="internal_error", message="Failed to update review", http_status=500
            )
        return _to_service_review_response(updated[0])

    insert_payload = {
        "job_id": body.job_id,
        "provider_vendor_id": provider_vendor_id,
        "customer_id": current_user.id,
        **payload,
    }
    try:
        insert_response = (
            service_client.client.table("service_reviews")
            .insert(insert_payload)
            .execute()
        )
    except Exception as exc:
        if _is_unique_violation(exc):
            raise AppError(
                code="conflict",
                message="A review already exists for this job",
                http_status=409,
                details={"job_id": body.job_id},
            ) from exc
        raise
    inserted = _rows(insert_response)
    if not inserted:
        raise AppError(
            code="internal_error", message="Failed to create review", http_status=500
        )
    return _to_service_review_response(inserted[0])


@router.get("", response_model=ServiceReviewsResponse)
async def list_service_reviews(
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    service_id: Annotated[str, Query(min_length=1, max_length=64)],
) -> ServiceReviewsResponse:
    service_response = (
        service_client.client.table("services")
        .select("id, vendor_id")
        .eq("id", service_id)
        .maybe_single()
        .execute()
    )
    service = _single_row(service_response)
    if service is None or not service.get("vendor_id"):
        return ServiceReviewsResponse(items=[], rating_avg=None, rating_count=0)

    reviews_response = (
        service_client.client.table("service_reviews")
        .select(REVIEW_SELECT_COLUMNS)
        .eq("provider_vendor_id", str(service["vendor_id"]))
        .eq("status", "published")
        .order("created_at", desc=True)
        .execute()
    )
    rows = _rows(reviews_response)
    items = [_to_service_review_response(row) for row in rows]
    count = len(items)
    rating_avg = round(sum(item.rating for item in items) / count, 2) if count else None
    return ServiceReviewsResponse(items=items, rating_avg=rating_avg, rating_count=count)


@router.get("/eligibility/{job_id}", response_model=ServiceReviewEligibility)
async def service_review_eligibility(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> ServiceReviewEligibility:
    job = _load_job(service_client, job_id)
    if job is None:
        raise AppError(code="not_found", message="Job not found", http_status=404)
    if str(job.get("customer_id")) != current_user.id:
        raise AppError(
            code="forbidden",
            message="Only the job customer may review this service",
            http_status=403,
            details={"job_id": job_id},
        )

    provider_vendor_id = _accepted_provider_vendor_id(service_client, job_id)
    completed = _service_order_completed(service_client, job_id)
    existing = _existing_review(service_client, job_id)

    review = _to_service_review_response(existing) if existing else None
    within_edit_window = False
    if existing is not None:
        deadline = _review_edit_deadline(existing.get("created_at"))
        within_edit_window = deadline is not None and datetime.now(tz=UTC) <= deadline

    can_review = (
        completed
        and provider_vendor_id is not None
        and (existing is None or within_edit_window)
    )
    return ServiceReviewEligibility(
        job_id=job_id,
        can_review=can_review,
        completed=completed,
        review=review,
    )


@router.post("/{review_id}/reply", response_model=ServiceReviewResponse)
async def submit_service_vendor_reply(
    review_id: str,
    body: ServiceVendorReplyRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> ServiceReviewResponse:
    _rate_limit(request, current_user.id, service_client, scope_suffix="reply")

    review_response = (
        service_client.client.table("service_reviews")
        .select(REVIEW_SELECT_COLUMNS)
        .eq("id", review_id)
        .maybe_single()
        .execute()
    )
    review = _single_row(review_response)
    if review is None:
        raise AppError(code="not_found", message="Review not found", http_status=404)

    vendor_response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id")
        .eq("id", str(review["provider_vendor_id"]))
        .maybe_single()
        .execute()
    )
    vendor = _single_row(vendor_response)
    if vendor is None or str(vendor.get("owner_user_id")) != current_user.id:
        raise AppError(
            code="forbidden",
            message="Only the reviewed provider may reply",
            http_status=403,
            details={"review_id": review_id},
        )

    existing_reply_at = review.get("vendor_reply_at")
    if existing_reply_at:
        deadline = _reply_edit_deadline(existing_reply_at)
        if deadline is None or datetime.now(tz=UTC) > deadline:
            raise AppError(
                code="forbidden",
                message="Reply edit window has expired",
                http_status=403,
                details={"review_id": review_id},
            )

    now_iso = _iso(datetime.now(tz=UTC))
    update_response = (
        service_client.client.table("service_reviews")
        .update({"vendor_reply": body.reply, "vendor_reply_at": now_iso})
        .eq("id", review_id)
        .execute()
    )
    updated = _rows(update_response)
    if not updated:
        raise AppError(
            code="internal_error", message="Failed to save reply", http_status=500
        )
    return _to_service_review_response(updated[0])
