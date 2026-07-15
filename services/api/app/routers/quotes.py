"""RFQ quote lifecycle — submit, withdraw, compare (M11-P03)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.products import _aggregate_vendor_ratings
from app.routers.services_listings import ResponseTimeTier, _fetch_response_tiers
from app.routers.vendor_orders import _load_vendor_for_owner
from app.schemas.base import NgweeInt, StrictModel
from app.services.moderation.contact_strip import strip_contacts
from app.services.notifications.dedupe import build_dedupe_key
from app.services.rfq.broadcast import RFQ_MATCH_EVENT, match_providers
from fastapi import APIRouter, Depends, Request
from pydantic import Field

router = APIRouter(tags=["quotes"])

QUOTE_STATUSES = frozenset({"submitted", "accepted", "declined", "expired"})
COMPARE_VISIBLE_STATUSES = frozenset({"submitted", "accepted"})
JOB_QUOTABLE_STATUSES = frozenset({"open", "quoted"})

# Contact-stripping moderation (M11-P06). Applied ONLY on the pre-acceptance
# quote-submit message path (job status in JOB_QUOTABLE_STATUSES); once a quote
# is accepted the job leaves that set and messages flow untouched.
CONTACT_STRIP_ACTION = "quote.contact_stripped"
CONTACT_EVASION_FLAG_REASON = "rfq_contact_evasion"
CONTACT_EVASION_FLAG_THRESHOLD = 3
# System actor for moderation audit rows (audit_log.actor is nullable, no FK).
MODERATION_ACTOR_ID = "00000000-0000-0000-0000-000000000001"


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class SubmitQuoteRequest(StrictModel):
    amount_ngwee: NgweeInt = Field(gt=0)
    message: str | None = Field(default=None, max_length=4000)
    validity_days: int = Field(default=7, ge=1, le=30)


class DeclineQuoteRequest(StrictModel):
    reason: str | None = Field(default=None, max_length=2000)


class QuoteProviderSummary(StrictModel):
    vendor_id: str
    slug: str
    display_name: str
    preferred_badge: bool = False
    rating_avg: float | None = None
    rating_count: int = 0
    response_time_tier: ResponseTimeTier | None = None


class QuoteItem(StrictModel):
    id: str
    job_id: str
    provider_vendor_id: str
    amount_ngwee: int
    message: str | None
    status: str
    expires_at: str | None
    created_at: str
    provider: QuoteProviderSummary | None = None


class JobQuotesResponse(StrictModel):
    job_id: str
    view: Literal["provider_own", "customer_compare"]
    items: list[QuoteItem]


class SubmitQuoteResponse(StrictModel):
    quote: QuoteItem


class QuoteActionResponse(StrictModel):
    quote: QuoteItem


class MatchedJobItem(StrictModel):
    id: str
    category: str
    description: str
    preferred_date: str | None
    budget_band_min_ngwee: int | None
    budget_band_max_ngwee: int | None
    status: str
    created_at: str
    own_quote: QuoteItem | None = None


class MatchedJobsResponse(StrictModel):
    items: list[MatchedJobItem]


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
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _rate_limit_quotes(request: Request, user_id: str, service_client: _ServiceRoleClient) -> None:
    ip = get_client_ip(request)
    allowed_ip, retry_ip = bump_rate_counter(
        scope="quotes_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=40,
        client=service_client.client,
    )
    if not allowed_ip:
        raise_rate_limited(
            retry_after=retry_ip,
            message_key="services.quotes.errors.rateLimited",
            message="Too many quote requests",
        )
    allowed_user, retry_user = bump_rate_counter(
        scope="quotes_user",
        key=user_id,
        window=timedelta(minutes=1),
        limit=15,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=retry_user,
            message_key="services.quotes.errors.rateLimited",
            message="Too many quote requests",
        )


def _load_job(client: Any, job_id: str) -> dict[str, Any]:
    response = client.table("jobs").select("*").eq("id", job_id).maybe_single().execute()
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Job not found", http_status=404)
    return row


def _load_job_service_area(client: Any, job_id: str) -> str:
    response = (
        client.table("audit_log")
        .select("after")
        .eq("entity_type", "job")
        .eq("entity_id", job_id)
        .eq("action", "job.created")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    for row in rows:
        after = row.get("after")
        if isinstance(after, dict):
            area = after.get("service_area")
            if isinstance(area, str) and area.strip():
                return area.strip()
    return ""


def _provider_notified_for_job(client: Any, *, job_id: str, vendor_id: str) -> bool:
    # notification_outbox has no event_type/entity_id columns — enqueue_outbox_row
    # folds them into dedupe_key ({event}:{entity}:{channel}). RFQ broadcasts always
    # enqueue on the whatsapp channel, so match that row's dedupe_key exactly.
    entity_id = f"{job_id}:{vendor_id}"
    dedupe_key = build_dedupe_key(RFQ_MATCH_EVENT, entity_id, "whatsapp")
    response = (
        client.table("notification_outbox")
        .select("id")
        .eq("dedupe_key", dedupe_key)
        .limit(1)
        .execute()
    )
    return bool(_rows(response))


def _is_provider_matched_to_job(
    service_client: _ServiceRoleClient,
    *,
    job_id: str,
    vendor_id: str,
    category: str,
    service_area: str,
) -> bool:
    client = service_client.client
    if _provider_notified_for_job(client, job_id=job_id, vendor_id=vendor_id):
        return True
    matches = match_providers(
        service_client,
        category=category,
        service_area=service_area,
        cap=None,
    )
    return any(match.vendor_id == vendor_id for match in matches)


def _assert_provider_matched(
    service_client: _ServiceRoleClient,
    *,
    job: dict[str, Any],
    vendor_id: str,
) -> None:
    job_id = str(job["id"])
    service_area = _load_job_service_area(service_client.client, job_id)
    if not _is_provider_matched_to_job(
        service_client,
        job_id=job_id,
        vendor_id=vendor_id,
        category=str(job.get("category", "")),
        service_area=service_area,
    ):
        raise AppError(
            code="forbidden",
            message="Provider was not matched to this job",
            http_status=403,
            details={"message_key": "services.quotes.errors.notMatched"},
        )


def _serialize_quote_row(row: dict[str, Any]) -> QuoteItem:
    return QuoteItem(
        id=str(row["id"]),
        job_id=str(row["job_id"]),
        provider_vendor_id=str(row["provider_vendor_id"]),
        amount_ngwee=int(row["amount_ngwee"]),
        message=row.get("message"),
        status=str(row["status"]),
        expires_at=str(row["expires_at"]) if row.get("expires_at") else None,
        created_at=str(row["created_at"]),
        provider=None,
    )


def _load_quote(client: Any, quote_id: str) -> dict[str, Any]:
    response = client.table("job_quotes").select("*").eq("id", quote_id).maybe_single().execute()
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Quote not found", http_status=404)
    return row


def _expire_stale_quotes(client: Any, *, job_id: str) -> None:
    now = datetime.now(tz=UTC)
    response = (
        client.table("job_quotes")
        .select("id, expires_at, status")
        .eq("job_id", job_id)
        .eq("status", "submitted")
        .execute()
    )
    for row in _rows(response):
        expires_at = _parse_timestamp(
            str(row["expires_at"]) if row.get("expires_at") else None
        )
        if expires_at is not None and expires_at <= now:
            client.table("job_quotes").update({"status": "expired"}).eq(
                "id", str(row["id"])
            ).eq("status", "submitted").execute()


def _quote_is_compare_visible(row: dict[str, Any], *, now: datetime | None = None) -> bool:
    status = str(row.get("status", ""))
    if status not in COMPARE_VISIBLE_STATUSES:
        return False
    expires_at = _parse_timestamp(str(row["expires_at"]) if row.get("expires_at") else None)
    instant = now or datetime.now(tz=UTC)
    if expires_at is not None and expires_at <= instant:
        return False
    return True


def _enrich_quotes_for_compare(
    client: Any,
    quote_rows: list[dict[str, Any]],
) -> list[QuoteItem]:
    vendor_ids = sorted(
        {str(row["provider_vendor_id"]) for row in quote_rows if row.get("provider_vendor_id")}
    )
    if not vendor_ids:
        return []

    vendors_response = (
        client.table("vendors")
        .select("id, slug, display_name, preferred_badge")
        .in_("id", vendor_ids)
        .execute()
    )
    vendors_by_id = {str(row["id"]): row for row in _rows(vendors_response)}
    ratings = _aggregate_vendor_ratings(client, vendor_ids)
    response_tiers = _fetch_response_tiers(client, vendor_ids)

    items: list[QuoteItem] = []
    for row in quote_rows:
        vendor_id = str(row["provider_vendor_id"])
        vendor = vendors_by_id.get(vendor_id, {})
        rating_avg, rating_count = ratings.get(vendor_id, (None, 0))
        provider = QuoteProviderSummary(
            vendor_id=vendor_id,
            slug=str(vendor.get("slug", "")),
            display_name=str(vendor.get("display_name", "")),
            preferred_badge=bool(vendor.get("preferred_badge")),
            rating_avg=rating_avg,
            rating_count=rating_count,
            response_time_tier=response_tiers.get(vendor_id),
        )
        item = _serialize_quote_row(row)
        item = item.model_copy(update={"provider": provider})
        items.append(item)

    items.sort(
        key=lambda item: (
            item.amount_ngwee,
            -(item.provider.rating_avg or 0.0) if item.provider else 0.0,
            item.created_at,
        )
    )
    return items


def _filter_provider_own_quotes(
    quote_rows: list[dict[str, Any]],
    *,
    vendor_id: str,
) -> list[dict[str, Any]]:
    """API-layer rival isolation: providers see only their own quote rows."""
    own_rows = [row for row in quote_rows if str(row.get("provider_vendor_id")) == vendor_id]
    if len(own_rows) != len(quote_rows):
        # Defensive: service-role reads all rows; strip rivals before responding.
        pass
    return own_rows


def _maybe_mark_job_quoted(client: Any, job_id: str) -> None:
    client.table("jobs").update({"status": "quoted"}).eq("id", job_id).eq(
        "status", "open"
    ).execute()


def _count_contact_evasions(client: Any, vendor_id: str) -> int:
    response = (
        client.table("audit_log")
        .select("id")
        .eq("action", CONTACT_STRIP_ACTION)
        .eq("entity_type", "vendor")
        .eq("entity_id", vendor_id)
        .execute()
    )
    return len(_rows(response))


def _maybe_flag_contact_evasion(client: Any, *, vendor_id: str, reporter_user_id: str) -> None:
    """Flag the provider once logged evasions reach the threshold (idempotent)."""
    if _count_contact_evasions(client, vendor_id) < CONTACT_EVASION_FLAG_THRESHOLD:
        return
    existing = (
        client.table("flags")
        .select("id")
        .eq("entity_type", "vendor")
        .eq("entity_id", vendor_id)
        .eq("reason", CONTACT_EVASION_FLAG_REASON)
        .eq("status", "open")
        .limit(1)
        .execute()
    )
    if _rows(existing):
        return
    client.table("flags").insert(
        {
            "entity_type": "vendor",
            "entity_id": vendor_id,
            "reason": CONTACT_EVASION_FLAG_REASON,
            "reporter_user_id": reporter_user_id,
            "status": "open",
        }
    ).execute()


def _record_contact_evasion(
    client: Any,
    *,
    vendor_id: str,
    job_id: str,
    reporter_user_id: str,
    stripped_spans: list[str],
    hit_count: int,
) -> None:
    """Log stripped originals server-side (never shown to counterparty) then flag."""
    client.table("audit_log").insert(
        {
            "actor": MODERATION_ACTOR_ID,
            "action": CONTACT_STRIP_ACTION,
            "entity_type": "vendor",
            "entity_id": vendor_id,
            "before": None,
            "after": {
                "job_id": job_id,
                "hit_count": hit_count,
                "stripped": stripped_spans,
            },
        }
    ).execute()
    _maybe_flag_contact_evasion(client, vendor_id=vendor_id, reporter_user_id=reporter_user_id)


def _clean_pre_acceptance_message(
    client: Any,
    *,
    message: str | None,
    vendor_id: str,
    job_id: str,
    reporter_user_id: str,
) -> str | None:
    """Strip contact info from a pre-acceptance quote message; log + flag evasion."""
    if not message:
        return None
    result = strip_contacts(message)
    if result.hit_count > 0:
        _record_contact_evasion(
            client,
            vendor_id=vendor_id,
            job_id=job_id,
            reporter_user_id=reporter_user_id,
            stripped_spans=result.stripped_spans,
            hit_count=result.hit_count,
        )
    return result.clean_text.strip() or None


@router.get("/provider/jobs", response_model=MatchedJobsResponse)
async def list_matched_jobs(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> MatchedJobsResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    client = service_client.client

    jobs_response = (
        client.table("jobs")
        .select("*")
        .in_("status", sorted(JOB_QUOTABLE_STATUSES))
        .order("created_at", desc=True)
        .execute()
    )

    quotes_response = (
        client.table("job_quotes")
        .select("*")
        .eq("provider_vendor_id", vendor_id)
        .execute()
    )
    own_quotes_by_job = {
        str(row["job_id"]): _serialize_quote_row(row) for row in _rows(quotes_response)
    }

    items: list[MatchedJobItem] = []
    for job in _rows(jobs_response):
        job_id = str(job["id"])
        service_area = _load_job_service_area(client, job_id)
        if not _is_provider_matched_to_job(
            service_client,
            job_id=job_id,
            vendor_id=vendor_id,
            category=str(job.get("category", "")),
            service_area=service_area,
        ):
            continue
        items.append(
            MatchedJobItem(
                id=job_id,
                category=str(job.get("category", "")),
                description=str(job.get("description", "")),
                preferred_date=str(job["preferred_date"]) if job.get("preferred_date") else None,
                budget_band_min_ngwee=job.get("budget_band_min_ngwee"),
                budget_band_max_ngwee=job.get("budget_band_max_ngwee"),
                status=str(job.get("status", "")),
                created_at=str(job.get("created_at", "")),
                own_quote=own_quotes_by_job.get(job_id),
            )
        )
    return MatchedJobsResponse(items=items)


@router.post("/jobs/{job_id}/quotes", response_model=SubmitQuoteResponse)
async def submit_quote(
    job_id: str,
    body: SubmitQuoteRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> SubmitQuoteResponse:
    _rate_limit_quotes(request, current_user.id, service_client)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    if str(vendor.get("status", "")) != "active":
        raise AppError(
            code="forbidden",
            message="Vendor must be active to submit quotes",
            http_status=403,
        )

    job = _load_job(service_client.client, job_id)
    status = str(job.get("status", ""))
    if status not in JOB_QUOTABLE_STATUSES:
        raise AppError(
            code="invalid_transition",
            message="Job is not accepting quotes",
            http_status=409,
            details={"status": status},
        )

    vendor_id = str(vendor["id"])
    _assert_provider_matched(service_client, job=job, vendor_id=vendor_id)

    existing = (
        service_client.client.table("job_quotes")
        .select("id, status")
        .eq("job_id", job_id)
        .eq("provider_vendor_id", vendor_id)
        .maybe_single()
        .execute()
    )
    existing_row = _single_row(existing)
    if existing_row is not None and str(existing_row.get("status")) in {"submitted", "accepted"}:
        raise AppError(
            code="conflict",
            message="You already have an active quote on this job",
            http_status=409,
        )

    # Pre-acceptance disintermediation guard: strip contact info before persist.
    # This path is reachable only while the job is quotable (open/quoted) — i.e.
    # strictly pre-acceptance — so post-acceptance messages are never stripped.
    clean_message = _clean_pre_acceptance_message(
        service_client.client,
        message=body.message,
        vendor_id=vendor_id,
        job_id=job_id,
        reporter_user_id=str(job["customer_id"]),
    )

    expires_at = datetime.now(tz=UTC) + timedelta(days=body.validity_days)
    insert_row = {
        "job_id": job_id,
        "provider_vendor_id": vendor_id,
        "amount_ngwee": body.amount_ngwee,
        "message": clean_message,
        "status": "submitted",
        "expires_at": expires_at.isoformat(),
    }
    response = service_client.client.table("job_quotes").insert(insert_row).execute()
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="internal_error",
            message="Failed to create quote",
            http_status=500,
        )

    _maybe_mark_job_quoted(service_client.client, job_id)
    return SubmitQuoteResponse(quote=_serialize_quote_row(row))


@router.get("/jobs/{job_id}/quotes", response_model=JobQuotesResponse)
async def list_job_quotes(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> JobQuotesResponse:
    job = _load_job(service_client.client, job_id)
    client = service_client.client
    _expire_stale_quotes(client, job_id=job_id)

    is_owner = str(job.get("customer_id")) == current_user.id
    vendor: dict[str, Any] | None = None
    if not is_owner:
        try:
            vendor = _load_vendor_for_owner(service_client, current_user.id)
        except AppError as exc:
            if exc.http_status == 403:
                raise AppError(
                    code="forbidden",
                    message="You may not view quotes for this job",
                    http_status=403,
                ) from exc
            raise

    quotes_response = client.table("job_quotes").select("*").eq("job_id", job_id).execute()
    quote_rows = _rows(quotes_response)

    if is_owner:
        visible_rows = [row for row in quote_rows if _quote_is_compare_visible(row)]
        items = _enrich_quotes_for_compare(client, visible_rows)
        return JobQuotesResponse(job_id=job_id, view="customer_compare", items=items)

    assert vendor is not None
    vendor_id = str(vendor["id"])
    _assert_provider_matched(service_client, job=job, vendor_id=vendor_id)
    own_rows = _filter_provider_own_quotes(quote_rows, vendor_id=vendor_id)
    items = [_serialize_quote_row(row) for row in own_rows]
    return JobQuotesResponse(job_id=job_id, view="provider_own", items=items)


@router.post("/quotes/{quote_id}/withdraw", response_model=QuoteActionResponse)
async def withdraw_quote(
    quote_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> QuoteActionResponse:
    _rate_limit_quotes(request, current_user.id, service_client)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    quote = _load_quote(service_client.client, quote_id)

    if str(quote.get("provider_vendor_id")) != str(vendor["id"]):
        raise AppError(
            code="forbidden",
            message="You may only withdraw your own quotes",
            http_status=403,
        )
    if str(quote.get("status")) != "submitted":
        raise AppError(
            code="invalid_transition",
            message="Only submitted quotes can be withdrawn",
            http_status=409,
            details={"status": quote.get("status")},
        )

    update_response = (
        service_client.client.table("job_quotes")
        .update({"status": "declined"})
        .eq("id", quote_id)
        .eq("status", "submitted")
        .execute()
    )
    updated = _single_row(update_response)
    if updated is None:
        quote = _load_quote(service_client.client, quote_id)
        if str(quote.get("status")) == "declined":
            return QuoteActionResponse(quote=_serialize_quote_row(quote))
        raise AppError(
            code="conflict",
            message="Quote status changed before withdrawal",
            http_status=409,
        )
    return QuoteActionResponse(quote=_serialize_quote_row(updated))


@router.post("/quotes/{quote_id}/decline", response_model=QuoteActionResponse)
async def decline_quote(
    quote_id: str,
    body: DeclineQuoteRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> QuoteActionResponse:
    _rate_limit_quotes(request, current_user.id, service_client)
    quote = _load_quote(service_client.client, quote_id)
    job = _load_job(service_client.client, str(quote["job_id"]))

    if str(job.get("customer_id")) != current_user.id:
        raise AppError(
            code="forbidden",
            message="Only the job owner may decline quotes",
            http_status=403,
        )
    if str(quote.get("status")) != "submitted":
        raise AppError(
            code="invalid_transition",
            message="Only submitted quotes can be declined",
            http_status=409,
            details={"status": quote.get("status")},
        )

    update_payload: dict[str, Any] = {"status": "declined"}
    if body.reason:
        prefix = "[declined] "
        existing = quote.get("message")
        note = f"{prefix}{body.reason.strip()}"
        if isinstance(existing, str) and existing.strip():
            update_payload["message"] = f"{existing}\n\n{note}"
        else:
            update_payload["message"] = note

    update_response = (
        service_client.client.table("job_quotes")
        .update(update_payload)
        .eq("id", quote_id)
        .eq("status", "submitted")
        .execute()
    )
    updated = _single_row(update_response)
    if updated is None:
        quote = _load_quote(service_client.client, quote_id)
        if str(quote.get("status")) == "declined":
            return QuoteActionResponse(quote=_serialize_quote_row(quote))
        raise AppError(
            code="conflict",
            message="Quote status changed before decline",
            http_status=409,
        )
    return QuoteActionResponse(quote=_serialize_quote_row(updated))
