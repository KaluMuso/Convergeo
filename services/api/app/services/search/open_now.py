"""Attach ``is_open_now`` to search hits from vendor branch hours (R02-P10/P11)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from app.services.vendors.hours import LUSAKA_TZ, is_open_at

if TYPE_CHECKING:
    from app.services.search import SearchHit


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _resolve_vendor_ids(client: Any, hits: list[SearchHit]) -> dict[str, str]:
    """Map each hit's ``entity_id`` to a vendor id when resolvable."""
    mapping: dict[str, str] = {}

    for hit in hits:
        if hit.entity_kind == "vendor":
            mapping[hit.entity_id] = hit.entity_id

    listing_ids = [hit.entity_id for hit in hits if hit.entity_kind == "listing"]
    if listing_ids:
        response = (
            client.table("vendor_listings")
            .select("id, vendor_id")
            .in_("id", listing_ids)
            .execute()
        )
        for row in _rows(response):
            listing_id = row.get("id")
            vendor_id = row.get("vendor_id")
            if listing_id and vendor_id:
                mapping[str(listing_id)] = str(vendor_id)

    service_ids = [hit.entity_id for hit in hits if hit.entity_kind == "service"]
    if service_ids:
        response = (
            client.table("services").select("id, vendor_id").in_("id", service_ids).execute()
        )
        for row in _rows(response):
            service_id = row.get("id")
            vendor_id = row.get("vendor_id")
            if service_id and vendor_id:
                mapping[str(service_id)] = str(vendor_id)

    product_ids = [hit.entity_id for hit in hits if hit.entity_kind == "product"]
    if product_ids:
        # Products are canonical — pick any active listing vendor for open-now.
        response = (
            client.table("vendor_listings")
            .select("product_id, vendor_id")
            .in_("product_id", product_ids)
            .eq("status", "active")
            .execute()
        )
        for row in _rows(response):
            product_id = row.get("product_id")
            vendor_id = row.get("vendor_id")
            if product_id and vendor_id and str(product_id) not in mapping:
                mapping[str(product_id)] = str(vendor_id)

    event_ids = [hit.entity_id for hit in hits if hit.entity_kind == "event"]
    if event_ids:
        response = (
            client.table("events").select("id, vendor_id").in_("id", event_ids).execute()
        )
        for row in _rows(response):
            event_id = row.get("id")
            vendor_id = row.get("vendor_id")
            if event_id and vendor_id:
                mapping[str(event_id)] = str(vendor_id)

    return mapping


def _load_branch_hours(client: Any, vendor_ids: list[str]) -> dict[str, list[Any]]:
    if not vendor_ids:
        return {}
    response = (
        client.table("vendor_locations")
        .select("vendor_id, hours, status")
        .in_("vendor_id", vendor_ids)
        .eq("status", "active")
        .execute()
    )
    hours_by_vendor: dict[str, list[Any]] = {vendor_id: [] for vendor_id in vendor_ids}
    for row in _rows(response):
        vendor_id = row.get("vendor_id")
        if vendor_id:
            hours_by_vendor.setdefault(str(vendor_id), []).append(row.get("hours"))
    return hours_by_vendor


def _vendor_open_now(hours_rows: list[Any], *, now: datetime) -> bool | None:
    """``True`` when any branch is open; ``None`` when no usable hours exist."""
    has_usable = False
    for hours in hours_rows:
        if isinstance(hours, dict) and hours:
            has_usable = True
            if is_open_at(hours, now):
                return True
    if not has_usable:
        return None
    return False


def attach_open_now(
    client: Any,
    hits: list[SearchHit],
    *,
    now: datetime | None = None,
) -> list[SearchHit]:
    """Stamp ``is_open_now`` on each hit from branch hours (Africa/Lusaka clock)."""
    if not hits:
        return hits

    at = now or datetime.now(LUSAKA_TZ)
    entity_vendor = _resolve_vendor_ids(client, hits)
    vendor_ids = sorted(set(entity_vendor.values()))
    hours_by_vendor = _load_branch_hours(client, vendor_ids)

    enriched: list[SearchHit] = []
    for hit in hits:
        vendor_id = entity_vendor.get(hit.entity_id)
        if vendor_id is None:
            enriched.append(hit.model_copy(update={"is_open_now": None}))
            continue
        open_now = _vendor_open_now(hours_by_vendor.get(vendor_id, []), now=at)
        enriched.append(hit.model_copy(update={"is_open_now": open_now}))
    return enriched
