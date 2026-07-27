"""M17-P06 — the vendor's private view of their own clips.

Three guards apply to every route here, in this order, and none of them is
optional:

1. ``require_role("vendor")`` — the caller holds the role;
2. ``require_vendor_scope`` — D-V7: the caller owns a **KYC-verified** vendor row,
   and the vendor id comes from that row rather than from anything the request
   said;
3. **ownership on the object itself** — every clip and every listing touched here
   is re-checked against that vendor id.

The third check is not redundant with the second. Scope answers "who are you";
ownership answers "is this yours" — and a route that only asks the first is how
an id in a URL becomes another vendor's data.

Cross-vendor listing links are refused here *and* by the ``clip_products_guard``
trigger from M17-P01. The trigger is the backstop, not the only check: a database
error surfaces as a 500 with no useful message, and a vendor who mistyped
deserves a 403 that says what went wrong.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, Final, Protocol

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.media.authz import VendorScope, require_vendor_scope
from app.schemas.base import StrictModel
from app.services.clips import quota
from fastapi import APIRouter, Depends
from pydantic import Field

router = APIRouter(prefix="/vendor/clips", tags=["vendor-clips"])

CLIPS_TABLE: Final = "video_clips"
CLIP_PRODUCTS_TABLE: Final = "clip_products"
LISTINGS_TABLE: Final = "vendor_listings"
VENDORS_TABLE: Final = "vendors"

MAX_LINKS_PER_CLIP: Final = 3
RATE_LIMIT_PER_MINUTE: Final = 30


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# --- Schemas ----------------------------------------------------------------
class ClipLinkOut(StrictModel):
    listing_id: str
    title: str | None
    price_ngwee: int
    sort_order: int


class VendorClipOut(StrictModel):
    id: str
    status: str
    caption: str | None
    category_id: str | None
    poster_url: str | None
    duration_s: int | None
    #: Present only once the transcode callback has run. Absent means "still
    #: processing", which the studio must not render as "live".
    renditions: dict[str, Any]
    like_count: int
    comment_count: int
    view_count: int
    rejection_reason: str | None
    published_at: str | None
    taken_down_at: str | None
    created_at: str | None
    listings: list[ClipLinkOut]


class VendorClipListResponse(StrictModel):
    items: list[VendorClipOut]
    weekly_cap: int
    remaining_this_week: int
    window_days: int


class ClipStatsOut(StrictModel):
    clip_id: str
    status: str
    view_count: int
    like_count: int
    comment_count: int
    orders_attributed: int


class LinkListingRequest(StrictModel):
    listing_id: str = Field(min_length=1)
    sort_order: int = Field(default=0, ge=0, lt=MAX_LINKS_PER_CLIP)


class LinkListingResponse(StrictModel):
    clip_id: str
    listings: list[ClipLinkOut]


# --- Helpers ----------------------------------------------------------------
def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _rate_limit(service_client: ServiceRoleClient, *, scope: str, key: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=scope,
        key=key,
        window=timedelta(minutes=1),
        limit=RATE_LIMIT_PER_MINUTE,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="vendor.clips.errors.rateLimited",
            message="Too many clip requests",
        )


def _own_clip(
    service_client: ServiceRoleClient, *, clip_id: str, vendor_id: str
) -> dict[str, Any]:
    """Load a clip that belongs to this vendor, or 404.

    404 rather than 403 for someone else's clip: telling a vendor "that clip
    exists but is not yours" confirms a competitor's clip id, and there is no
    legitimate reason for them to learn it.
    """
    rows = _rows(
        service_client.client.table(CLIPS_TABLE)
        .select("*")
        .eq("id", clip_id)
        .maybe_single()
        .execute()
    )
    if not rows or str(rows[0].get("vendor_id")) != vendor_id:
        raise AppError(
            code="not_found",
            message="Clip not found",
            http_status=404,
            details={"clip_id": clip_id},
        )
    return rows[0]


def _links_for(
    service_client: ServiceRoleClient, clip_ids: list[str]
) -> dict[str, list[ClipLinkOut]]:
    if not clip_ids:
        return {}
    links = _rows(
        service_client.client.table(CLIP_PRODUCTS_TABLE)
        .select("clip_id, listing_id, sort_order")
        .in_("clip_id", clip_ids)
        .execute()
    )
    if not links:
        return {}
    listing_rows = _rows(
        service_client.client.table(LISTINGS_TABLE)
        .select("id, title_override, price_ngwee, status")
        .in_("id", sorted({str(link["listing_id"]) for link in links}))
        .execute()
    )
    by_id = {str(row["id"]): row for row in listing_rows}

    grouped: dict[str, list[ClipLinkOut]] = {}
    for link in sorted(links, key=lambda item: int(item.get("sort_order") or 0)):
        listing = by_id.get(str(link["listing_id"]))
        if listing is None:
            continue
        grouped.setdefault(str(link["clip_id"]), []).append(
            ClipLinkOut(
                listing_id=str(listing["id"]),
                title=listing.get("title_override"),
                price_ngwee=int(listing.get("price_ngwee") or 0),
                sort_order=int(link.get("sort_order") or 0),
            )
        )
    return grouped


def _vendor_tier(service_client: ServiceRoleClient, vendor_id: str) -> int:
    rows = _rows(
        service_client.client.table(VENDORS_TABLE)
        .select("kyc_tier")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    if not rows:
        return 1
    try:
        return max(1, int(rows[0].get("kyc_tier") or 1))
    except (TypeError, ValueError):
        return 1


def _to_out(clip: dict[str, Any], links: list[ClipLinkOut]) -> VendorClipOut:
    renditions = clip.get("renditions")
    return VendorClipOut(
        id=str(clip["id"]),
        status=str(clip.get("status") or ""),
        caption=clip.get("caption"),
        category_id=str(clip["category_id"]) if clip.get("category_id") else None,
        poster_url=clip.get("poster_url"),
        duration_s=clip.get("duration_s"),
        renditions=renditions if isinstance(renditions, dict) else {},
        like_count=int(clip.get("like_count") or 0),
        comment_count=int(clip.get("comment_count") or 0),
        view_count=int(clip.get("view_count") or 0),
        rejection_reason=clip.get("rejection_reason"),
        published_at=str(clip["published_at"]) if clip.get("published_at") else None,
        taken_down_at=str(clip["taken_down_at"]) if clip.get("taken_down_at") else None,
        created_at=str(clip["created_at"]) if clip.get("created_at") else None,
        listings=links,
    )


def _orders_attributed(service_client: ServiceRoleClient, clip_id: str) -> int:
    """Orders credited to a clip, read from the analytics stream.

    Best-effort: an analytics outage must not take the studio down with it, so a
    failed read reports zero rather than erroring. The number is informational,
    not money.
    """
    try:
        rows = _rows(
            service_client.client.table("analytics_events")
            .select("id")
            .eq("entity_type", "video_clip")
            .eq("entity_id", clip_id)
            .eq("event_type", "clip_add_to_cart")
            .execute()
        )
    except Exception:
        return 0
    return len(rows)


# --- Routes -----------------------------------------------------------------
@router.get("", response_model=VendorClipListResponse)
async def list_my_clips(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    scope: Annotated[VendorScope, Depends(require_vendor_scope)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorClipListResponse:
    """Every clip this vendor owns, in every state, with the live quota."""
    clips = _rows(
        service_client.client.table(CLIPS_TABLE)
        .select("*")
        .eq("vendor_id", scope.vendor_id)
        .order("created_at", desc=True)
        .execute()
    )
    links = _links_for(service_client, [str(clip["id"]) for clip in clips])
    remaining, cap = quota.remaining_quota(
        service_client,
        vendor_id=scope.vendor_id,
        tier=_vendor_tier(service_client, scope.vendor_id),
    )
    return VendorClipListResponse(
        items=[_to_out(clip, links.get(str(clip["id"]), [])) for clip in clips],
        weekly_cap=cap,
        remaining_this_week=remaining,
        window_days=quota.WINDOW.days,
    )


@router.get("/{clip_id}", response_model=VendorClipOut)
async def get_my_clip(
    clip_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    scope: Annotated[VendorScope, Depends(require_vendor_scope)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VendorClipOut:
    clip = _own_clip(service_client, clip_id=clip_id, vendor_id=scope.vendor_id)
    links = _links_for(service_client, [clip_id])
    return _to_out(clip, links.get(clip_id, []))


@router.get("/{clip_id}/stats", response_model=ClipStatsOut)
async def get_my_clip_stats(
    clip_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    scope: Annotated[VendorScope, Depends(require_vendor_scope)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ClipStatsOut:
    clip = _own_clip(service_client, clip_id=clip_id, vendor_id=scope.vendor_id)
    return ClipStatsOut(
        clip_id=clip_id,
        status=str(clip.get("status") or ""),
        view_count=int(clip.get("view_count") or 0),
        like_count=int(clip.get("like_count") or 0),
        comment_count=int(clip.get("comment_count") or 0),
        orders_attributed=_orders_attributed(service_client, clip_id),
    )


@router.post("/{clip_id}/listings", response_model=LinkListingResponse)
async def link_listing(
    clip_id: str,
    body: LinkListingRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    scope: Annotated[VendorScope, Depends(require_vendor_scope)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> LinkListingResponse:
    """Link one of the vendor's **own** active listings to their own clip."""
    _own_clip(service_client, clip_id=clip_id, vendor_id=scope.vendor_id)
    _rate_limit(service_client, scope="clip_link", key=current_user.id)

    listing_rows = _rows(
        service_client.client.table(LISTINGS_TABLE)
        .select("id, vendor_id, status")
        .eq("id", body.listing_id)
        .maybe_single()
        .execute()
    )
    # Ownership before existence in the message: a vendor must not be able to
    # probe which listing ids exist by watching which error they get.
    if not listing_rows or str(listing_rows[0].get("vendor_id")) != scope.vendor_id:
        raise AppError(
            code="listing_not_owned",
            message="Listing does not belong to this vendor",
            http_status=403,
            details={"listing_id": body.listing_id},
        )
    if str(listing_rows[0].get("status")) != "active":
        raise AppError(
            code="listing_not_active",
            message="Only an active listing can be linked to a clip",
            http_status=422,
            details={"listing_id": body.listing_id},
        )

    existing = _rows(
        service_client.client.table(CLIP_PRODUCTS_TABLE)
        .select("listing_id")
        .eq("clip_id", clip_id)
        .execute()
    )
    if any(str(row.get("listing_id")) == body.listing_id for row in existing):
        # Already linked. Idempotent: re-tapping "add" is not an error.
        links = _links_for(service_client, [clip_id])
        return LinkListingResponse(clip_id=clip_id, listings=links.get(clip_id, []))

    if len(existing) >= MAX_LINKS_PER_CLIP:
        raise AppError(
            code="clip_link_limit",
            message="A clip may link at most three listings",
            http_status=422,
            details={"max_links": MAX_LINKS_PER_CLIP},
        )

    service_client.client.table(CLIP_PRODUCTS_TABLE).insert(
        {
            "clip_id": clip_id,
            "listing_id": body.listing_id,
            "sort_order": body.sort_order,
        }
    ).execute()

    links = _links_for(service_client, [clip_id])
    return LinkListingResponse(clip_id=clip_id, listings=links.get(clip_id, []))


@router.delete("/{clip_id}/listings/{listing_id}", response_model=LinkListingResponse)
async def unlink_listing(
    clip_id: str,
    listing_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    scope: Annotated[VendorScope, Depends(require_vendor_scope)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> LinkListingResponse:
    _own_clip(service_client, clip_id=clip_id, vendor_id=scope.vendor_id)
    _rate_limit(service_client, scope="clip_link", key=current_user.id)

    service_client.client.table(CLIP_PRODUCTS_TABLE).delete().eq("clip_id", clip_id).eq(
        "listing_id", listing_id
    ).execute()

    links = _links_for(service_client, [clip_id])
    return LinkListingResponse(clip_id=clip_id, listings=links.get(clip_id, []))
