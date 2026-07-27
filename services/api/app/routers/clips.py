"""M17-P03 — public clip feed and detail.

Two rules shape this module:

**Published-only, with no exceptions.** A non-published clip is invisible here
even to the vendor who owns it — their view is M17-P06's authenticated surface.
Keeping the public reader unconditional means there is no branch where a status
check could be forgotten.

**One request per card.** The feed item carries poster, duration, approximate
byte size per rendition, caption, vendor summary, linked listings and counters,
because a follow-up request per card on a 3G connection is exactly the cost D-V1
exists to avoid.

Byte honesty (D-V5) is served from `renditions[*].bytes`, so the size chip shown
before tap-to-play is the real transcoded size rather than an estimate.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Annotated, Any, Final, Protocol

from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.clips import ranking, state_machine
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/clips", tags=["clips"])

CLIPS_TABLE: Final = "video_clips"
CLIP_PRODUCTS_TABLE: Final = "clip_products"
LISTINGS_TABLE: Final = "vendor_listings"
VENDORS_TABLE: Final = "vendors"

MAX_PAGE_SIZE: Final = 20
#: Scored over a bounded candidate window rather than the whole table: ranking is
#: freshness-dominated, so a clip outside this window cannot win a slot anyway.
CANDIDATE_WINDOW: Final = 200


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# --- Schemas ----------------------------------------------------------------
class RenditionOut(StrictModel):
    url: str
    width: int
    #: D-V5 byte honesty: the real transcoded size, so the "~2 MB" chip is true.
    bytes: int | None = None


class LinkedListingOut(StrictModel):
    listing_id: str
    title: str | None
    price_ngwee: int


class VendorSummaryOut(StrictModel):
    vendor_id: str
    display_name: str | None
    slug: str | None


class ClipOut(StrictModel):
    id: str
    caption: str | None
    poster_url: str | None
    duration_s: int | None
    renditions: dict[str, RenditionOut]
    like_count: int
    comment_count: int
    view_count: int
    published_at: str | None
    vendor: VendorSummaryOut
    listings: list[LinkedListingOut]


class ClipFeedResponse(StrictModel):
    items: list[ClipOut]
    next_cursor: str | None


# --- Helpers ----------------------------------------------------------------
def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _encode_cursor(payload: dict[str, Any]) -> str:
    """Opaque, stable cursor. Deliberately not an OFFSET.

    OFFSET pagination on a feed that is still receiving new clips skips or
    repeats items as rows shift underneath it. Encoding the last item's sort key
    keeps the page boundary attached to the data rather than to a row number.
    """
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        decoded = json.loads(raw)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        # A malformed cursor is a client error, not a server one, and must not
        # silently fall back to page one — that would loop a broken client.
        raise AppError(
            code="invalid_cursor",
            message="Feed cursor is not valid",
            http_status=400,
        ) from None
    return decoded if isinstance(decoded, dict) else None


def _renditions(raw: Any) -> dict[str, RenditionOut]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, RenditionOut] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        if not isinstance(url, str) or not url:
            continue
        width = entry.get("width")
        out[str(name)] = RenditionOut(
            url=url,
            width=int(width) if isinstance(width, int) else 0,
            bytes=int(entry["bytes"]) if isinstance(entry.get("bytes"), int) else None,
        )
    return out


def _load_vendors(
    service_client: ServiceRoleClient, vendor_ids: list[str]
) -> dict[str, dict[str, Any]]:
    if not vendor_ids:
        return {}
    rows = _rows(
        service_client.client.table(VENDORS_TABLE)
        .select("id, display_name, slug, status")
        .in_("id", vendor_ids)
        .execute()
    )
    return {str(row["id"]): row for row in rows}


def _load_listings(
    service_client: ServiceRoleClient, clip_ids: list[str]
) -> dict[str, list[LinkedListingOut]]:
    """Linked listings for a page of clips, in one round trip."""
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

    listing_ids = sorted({str(link["listing_id"]) for link in links})
    listing_rows = _rows(
        service_client.client.table(LISTINGS_TABLE)
        .select("id, title_override, price_ngwee, status")
        .in_("id", listing_ids)
        .execute()
    )
    by_id = {str(row["id"]): row for row in listing_rows}

    grouped: dict[str, list[LinkedListingOut]] = {}
    for link in sorted(links, key=lambda item: int(item.get("sort_order") or 0)):
        listing = by_id.get(str(link["listing_id"]))
        # A listing that is no longer active must not be advertised on a clip:
        # the overlay would offer an add-to-cart that cannot succeed.
        if listing is None or str(listing.get("status")) != "active":
            continue
        grouped.setdefault(str(link["clip_id"]), []).append(
            LinkedListingOut(
                listing_id=str(listing["id"]),
                title=listing.get("title_override"),
                price_ngwee=int(listing.get("price_ngwee") or 0),
            )
        )
    return grouped


def _to_clip_out(
    clip: dict[str, Any],
    vendors: dict[str, dict[str, Any]],
    listings: dict[str, list[LinkedListingOut]],
) -> ClipOut:
    vendor_id = str(clip.get("vendor_id") or "")
    vendor = vendors.get(vendor_id, {})
    return ClipOut(
        id=str(clip["id"]),
        caption=clip.get("caption"),
        poster_url=clip.get("poster_url"),
        duration_s=clip.get("duration_s"),
        renditions=_renditions(clip.get("renditions")),
        like_count=int(clip.get("like_count") or 0),
        comment_count=int(clip.get("comment_count") or 0),
        view_count=int(clip.get("view_count") or 0),
        published_at=str(clip["published_at"]) if clip.get("published_at") else None,
        vendor=VendorSummaryOut(
            vendor_id=vendor_id,
            display_name=vendor.get("display_name"),
            slug=vendor.get("slug"),
        ),
        listings=listings.get(str(clip["id"]), []),
    )


def _published_candidates(
    service_client: ServiceRoleClient, before: str | None
) -> list[dict[str, Any]]:
    query = (
        service_client.client.table(CLIPS_TABLE)
        .select(
            "id, vendor_id, caption, poster_url, duration_s, renditions, "
            "like_count, comment_count, view_count, published_at, category_id"
        )
        .eq("status", state_machine.PUBLISHED)
        .order("published_at", desc=True)
        .limit(CANDIDATE_WINDOW)
    )
    if before:
        query = query.lt("published_at", before)
    return _rows(query.execute())


# --- Routes -----------------------------------------------------------------
@router.get("/feed", response_model=ClipFeedResponse)
async def get_clip_feed(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
) -> ClipFeedResponse:
    """The ranked, cursor-paginated public feed. Published clips only."""
    decoded = _decode_cursor(cursor)
    before = str(decoded.get("published_before")) if decoded else None

    candidates = _published_candidates(service_client, before)
    # Suspended vendors' clips are already excluded by RLS on a client read; the
    # service-role read here filters explicitly so the two paths agree.
    vendors = _load_vendors(
        service_client, sorted({str(c.get("vendor_id") or "") for c in candidates})
    )
    visible = [
        clip
        for clip in candidates
        if str(vendors.get(str(clip.get("vendor_id")), {}).get("status")) == "active"
    ]

    ordered = ranking.rank(visible, page_size=limit)[:limit]
    listings = _load_listings(service_client, [str(c["id"]) for c in ordered])

    next_cursor = None
    if len(ordered) == limit and ordered:
        oldest = min(
            (str(c.get("published_at") or "") for c in ordered if c.get("published_at")),
            default="",
        )
        if oldest:
            next_cursor = _encode_cursor({"published_before": oldest})

    return ClipFeedResponse(
        items=[_to_clip_out(clip, vendors, listings) for clip in ordered],
        next_cursor=next_cursor,
    )


@router.get("/{clip_id}", response_model=ClipOut)
async def get_clip(
    clip_id: str,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ClipOut:
    """Public clip detail, used by the share/OG page in M17-P08."""
    rows = _rows(
        service_client.client.table(CLIPS_TABLE)
        .select(
            "id, vendor_id, caption, poster_url, duration_s, renditions, "
            "like_count, comment_count, view_count, published_at, status, category_id"
        )
        .eq("id", clip_id)
        .maybe_single()
        .execute()
    )
    # Not-found and not-published are the same answer on purpose: a 403 here
    # would confirm that a given clip id exists but is unpublished.
    if not rows or str(rows[0].get("status")) != state_machine.PUBLISHED:
        raise AppError(
            code="not_found",
            message="Clip not found",
            http_status=404,
            details={"clip_id": clip_id},
        )
    clip = rows[0]

    vendors = _load_vendors(service_client, [str(clip.get("vendor_id") or "")])
    if str(vendors.get(str(clip.get("vendor_id")), {}).get("status")) != "active":
        raise AppError(
            code="not_found",
            message="Clip not found",
            http_status=404,
            details={"clip_id": clip_id},
        )

    listings = _load_listings(service_client, [clip_id])
    return _to_clip_out(clip, vendors, listings)


@router.get("/{clip_id}/ranking")
async def explain_clip_ranking(
    clip_id: str,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, Any]:
    """Why a clip ranks where it does — the explainability path from spec §3.

    Public and read-only: the formula is not a secret, and a vendor asking "why
    is my clip below theirs?" deserves an answer that is not "the model decided".
    """
    rows = _rows(
        service_client.client.table(CLIPS_TABLE)
        .select("id, status, published_at, like_count")
        .eq("id", clip_id)
        .maybe_single()
        .execute()
    )
    if not rows or str(rows[0].get("status")) != state_machine.PUBLISHED:
        raise AppError(
            code="not_found",
            message="Clip not found",
            http_status=404,
            details={"clip_id": clip_id},
        )

    breakdown = ranking.explain(rows[0]).as_dict()
    breakdown["formula"] = (
        "freshness_decay(published_at) * (1 + log(1+likes) + 2*log(1+orders))"
    )
    breakdown["freshness_half_life_hours"] = ranking.FRESHNESS_HALF_LIFE_HOURS
    breakdown["max_per_vendor_per_page"] = ranking.MAX_PER_VENDOR_PER_PAGE
    return breakdown
