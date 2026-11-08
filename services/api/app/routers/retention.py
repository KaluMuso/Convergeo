"""Retention surfaces: saved searches, listing alerts, follow feed, deals, product Q&A.

Reuses existing foundations instead of duplicating them: recently viewed is
``/account/recently-viewed`` (user_recently_viewed); review photos are
``reviews.photos`` on ``POST /reviews`` (verified purchase by construction);
follows are ``vendor_follows``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.core.ratelimit_policies import (
    PUBLIC_DISCOVERY_READ,
    SENSITIVE_WRITE,
    STANDARD_WRITE,
    RateLimitPolicy,
)
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.catalog import (
    CatalogListingItem,
    build_catalog_candidates,
    catalog_item_from_candidate,
)
from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

router = APIRouter(tags=["retention"])

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
UNIQUE_VIOLATION = "23505"
MAX_SAVED_SEARCHES = 20
MAX_LISTING_ALERTS = 100
AUTO_HIDE_FLAGS = 3
ALLOWED_FILTER_KEYS = frozenset(
    {"category_path", "min_price", "max_price", "condition", "min_rating", "sort", "kind"}
)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _limit(client: Any, policy: RateLimitPolicy, key: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=policy.scope, key=key, window=policy.window, limit=policy.limit, client=client
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="retention.errors.rate_limited",
            message="Too many requests",
        )


def _uuid(value: str, kind: str) -> str:
    if not UUID_RE.match(value):
        raise AppError(code="not_found", message=f"{kind} not found", http_status=404)
    return value


def _validation(message: str) -> AppError:
    return AppError(code="validation_error", message=message, http_status=422)


# ---------------------------------------------------------------------------
# Saved searches
# ---------------------------------------------------------------------------


class SavedSearchIn(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = Field(default=None, min_length=1, max_length=80)
    query: str = Field(default="", max_length=200)
    filters: dict[str, str | int | list[str]] = Field(default_factory=dict)
    alert_enabled: bool = True
    alert_frequency: Literal["instant", "daily", "weekly"] = "daily"

    @field_validator("filters")
    @classmethod
    def _filters(cls, value: dict[str, Any]) -> dict[str, Any]:
        unknown = set(value) - ALLOWED_FILTER_KEYS
        if unknown:
            raise ValueError(f"unsupported filters: {sorted(unknown)}")
        for key in ("min_price", "max_price", "min_rating"):
            if key in value and (not isinstance(value[key], int) or value[key] < 0):
                raise ValueError(f"{key} must be a non-negative integer (ngwee for prices)")
        return value


class SavedSearchPatch(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = Field(default=None, min_length=1, max_length=80)
    alert_enabled: bool | None = None
    alert_frequency: Literal["instant", "daily", "weekly"] | None = None


class SavedSearchOut(BaseModel):
    id: str
    label: str | None
    query: str
    filters: dict[str, Any]
    alert_enabled: bool
    alert_frequency: str
    last_alerted_at: str | None = None
    created_at: str | None = None


def _saved_out(row: dict[str, Any]) -> SavedSearchOut:
    return SavedSearchOut(
        id=str(row["id"]),
        label=row.get("label"),
        query=str(row.get("query") or ""),
        filters=dict(row.get("filters") or {}),
        alert_enabled=bool(row.get("alert_enabled", True)),
        alert_frequency=str(row.get("alert_frequency") or "daily"),
        last_alerted_at=row.get("last_alerted_at"),
        created_at=row.get("created_at"),
    )


@router.get("/me/saved-searches", response_model=list[SavedSearchOut])
def list_saved_searches(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> list[SavedSearchOut]:
    rows = _rows(
        supabase.client.table("saved_searches")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return [_saved_out(row) for row in rows]


@router.post("/me/saved-searches", response_model=SavedSearchOut, status_code=201)
def create_saved_search(
    body: SavedSearchIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> SavedSearchOut:
    _limit(supabase.client, STANDARD_WRITE, user.id)
    if not body.query.strip() and not body.filters:
        raise _validation("A saved search needs a query or at least one filter")
    existing = _rows(
        supabase.client.table("saved_searches").select("id").eq("user_id", user.id).execute()
    )
    if len(existing) >= MAX_SAVED_SEARCHES:
        raise _validation(f"At most {MAX_SAVED_SEARCHES} saved searches")
    row = {"user_id": user.id, **body.model_dump(), "query": body.query.strip()}
    try:
        created = _rows(supabase.client.table("saved_searches").insert(row).execute())
    except Exception as exc:
        if getattr(exc, "code", None) == UNIQUE_VIOLATION:
            raise AppError(
                code="conflict", message="Search already saved", http_status=409
            ) from exc
        raise
    if not created:
        raise AppError(code="internal_error", message="Could not save search", http_status=500)
    return _saved_out(created[0])


@router.patch("/me/saved-searches/{search_id}", response_model=SavedSearchOut)
def update_saved_search(
    search_id: str,
    body: SavedSearchPatch,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> SavedSearchOut:
    _limit(supabase.client, STANDARD_WRITE, user.id)
    _uuid(search_id, "Saved search")
    fields = body.model_dump(exclude_none=True)
    updated = _rows(
        supabase.client.table("saved_searches")
        .update(fields or {"alert_enabled": True})
        .eq("id", search_id)
        .eq("user_id", user.id)
        .execute()
    )
    if not updated:
        raise AppError(code="not_found", message="Saved search not found", http_status=404)
    return _saved_out(updated[0])


@router.delete("/me/saved-searches/{search_id}", status_code=204)
def delete_saved_search(
    search_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> Response:
    _limit(supabase.client, STANDARD_WRITE, user.id)
    _uuid(search_id, "Saved search")
    supabase.client.table("saved_searches").delete().eq("id", search_id).eq(
        "user_id", user.id
    ).execute()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Price-drop / back-in-stock subscriptions
# ---------------------------------------------------------------------------


class ListingAlertIn(BaseModel):
    model_config = {"extra": "forbid"}

    listing_id: str
    kind: Literal["price_drop", "back_in_stock"]
    target_price_ngwee: int | None = Field(default=None, gt=0, le=10_000_000_000)

    @field_validator("listing_id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not UUID_RE.match(value):
            raise ValueError("listing_id must be a UUID")
        return value


class ListingAlertOut(BaseModel):
    id: str
    listing_id: str
    kind: str
    baseline_price_ngwee: int | None
    target_price_ngwee: int | None
    active: bool
    last_notified_at: str | None = None


def _alert_out(row: dict[str, Any]) -> ListingAlertOut:
    baseline = row.get("baseline_price_ngwee")
    target = row.get("target_price_ngwee")
    return ListingAlertOut(
        id=str(row["id"]),
        listing_id=str(row["listing_id"]),
        kind=str(row["kind"]),
        baseline_price_ngwee=int(baseline) if baseline is not None else None,
        target_price_ngwee=int(target) if target is not None else None,
        active=bool(row.get("active", True)),
        last_notified_at=row.get("last_notified_at"),
    )


@router.get("/me/listing-alerts", response_model=list[ListingAlertOut])
def list_listing_alerts(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> list[ListingAlertOut]:
    rows = _rows(
        supabase.client.table("listing_alert_subscriptions")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return [_alert_out(row) for row in rows]


@router.post("/me/listing-alerts", response_model=ListingAlertOut, status_code=201)
def create_listing_alert(
    body: ListingAlertIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> ListingAlertOut:
    _limit(supabase.client, STANDARD_WRITE, user.id)
    listing = _rows(
        supabase.client.table("vendor_listings")
        .select("id, price_ngwee, status")
        .eq("id", body.listing_id)
        .eq("status", "active")
        .execute()
    )
    if not listing:
        raise AppError(code="not_found", message="Listing not found", http_status=404)
    current = _rows(
        supabase.client.table("listing_alert_subscriptions")
        .select("id")
        .eq("user_id", user.id)
        .execute()
    )
    if len(current) >= MAX_LISTING_ALERTS:
        raise _validation(f"At most {MAX_LISTING_ALERTS} listing alerts")
    price = int(listing[0]["price_ngwee"])
    if body.target_price_ngwee is not None and body.target_price_ngwee >= price:
        raise _validation("target_price_ngwee must be below the current price")
    row = {
        "user_id": user.id,
        "listing_id": body.listing_id,
        "kind": body.kind,
        "baseline_price_ngwee": price,
        "target_price_ngwee": body.target_price_ngwee,
        "active": True,
    }
    existing = _rows(
        supabase.client.table("listing_alert_subscriptions")
        .select("*")
        .eq("user_id", user.id)
        .eq("listing_id", body.listing_id)
        .eq("kind", body.kind)
        .execute()
    )
    if existing:
        updated = _rows(
            supabase.client.table("listing_alert_subscriptions")
            .update({key: value for key, value in row.items() if key != "user_id"})
            .eq("id", existing[0]["id"])
            .execute()
        )
        return _alert_out(updated[0] if updated else existing[0])
    created = _rows(supabase.client.table("listing_alert_subscriptions").insert(row).execute())
    if not created:
        raise AppError(code="internal_error", message="Could not subscribe", http_status=500)
    return _alert_out(created[0])


@router.delete("/me/listing-alerts/{alert_id}", status_code=204)
def delete_listing_alert(
    alert_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> Response:
    _limit(supabase.client, STANDARD_WRITE, user.id)
    _uuid(alert_id, "Alert")
    supabase.client.table("listing_alert_subscriptions").delete().eq("id", alert_id).eq(
        "user_id", user.id
    ).execute()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Follow-vendor new arrivals feed
# ---------------------------------------------------------------------------


class FollowFeedOut(BaseModel):
    items: list[CatalogListingItem]
    next_offset: int | None = None


@router.get("/me/follows/feed", response_model=FollowFeedOut)
def follow_feed(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Any, Depends(get_supabase_client)],
    days: Annotated[int, Query(ge=1, le=90)] = 30,
    limit: Annotated[int, Query(ge=1, le=48)] = 24,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> FollowFeedOut:
    """Newest in-stock listings from vendors the caller follows (last ``days``)."""
    follows = _rows(
        supabase.client.table("vendor_follows").select("vendor_id").eq("user_id", user.id).execute()
    )
    vendor_ids = {str(row["vendor_id"]) for row in follows if row.get("vendor_id")}
    if not vendor_ids:
        return FollowFeedOut(items=[])
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    pool = [
        row
        for row in build_catalog_candidates(supabase.client)
        if row.listing.vendor_id in vendor_ids and (row.listing.created_at or "") >= since
    ]
    pool.sort(key=lambda row: (row.in_stock, row.listing.created_at or ""), reverse=True)
    page = pool[offset : offset + limit]
    next_offset = offset + limit if offset + limit < len(pool) else None
    return FollowFeedOut(
        items=[catalog_item_from_candidate(row) for row in page], next_offset=next_offset
    )


# ---------------------------------------------------------------------------
# Flash deals (public)
# ---------------------------------------------------------------------------


class DealOut(BaseModel):
    deal_id: str
    starts_at: str
    ends_at: str
    deal_price_ngwee: int
    reference_price_ngwee: int
    discount_percent: int
    listing: CatalogListingItem


class DealsOut(BaseModel):
    server_time: str
    items: list[DealOut]


def live_deals(client: Any, *, now: datetime, limit: int) -> list[DealOut]:
    rows = _rows(
        client.table("flash_deals")
        .select(
            "id, listing_id, deal_price_ngwee, reference_price_ngwee, starts_at, ends_at, position"
        )
        .eq("enabled", True)
        .lte("starts_at", now.isoformat())
        .gt("ends_at", now.isoformat())
        .order("position", desc=False)
        .execute()
    )
    if not rows:
        return []
    by_listing = {row.listing.id: row for row in build_catalog_candidates(client)}
    out: list[DealOut] = []
    for row in rows:
        candidate = by_listing.get(str(row["listing_id"]))
        deal_price = int(row["deal_price_ngwee"])
        reference = int(row["reference_price_ngwee"])
        # Price honesty: only show while the live price actually honours the deal.
        if candidate is None or not candidate.in_stock:
            continue
        live_price = candidate.search_doc.price_min_ngwee or 0
        if live_price <= 0 or live_price > deal_price:
            continue
        out.append(
            DealOut(
                deal_id=str(row["id"]),
                starts_at=str(row["starts_at"]),
                ends_at=str(row["ends_at"]),
                deal_price_ngwee=live_price,
                reference_price_ngwee=reference,
                discount_percent=((reference - live_price) * 100) // reference,
                listing=catalog_item_from_candidate(candidate),
            )
        )
        if len(out) >= limit:
            break
    return out


@router.get("/deals", response_model=DealsOut)
def list_deals(
    request: Request,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=48)] = 24,
) -> DealsOut:
    try:
        _limit(supabase.client, PUBLIC_DISCOVERY_READ, get_client_ip(request))
    except AppError:
        raise
    except Exception:  # noqa: BLE001 — public read fails open on limiter outage.
        pass
    now = datetime.now(UTC)
    return DealsOut(
        server_time=now.isoformat(), items=live_deals(supabase.client, now=now, limit=limit)
    )


# ---------------------------------------------------------------------------
# Product Q&A
# ---------------------------------------------------------------------------


class AnswerOut(BaseModel):
    id: str
    body: str
    author_role: str
    vendor_name: str | None = None
    created_at: str | None = None


class QuestionOut(BaseModel):
    id: str
    body: str
    created_at: str | None = None
    answers: list[AnswerOut] = Field(default_factory=list)


class QuestionIn(BaseModel):
    model_config = {"extra": "forbid"}

    body: str = Field(min_length=5, max_length=500)


class AnswerIn(BaseModel):
    model_config = {"extra": "forbid"}

    body: str = Field(min_length=2, max_length=1000)


def _active_product_id(client: Any, slug: str) -> str:
    rows = _rows(
        client.table("products").select("id").eq("slug", slug).eq("status", "active").execute()
    )
    if not rows:
        raise AppError(code="not_found", message="Product not found", http_status=404)
    return str(rows[0]["id"])


@router.get("/products/{slug}/questions", response_model=list[QuestionOut])
def list_questions(
    slug: str,
    supabase: Annotated[Any, Depends(get_supabase_client)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[QuestionOut]:
    product_id = _active_product_id(supabase.client, slug)
    questions = _rows(
        supabase.client.table("product_questions")
        .select("id, body, created_at")
        .eq("product_id", product_id)
        .eq("status", "published")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    ids = [str(row["id"]) for row in questions]
    answers = (
        _rows(
            supabase.client.table("product_answers")
            .select("id, question_id, body, author_role, vendor_id, created_at")
            .in_("question_id", ids)
            .eq("status", "published")
            .order("created_at", desc=False)
            .execute()
        )
        if ids
        else []
    )
    vendor_ids = sorted({str(row["vendor_id"]) for row in answers if row.get("vendor_id")})
    vendor_names = (
        {
            str(row["id"]): str(row.get("display_name") or "")
            for row in _rows(
                supabase.client.table("vendors")
                .select("id, display_name")
                .in_("id", vendor_ids)
                .execute()
            )
        }
        if vendor_ids
        else {}
    )
    grouped: dict[str, list[AnswerOut]] = {}
    for row in answers:
        grouped.setdefault(str(row["question_id"]), []).append(
            AnswerOut(
                id=str(row["id"]),
                body=str(row["body"]),
                author_role=str(row["author_role"]),
                vendor_name=vendor_names.get(str(row.get("vendor_id"))),
                created_at=row.get("created_at"),
            )
        )
    return [
        QuestionOut(
            id=str(row["id"]),
            body=str(row["body"]),
            created_at=row.get("created_at"),
            answers=grouped.get(str(row["id"]), []),
        )
        for row in questions
    ]


@router.post("/products/{slug}/questions", response_model=QuestionOut, status_code=201)
def ask_question(
    slug: str,
    body: QuestionIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> QuestionOut:
    _limit(supabase.client, SENSITIVE_WRITE, user.id)
    product_id = _active_product_id(supabase.client, slug)
    created = _rows(
        supabase.client.table("product_questions")
        .insert({"product_id": product_id, "asker_user_id": user.id, "body": body.body.strip()})
        .execute()
    )
    if not created:
        raise AppError(code="internal_error", message="Could not post question", http_status=500)
    return QuestionOut(id=str(created[0]["id"]), body=str(created[0]["body"]))


def _vendor_for_product(client: Any, user_id: str, product_id: str) -> str | None:
    vendors = _rows(
        client.table("vendors")
        .select("id")
        .eq("owner_user_id", user_id)
        .eq("status", "active")
        .execute()
    )
    for vendor in vendors:
        listings = _rows(
            client.table("vendor_listings")
            .select("id")
            .eq("vendor_id", vendor["id"])
            .eq("product_id", product_id)
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        if listings:
            return str(vendor["id"])
    return None


@router.post("/questions/{question_id}/answers", response_model=AnswerOut, status_code=201)
def answer_question(
    question_id: str,
    body: AnswerIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> AnswerOut:
    _limit(supabase.client, SENSITIVE_WRITE, user.id)
    _uuid(question_id, "Question")
    question = _rows(
        supabase.client.table("product_questions")
        .select("id, product_id, status")
        .eq("id", question_id)
        .eq("status", "published")
        .execute()
    )
    if not question:
        raise AppError(code="not_found", message="Question not found", http_status=404)
    vendor_id = _vendor_for_product(supabase.client, user.id, str(question[0]["product_id"]))
    if vendor_id:
        role = "vendor"
    elif user.roles.intersection({"admin", "superadmin"}):
        role = "admin"
    else:
        role = "customer"
    created = _rows(
        supabase.client.table("product_answers")
        .insert(
            {
                "question_id": question_id,
                "author_user_id": user.id,
                "author_role": role,
                "vendor_id": vendor_id,
                "body": body.body.strip(),
            }
        )
        .execute()
    )
    if not created:
        raise AppError(code="internal_error", message="Could not post answer", http_status=500)
    return AnswerOut(id=str(created[0]["id"]), body=str(created[0]["body"]), author_role=role)


@router.post("/qa/{kind}/{item_id}/flag", status_code=204)
def flag_qa(
    kind: Literal["questions", "answers"],
    item_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> Response:
    """Community flag; auto-hides at ``AUTO_HIDE_FLAGS`` pending admin review."""
    _limit(supabase.client, SENSITIVE_WRITE, user.id)
    _uuid(item_id, "Item")
    table = "product_questions" if kind == "questions" else "product_answers"
    rows = _rows(
        supabase.client.table(table).select("id, flag_count, status").eq("id", item_id).execute()
    )
    if not rows:
        raise AppError(code="not_found", message="Item not found", http_status=404)
    count = int(rows[0].get("flag_count") or 0) + 1
    fields: dict[str, Any] = {"flag_count": count}
    if count >= AUTO_HIDE_FLAGS:
        fields["status"] = "hidden"
    supabase.client.table(table).update(fields).eq("id", item_id).execute()
    return Response(status_code=204)
