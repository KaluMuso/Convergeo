"""Verified-purchase reviews — customer submit/edit and vendor replies (M15-P01)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends, Request
from pydantic import Field

router = APIRouter(prefix="/reviews", tags=["reviews"])

REVIEW_SELECT_COLUMNS = (
    "id, order_item_id, rating, body, photos, vendor_reply, vendor_reply_at, "
    "status, created_at, updated_at"
)

REVIEW_EDIT_DAYS = 7
REPLY_EDIT_HOURS = 24
MAX_REVIEW_PHOTOS = 3
PUBLIC_ID_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")
REVIEWABLE_ORDER_STATUSES = frozenset({"delivered", "completed"})


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class SubmitReviewRequest(StrictModel):
    order_item_id: str
    rating: int = Field(ge=1, le=5)
    body: str | None = Field(default=None, max_length=4000)
    photos: list[str] = Field(default_factory=list, max_length=MAX_REVIEW_PHOTOS)


class VendorReplyRequest(StrictModel):
    reply: str = Field(min_length=1, max_length=4000)


class ReviewResponse(StrictModel):
    id: str
    order_item_id: str
    rating: int
    body: str | None
    photos: list[str]
    vendor_reply: str | None
    vendor_reply_at: str | None
    status: str
    created_at: str
    updated_at: str
    editable_until: str | None = None
    reply_editable_until: str | None = None
    item_title: str | None = None
    product_id: str | None = None
    listing_id: str | None = None


class OrderReviewItem(StrictModel):
    order_item_id: str
    title: str
    review_id: str | None = None
    rating: int | None = None
    can_review: bool
    can_edit: bool = False


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


def _validate_photo_public_ids(photos: list[str]) -> list[str]:
    cleaned: list[str] = []
    for public_id in photos:
        trimmed = public_id.strip()
        if not trimmed:
            continue
        if ".." in trimmed or "\\" in trimmed:
            raise AppError(
                code="validation_error",
                message="photo public_id contains invalid path segments",
                http_status=400,
                details={"public_id": public_id},
            )
        if not PUBLIC_ID_PATTERN.fullmatch(trimmed):
            raise AppError(
                code="validation_error",
                message="photo public_id contains invalid characters",
                http_status=400,
                details={"public_id": public_id},
            )
        cleaned.append(trimmed)
    if len(cleaned) > MAX_REVIEW_PHOTOS:
        raise AppError(
            code="validation_error",
            message=f"At most {MAX_REVIEW_PHOTOS} photos allowed",
            http_status=400,
            details={"max_photos": MAX_REVIEW_PHOTOS},
        )
    return cleaned


def _load_order_item_context(
    service_client: _ServiceRoleClient,
    order_item_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("order_items")
        .select("id, order_id, title_snapshot, order_item_products(listing_id, product_id)")
        .eq("id", order_item_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Order item not found",
            http_status=404,
            details={"order_item_id": order_item_id},
        )

    order_response = (
        service_client.client.table("orders")
        .select("id, customer_id, status")
        .eq("id", row["order_id"])
        .maybe_single()
        .execute()
    )
    order = _single_row(order_response)
    if order is None:
        raise AppError(
            code="not_found",
            message="Order not found",
            http_status=404,
            details={"order_item_id": order_item_id},
        )

    product_link = row.get("order_item_products")
    listing_id: str | None = None
    product_id: str | None = None
    if isinstance(product_link, dict):
        listing_id = product_link.get("listing_id")
        product_id = product_link.get("product_id")
    elif isinstance(product_link, list) and product_link and isinstance(product_link[0], dict):
        listing_id = product_link[0].get("listing_id")
        product_id = product_link[0].get("product_id")

    return {
        "order_item_id": str(row["id"]),
        "order_id": str(row["order_id"]),
        "title": str(row.get("title_snapshot") or ""),
        "customer_id": str(order["customer_id"]),
        "status": str(order["status"]),
        "listing_id": str(listing_id) if listing_id else None,
        "product_id": str(product_id) if product_id else None,
    }


def _assert_verified_purchase(customer_id: str, context: dict[str, Any]) -> None:
    if context["customer_id"] != customer_id:
        raise AppError(
            code="forbidden",
            message="Only the purchaser may review this order item",
            http_status=403,
            details={"order_item_id": context["order_item_id"]},
        )
    if context["status"] not in REVIEWABLE_ORDER_STATUSES:
        raise AppError(
            code="forbidden",
            message="Reviews are only allowed after delivery",
            http_status=403,
            details={"order_status": context["status"]},
        )


def _review_edit_deadline(created_at: object) -> datetime | None:
    created = _parse_ts(created_at)
    if created is None:
        return None
    return created + timedelta(days=REVIEW_EDIT_DAYS)


def _reply_edit_deadline(reply_at: object) -> datetime | None:
    replied = _parse_ts(reply_at)
    if replied is None:
        return None
    return replied + timedelta(hours=REPLY_EDIT_HOURS)


def _to_review_response(row: dict[str, Any], *, item_title: str | None = None) -> ReviewResponse:
    created_at = str(row.get("created_at") or "")
    edit_deadline = _review_edit_deadline(created_at)
    reply_deadline = _reply_edit_deadline(row.get("vendor_reply_at"))
    photos = row.get("photos")
    if not isinstance(photos, list):
        photos = []
    return ReviewResponse(
        id=str(row["id"]),
        order_item_id=str(row["order_item_id"]),
        rating=int(row["rating"]),
        body=row.get("body"),
        photos=[str(photo) for photo in photos],
        vendor_reply=row.get("vendor_reply"),
        vendor_reply_at=row.get("vendor_reply_at"),
        status=str(row.get("status") or "published"),
        created_at=created_at,
        updated_at=str(row.get("updated_at") or created_at),
        editable_until=_iso(edit_deadline) if edit_deadline else None,
        reply_editable_until=_iso(reply_deadline) if reply_deadline else None,
        item_title=item_title,
        product_id=row.get("product_id"),
        listing_id=row.get("listing_id"),
    )


def _load_review_row(service_client: _ServiceRoleClient, review_id: str) -> dict[str, Any]:
    response = (
        service_client.client.table("reviews")
        .select(REVIEW_SELECT_COLUMNS)
        .eq("id", review_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Review not found",
            http_status=404,
            details={"review_id": review_id},
        )
    return row


def _load_vendor_for_review(
    service_client: _ServiceRoleClient,
    order_item_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("order_item_products")
        .select("listing_id, vendor_listings(vendor_id, vendors(id, owner_user_id))")
        .eq("order_item_id", order_item_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Product link not found for review",
            http_status=404,
            details={"order_item_id": order_item_id},
        )

    listing = row.get("vendor_listings")
    if isinstance(listing, list):
        listing = listing[0] if listing else None
    if not isinstance(listing, dict):
        raise AppError(
            code="not_found",
            message="Listing not found for review",
            http_status=404,
            details={"order_item_id": order_item_id},
        )

    vendor = listing.get("vendors")
    if isinstance(vendor, list):
        vendor = vendor[0] if vendor else None
    if not isinstance(vendor, dict):
        raise AppError(
            code="not_found",
            message="Vendor not found for review",
            http_status=404,
            details={"order_item_id": order_item_id},
        )
    return vendor


def _is_unique_violation(exc: Exception) -> bool:
    message = str(exc).lower()
    return "duplicate" in message or "unique" in message or "reviews_order_item_id_key" in message


def _rate_limit_reviews(
    request: Request,
    user_id: str,
    service_client: _ServiceRoleClient,
    *,
    scope_suffix: str,
) -> None:
    ip = get_client_ip(request)
    allowed, retry_after = bump_rate_counter(
        scope=f"reviews_ip_{scope_suffix}",
        key=ip,
        window=timedelta(minutes=1),
        limit=30,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="catalog.reviews.errors.rateLimited",
            message="Too many review requests",
        )
    allowed_user, user_retry = bump_rate_counter(
        scope=f"reviews_user_{scope_suffix}",
        key=user_id,
        window=timedelta(minutes=1),
        limit=10,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=user_retry,
            message_key="catalog.reviews.errors.rateLimited",
            message="Too many review requests",
        )


@router.get("", response_model=list[ReviewResponse])
async def list_product_reviews(
    product_id: str,
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> list[ReviewResponse]:
    links = _rows(
        service_client.client.table("order_item_products")
        .select("order_item_id")
        .eq("product_id", product_id)
        .execute()
    )
    order_item_ids = [str(row["order_item_id"]) for row in links if row.get("order_item_id")]
    if not order_item_ids:
        return []

    reviews = _rows(
        service_client.client.table("reviews")
        .select(REVIEW_SELECT_COLUMNS)
        .in_("order_item_id", order_item_ids)
        .eq("status", "published")
        .order("created_at", desc=True)
        .execute()
    )
    return [_to_review_response(row) for row in reviews]


@router.get("/order/{order_id}", response_model=list[OrderReviewItem])
async def list_order_review_items(
    order_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> list[OrderReviewItem]:
    order_response = (
        service_client.client.table("orders")
        .select("id, customer_id, status")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    order = _single_row(order_response)
    if order is None:
        raise AppError(
            code="not_found",
            message="Order not found",
            http_status=404,
            details={"order_id": order_id},
        )
    if str(order["customer_id"]) != current_user.id:
        raise AppError(
            code="forbidden",
            message="Order not found",
            http_status=403,
            details={"order_id": order_id},
        )

    items = _rows(
        service_client.client.table("order_items")
        .select("id, title_snapshot")
        .eq("order_id", order_id)
        .execute()
    )
    if not items:
        return []

    item_ids = [str(item["id"]) for item in items]
    existing = _rows(
        service_client.client.table("reviews")
        .select("id, order_item_id, rating, created_at")
        .in_("order_item_id", item_ids)
        .execute()
    )
    by_item = {str(row["order_item_id"]): row for row in existing}
    reviewable = str(order["status"]) in REVIEWABLE_ORDER_STATUSES
    now = datetime.now(tz=UTC)

    result: list[OrderReviewItem] = []
    for item in items:
        item_id = str(item["id"])
        review = by_item.get(item_id)
        can_edit = False
        if review is not None:
            deadline = _review_edit_deadline(review.get("created_at"))
            can_edit = deadline is not None and now <= deadline
        result.append(
            OrderReviewItem(
                order_item_id=item_id,
                title=str(item.get("title_snapshot") or ""),
                review_id=str(review["id"]) if review else None,
                rating=int(review["rating"]) if review else None,
                can_review=reviewable and review is None,
                can_edit=can_edit,
            )
        )
    return result


@router.get("/vendor", response_model=list[ReviewResponse])
async def list_vendor_reviews(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> list[ReviewResponse]:
    vendor_response = (
        service_client.client.table("vendors")
        .select("id")
        .eq("owner_user_id", current_user.id)
        .maybe_single()
        .execute()
    )
    vendor = _single_row(vendor_response)
    if vendor is None:
        return []

    listings = _rows(
        service_client.client.table("vendor_listings")
        .select("id")
        .eq("vendor_id", vendor["id"])
        .execute()
    )
    listing_ids = [str(row["id"]) for row in listings]
    if not listing_ids:
        return []

    links = _rows(
        service_client.client.table("order_item_products")
        .select("order_item_id, listing_id, product_id")
        .in_("listing_id", listing_ids)
        .execute()
    )
    order_item_ids = [str(row["order_item_id"]) for row in links if row.get("order_item_id")]
    if not order_item_ids:
        return []

    reviews = _rows(
        service_client.client.table("reviews")
        .select(REVIEW_SELECT_COLUMNS)
        .in_("order_item_id", order_item_ids)
        .eq("status", "published")
        .order("created_at", desc=True)
        .execute()
    )

    item_titles: dict[str, str] = {}
    if reviews:
        item_rows = _rows(
            service_client.client.table("order_items")
            .select("id, title_snapshot")
            .in_("id", [str(row["order_item_id"]) for row in reviews])
            .execute()
        )
        item_titles = {str(row["id"]): str(row.get("title_snapshot") or "") for row in item_rows}

    link_by_item = {str(row["order_item_id"]): row for row in links}
    output: list[ReviewResponse] = []
    for row in reviews:
        item_id = str(row["order_item_id"])
        link = link_by_item.get(item_id, {})
        enriched = dict(row)
        enriched["listing_id"] = link.get("listing_id")
        enriched["product_id"] = link.get("product_id")
        output.append(_to_review_response(enriched, item_title=item_titles.get(item_id)))
    return output


@router.post("", response_model=ReviewResponse)
async def submit_review(
    body: SubmitReviewRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> ReviewResponse:
    _rate_limit_reviews(request, current_user.id, service_client, scope_suffix="submit")
    photos = _validate_photo_public_ids(body.photos)
    context = _load_order_item_context(service_client, body.order_item_id)
    _assert_verified_purchase(current_user.id, context)

    existing_response = (
        service_client.client.table("reviews")
        .select("id, created_at")
        .eq("order_item_id", body.order_item_id)
        .maybe_single()
        .execute()
    )
    existing = _single_row(existing_response)

    payload = {
        "rating": body.rating,
        "body": body.body,
        "photos": photos,
        "status": "published",
    }

    if existing is not None:
        deadline = _review_edit_deadline(existing.get("created_at"))
        now = datetime.now(tz=UTC)
        if deadline is None or now > deadline:
            raise AppError(
                code="forbidden",
                message="Review edit window has expired",
                http_status=403,
                details={"order_item_id": body.order_item_id},
            )
        update_response = (
            service_client.client.table("reviews")
            .update(payload)
            .eq("id", existing["id"])
            .execute()
        )
        updated_rows = _rows(update_response)
        if not updated_rows:
            raise AppError(
                code="internal_error",
                message="Failed to update review",
                http_status=500,
            )
        row = updated_rows[0]
    else:
        insert_payload = {
            "order_item_id": body.order_item_id,
            **payload,
        }
        try:
            insert_response = (
                service_client.client.table("reviews").insert(insert_payload).execute()
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise AppError(
                    code="conflict",
                    message="A review already exists for this order item",
                    http_status=409,
                    details={"order_item_id": body.order_item_id},
                ) from exc
            raise
        inserted = _rows(insert_response)
        if not inserted:
            existing_after = (
                service_client.client.table("reviews")
                .select("id")
                .eq("order_item_id", body.order_item_id)
                .maybe_single()
                .execute()
            )
            if _single_row(existing_after) is not None:
                raise AppError(
                    code="conflict",
                    message="A review already exists for this order item",
                    http_status=409,
                    details={"order_item_id": body.order_item_id},
                )
            raise AppError(
                code="internal_error",
                message="Failed to create review",
                http_status=500,
            )
        row = inserted[0]

    enriched = dict(row)
    enriched["product_id"] = context.get("product_id")
    enriched["listing_id"] = context.get("listing_id")
    return _to_review_response(enriched, item_title=context.get("title"))


@router.post("/{review_id}/reply", response_model=ReviewResponse)
async def submit_vendor_reply(
    review_id: str,
    body: VendorReplyRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> ReviewResponse:
    _rate_limit_reviews(request, current_user.id, service_client, scope_suffix="reply")
    review = _load_review_row(service_client, review_id)
    vendor = _load_vendor_for_review(service_client, str(review["order_item_id"]))
    if str(vendor.get("owner_user_id")) != current_user.id:
        raise AppError(
            code="forbidden",
            message="Only the item vendor may reply to this review",
            http_status=403,
            details={"review_id": review_id},
        )

    now = datetime.now(tz=UTC)
    existing_reply = review.get("vendor_reply")
    existing_reply_at = review.get("vendor_reply_at")
    if existing_reply and existing_reply_at:
        deadline = _reply_edit_deadline(existing_reply_at)
        if deadline is None or now > deadline:
            raise AppError(
                code="forbidden",
                message="Vendor reply edit window has expired",
                http_status=403,
                details={"review_id": review_id},
            )

    update_payload = {
        "vendor_reply": body.reply,
        "vendor_reply_at": _iso(now),
    }
    update_response = (
        service_client.client.table("reviews")
        .update(update_payload)
        .eq("id", review_id)
        .execute()
    )
    updated_rows = _rows(update_response)
    if not updated_rows:
        raise AppError(
            code="internal_error",
            message="Failed to save vendor reply",
            http_status=500,
        )
    return _to_review_response(updated_rows[0])
