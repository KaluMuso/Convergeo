"""Read-side display titles for order lines.

``order_items.title_snapshot`` is NULL for most product lines because order creation
snapshots only ``listing.title_override``. Serializers call :func:`resolve_missing_titles`
to fill the gap from the listing (override, then product name) in one batched query.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.services.cart.grouping import listing_display_title

_CHUNK = 200


def clean_title(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def resolve_missing_titles(client: Any, rows: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Return ``{order_item_id: title}`` for rows whose ``title_snapshot`` is empty.

    Rows with a snapshot are never looked up. One ``order_item_products`` query (with the
    listing and product name embedded) per chunk of 200 ids; lines with no linked
    listing, or a listing with neither override nor product name, are omitted.
    """
    missing = sorted(
        {
            str(row["id"])
            for row in rows
            if row.get("id") and not clean_title(row.get("title_snapshot"))
        }
    )
    resolved: dict[str, str] = {}
    for start in range(0, len(missing), _CHUNK):
        chunk = missing[start : start + _CHUNK]
        response = (
            client.table("order_item_products")
            .select("order_item_id, listings(id, title_override, products(name))")
            .in_("order_item_id", chunk)
            .execute()
        )
        for link in response.data or []:
            listing = link.get("listings")
            if isinstance(listing, list):
                listing = listing[0] if listing else None
            if not isinstance(listing, dict):
                continue
            title = listing_display_title(listing)
            if title:
                resolved[str(link["order_item_id"])] = title
    return resolved


def display_title(row: dict[str, Any], resolved: dict[str, str]) -> str | None:
    """Snapshot wins; else the batched listing title; else ``None`` (UI shows i18n label)."""
    return clean_title(row.get("title_snapshot")) or resolved.get(str(row.get("id")))
