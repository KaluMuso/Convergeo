"""Internal batch jobs for RFQ expiry (M11-P02)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.notifications.dedupe import enqueue_outbox_row
from fastapi import APIRouter, Depends, Request
from pydantic import Field

router = APIRouter(prefix="/internal/jobs", tags=["internal-job-jobs"])

_INTERNAL_TOKEN_ENV = "INTERNAL_JOB_JOBS_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-job-jobs"
DEFAULT_BATCH_LIMIT = 50
MAX_BATCH_LIMIT = 200
DEFAULT_EXPIRY_DAYS = 7
RFQ_EXPIRED_EVENT = "rfq_job_expired"
EXPIRY_NOTE = "Auto-closed after 7 days with no accepted quote"


class BatchJobRequest(StrictModel):
    limit: int = Field(default=DEFAULT_BATCH_LIMIT, ge=1, le=MAX_BATCH_LIMIT)
    cursor: str | None = None


class ExpireTickResponse(StrictModel):
    scanned: int
    expired: int
    skipped: int
    next_cursor: str | None = None


def _expected_internal_token() -> str:
    try:
        return resolve_internal_token(
            _INTERNAL_TOKEN_ENV,
            dev_default=_DEFAULT_INTERNAL_TOKEN,
        )
    except InternalTokenMisconfigured as exc:
        raise AppError(
            code="configuration_error",
            message=str(exc),
            http_status=503,
        ) from exc


async def require_internal_job_jobs_token(request: Request) -> None:
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal job jobs token",
            http_status=401,
        )


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


def _list_stale_open_jobs(
    client: Any,
    *,
    limit: int,
    cursor: str | None,
    now: datetime,
) -> list[dict[str, Any]]:
    deadline = now - timedelta(days=DEFAULT_EXPIRY_DAYS)
    query = (
        client.table("jobs")
        .select("id, customer_id, category, description, status, created_at")
        .eq("status", "open")
        .lte("created_at", deadline.isoformat())
        .order("id")
        .limit(limit)
    )
    if cursor:
        query = query.gt("id", cursor)
    response = query.execute()
    return _rows(response)


def _already_expired(client: Any, job_id: str) -> bool:
    response = (
        client.table("audit_log")
        .select("id")
        .eq("entity_type", "job")
        .eq("entity_id", job_id)
        .eq("action", "job.expired")
        .limit(1)
        .execute()
    )
    return bool(_rows(response))


def _expire_job(client: Any, job: dict[str, Any], *, now: datetime) -> bool:
    job_id = str(job["id"])
    if _already_expired(client, job_id):
        return False

    update_response = (
        client.table("jobs")
        .update({"status": "cancelled"})
        .eq("id", job_id)
        .eq("status", "open")
        .execute()
    )
    updated = _single_row(update_response)
    if updated is None:
        return False

    resolve_snapshot = {
        "expired": True,
        "reason": EXPIRY_NOTE,
        "expired_at": now.isoformat(),
        "original_status": "open",
        "mapped_status": "cancelled",
    }
    client.table("audit_log").insert(
        {
            "actor": None,
            "action": "job.expired",
            "entity_type": "job",
            "entity_id": job_id,
            "before": {"status": "open"},
            "after": {
                "status": "cancelled",
                "resolve_snapshot": resolve_snapshot,
                "note": EXPIRY_NOTE,
            },
        }
    ).execute()

    customer_id = str(job.get("customer_id", ""))
    if customer_id:
        enqueue_outbox_row(
            client,
            event_type=RFQ_EXPIRED_EVENT,
            entity_id=job_id,
            channel="whatsapp",
            template=None,
            payload={
                "job_id": job_id,
                "category": str(job.get("category", "")),
                "recipient_user_id": customer_id,
                "note": EXPIRY_NOTE,
            },
        )
    return True


def _next_cursor(jobs: list[dict[str, Any]], limit: int) -> str | None:
    if len(jobs) < limit:
        return None
    if not jobs:
        return None
    return str(jobs[-1]["id"])


@router.post(
    "/expire-tick",
    response_model=ExpireTickResponse,
    dependencies=[Depends(require_internal_job_jobs_token)],
)
async def expire_tick_batch(
    service_client: Annotated[Any, Depends(get_supabase_client)],
    body: BatchJobRequest | None = None,
) -> ExpireTickResponse:
    request = body or BatchJobRequest()
    now = datetime.now(UTC)
    candidates = _list_stale_open_jobs(
        service_client.client,
        limit=request.limit,
        cursor=request.cursor,
        now=now,
    )

    expired = 0
    skipped = 0
    for job in candidates:
        if _expire_job(service_client.client, job, now=now):
            expired += 1
        else:
            skipped += 1

    return ExpireTickResponse(
        scanned=len(candidates),
        expired=expired,
        skipped=skipped,
        next_cursor=_next_cursor(candidates, request.limit),
    )
