"""Durable event cancellation refund orchestration (EVT-CANCELLATION-REFUND-JOBS).

Organiser cancellation enqueues one row per paid ticket order in
``event_refund_jobs``. An internal sweeper executes ``execute_refund`` asynchronously
with provider-authoritative completion (Prompt F) instead of blocking the cancel HTTP
request or requiring manual admin execution per order.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol, cast

from app.errors import AppError
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.refunds.execute import RefundExecutionResult, execute_refund
from app.services.refunds.execute import ServiceRoleClient as RefundServiceClient
from app.services.refunds.payout_port import CustomerRail
from app.services.stock.claim import sql_int, sql_uuid

SOURCE_ORGANISER_CANCEL = "organiser_cancel"
SOURCE_BUYER_CANCEL = "buyer_cancel"
SOURCE_RESCHEDULE_OPT_OUT = "reschedule_opt_out"
SOURCE_KEY_V1 = "v1"
RefundSource = Literal["organiser_cancel", "buyer_cancel", "reschedule_opt_out"]
MAX_JOB_ATTEMPTS = 5
RETRY_BACKOFF_BASE_SECONDS = 120

WORK_STATUSES = frozenset({"queued", "processing", "awaiting_payout"})
TERMINAL_JOB_STATUSES = frozenset({"completed", "dead"})


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class EventRefundJobSweepResult:
    scanned: int
    executed: int
    awaiting_payout: int
    needs_destination: int
    manual_review: int
    completed: int
    retried: int
    dead: int
    skipped: int


@dataclass(frozen=True, slots=True)
class EventRefundJobProcessResult:
    job_id: str
    outcome: Literal[
        "executed",
        "awaiting_payout",
        "completed",
        "needs_destination",
        "manual_review",
        "retried",
        "dead",
        "skipped",
    ]
    reason: str = ""


def compute_job_retry_backoff_seconds(
    attempt: int,
    *,
    base_seconds: int = RETRY_BACKOFF_BASE_SECONDS,
) -> int:
    if attempt < 1:
        return base_seconds
    return int(base_seconds * (2 ** (attempt - 1)))


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _policy_snapshot(
    *,
    event_id: str,
    order_id: str,
    source: str = SOURCE_ORGANISER_CANCEL,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "reason": source,
        "lane": 1,
        "event_id": event_id,
        "order_id": order_id,
        "refund_policy": "full_ticket_refund" if source != SOURCE_BUYER_CANCEL else source,
    }
    if extra:
        snapshot.update(extra)
    return snapshot


def order_ticket_refund_amount_ngwee(order_id: str) -> int:
    order_sql = sql_uuid(order_id, "order_id")
    script = f"""
SELECT (
  coalesce(
    (
      SELECT sum(oi.qty * oi.unit_price_ngwee)::bigint
      FROM public.order_items oi
      WHERE oi.order_id = {order_sql}
        AND oi.item_kind = 'ticket'
    ),
    0
  )
  + coalesce(
    (
      SELECT o.delivery_fee_ngwee::bigint
      FROM public.orders o
      WHERE o.id = {order_sql}
    ),
    0
  )
  + coalesce(
    (
      SELECT o.platform_fee_ngwee::bigint
      FROM public.orders o
      WHERE o.id = {order_sql}
    ),
    0
  )
)::text;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise RuntimeError(f"ticket refund amount query failed: {result.error}")
    return int(result.rows[0])


def enqueue_event_refund_job(
    *,
    event_id: str,
    order_id: str,
    customer_id: str,
    amount_ngwee: int,
    source: RefundSource,
    source_key: str = SOURCE_KEY_V1,
    extra_policy: dict[str, Any] | None = None,
) -> bool:
    """Idempotently queue a refund job for one paid ticket order."""
    if amount_ngwee <= 0:
        return False

    event_sql = sql_uuid(event_id, "event_id")
    order_sql = sql_uuid(order_id, "order_id")
    customer_sql = sql_uuid(customer_id, "customer_id")
    amount_sql = sql_int(amount_ngwee, "amount_ngwee")
    source_sql = sql_literal(source)
    source_key_sql = sql_literal(source_key)
    policy_json = json.dumps(
        _policy_snapshot(
            event_id=event_id, order_id=order_id, source=source, extra=extra_policy
        )
    )
    policy_sql = sql_literal(policy_json) + "::jsonb"

    script = f"""
INSERT INTO public.event_refund_jobs (
  event_id, order_id, customer_id, source, source_key, policy_snapshot, amount_ngwee, status
)
VALUES (
  {event_sql}, {order_sql}, {customer_sql}, {source_sql}, {source_key_sql},
  {policy_sql}, {amount_sql}, 'queued'
)
ON CONFLICT (event_id, order_id, source, source_key) DO NOTHING
RETURNING id::text;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"enqueue event refund job failed: {result.error}")
    return bool(result.rows)


def enqueue_organiser_cancel_refund_job(
    *,
    event_id: str,
    order_id: str,
    customer_id: str,
    amount_ngwee: int,
) -> bool:
    """Idempotently queue a cancellation refund job for one paid ticket order."""
    return enqueue_event_refund_job(
        event_id=event_id,
        order_id=order_id,
        customer_id=customer_id,
        amount_ngwee=amount_ngwee,
        source=SOURCE_ORGANISER_CANCEL,
    )


def load_customer_refund_destination(
    service_client: ServiceRoleClient,
    *,
    order_id: str,
    customer_id: str,
) -> tuple[str, CustomerRail] | None:
    """Resolve MoMo destination from profile phone + successful payment rail."""
    profile = (
        service_client.client.table("profiles")
        .select("phone")
        .eq("id", customer_id)
        .maybe_single()
        .execute()
    )
    profile_row = getattr(profile, "data", None)
    phone = profile_row.get("phone") if isinstance(profile_row, dict) else None
    if not isinstance(phone, str) or len(phone.strip()) < 8:
        return None

    order = (
        service_client.client.table("orders")
        .select("checkout_group_id")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    order_row = getattr(order, "data", None)
    group_id = order_row.get("checkout_group_id") if isinstance(order_row, dict) else None
    if not isinstance(group_id, str) or not group_id:
        return None

    payment = (
        service_client.client.table("payments")
        .select("rail")
        .eq("checkout_group_id", group_id)
        .eq("status", "success")
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    payment_row = getattr(payment, "data", None)
    rail_raw = payment_row.get("rail") if isinstance(payment_row, dict) else None
    rail = cast(CustomerRail, rail_raw if rail_raw in {"mtn", "airtel", "zamtel"} else "mtn")
    return phone.strip(), rail


def sync_event_refund_job_for_refund(
    service_client: ServiceRoleClient,
    *,
    refund_id: str,
) -> bool:
    """Advance linked jobs when provider-authoritative refund status changes."""
    refund_sql = sql_uuid(refund_id, "refund_id")
    script = f"""
SELECT id::text, status
FROM public.event_refund_jobs
WHERE refund_id = {refund_sql}
LIMIT 1;
"""
    loaded = run_sql_script(script)
    if not loaded.ok or not loaded.rows:
        return False

    job_id, _job_status = loaded.rows[0].split("|", 1)
    refund_status = run_sql_script(
        f"SELECT status FROM public.refunds WHERE id = {refund_sql} LIMIT 1;"
    )
    if not refund_status.ok or not refund_status.rows:
        return False

    status = refund_status.rows[0].strip()
    if status == "completed":
        job_sql = sql_uuid(job_id, "job_id")
        run_sql_script(
            f"""
UPDATE public.event_refund_jobs
SET status = 'completed',
    locked_at = NULL,
    last_error = NULL,
    updated_at = timezone('utc', now())
WHERE id = {job_sql}
  AND status IN ('awaiting_payout', 'processing', 'queued');
"""
        )
        return True
    if status == "failed":
        job_sql = sql_uuid(job_id, "job_id")
        run_sql_script(
            f"""
UPDATE public.event_refund_jobs
SET status = 'manual_review',
    locked_at = NULL,
    last_error = 'refund_provider_failed',
    updated_at = timezone('utc', now())
WHERE id = {job_sql}
  AND status IN ('awaiting_payout', 'processing', 'queued');
"""
        )
        return True
    return False


def _load_job(job_id: str) -> dict[str, str] | None:
    job_sql = sql_uuid(job_id, "job_id")
    script = f"""
SELECT
  id::text,
  event_id::text,
  order_id::text,
  customer_id::text,
  source,
  source_key,
  amount_ngwee::text,
  status,
  coalesce(refund_id::text, ''),
  coalesce(payout_id::text, ''),
  attempts::text,
  coalesce(next_retry_at::text, ''),
  coalesce(last_error, '')
FROM public.event_refund_jobs
WHERE id = {job_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None
    parts = result.rows[0].split("|", 12)
    if len(parts) != 13:
        return None
    return {
        "id": parts[0],
        "event_id": parts[1],
        "order_id": parts[2],
        "customer_id": parts[3],
        "source": parts[4],
        "source_key": parts[5],
        "amount_ngwee": parts[6],
        "status": parts[7],
        "refund_id": parts[8],
        "payout_id": parts[9],
        "attempts": parts[10],
        "next_retry_at": parts[11],
        "last_error": parts[12],
    }


def _claim_job(job_id: str, *, now: datetime) -> bool:
    job_sql = sql_uuid(job_id, "job_id")
    now_sql = sql_literal(now.isoformat())
    script = f"""
UPDATE public.event_refund_jobs
SET status = 'processing',
    attempts = attempts + 1,
    locked_at = {now_sql}::timestamptz,
    updated_at = timezone('utc', now())
WHERE id = {job_sql}
  AND status = 'queued'
  AND (next_retry_at IS NULL OR next_retry_at <= {now_sql}::timestamptz)
RETURNING id::text;
"""
    result = run_sql_script(script)
    return bool(result.ok and result.rows)


def _update_job(
    job_id: str,
    *,
    status: str,
    refund_id: str | None = None,
    payout_id: str | None = None,
    last_error: str | None = None,
    next_retry_at: datetime | None = None,
) -> None:
    job_sql = sql_uuid(job_id, "job_id")
    sets = [
        f"status = {sql_literal(status)}",
        "locked_at = NULL",
        "updated_at = timezone('utc', now())",
    ]
    if refund_id:
        sets.append(f"refund_id = {sql_uuid(refund_id, 'refund_id')}")
    if payout_id:
        sets.append(f"payout_id = {sql_uuid(payout_id, 'payout_id')}")
    if last_error is not None:
        sets.append(f"last_error = {sql_literal(last_error)}")
    else:
        sets.append("last_error = NULL")
    if next_retry_at is None:
        sets.append("next_retry_at = NULL")
    else:
        sets.append(f"next_retry_at = {sql_literal(next_retry_at.isoformat())}::timestamptz")
    script = f"UPDATE public.event_refund_jobs SET {', '.join(sets)} WHERE id = {job_sql};"
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"update event refund job failed: {result.error}")


def _sync_awaiting_job(
    service_client: ServiceRoleClient,
    job: dict[str, str],
) -> EventRefundJobProcessResult:
    refund_id = job.get("refund_id", "").strip()
    if not refund_id:
        _update_job(job["id"], status="manual_review", last_error="missing_refund_id")
        return EventRefundJobProcessResult(job["id"], "manual_review", "missing_refund_id")

    sync_event_refund_job_for_refund(service_client, refund_id=refund_id)
    refreshed = _load_job(job["id"])
    if refreshed is None:
        return EventRefundJobProcessResult(job["id"], "skipped", "job_missing")
    status = refreshed["status"]
    if status == "completed":
        return EventRefundJobProcessResult(job["id"], "completed", "provider_paid")
    if status == "manual_review":
        return EventRefundJobProcessResult(job["id"], "manual_review", "provider_failed")
    return EventRefundJobProcessResult(job["id"], "awaiting_payout", "still_in_flight")


def process_event_refund_job(
    service_client: ServiceRoleClient,
    job_id: str,
    *,
    now: datetime | None = None,
) -> EventRefundJobProcessResult:
    """Execute or advance one cancellation refund job."""
    effective_now = now or datetime.now(UTC)
    job = _load_job(job_id)
    if job is None:
        return EventRefundJobProcessResult(job_id, "skipped", "not_found")

    status = job["status"]
    if status in TERMINAL_JOB_STATUSES:
        return EventRefundJobProcessResult(job_id, "skipped", status)
    if status == "needs_destination":
        return EventRefundJobProcessResult(job_id, "skipped", status)
    if status == "manual_review":
        return EventRefundJobProcessResult(job_id, "skipped", status)

    if status == "awaiting_payout":
        return _sync_awaiting_job(service_client, job)

    next_retry = _parse_timestamp(job.get("next_retry_at"))
    if next_retry is not None and effective_now < next_retry:
        return EventRefundJobProcessResult(job_id, "skipped", "backoff")

    if status == "queued":
        if not _claim_job(job_id, now=effective_now):
            return EventRefundJobProcessResult(job_id, "skipped", "claim_failed")
        job = _load_job(job_id) or job

    destination = load_customer_refund_destination(
        service_client,
        order_id=job["order_id"],
        customer_id=job["customer_id"],
    )
    if destination is None:
        _update_job(job_id, status="needs_destination", last_error="missing_customer_momo")
        return EventRefundJobProcessResult(job_id, "needs_destination", "missing_customer_momo")

    phone, rail = destination
    idempotency_key = f"evt-refund-{job['event_id']}-{job['order_id']}"

    try:
        result: RefundExecutionResult = execute_refund(
            service_client=cast(RefundServiceClient, service_client),
            order_id=job["order_id"],
            lane=1,
            customer_rail=rail,
            customer_momo=phone,
            idempotency_key=idempotency_key,
        )
    except AppError as exc:
        code = str(exc.code or "refund_failed")
        if code in {"partial_release_refund_blocked", "cod_not_collected"}:
            _update_job(job_id, status="manual_review", last_error=code)
            return EventRefundJobProcessResult(job_id, "manual_review", code)
        if code == "release_in_progress":
            attempts = int(job.get("attempts") or "0")
            if attempts >= MAX_JOB_ATTEMPTS:
                _update_job(job_id, status="dead", last_error=code)
                return EventRefundJobProcessResult(job_id, "dead", code)
            backoff = compute_job_retry_backoff_seconds(attempts)
            retry_at = effective_now + timedelta(seconds=backoff)
            _update_job(
                job_id,
                status="queued",
                last_error=code,
                next_retry_at=retry_at,
            )
            return EventRefundJobProcessResult(job_id, "retried", code)
        _update_job(job_id, status="manual_review", last_error=code)
        return EventRefundJobProcessResult(job_id, "manual_review", code)
    except Exception as exc:
        attempts = int(job.get("attempts") or "0")
        if attempts >= MAX_JOB_ATTEMPTS:
            _update_job(job_id, status="dead", last_error=str(exc))
            return EventRefundJobProcessResult(job_id, "dead", str(exc))
        backoff = compute_job_retry_backoff_seconds(attempts)
        retry_at = effective_now + timedelta(seconds=backoff)
        _update_job(job_id, status="queued", last_error=str(exc), next_retry_at=retry_at)
        return EventRefundJobProcessResult(job_id, "retried", str(exc))

    refund_id_sql = sql_uuid(result.refund_id, "refund_id")
    refund_status = run_sql_script(
        f"SELECT status FROM public.refunds WHERE id = {refund_id_sql} LIMIT 1;"
    )
    if refund_status.ok and refund_status.rows:
        provider_status = refund_status.rows[0].strip()
    else:
        provider_status = "awaiting_payout"
    if provider_status == "completed":
        _update_job(
            job_id,
            status="completed",
            refund_id=result.refund_id,
            payout_id=result.payout_id or None,
        )
        return EventRefundJobProcessResult(job_id, "completed", "refund_completed")

    _update_job(
        job_id,
        status="awaiting_payout",
        refund_id=result.refund_id,
        payout_id=result.payout_id or None,
    )
    return EventRefundJobProcessResult(job_id, "awaiting_payout", "payout_queued")


def _list_candidate_job_ids(*, limit: int, now: datetime) -> list[str]:
    now_sql = sql_literal(now.isoformat())
    script = f"""
SELECT id::text
FROM public.event_refund_jobs
WHERE status IN ('queued', 'awaiting_payout')
  AND (next_retry_at IS NULL OR next_retry_at <= {now_sql}::timestamptz)
ORDER BY created_at ASC
LIMIT {int(limit)};
"""
    result = run_sql_script(script)
    if not result.ok:
        return []
    return result.rows


def sweep_event_refund_jobs(
    service_client: ServiceRoleClient,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> EventRefundJobSweepResult:
    """Batch-process queued / in-flight cancellation refund jobs."""
    effective_now = now or datetime.now(UTC)
    job_ids = _list_candidate_job_ids(limit=limit, now=effective_now)

    executed = 0
    awaiting = 0
    needs_destination = 0
    manual_review = 0
    completed = 0
    retried = 0
    dead = 0
    skipped = 0

    for job_id in job_ids:
        outcome = process_event_refund_job(service_client, job_id, now=effective_now)
        if outcome.outcome == "executed":
            executed += 1
        elif outcome.outcome == "awaiting_payout":
            awaiting += 1
        elif outcome.outcome == "needs_destination":
            needs_destination += 1
        elif outcome.outcome == "manual_review":
            manual_review += 1
        elif outcome.outcome == "completed":
            completed += 1
        elif outcome.outcome == "retried":
            retried += 1
        elif outcome.outcome == "dead":
            dead += 1
        else:
            skipped += 1

    return EventRefundJobSweepResult(
        scanned=len(job_ids),
        executed=executed,
        awaiting_payout=awaiting,
        needs_destination=needs_destination,
        manual_review=manual_review,
        completed=completed,
        retried=retried,
        dead=dead,
        skipped=skipped,
    )
