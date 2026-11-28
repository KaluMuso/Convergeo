"""Resolve the seller behind each Ask Vergeo citation and fill customer paths.

Search documents only carry the entity itself. A customer (and the audit log) also
needs to know *who sells it*, so each citation gets ``vendor_id`` / ``vendor_name`` /
``vendor_slug`` / ``vendor_href`` beside the entity's own ``href``.

Best-effort by design: a lookup failure leaves the citation exactly as retrieved and
never breaks an Ask answer.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.ask.citations import CitationRef, route_path

logger = logging.getLogger(__name__)


def rows_of(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _ids(citations: list[CitationRef], kind: str) -> list[str]:
    return sorted({c.entity_id for c in citations if c.entity_kind == kind})


def resolve_vendor_ids(client: Any, citations: list[CitationRef]) -> dict[str, str]:
    """Map ``kind:id`` -> seller vendor id for every citation that has one.

    A canonical product has many sellers; the seller shown is the one behind the
    lowest active price (the price the card displays).
    """
    out: dict[str, str] = {}
    for citation in citations:
        if citation.entity_kind == "vendor":
            out[f"vendor:{citation.entity_id}"] = citation.entity_id

    listing_ids = _ids(citations, "listing")
    if listing_ids:
        rows = rows_of(
            client.table("vendor_listings").select("id, vendor_id").in_("id", listing_ids).execute()
        )
        for row in rows:
            if row.get("id") and row.get("vendor_id"):
                out[f"listing:{row['id']}"] = str(row["vendor_id"])

    product_ids = _ids(citations, "product")
    if product_ids:
        rows = rows_of(
            client.table("vendor_listings")
            .select("product_id, vendor_id, price_ngwee")
            .in_("product_id", product_ids)
            .eq("status", "active")
            .eq("wholesale", False)
            .order("price_ngwee")
            .limit(500)
            .execute()
        )
        for row in rows:  # ascending price: first row per product is the cheapest
            key = f"product:{row.get('product_id')}"
            if row.get("product_id") and row.get("vendor_id") and key not in out:
                out[key] = str(row["vendor_id"])

    service_ids = _ids(citations, "service")
    if service_ids:
        rows = rows_of(
            client.table("services").select("id, vendor_id").in_("id", service_ids).execute()
        )
        for row in rows:
            if row.get("id") and row.get("vendor_id"):
                out[f"service:{row['id']}"] = str(row["vendor_id"])

    event_ids = _ids(citations, "event")
    if event_ids:
        rows = rows_of(
            client.table("events").select("id, organiser_vendor_id").in_("id", event_ids).execute()
        )
        for row in rows:
            if row.get("id") and row.get("organiser_vendor_id"):
                out[f"event:{row['id']}"] = str(row["organiser_vendor_id"])
    return out


def attach_vendor_info(client: Any, citations: list[CitationRef]) -> list[CitationRef]:
    """Return citations with ``href`` and seller fields filled in (never raises)."""
    if not citations:
        return citations
    try:
        vendor_for = resolve_vendor_ids(client, citations)
        vendor_ids = sorted(set(vendor_for.values()))
        vendors: dict[str, dict[str, Any]] = {}
        if vendor_ids:
            for row in rows_of(
                client.table("vendors")
                .select("id, slug, display_name")
                .in_("id", vendor_ids)
                .execute()
            ):
                if row.get("id"):
                    vendors[str(row["id"])] = row
    except Exception:  # noqa: BLE001 — enrichment must never break Ask
        logger.warning("Ask citation vendor enrichment failed (swallowed)", exc_info=True)
        return [_with_href(c) for c in citations]

    enriched: list[CitationRef] = []
    for citation in citations:
        vendor_id = vendor_for.get(f"{citation.entity_kind}:{citation.entity_id}")
        vendor = vendors.get(vendor_id) if vendor_id else None
        slug = vendor.get("slug") if vendor else None
        slug = slug.strip() if isinstance(slug, str) and slug.strip() else None
        name = vendor.get("display_name") if vendor else None
        enriched.append(
            _with_href(citation).model_copy(
                update={
                    "vendor_id": vendor_id,
                    "vendor_name": name.strip() if isinstance(name, str) and name.strip() else None,
                    "vendor_slug": slug,
                    "vendor_href": route_path("vendor", vendor_id, slug) if vendor_id else None,
                }
            )
        )
    return enriched


def _with_href(citation: CitationRef) -> CitationRef:
    if citation.href:
        return citation
    return citation.model_copy(
        update={"href": route_path(citation.entity_kind, citation.entity_id, citation.slug)}
    )
