"""RFQ job endpoints — post, read, and lifecycle transitions (M11-P02)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.rfq.broadcast import broadcast_job
from fastapi import APIRouter, Depends, Request
from pydantic import Field

router = APIRouter(prefix="/jobs", tags=["jobs"])

JOB_STATUSES = frozenset({"open", "quoted", "accepted", "completed", "cancelled"})
SERVICE_CATEGORIES = frozenset(
    {
        "beauty",
        "food_catering",
        "auto",
        "printing_creative",
        "home_services",
        "tech_services",
        "cleaning",
        "tailoring",
    }
)
CANCELABLE_STATUSES = frozenset({"open", "quoted"})
BUDGET_BANDS: dict[str, tuple[int | None, int | None]] = {
    "under_500": (None, 50_000),
    "500_2000": (50_000, 200_000),
    "2000_5000": (200_000, 500_000),
    "over_5000": (500_000, None),
    "flexible": (None, None),
}


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class CreateJobRequest(StrictModel):
    category: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=10, max_length=4000)
    service_area: str = Field(min_length=1, max_length=120)
    preferred_date: date | None = None
    budget_band: Literal["under_500", "500_2000", "2000_5000", "over_5000", "flexible"]
    photo_paths: list[str] = Field(default_factory=list, max_length=8)


class JobBroadcastSummary(StrictModel):
    matched_count: int
    notified_count: int
    capped: bool
    no_match: bool
    admin_flagged: bool
    message_key: str


class JobResponse(StrictModel):
    id: str
    customer_id: str
    category: str
    description: str
    preferred_date: str | None
    budget_band_min_ngwee: int | None
    budget_band_max_ngwee: int | None
    status: str
    created_at: str
    updated_at: str
    broadcast: JobBroadcastSummary | None = None


class CreateJobResponse(StrictModel):
    job: JobResponse


class CancelJobResponse(StrictModel):
    job: JobResponse


class JobListResponse(StrictModel):
    items: list[JobResponse]


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


def _rate_limit_jobs(request: Request, user_id: str, service_client: _ServiceRoleClient) -> None:
    ip = get_client_ip(request)
    allowed_ip, retry_ip = bump_rate_counter(
        scope="jobs_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=30,
        client=service_client.client,
    )
    if not allowed_ip:
        raise_rate_limited(
            retry_after=retry_ip,
            message_key="services.postJob.errors.rateLimited",
            message="Too many job requests",
        )
    allowed_user, retry_user = bump_rate_counter(
        scope="jobs_user",
        key=user_id,
        window=timedelta(minutes=1),
        limit=10,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=retry_user,
            message_key="services.postJob.errors.rateLimited",
            message="Too many job requests",
        )


def _budget_bounds(band: str) -> tuple[int | None, int | None]:
    return BUDGET_BANDS[band]


def _validate_category(category: str) -> None:
    if category not in SERVICE_CATEGORIES:
        raise AppError(
            code="validation_error",
            message="Unsupported service category",
            http_status=400,
            details={"category": category, "allowed": sorted(SERVICE_CATEGORIES)},
        )


def _validate_preferred_date(preferred_date: date | None) -> None:
    if preferred_date is None:
        return
    if preferred_date < date.today():
        raise AppError(
            code="validation_error",
            message="Preferred date must be today or in the future",
            http_status=400,
        )


def _write_job_audit(
    client: Any,
    *,
    actor_id: str,
    action: str,
    job_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> None:
    client.table("audit_log").insert(
        {
            "actor": actor_id,
            "action": action,
            "entity_type": "job",
            "entity_id": job_id,
            "before": before,
            "after": after,
        }
    ).execute()


def _serialize_job(
    row: dict[str, Any],
    *,
    broadcast: JobBroadcastSummary | None = None,
) -> JobResponse:
    return JobResponse(
        id=str(row["id"]),
        customer_id=str(row["customer_id"]),
        category=str(row["category"]),
        description=str(row["description"]),
        preferred_date=str(row["preferred_date"]) if row.get("preferred_date") else None,
        budget_band_min_ngwee=row.get("budget_band_min_ngwee"),
        budget_band_max_ngwee=row.get("budget_band_max_ngwee"),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        broadcast=broadcast,
    )


def _load_job(client: Any, job_id: str) -> dict[str, Any]:
    response = client.table("jobs").select("*").eq("id", job_id).maybe_single().execute()
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Job not found", http_status=404)
    return row


def _assert_owner(job: dict[str, Any], user_id: str) -> None:
    if str(job.get("customer_id")) != user_id:
        raise AppError(
            code="forbidden",
            message="You may only view your own jobs before quotes are shared",
            http_status=403,
        )


def _broadcast_summary(result: Any) -> JobBroadcastSummary:
    message_key = (
        "services.postJob.ack.noMatch"
        if result.no_match
        else "services.postJob.ack.sent"
    )
    return JobBroadcastSummary(
        matched_count=result.matched_count,
        notified_count=result.notified_count,
        capped=result.capped,
        no_match=result.no_match,
        admin_flagged=result.admin_flagged,
        message_key=message_key,
    )


@router.post("", response_model=CreateJobResponse)
async def create_job(
    body: CreateJobRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CreateJobResponse:
    _rate_limit_jobs(request, current_user.id, service_client)
    _validate_category(body.category)
    _validate_preferred_date(body.preferred_date)
    min_ngwee, max_ngwee = _budget_bounds(body.budget_band)

    insert_row = {
        "customer_id": current_user.id,
        "category": body.category,
        "description": body.description.strip(),
        "preferred_date": body.preferred_date.isoformat() if body.preferred_date else None,
        "budget_band_min_ngwee": min_ngwee,
        "budget_band_max_ngwee": max_ngwee,
        "status": "open",
    }
    response = service_client.client.table("jobs").insert(insert_row).execute()
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="internal_error",
            message="Failed to create job",
            http_status=500,
        )

    job_id = str(row["id"])
    _write_job_audit(
        service_client.client,
        actor_id=current_user.id,
        action="job.created",
        job_id=job_id,
        before=None,
        after={
            "status": "open",
            "category": body.category,
            "service_area": body.service_area,
            "budget_band": body.budget_band,
            "photo_paths": body.photo_paths,
        },
    )

    broadcast_result = broadcast_job(
        service_client,
        job_id=job_id,
        customer_id=current_user.id,
        category=body.category,
        service_area=body.service_area,
        description=body.description.strip(),
    )
    summary = _broadcast_summary(broadcast_result)
    return CreateJobResponse(job=_serialize_job(row, broadcast=summary))


@router.get("", response_model=JobListResponse)
async def list_jobs(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> JobListResponse:
    response = (
        service_client.client.table("jobs")
        .select("*")
        .eq("customer_id", current_user.id)
        .order("created_at", desc=True)
        .execute()
    )
    items = [_serialize_job(row) for row in _rows(response)]
    return JobListResponse(items=items)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> JobResponse:
    job = _load_job(service_client.client, job_id)
    _assert_owner(job, current_user.id)
    return _serialize_job(job)


@router.post("/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_job(
    job_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CancelJobResponse:
    _rate_limit_jobs(request, current_user.id, service_client)
    job = _load_job(service_client.client, job_id)
    _assert_owner(job, current_user.id)
    status = str(job.get("status", ""))
    if status not in CANCELABLE_STATUSES:
        raise AppError(
            code="invalid_transition",
            message="Job cannot be cancelled in its current state",
            http_status=409,
            details={"status": status},
        )

    before = {"status": status}
    update_response = (
        service_client.client.table("jobs")
        .update({"status": "cancelled"})
        .eq("id", job_id)
        .eq("status", status)
        .execute()
    )
    updated = _single_row(update_response)
    if updated is None:
        job = _load_job(service_client.client, job_id)
        if str(job.get("status")) == "cancelled":
            return CancelJobResponse(job=_serialize_job(job))
        raise AppError(
            code="conflict",
            message="Job status changed before cancellation",
            http_status=409,
        )

    _write_job_audit(
        service_client.client,
        actor_id=current_user.id,
        action="job.cancelled",
        job_id=job_id,
        before=before,
        after={"status": "cancelled", "resolve_snapshot": {"cancelled_by": "customer"}},
    )
    return CancelJobResponse(job=_serialize_job(updated))
