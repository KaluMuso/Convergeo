from __future__ import annotations

import re
import statistics
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol, cast

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import NgweeInt, StrictModel
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.listings.demo import fetch_demo_service_ids, has_demo_media
from app.services.moderation.prohibited import screen_listing
from fastapi import APIRouter, Depends, Query
from pydantic import Field, field_validator, model_validator

router = APIRouter(tags=["services-listings"])

SERVICE_VERTICALS = (
    "beauty",
    "food-catering",
    "auto",
    "printing-creative",
    "home-services",
    "tech-services",
    "cleaning",
    "tailoring",
)

ServiceVertical = Literal[
    "beauty",
    "food-catering",
    "auto",
    "printing-creative",
    "home-services",
    "tech-services",
    "cleaning",
    "tailoring",
]

ServiceStatus = Literal["draft", "active", "paused"]
ResponseTimeTier = Literal["fast", "same_day", "slow"]

FAST_RESPONSE_SECONDS = 2 * 60 * 60
SAME_DAY_RESPONSE_SECONDS = 24 * 60 * 60
MAX_PORTFOLIO_IMAGES = 8
MAX_INCLUDES = 12
MAX_INCLUDE_LEN = 160


def _clean_includes(items: list[str]) -> list[str]:
    """Trim, drop empties, cap item length, and cap the count of include bullets."""
    cleaned = [item.strip()[:MAX_INCLUDE_LEN] for item in items if item.strip()]
    return cleaned[:MAX_INCLUDES]
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class _ServiceClient(Protocol):
    @property
    def client(self) -> Any: ...


class ProviderSummary(StrictModel):
    id: str
    slug: str
    display_name: str
    preferred_badge: bool = False
    response_time_tier: ResponseTimeTier | None = None


class ServiceBrowseItem(StrictModel):
    id: str
    slug: str
    title: str
    category: ServiceVertical
    description: str | None = None
    service_area: str | None = None
    from_price_ngwee: int | None = None
    portfolio_images: list[str] = Field(default_factory=list)
    provider: ProviderSummary


class ServiceBrowseResponse(StrictModel):
    items: list[ServiceBrowseItem]
    total: int
    verticals: list[str] = Field(default_factory=lambda: list(SERVICE_VERTICALS))


class ServiceDetailResponse(StrictModel):
    id: str
    slug: str
    title: str
    category: ServiceVertical
    description: str | None = None
    service_area: str | None = None
    from_price_ngwee: int | None = None
    bookable: bool = False
    booking_price_ngwee: int | None = None
    portfolio_images: list[str] = Field(default_factory=list)
    includes: list[str] = Field(default_factory=list)
    provider: ProviderSummary


class ServiceSummary(StrictModel):
    id: str
    slug: str
    title: str
    category: ServiceVertical
    description: str | None = None
    service_area: str | None = None
    from_price_ngwee: int | None = None
    bookable: bool = False
    booking_price_ngwee: int | None = None
    status: ServiceStatus
    portfolio_images: list[str] = Field(default_factory=list)
    includes: list[str] = Field(default_factory=list)


class ServiceVendorListResponse(StrictModel):
    items: list[ServiceSummary]


class ServiceCreateRequest(StrictModel):
    category: ServiceVertical
    title: str = Field(min_length=2, max_length=200)
    description: str | None = None
    service_area: str | None = None
    from_price_ngwee: NgweeInt | None = None
    bookable: bool = False
    booking_price_ngwee: NgweeInt | None = None
    portfolio_images: list[str] = Field(default_factory=list, max_length=MAX_PORTFOLIO_IMAGES)
    includes: list[str] = Field(default_factory=list, max_length=MAX_INCLUDES)
    status: ServiceStatus = "draft"

    @field_validator("from_price_ngwee", "booking_price_ngwee")
    @classmethod
    def validate_positive_price(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            msg = "price must be greater than zero when provided"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_bookable_price(self) -> ServiceCreateRequest:
        if self.bookable and not self.booking_price_ngwee:
            msg = "booking_price_ngwee is required (and must be > 0) when bookable is true"
            raise ValueError(msg)
        return self

    @field_validator("portfolio_images")
    @classmethod
    def validate_portfolio_images(cls, images: list[str]) -> list[str]:
        cleaned = [item.strip() for item in images if item.strip()]
        if len(cleaned) > MAX_PORTFOLIO_IMAGES:
            msg = f"At most {MAX_PORTFOLIO_IMAGES} portfolio images are allowed"
            raise ValueError(msg)
        return cleaned

    @field_validator("includes")
    @classmethod
    def validate_includes(cls, items: list[str]) -> list[str]:
        return _clean_includes(items)


class ServiceUpdateRequest(StrictModel):
    category: ServiceVertical | None = None
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    service_area: str | None = None
    from_price_ngwee: NgweeInt | None = None
    bookable: bool | None = None
    booking_price_ngwee: NgweeInt | None = None
    portfolio_images: list[str] | None = Field(default=None, max_length=MAX_PORTFOLIO_IMAGES)
    includes: list[str] | None = Field(default=None, max_length=MAX_INCLUDES)
    status: ServiceStatus | None = None

    @field_validator("from_price_ngwee", "booking_price_ngwee")
    @classmethod
    def validate_positive_price(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            msg = "price must be greater than zero when provided"
            raise ValueError(msg)
        return value

    @field_validator("portfolio_images")
    @classmethod
    def validate_portfolio_images(cls, images: list[str] | None) -> list[str] | None:
        if images is None:
            return None
        cleaned = [item.strip() for item in images if item.strip()]
        if len(cleaned) > MAX_PORTFOLIO_IMAGES:
            msg = f"At most {MAX_PORTFOLIO_IMAGES} portfolio images are allowed"
            raise ValueError(msg)
        return cleaned

    @field_validator("includes")
    @classmethod
    def validate_includes(cls, items: list[str] | None) -> list[str] | None:
        if items is None:
            return None
        return _clean_includes(items)


class ServiceMutationResponse(StrictModel):
    service: ServiceSummary


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


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    return None


def service_slug(service_id: str) -> str:
    """Public URL slug — services table has no slug column; use stable UUID."""
    return service_id


def compute_first_response_seconds(job_created_at: datetime, quote_created_at: datetime) -> float:
    return max(0.0, (quote_created_at - job_created_at).total_seconds())


def response_time_tier_from_seconds(median_seconds: float | None) -> ResponseTimeTier | None:
    """Map median first-response time to badge tier (fast <2h, same-day <24h, else slow)."""
    if median_seconds is None:
        return None
    if median_seconds < FAST_RESPONSE_SECONDS:
        return "fast"
    if median_seconds < SAME_DAY_RESPONSE_SECONDS:
        return "same_day"
    return "slow"


def response_time_tier_from_samples(seconds_samples: list[float]) -> ResponseTimeTier | None:
    if not seconds_samples:
        return None
    median = statistics.median(seconds_samples)
    return response_time_tier_from_seconds(float(median))


def _cached_response_time_tier(caps_snapshot: Any) -> ResponseTimeTier | None:
    if not isinstance(caps_snapshot, dict):
        return None
    raw = caps_snapshot.get("response_time_tier")
    if raw in ("fast", "same_day", "slow"):
        return cast(ResponseTimeTier, raw)
    return None


def response_time_tier(
    *,
    quote_rows: list[dict[str, Any]],
    job_rows_by_id: dict[str, dict[str, Any]],
    caps_snapshot: dict[str, Any] | None = None,
    prefer_cache: bool = True,
) -> ResponseTimeTier | None:
    """
    Compute provider response-time badge from job_quotes first-response history.

    Nightly n8n/internal job may refresh vendors.caps_snapshot.response_time_tier;
    when prefer_cache=True and a cached tier exists, return it (compute-on-read fallback).
    """
    if prefer_cache and caps_snapshot is not None:
        cached = _cached_response_time_tier(caps_snapshot)
        if cached is not None:
            return cached

    samples: list[float] = []
    for quote in quote_rows:
        job_id = str(quote.get("job_id") or "")
        job = job_rows_by_id.get(job_id)
        if job is None:
            continue
        job_created = _parse_datetime(job.get("created_at"))
        quote_created = _parse_datetime(quote.get("created_at"))
        if job_created is None or quote_created is None:
            continue
        samples.append(compute_first_response_seconds(job_created, quote_created))

    return response_time_tier_from_samples(samples)


def _load_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, slug, display_name, preferred_badge, caps_snapshot")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def _assert_vendor_owns_service(
    service_client: ServiceRoleClient,
    owner_user_id: str,
    service_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    vendor = _load_vendor_for_owner(service_client, owner_user_id)
    response = (
        service_client.client.table("services")
        .select("*")
        .eq("id", service_id)
        .eq("vendor_id", vendor["id"])
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Service not found",
            http_status=404,
            details={"message_key": "services.errors.not_found"},
        )
    return vendor, row


def _parse_vendor_embed(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None


def _fetch_response_tiers(
    client: Any,
    vendor_ids: list[str],
) -> dict[str, ResponseTimeTier | None]:
    if not vendor_ids:
        return {}

    vendors_response = (
        client.table("vendors")
        .select("id, caps_snapshot")
        .in_("id", vendor_ids)
        .execute()
    )
    caps_by_vendor: dict[str, dict[str, Any] | None] = {}
    for row in _rows(vendors_response):
        vendor_id = str(row.get("id") or "")
        snapshot = row.get("caps_snapshot")
        caps_by_vendor[vendor_id] = snapshot if isinstance(snapshot, dict) else None

    quotes_response = (
        client.table("job_quotes")
        .select("job_id, provider_vendor_id, created_at")
        .in_("provider_vendor_id", vendor_ids)
        .execute()
    )
    quote_rows = _rows(quotes_response)
    job_ids = list({str(row.get("job_id")) for row in quote_rows if row.get("job_id")})

    jobs_by_id: dict[str, dict[str, Any]] = {}
    if job_ids:
        jobs_response = (
            client.table("jobs").select("id, created_at").in_("id", job_ids).execute()
        )
        for row in _rows(jobs_response):
            jobs_by_id[str(row["id"])] = row

    tiers: dict[str, ResponseTimeTier | None] = {}
    for vendor_id in vendor_ids:
        vendor_quotes = [
            row for row in quote_rows if str(row.get("provider_vendor_id")) == vendor_id
        ]
        tiers[vendor_id] = response_time_tier(
            quote_rows=vendor_quotes,
            job_rows_by_id=jobs_by_id,
            caps_snapshot=caps_by_vendor.get(vendor_id),
        )
    return tiers


def _provider_from_vendor(
    vendor_row: dict[str, Any] | None,
    *,
    response_time_tier_value: ResponseTimeTier | None = None,
) -> ProviderSummary:
    if vendor_row is None:
        return ProviderSummary(id="", slug="", display_name="")
    return ProviderSummary(
        id=str(vendor_row.get("id") or ""),
        slug=str(vendor_row.get("slug") or ""),
        display_name=str(vendor_row.get("display_name") or ""),
        preferred_badge=bool(vendor_row.get("preferred_badge")),
        response_time_tier=response_time_tier_value,
    )


def _parse_images(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _parse_includes(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _clean_includes([str(item) for item in value if isinstance(item, str)])


def _to_browse_item(
    row: dict[str, Any],
    *,
    response_time_tier_value: ResponseTimeTier | None,
) -> ServiceBrowseItem:
    service_id = str(row["id"])
    vendor_row = _parse_vendor_embed(row.get("vendors"))
    return ServiceBrowseItem(
        id=service_id,
        slug=service_slug(service_id),
        title=str(row.get("title") or ""),
        category=row["category"],
        description=row.get("description"),
        service_area=row.get("service_area"),
        from_price_ngwee=row.get("from_price_ngwee"),
        portfolio_images=_parse_images(row.get("portfolio_images")),
        provider=_provider_from_vendor(
            vendor_row,
            response_time_tier_value=response_time_tier_value,
        ),
    )


def _to_detail(
    row: dict[str, Any],
    *,
    response_time_tier_value: ResponseTimeTier | None,
) -> ServiceDetailResponse:
    service_id = str(row["id"])
    vendor_row = _parse_vendor_embed(row.get("vendors"))
    return ServiceDetailResponse(
        id=service_id,
        slug=service_slug(service_id),
        title=str(row.get("title") or ""),
        category=row["category"],
        description=row.get("description"),
        service_area=row.get("service_area"),
        from_price_ngwee=row.get("from_price_ngwee"),
        bookable=bool(row.get("bookable")),
        booking_price_ngwee=row.get("booking_price_ngwee"),
        portfolio_images=_parse_images(row.get("portfolio_images")),
        includes=_parse_includes(row.get("includes")),
        provider=_provider_from_vendor(
            vendor_row,
            response_time_tier_value=response_time_tier_value,
        ),
    )


def _to_summary(row: dict[str, Any]) -> ServiceSummary:
    service_id = str(row["id"])
    return ServiceSummary(
        id=service_id,
        slug=service_slug(service_id),
        title=str(row.get("title") or ""),
        category=row["category"],
        description=row.get("description"),
        service_area=row.get("service_area"),
        from_price_ngwee=row.get("from_price_ngwee"),
        bookable=bool(row.get("bookable")),
        booking_price_ngwee=row.get("booking_price_ngwee"),
        status=row["status"],
        portfolio_images=_parse_images(row.get("portfolio_images")),
        includes=_parse_includes(row.get("includes")),
    )


def _sanitize_area(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"[%_\\]", "", value.strip())
    return cleaned or None


def build_browse_response(
    client: Any,
    *,
    category: ServiceVertical | None = None,
    area: str | None = None,
) -> ServiceBrowseResponse:
    query = (
        client.table("services")
        .select(
            "id, vendor_id, category, title, description, service_area, "
            "from_price_ngwee, portfolio_images, status, "
            "vendors!inner(id, slug, display_name, preferred_badge, status)"
        )
        .eq("status", "active")
        .eq("vendors.status", "active")
    )
    if category is not None:
        query = query.eq("category", category)
    area_filter = _sanitize_area(area)
    if area_filter is not None:
        query = query.ilike("service_area", f"%{area_filter}%")

    response = query.order("updated_at", desc=True).execute()
    rows = _rows(response)
    service_ids = [str(row.get("id")) for row in rows if row.get("id")]
    demo_service_ids = fetch_demo_service_ids(client, service_ids)
    public_rows = [row for row in rows if str(row.get("id") or "") not in demo_service_ids]
    vendor_ids = list(
        {str(row.get("vendor_id")) for row in public_rows if row.get("vendor_id")}
    )
    tiers = _fetch_response_tiers(client, vendor_ids)

    items = [
        _to_browse_item(
            row,
            response_time_tier_value=tiers.get(str(row.get("vendor_id") or "")),
        )
        for row in public_rows
    ]
    return ServiceBrowseResponse(items=items, total=len(items))


def resolve_service_id(slug_or_id: str) -> str:
    if UUID_RE.match(slug_or_id):
        return slug_or_id
    raise AppError(
        code="not_found",
        message="Service not found",
        http_status=404,
        details={"message_key": "services.errors.not_found"},
    )


@router.get("/services", response_model=ServiceBrowseResponse)
def browse_services(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    category: Annotated[ServiceVertical | None, Query()] = None,
    area: Annotated[str | None, Query(max_length=120)] = None,
) -> ServiceBrowseResponse:
    return build_browse_response(service_client.client, category=category, area=area)


@router.get("/services/{slug}", response_model=ServiceDetailResponse)
def get_service_detail(
    slug: str,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ServiceDetailResponse:
    service_id = resolve_service_id(slug)
    response = (
        service_client.client.table("services")
        .select(
            "id, vendor_id, category, title, description, service_area, "
            "from_price_ngwee, bookable, booking_price_ngwee, portfolio_images, includes, status, "
            "vendors!inner(id, slug, display_name, preferred_badge, status)"
        )
        .eq("id", service_id)
        .eq("status", "active")
        .eq("vendors.status", "active")
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None or has_demo_media(row.get("portfolio_images")):
        raise AppError(
            code="not_found",
            message="Service not found",
            http_status=404,
            details={"message_key": "services.errors.not_found"},
        )

    vendor_id = str(row.get("vendor_id") or "")
    tiers = _fetch_response_tiers(service_client.client, [vendor_id])
    return _to_detail(row, response_time_tier_value=tiers.get(vendor_id))


@router.get("/vendor/services", response_model=ServiceVendorListResponse)
def list_vendor_services(
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ServiceVendorListResponse:
    vendor = _load_vendor_for_owner(service_client, user.id)
    response = (
        service_client.client.table("services")
        .select(
            "id, category, title, description, service_area, from_price_ngwee, "
            "bookable, booking_price_ngwee, portfolio_images, includes, status"
        )
        .eq("vendor_id", vendor["id"])
        .order("updated_at", desc=True)
        .execute()
    )
    items = [_to_summary(row) for row in _rows(response)]
    return ServiceVendorListResponse(items=items)


@router.post("/vendor/services", response_model=ServiceMutationResponse)
def create_vendor_service(
    payload: ServiceCreateRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ServiceMutationResponse:
    vendor = _load_vendor_for_owner(service_client, user.id)
    guard = screen_listing(
        title=payload.title, description=payload.description, category=payload.category
    )
    if not guard.allowed:
        raise AppError(
            code="prohibited_listing",
            message="Service listing contains a prohibited category or keyword",
            http_status=422,
            details={
                "message_key": "vendor.listings.errors.submitFailed",
                "reason": guard.reason,
                "matched": guard.matched,
            },
        )
    insert_row = {
        "id": str(uuid.uuid4()),
        "vendor_id": vendor["id"],
        "category": payload.category,
        "title": payload.title.strip(),
        "description": payload.description,
        "service_area": payload.service_area,
        "from_price_ngwee": payload.from_price_ngwee,
        "bookable": payload.bookable,
        "booking_price_ngwee": payload.booking_price_ngwee,
        "portfolio_images": payload.portfolio_images,
        "includes": payload.includes,
        "status": payload.status,
    }
    response = service_client.client.table("services").insert(insert_row).execute()
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="internal_error",
            message="Failed to create service",
            http_status=500,
        )
    return ServiceMutationResponse(service=_to_summary(row))


@router.patch("/vendor/services/{service_id}", response_model=ServiceMutationResponse)
def update_vendor_service(
    service_id: str,
    payload: ServiceUpdateRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ServiceMutationResponse:
    _vendor, existing = _assert_vendor_owns_service(service_client, user.id, service_id)
    updates = payload.model_dump(exclude_unset=True)
    if "title" in updates and updates["title"] is not None:
        updates["title"] = updates["title"].strip()

    # Mirror the DB CHECK with a clean 422: the resulting service must have a
    # positive booking price if it is (or stays) bookable.
    effective_bookable = updates.get("bookable", existing.get("bookable"))
    effective_price = updates.get("booking_price_ngwee", existing.get("booking_price_ngwee"))
    if effective_bookable and not effective_price:
        raise AppError(
            code="validation_error",
            message="A bookable service must have a positive booking price",
            http_status=422,
            details={"message_key": "vendor.services.errors.bookablePrice"},
        )

    if not updates:
        return ServiceMutationResponse(service=_to_summary(existing))

    response = (
        service_client.client.table("services")
        .update(updates)
        .eq("id", service_id)
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="internal_error",
            message="Failed to update service",
            http_status=500,
        )
    return ServiceMutationResponse(service=_to_summary(row))
