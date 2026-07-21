"""Demo inventory detection for public discovery (D25 / FD-04 / G11 / VC-P06).

Canonical marker: Cloudinary ``listing_images.cloudinary_public_id`` matching the
seed ``demo/`` prefix used by ``scripts/seed/upload_demo_images.py`` and verified
live (``LIKE 'demo/%'``). Matches the customer helper in
``apps/customer/.../demo-listing.ts`` so labelling and exclusion share one rule.

A listing is demo when **any** of its images carries a demo public_id. Products
and vendors are demo-only when every active listing under them is demo (derived
from the same marker — no second column).
"""

from __future__ import annotations

from typing import Any, cast


def is_demo_public_id(public_id: str | None) -> bool:
    """Return True when a Cloudinary public_id is demo seed media."""
    if not public_id or not isinstance(public_id, str):
        return False
    normalized = public_id.strip().lstrip("/").lower()
    if not normalized:
        return False
    return (
        normalized == "demo"
        or normalized.startswith("demo/")
        or "/demo/" in normalized
    )


def has_demo_media(images: list[str] | None) -> bool:
    """Return True when any entry in a media array is demo seed inventory."""
    if not images:
        return False
    return any(is_demo_public_id(image) for image in images if isinstance(image, str))


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def fetch_demo_listing_ids(client: Any, listing_ids: list[str]) -> set[str]:
    """Batch-resolve which listing IDs carry demo Cloudinary media.

    One ``listing_images`` query for the candidate set — no N+1.
    """
    if not listing_ids:
        return set()
    # Deduplicate while preserving a stable bound for the IN clause.
    unique_ids = list(dict.fromkeys(listing_ids))
    response = (
        client.table("listing_images")
        .select("listing_id, cloudinary_public_id")
        .in_("listing_id", unique_ids)
        .execute()
    )
    demo_ids: set[str] = set()
    for row in _rows(response):
        listing_id = row.get("listing_id")
        if listing_id and is_demo_public_id(
            row.get("cloudinary_public_id")
            if isinstance(row.get("cloudinary_public_id"), str)
            else None
        ):
            demo_ids.add(str(listing_id))
    return demo_ids


def filter_out_demo_listing_ids(client: Any, listing_ids: list[str]) -> list[str]:
    """Return listing IDs with demo inventory removed (order preserved)."""
    demo_ids = fetch_demo_listing_ids(client, listing_ids)
    if not demo_ids:
        return listing_ids
    return [listing_id for listing_id in listing_ids if listing_id not in demo_ids]


def _demo_only_parent_ids(
    client: Any,
    *,
    parent_ids: list[str],
    parent_column: str,
) -> set[str]:
    """Parents whose every active listing is demo (or who have only demo listings)."""
    if not parent_ids:
        return set()
    unique_parents = list(dict.fromkeys(parent_ids))
    response = (
        client.table("vendor_listings")
        .select(f"id, {parent_column}")
        .in_(parent_column, unique_parents)
        .eq("status", "active")
        .execute()
    )
    by_parent: dict[str, list[str]] = {pid: [] for pid in unique_parents}
    all_listing_ids: list[str] = []
    for row in _rows(response):
        parent_id = row.get(parent_column)
        listing_id = row.get("id")
        if not parent_id or not listing_id:
            continue
        parent_key = str(parent_id)
        listing_key = str(listing_id)
        if parent_key in by_parent:
            by_parent[parent_key].append(listing_key)
            all_listing_ids.append(listing_key)

    if not all_listing_ids:
        return set()

    demo_listing_ids = fetch_demo_listing_ids(client, all_listing_ids)
    demo_only: set[str] = set()
    for parent_id, lids in by_parent.items():
        if lids and all(lid in demo_listing_ids for lid in lids):
            demo_only.add(parent_id)
    return demo_only


def fetch_demo_only_product_ids(client: Any, product_ids: list[str]) -> set[str]:
    """Product IDs whose active listings are entirely demo inventory."""
    return _demo_only_parent_ids(client, parent_ids=product_ids, parent_column="product_id")


def fetch_demo_only_vendor_ids(client: Any, vendor_ids: list[str]) -> set[str]:
    """Vendor IDs whose active listings are entirely demo inventory."""
    return _demo_only_parent_ids(client, parent_ids=vendor_ids, parent_column="vendor_id")


def fetch_demo_service_ids(client: Any, service_ids: list[str]) -> set[str]:
    """Service IDs whose portfolio carries demo Cloudinary media."""
    if not service_ids:
        return set()
    unique_ids = list(dict.fromkeys(service_ids))
    response = (
        client.table("services")
        .select("id, portfolio_images")
        .in_("id", unique_ids)
        .execute()
    )
    demo_ids: set[str] = set()
    for row in _rows(response):
        service_id = row.get("id")
        if service_id and has_demo_media(row.get("portfolio_images")):
            demo_ids.add(str(service_id))
    return demo_ids


def fetch_demo_event_ids(client: Any, event_ids: list[str]) -> set[str]:
    """Event IDs whose image array carries demo Cloudinary media."""
    if not event_ids:
        return set()
    unique_ids = list(dict.fromkeys(event_ids))
    response = (
        client.table("events")
        .select("id, images")
        .in_("id", unique_ids)
        .execute()
    )
    demo_ids: set[str] = set()
    for row in _rows(response):
        event_id = row.get("id")
        if event_id and has_demo_media(row.get("images")):
            demo_ids.add(str(event_id))
    return demo_ids


def drop_demo_listing_hits(client: Any, hits: list[Any]) -> list[Any]:
    """Remove demo discovery hits from a consumer result set.

    Mirrors ``drop_wholesale_listing_hits``: post-filter after ``search_rrf`` so
    the RPC stays unchanged. Listing hits drop when any image is demo; product
    and vendor hits drop when every active listing under them is demo; service
    and event hits drop when any portfolio/event image is demo.
    """
    if not hits:
        return hits

    listing_ids = [
        hit.entity_id for hit in hits if getattr(hit, "entity_kind", None) == "listing"
    ]
    product_ids = [
        hit.entity_id for hit in hits if getattr(hit, "entity_kind", None) == "product"
    ]
    vendor_ids = [
        hit.entity_id for hit in hits if getattr(hit, "entity_kind", None) == "vendor"
    ]
    service_ids = [
        hit.entity_id for hit in hits if getattr(hit, "entity_kind", None) == "service"
    ]
    event_ids = [
        hit.entity_id for hit in hits if getattr(hit, "entity_kind", None) == "event"
    ]

    demo_listing_ids = fetch_demo_listing_ids(client, listing_ids)
    demo_product_ids = fetch_demo_only_product_ids(client, product_ids)
    demo_vendor_ids = fetch_demo_only_vendor_ids(client, vendor_ids)
    demo_service_ids = fetch_demo_service_ids(client, service_ids)
    demo_event_ids = fetch_demo_event_ids(client, event_ids)

    if (
        not demo_listing_ids
        and not demo_product_ids
        and not demo_vendor_ids
        and not demo_service_ids
        and not demo_event_ids
    ):
        return hits

    kept: list[Any] = []
    for hit in hits:
        kind = getattr(hit, "entity_kind", None)
        entity_id = getattr(hit, "entity_id", None)
        if kind == "listing" and entity_id in demo_listing_ids:
            continue
        if kind == "product" and entity_id in demo_product_ids:
            continue
        if kind == "vendor" and entity_id in demo_vendor_ids:
            continue
        if kind == "service" and entity_id in demo_service_ids:
            continue
        if kind == "event" and entity_id in demo_event_ids:
            continue
        kept.append(hit)
    return kept
