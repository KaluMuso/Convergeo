"""Shared canonical product photos + sha256 dedup (flag ``shared_canonical_photos``).

Rules (founder-approved 2026-11-13):

* Listings attached to a canonical product reuse ``product_images`` instead of
  every vendor uploading copies of the same product shot.
* The ≤8-per-listing rule holds for what a listing SHOWS: the vendor's own
  photos are always shown, and canonical photos fill only the slots left
  (``own + canonical <= 8``). Vendors can still add their own photos.
* Dedup is by sha256 of the uploaded bytes, scoped so a vendor-claimed hash can
  never surface another vendor's photo: a hit is either the vendor's OWN earlier
  upload, or the canonical (admin-approved) photo of the listing's own product.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final, Literal

from app.services.vendor_plans.resolver import HARD_MAX_IMAGES_PER_LISTING

logger = logging.getLogger(__name__)

SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
# Seeded on approval: the proposing vendor's photos become the product's.
MAX_SEEDED_CANONICAL_IMAGES: Final = 6

DedupMatch = Literal["none", "listing", "own", "canonical"]


@dataclass(frozen=True, slots=True)
class DedupResult:
    match: DedupMatch
    cloudinary_public_id: str | None = None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def normalize_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if not SHA256_RE.fullmatch(normalized):
        raise ValueError("content_sha256 must be 64 hex characters")
    return normalized


def load_canonical_images(client: Any, product_ids: Iterable[str]) -> dict[str, list[str]]:
    """``product_id -> [public_id, ...]`` in position order."""
    ids = sorted({pid for pid in product_ids if pid})
    if not ids:
        return {}
    rows = _rows(
        client.table("product_images")
        .select("product_id, cloudinary_public_id, position")
        .in_("product_id", ids)
        .order("position")
        .execute()
    )
    result: dict[str, list[str]] = {}
    for row in sorted(rows, key=lambda item: int(item.get("position") or 0)):
        public_id = row.get("cloudinary_public_id")
        product_id = row.get("product_id")
        if isinstance(public_id, str) and public_id.strip() and product_id:
            result.setdefault(str(product_id), []).append(public_id.strip())
    return result


def merge_listing_gallery(
    own_public_ids: list[str],
    canonical_public_ids: list[str],
    *,
    cap: int = HARD_MAX_IMAGES_PER_LISTING,
) -> list[tuple[str, Literal["canonical", "listing"]]]:
    """Canonical first, then all own photos; canonical yields slots to own ones.

    Own photos are never dropped (they are already ≤8 by the DB guard); the
    canonical set is truncated to ``cap - len(own)``. Exact duplicates collapse.
    """
    own = list(dict.fromkeys(pid for pid in own_public_ids if pid))[:cap]
    room = max(cap - len(own), 0)
    canonical = [pid for pid in dict.fromkeys(canonical_public_ids) if pid not in own][:room]
    return [(pid, "canonical") for pid in canonical] + [(pid, "listing") for pid in own]


def find_duplicate(
    client: Any,
    *,
    vendor_id: str,
    listing_id: str,
    product_id: str | None,
    sha256: str,
) -> DedupResult:
    """Scoped dedup lookup (see module docstring for the trust boundary)."""
    on_listing = _rows(
        client.table("listing_images")
        .select("cloudinary_public_id")
        .eq("listing_id", listing_id)
        .eq("content_sha256", sha256)
        .limit(1)
        .execute()
    )
    if on_listing:
        return DedupResult("listing", str(on_listing[0].get("cloudinary_public_id") or ""))

    if product_id:
        canonical = _rows(
            client.table("product_images")
            .select("cloudinary_public_id")
            .eq("product_id", product_id)
            .eq("content_sha256", sha256)
            .limit(1)
            .execute()
        )
        if canonical:
            return DedupResult("canonical", str(canonical[0].get("cloudinary_public_id") or ""))

    own = _rows(
        client.table("listing_images")
        .select("cloudinary_public_id, vendor_listings!inner(vendor_id)")
        .eq("content_sha256", sha256)
        .eq("vendor_listings.vendor_id", vendor_id)
        .limit(1)
        .execute()
    )
    if own and own[0].get("cloudinary_public_id"):
        return DedupResult("own", str(own[0]["cloudinary_public_id"]))
    return DedupResult("none")


def seed_canonical_images_from_listings(client: Any, product_id: str) -> int:
    """On canonical approval, adopt the proposing listings' photos (if none yet).

    Idempotent: does nothing when the product already has canonical photos.
    Oldest listing first (the proposer), then position order; distinct ids only.
    Returns how many rows were inserted.
    """
    existing = _rows(
        client.table("product_images").select("id").eq("product_id", product_id).limit(1).execute()
    )
    if existing:
        return 0
    listings = _rows(
        client.table("vendor_listings")
        .select("id, created_at")
        .eq("product_id", product_id)
        .order("created_at")
        .execute()
    )
    listing_order = [str(row["id"]) for row in listings if row.get("id")]
    if not listing_order:
        return 0
    images = _rows(
        client.table("listing_images")
        .select("id, listing_id, cloudinary_public_id, position, content_sha256")
        .in_("listing_id", listing_order)
        .execute()
    )
    rank = {listing_id: index for index, listing_id in enumerate(listing_order)}
    images.sort(
        key=lambda row: (rank.get(str(row.get("listing_id")), 1_000), int(row.get("position") or 0))
    )
    seen: set[str] = set()
    payload: list[dict[str, Any]] = []
    for row in images:
        public_id = row.get("cloudinary_public_id")
        if not isinstance(public_id, str) or not public_id.strip() or public_id in seen:
            continue
        seen.add(public_id)
        payload.append(
            {
                "product_id": product_id,
                "cloudinary_public_id": public_id,
                "position": len(payload) + 1,
                "content_sha256": row.get("content_sha256"),
                "source_listing_image_id": row.get("id"),
            }
        )
        if len(payload) >= MAX_SEEDED_CANONICAL_IMAGES:
            break
    if not payload:
        return 0
    client.table("product_images").insert(payload).execute()
    return len(payload)
