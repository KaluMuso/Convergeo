"""Vendor sourcing hub (docs/plan/vendor-sourcing-hub.md) — vendor-only.

Read-only discovery of other vendors' wholesale / Made in Zambia listings,
supplier shops and business services, plus a data-only import-request queue.
Wholesale tier prices are vendor-app only (D28/D36): every route here requires
the ``vendor`` role and never serves customers or anonymous callers.

No payments, orders or ledger rows are created from anything in this module.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import POLICIES, STANDARD_WRITE, RateLimitPolicy, route_id
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import NgweeInt, StrictModel
from app.services.kyc.caps import _load_vendor_for_owner
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.listings.demo import fetch_demo_listing_ids
from app.services.moderation.prohibited import screen_listing
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/vendor/sourcing", tags=["vendor-sourcing"])

SupplierType = Literal["wholesaler", "manufacturer", "importer", "service_provider"]
Tab = Literal["suppliers", "made_in_zambia", "services"]
MizStatus = Literal["claimed", "approved", "rejected"]

#: Service verticals shown as business services (``logistics`` and ``packaging``
#: are first-class verticals in ``services_listings.ServiceVertical``).
BUSINESS_SERVICE_VERTICALS: Final[tuple[str, ...]] = (
    "printing-creative",
    "tech-services",
    "logistics",
    "packaging",
)
CANDIDATE_CAP: Final = 300
MAX_PAGE: Final = 24
VERIFIED_MIN_KYC_TIER: Final = 2
#: Import requests share the registered ``write_standard`` counter scope (a new scope
#: would violate rate_counters_scope_check) under a distinct key with a 1-day window.
IMPORT_DAILY_LIMIT: Final = RateLimitPolicy(
    scope=STANDARD_WRITE.scope, limit=5, window=timedelta(days=1)
)
MIZ_REFERENCE_MAX: Final = 80
_UUID_RE: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

for _method, _path in (
    ("PUT", "/vendor/sourcing/profile"),
    ("PUT", "/vendor/sourcing/listings/{listing_id}/made-in-zambia"),
    ("POST", "/vendor/sourcing/import-requests"),
    ("POST", "/vendor/sourcing/import-requests/{request_id}/cancel"),
):
    POLICIES.setdefault(route_id(_method, _path), STANDARD_WRITE)

REQUEST_COLUMNS: Final = (
    "id, vendor_id, title, description, reference_url, image_urls, quantity, unit, "
    "target_unit_price_ngwee, destination_city, status, created_at, updated_at"
)
QUOTE_COLUMNS: Final = (
    "id, request_id, partner_label, product_ngwee, freight_ngwee, duty_ngwee, "
    "clearing_ngwee, other_ngwee, total_ngwee, lead_time_days, valid_until, notes, "
    "is_estimate, created_at"
)


def rows_of(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _limit(client: Any, user_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=STANDARD_WRITE.scope,
        key=f"sourcing:{user_id}",
        window=STANDARD_WRITE.window,
        limit=STANDARD_WRITE.limit,
        client=client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after, message_key="vendor.sourcing.errors.rateLimited"
        )


def _not_found(message: str = "Not found") -> AppError:
    return AppError(code="not_found", message=message, http_status=404)


def _is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


# --- Schemas ---------------------------------------------------------------
class SourcingItem(BaseModel):
    kind: Literal["listing", "shop", "service"]
    id: str
    title: str
    image_public_id: str | None = None
    image_url: str | None = None
    price_ngwee: int | None = None
    price_tiers: list[dict[str, Any]] | None = None
    #: True when bulk/tier pricing exists but the viewing vendor is not verified
    #: (kyc_tier < 2): price fields are withheld server-side, not just hidden in the UI.
    prices_locked: bool = False
    moq: int | None = None
    wholesale: bool = False
    made_in_zambia: bool = False
    vendor_id: str
    shop_name: str
    shop_slug: str | None = None
    landmark: str | None = None
    verified: bool = False
    whatsapp_msisdn: str | None = None
    supplier_types: list[str] = []
    service_category: str | None = None


class SourcingSearchResponse(BaseModel):
    tab: Tab
    viewer_verified: bool = False
    items: list[SourcingItem]
    next_offset: int | None = None


class SourcingProfile(BaseModel):
    supplier_types: list[SupplierType]


class SourcingProfileBody(StrictModel):
    supplier_types: list[SupplierType] = Field(max_length=4)

    @field_validator("supplier_types")
    @classmethod
    def dedupe(cls, value: list[SupplierType]) -> list[SupplierType]:
        return list(dict.fromkeys(value))


class OwnListing(BaseModel):
    id: str
    title: str
    status: str
    wholesale: bool
    #: null = no claim; claimed = awaiting admin; approved = public badge; rejected.
    made_in_zambia_status: MizStatus | None = None
    made_in_zambia_reference: str | None = None
    made_in_zambia_review_note: str | None = None


class MadeInZambiaBody(StrictModel):
    claim: bool
    reference: str | None = Field(default=None, max_length=MIZ_REFERENCE_MAX)

    @field_validator("reference")
    @classmethod
    def clean_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) < 3:
            raise ValueError("reference is too short")
        return cleaned


class ImportRequestBody(StrictModel):
    title: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    reference_url: str | None = Field(default=None, max_length=500)
    image_urls: list[str] = Field(default_factory=list, max_length=5)
    quantity: int = Field(ge=1, le=1_000_000)
    unit: str = Field(default="pcs", min_length=1, max_length=20)
    target_unit_price_ngwee: NgweeInt | None = Field(default=None, gt=0, le=100_000_000_000)
    destination_city: str | None = Field(default=None, min_length=2, max_length=60)

    @field_validator("title", "unit")
    @classmethod
    def strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("reference_url")
    @classmethod
    def https_only(cls, value: str | None) -> str | None:
        return _check_https(value) if value is not None else None

    @field_validator("image_urls")
    @classmethod
    def https_images(cls, value: list[str]) -> list[str]:
        return [_check_https(item) for item in value]


def _check_https(value: str) -> str:
    cleaned = value.strip()
    if not re.fullmatch(r"https://[^\s]{1,480}", cleaned):
        raise ValueError("must be an https URL")
    return cleaned


class QuoteOut(BaseModel):
    id: str
    request_id: str
    partner_label: str | None = None
    product_ngwee: int
    freight_ngwee: int
    duty_ngwee: int
    clearing_ngwee: int
    other_ngwee: int
    total_ngwee: int
    lead_time_days: int | None = None
    valid_until: str | None = None
    notes: str | None = None
    is_estimate: bool = True
    created_at: str


class ImportRequestOut(BaseModel):
    id: str
    title: str
    description: str | None = None
    reference_url: str | None = None
    image_urls: list[str] = []
    quantity: int
    unit: str
    target_unit_price_ngwee: int | None = None
    destination_city: str | None = None
    status: str
    created_at: str
    updated_at: str
    latest_quote: QuoteOut | None = None


def quote_from_row(row: dict[str, Any]) -> QuoteOut:
    return QuoteOut(
        id=str(row["id"]),
        request_id=str(row["request_id"]),
        partner_label=row.get("partner_label"),
        product_ngwee=int(row["product_ngwee"]),
        freight_ngwee=int(row["freight_ngwee"]),
        duty_ngwee=int(row["duty_ngwee"]),
        clearing_ngwee=int(row["clearing_ngwee"]),
        other_ngwee=int(row.get("other_ngwee") or 0),
        total_ngwee=int(row["total_ngwee"]),
        lead_time_days=row.get("lead_time_days"),
        valid_until=str(row["valid_until"]) if row.get("valid_until") else None,
        notes=row.get("notes"),
        is_estimate=True,
        created_at=str(row["created_at"]),
    )


def request_from_row(row: dict[str, Any], quote: dict[str, Any] | None = None) -> ImportRequestOut:
    return ImportRequestOut(
        id=str(row["id"]),
        title=str(row["title"]),
        description=row.get("description"),
        reference_url=row.get("reference_url"),
        image_urls=list(row.get("image_urls") or []),
        quantity=int(row["quantity"]),
        unit=str(row.get("unit") or "pcs"),
        target_unit_price_ngwee=(
            int(row["target_unit_price_ngwee"])
            if row.get("target_unit_price_ngwee") is not None
            else None
        ),
        destination_city=row.get("destination_city"),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        latest_quote=quote_from_row(quote) if quote else None,
    )


def latest_quotes(client: Any, request_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not request_ids:
        return {}
    rows = rows_of(
        client.table("import_request_quotes")
        .select(QUOTE_COLUMNS)
        .in_("request_id", request_ids)
        .order("created_at", desc=True)
        .execute()
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:  # newest first
        latest.setdefault(str(row["request_id"]), row)
    return latest


# --- Search ----------------------------------------------------------------
def _vendor_embed(row: dict[str, Any]) -> dict[str, Any]:
    embed = row.get("vendors")
    if isinstance(embed, list):
        embed = embed[0] if embed else {}
    return embed if isinstance(embed, dict) else {}


def _landmark(vendor: dict[str, Any]) -> str | None:
    for loc in vendor.get("vendor_locations") or []:
        if isinstance(loc, dict) and loc.get("landmark"):
            return str(loc["landmark"])
    return None


def _verified(vendor: dict[str, Any]) -> bool:
    tier = vendor.get("kyc_tier")
    return isinstance(tier, int) and tier >= VERIFIED_MIN_KYC_TIER


def _matches(q: str | None, *parts: str | None) -> bool:
    if not q:
        return True
    needle = q.lower()
    return any(needle in (part or "").lower() for part in parts)


def _listing_item(row: dict[str, Any], *, viewer_verified: bool) -> SourcingItem:
    vendor = _vendor_embed(row)
    product = row.get("products") if isinstance(row.get("products"), dict) else {}
    images = sorted(
        (i for i in row.get("listing_images") or [] if isinstance(i, dict)),
        key=lambda i: i.get("position") or 0,
    )
    wholesale = bool(row.get("wholesale"))
    tiers = row.get("price_tiers") if wholesale else None
    has_bulk = wholesale or isinstance(tiers, list)
    locked = has_bulk and not viewer_verified
    if locked:
        tiers = None
    return SourcingItem(
        kind="listing",
        id=str(row["id"]),
        title=str(row.get("title_override") or (product or {}).get("name") or ""),
        image_public_id=images[0].get("cloudinary_public_id") if images else None,
        price_ngwee=(
            int(row["price_ngwee"]) if row.get("price_ngwee") is not None and not locked else None
        ),
        price_tiers=tiers if isinstance(tiers, list) else None,
        prices_locked=locked,
        moq=int(row.get("moq") or 1),
        wholesale=wholesale,
        made_in_zambia=row.get("made_in_zambia_status") == "approved",
        vendor_id=str(row["vendor_id"]),
        shop_name=str(vendor.get("display_name") or ""),
        shop_slug=vendor.get("slug"),
        landmark=_landmark(vendor),
        verified=_verified(vendor),
        whatsapp_msisdn=vendor.get("whatsapp_msisdn"),
        supplier_types=list(vendor.get("supplier_types") or []),
    )


def _shop_item(row: dict[str, Any]) -> SourcingItem:
    return SourcingItem(
        kind="shop",
        id=str(row["id"]),
        title=str(row.get("display_name") or ""),
        vendor_id=str(row["id"]),
        shop_name=str(row.get("display_name") or ""),
        shop_slug=row.get("slug"),
        landmark=_landmark(row),
        verified=_verified(row),
        whatsapp_msisdn=row.get("whatsapp_msisdn"),
        supplier_types=list(row.get("supplier_types") or []),
    )


def _service_item(row: dict[str, Any]) -> SourcingItem:
    vendor = _vendor_embed(row)
    images = row.get("portfolio_images") or []
    return SourcingItem(
        kind="service",
        id=str(row["id"]),
        title=str(row.get("title") or ""),
        image_url=str(images[0]) if images else None,
        price_ngwee=(
            int(row["from_price_ngwee"]) if row.get("from_price_ngwee") is not None else None
        ),
        vendor_id=str(row["vendor_id"]),
        shop_name=str(vendor.get("display_name") or ""),
        shop_slug=vendor.get("slug"),
        landmark=row.get("service_area"),
        verified=_verified(vendor),
        whatsapp_msisdn=vendor.get("whatsapp_msisdn"),
        supplier_types=list(vendor.get("supplier_types") or []),
        service_category=row.get("category"),
    )


_OWN_LISTING_COLUMNS = (
    "id, title_override, status, wholesale, made_in_zambia_status, "
    "made_in_zambia_reference, made_in_zambia_review_note"
)
_VENDOR_EMBED = (
    "vendors!inner(id, slug, display_name, status, kyc_tier, whatsapp_msisdn, "
    "supplier_types, vendor_locations(landmark))"
)
_LISTING_SELECT = (
    "id, vendor_id, product_id, title_override, price_ngwee, wholesale, price_tiers, moq, "
    "made_in_zambia_status, status, products(name, category_id), "
    "listing_images(cloudinary_public_id, position), " + _VENDOR_EMBED
)
_SERVICE_SELECT = (
    "id, vendor_id, category, title, description, service_area, from_price_ngwee, "
    "portfolio_images, status, " + _VENDOR_EMBED
)


def _search_listings(
    client: Any,
    *,
    own_vendor_id: str,
    tab: str,
    q: str | None,
    category: str | None,
    viewer_verified: bool,
) -> list[SourcingItem]:
    query = (
        client.table("vendor_listings")
        .select(_LISTING_SELECT)
        .eq("status", "active")
        .eq("vendors.status", "active")
        .neq("vendor_id", own_vendor_id)
    )
    query = (
        query.eq("wholesale", True)
        if tab == "suppliers"
        else query.eq("made_in_zambia_status", "approved")
    )
    rows = rows_of(query.order("updated_at", desc=True).limit(CANDIDATE_CAP).execute())
    demo = fetch_demo_listing_ids(client, [str(r["id"]) for r in rows if r.get("id")])
    out: list[SourcingItem] = []
    for row in rows:
        if str(row.get("id")) in demo:
            continue
        product = row.get("products") if isinstance(row.get("products"), dict) else {}
        if category and str((product or {}).get("category_id") or "") != category:
            continue
        item = _listing_item(row, viewer_verified=viewer_verified)
        if _matches(q, item.title, item.shop_name):
            out.append(item)
    return out


def _search_shops(
    client: Any, *, own_vendor_id: str, kind: str, q: str | None
) -> list[SourcingItem]:
    rows = rows_of(
        client.table("vendors")
        .select(
            "id, slug, display_name, status, kyc_tier, whatsapp_msisdn, supplier_types, "
            "vendor_locations(landmark)"
        )
        .eq("status", "active")
        .neq("id", own_vendor_id)
        .contains("supplier_types", [kind])
        .limit(CANDIDATE_CAP)
        .execute()
    )
    return [_shop_item(r) for r in rows if _matches(q, r.get("display_name"))]


def _search_services(
    client: Any, *, own_vendor_id: str, q: str | None, category: str | None
) -> list[SourcingItem]:
    verticals = (
        [category] if category in BUSINESS_SERVICE_VERTICALS else list(BUSINESS_SERVICE_VERTICALS)
    )
    rows = rows_of(
        client.table("services")
        .select(_SERVICE_SELECT)
        .eq("status", "active")
        .eq("vendors.status", "active")
        .neq("vendor_id", own_vendor_id)
        .in_("category", verticals)
        .order("updated_at", desc=True)
        .limit(CANDIDATE_CAP)
        .execute()
    )
    return [
        _service_item(r)
        for r in rows
        if _matches(q, r.get("title"), r.get("description"), _vendor_embed(r).get("display_name"))
    ]


@router.get("/search", response_model=SourcingSearchResponse)
def search_sourcing(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    tab: Annotated[Tab, Query()] = "suppliers",
    q: Annotated[str | None, Query(max_length=80)] = None,
    category: Annotated[str | None, Query(max_length=64)] = None,
    offset: Annotated[int, Query(ge=0, le=CANDIDATE_CAP)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 12,
) -> SourcingSearchResponse:
    client: Any = service_client.client
    me = _load_vendor_for_owner(service_client, current_user.id)
    own = str(me["id"])
    viewer_verified = _verified(me)
    needle = re.sub(r"[%_\\]", "", q.strip()) if q else None
    needle = needle or None
    if category is not None and tab != "services" and not _is_uuid(category):
        category = None
    if tab == "services":
        items = _search_services(client, own_vendor_id=own, q=needle, category=category)
    else:
        # A product category never matches a shop, so shops show only unfiltered.
        # Made in Zambia is approval-only: no shop-level (manufacturer) fallback.
        items = (
            _search_shops(client, own_vendor_id=own, kind="wholesaler", q=needle)
            if tab == "suppliers" and category is None
            else []
        )
        items += _search_listings(
            client,
            own_vendor_id=own,
            tab=tab,
            q=needle,
            category=category,
            viewer_verified=viewer_verified,
        )
    page = items[offset : offset + limit]
    next_offset = offset + limit if offset + limit < len(items) else None
    return SourcingSearchResponse(
        tab=tab, viewer_verified=viewer_verified, items=page, next_offset=next_offset
    )


# --- Supplier profile + Made in Zambia ---------------------------------------
@router.get("/profile", response_model=SourcingProfile)
def get_sourcing_profile(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> SourcingProfile:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    rows = rows_of(
        service_client.client.table("vendors")
        .select("id, supplier_types")
        .eq("id", str(vendor["id"]))
        .execute()
    )
    types = list(rows[0].get("supplier_types") or []) if rows else []
    return SourcingProfile(supplier_types=types)


@router.put("/profile", response_model=SourcingProfile)
def put_sourcing_profile(
    body: SourcingProfileBody,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> SourcingProfile:
    client: Any = service_client.client
    _limit(client, current_user.id)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    client.table("vendors").update({"supplier_types": body.supplier_types}).eq(
        "id", str(vendor["id"])
    ).execute()
    return SourcingProfile(supplier_types=body.supplier_types)


@router.get("/listings", response_model=list[OwnListing])
def list_own_listings(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[OwnListing]:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    rows = rows_of(
        service_client.client.table("vendor_listings")
        .select(f"{_OWN_LISTING_COLUMNS}, products(name)")
        .eq("vendor_id", str(vendor["id"]))
        .in_("status", ["draft", "active", "paused"])
        .order("updated_at", desc=True)
        .limit(200)
        .execute()
    )
    out: list[OwnListing] = []
    for row in rows:
        product = row.get("products") if isinstance(row.get("products"), dict) else {}
        out.append(
            OwnListing(
                id=str(row["id"]),
                title=str(row.get("title_override") or (product or {}).get("name") or ""),
                status=str(row["status"]),
                wholesale=bool(row.get("wholesale")),
                made_in_zambia_status=row.get("made_in_zambia_status"),
                made_in_zambia_reference=row.get("made_in_zambia_reference"),
                made_in_zambia_review_note=row.get("made_in_zambia_review_note"),
            )
        )
    return out


@router.put("/listings/{listing_id}/made-in-zambia", response_model=OwnListing)
def set_made_in_zambia(
    listing_id: UUID,
    body: MadeInZambiaBody,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> OwnListing:
    """Vendor files (or withdraws) a Made in Zambia CLAIM. Approval is admin-only."""
    client: Any = service_client.client
    _limit(client, current_user.id)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    rows = rows_of(
        client.table("vendor_listings")
        .select(f"{_OWN_LISTING_COLUMNS}, products(name)")
        .eq("id", str(listing_id))
        .eq("vendor_id", str(vendor["id"]))
        .execute()
    )
    if not rows:
        raise _not_found("Listing not found")  # not yours = not found (no enumeration)
    row = dict(rows[0])
    current = row.get("made_in_zambia_status")
    patch: dict[str, Any] | None = None
    if not body.claim:
        if current is not None:
            patch = {"made_in_zambia_status": None}
    elif current != "approved":  # an approved claim is already final; claiming again is a no-op
        patch = {
            "made_in_zambia_status": "claimed",
            "made_in_zambia_reference": body.reference,
            "made_in_zambia_claimed_at": datetime.now(UTC).isoformat(),
        }
    if patch is not None:
        client.table("vendor_listings").update(patch).eq("id", str(listing_id)).eq(
            "vendor_id", str(vendor["id"])
        ).execute()
        row.update(patch)
        if patch["made_in_zambia_status"] is None:
            row["made_in_zambia_reference"] = None
        if patch["made_in_zambia_status"] in (None, "claimed"):
            row["made_in_zambia_review_note"] = None
    product = row.get("products") if isinstance(row.get("products"), dict) else {}
    return OwnListing(
        id=str(row["id"]),
        title=str(row.get("title_override") or (product or {}).get("name") or ""),
        status=str(row["status"]),
        wholesale=bool(row.get("wholesale")),
        made_in_zambia_status=row.get("made_in_zambia_status"),
        made_in_zambia_reference=row.get("made_in_zambia_reference"),
        made_in_zambia_review_note=row.get("made_in_zambia_review_note"),
    )


# --- Import requests (data only) ------------------------------------------------
@router.post("/import-requests", response_model=ImportRequestOut, status_code=201)
def create_import_request(
    body: ImportRequestBody,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ImportRequestOut:
    client: Any = service_client.client
    allowed, retry_after = bump_rate_counter(
        scope=IMPORT_DAILY_LIMIT.scope,
        key=f"import-request:{current_user.id}",
        window=IMPORT_DAILY_LIMIT.window,
        limit=IMPORT_DAILY_LIMIT.limit,
        client=client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after, message_key="vendor.sourcing.errors.importRateLimited"
        )
    guard = screen_listing(title=body.title, description=body.description)
    if not guard.allowed:
        raise AppError(
            code="import_request.prohibited",
            message="Import request contains a prohibited item or keyword",
            http_status=422,
            details={"message_key": "vendor.sourcing.errors.prohibited"},
        )
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    payload = {
        "vendor_id": str(vendor["id"]),
        "requested_by": current_user.id,
        "title": body.title,
        "description": body.description,
        "reference_url": body.reference_url,
        "image_urls": body.image_urls,
        "quantity": body.quantity,
        "unit": body.unit,
        "target_unit_price_ngwee": body.target_unit_price_ngwee,
        "destination_city": body.destination_city,
        "status": "submitted",
    }
    created = rows_of(client.table("import_requests").insert(payload).execute())
    if not created:
        raise AppError(code="internal_error", message="Could not save request", http_status=500)
    return request_from_row(created[0])


@router.get("/import-requests", response_model=list[ImportRequestOut])
def list_import_requests(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[ImportRequestOut]:
    client: Any = service_client.client
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    rows = rows_of(
        client.table("import_requests")
        .select(REQUEST_COLUMNS)
        .eq("vendor_id", str(vendor["id"]))
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )
    quotes = latest_quotes(client, [str(r["id"]) for r in rows])
    return [request_from_row(r, quotes.get(str(r["id"]))) for r in rows]


@router.post("/import-requests/{request_id}/cancel", response_model=ImportRequestOut)
def cancel_import_request(
    request_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ImportRequestOut:
    client: Any = service_client.client
    _limit(client, current_user.id)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    rows = rows_of(
        client.table("import_requests")
        .select(REQUEST_COLUMNS)
        .eq("id", str(request_id))
        .eq("vendor_id", str(vendor["id"]))
        .execute()
    )
    if not rows:
        raise _not_found("Import request not found")
    row = rows[0]
    if row["status"] in ("closed", "cancelled"):
        return request_from_row(row)
    client.table("import_requests").update({"status": "cancelled"}).eq("id", str(request_id)).eq(
        "vendor_id", str(vendor["id"])
    ).execute()
    quotes = latest_quotes(client, [str(request_id)])
    return request_from_row({**row, "status": "cancelled"}, quotes.get(str(request_id)))
