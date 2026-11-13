"""Demo and staging-synthetic inventory detection for public discovery.

Covers D25 / FD-04 / G11 / VC-P06 / STG-SEED-04.

Canonical markers:
- Legacy demo seed: Cloudinary ``listing_images.cloudinary_public_id`` matching ``demo/``
- Staging synthetic seed: ``staging-synthetic/`` prefix (STG-SEED-04 contract)

Matches the customer helper in ``apps/customer/.../demo-listing.ts`` for demo media so
labelling and exclusion share one rule on the API side.

A listing is non-genuine when **any** of its images carries a non-genuine public_id.
Products and vendors are demo-only when every active listing under them is non-genuine
(derived from the same marker — no second column).

Deployment-plane policy (single decision point — see ``_resolve_deployment_plane``):
legacy ``demo/`` media is excluded on every plane, always. ``staging-synthetic/``
media is excluded everywhere EXCEPT the staging plane itself: that prefix is
generated exclusively by ``app.staging.synthetic_contract`` (isolation-asserted to
the staging Supabase project — see ``app.core.env_guards``), so on staging it is the
canonical strict-E2E fixture data, not something to hide from the exact
customer-facing routes it exists to exercise. Reads the same ``ENV`` variable and
default (``"development"``) as ``app.core.env_guards``'s suppression predicates —
no second environment system. Fails closed: any value other than the literal
string ``"staging"`` (missing, unrecognised, ``"production"``, ``"development"``)
keeps the staging-synthetic exclusion ON.
"""

from __future__ import annotations

import os
from typing import Any, cast

# Staging synthetic media prefix — aligned with synthetic_contract.SYNTHETIC_IMAGE_PREFIX
STAGING_SYNTHETIC_PREFIX: str = "staging-synthetic/"


def _resolve_deployment_plane(*, env: str | None = None) -> str:
    """Canonical deployment-plane read — mirrors env_guards' inline ``ENV`` pattern.

    Never derived from request headers, query params, or body: ``env`` is only
    ever supplied by trusted call sites (tests, or a future server-side caller
    that already resolved it the same way) and otherwise falls back straight to
    the process environment, exactly like ``outbound_suppressed`` /
    ``payouts_suppressed`` / ``require_sandbox_payments`` in
    ``app.core.env_guards``.
    """
    resolved = env if env is not None else os.environ.get("ENV", "development")
    return resolved.strip().lower()


def is_demo_public_id(public_id: str | None) -> bool:
    """Return True when a Cloudinary public_id is legacy demo seed media."""
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


def is_staging_synthetic_public_id(public_id: str | None) -> bool:
    """Return True when a Cloudinary public_id is staging synthetic seed media."""
    if not public_id or not isinstance(public_id, str):
        return False
    normalized = public_id.strip().lstrip("/").lower()
    if not normalized:
        return False
    return (
        normalized.startswith(STAGING_SYNTHETIC_PREFIX)
        or f"/{STAGING_SYNTHETIC_PREFIX}" in normalized
    )


def is_non_genuine_public_id(public_id: str | None, *, env: str | None = None) -> bool:
    """Return True when inventory must not appear on this plane's public surfaces.

    Legacy ``demo/`` media: excluded unconditionally. ``staging-synthetic/`` media:
    excluded unless the resolved deployment plane is exactly ``"staging"`` — see
    the module docstring for the fail-closed contract.
    """
    if is_demo_public_id(public_id):
        return True
    if is_staging_synthetic_public_id(public_id):
        return _resolve_deployment_plane(env=env) != "staging"
    return False


def has_demo_media(images: list[str] | None) -> bool:
    """Return True when any entry in a media array is legacy demo seed inventory."""
    if not images:
        return False
    return any(is_demo_public_id(image) for image in images if isinstance(image, str))


def has_non_genuine_media(images: list[str] | None, *, env: str | None = None) -> bool:
    """Return True when any entry in a media array is demo or staging-synthetic inventory."""
    if not images:
        return False
    return any(
        is_non_genuine_public_id(image, env=env) for image in images if isinstance(image, str)
    )


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def fetch_demo_listing_ids(
    client: Any, listing_ids: list[str], *, env: str | None = None
) -> set[str]:
    """Batch-resolve which listing IDs carry non-genuine Cloudinary media.

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
    excluded_ids: set[str] = set()
    for row in _rows(response):
        listing_id = row.get("listing_id")
        if listing_id and is_non_genuine_public_id(
            row.get("cloudinary_public_id")
            if isinstance(row.get("cloudinary_public_id"), str)
            else None,
            env=env,
        ):
            excluded_ids.add(str(listing_id))
    return excluded_ids


def filter_out_demo_listing_ids(
    client: Any, listing_ids: list[str], *, env: str | None = None
) -> list[str]:
    """Return listing IDs with non-genuine inventory removed (order preserved)."""
    excluded_ids = fetch_demo_listing_ids(client, listing_ids, env=env)
    if not excluded_ids:
        return listing_ids
    return [listing_id for listing_id in listing_ids if listing_id not in excluded_ids]


def _non_genuine_only_parent_ids(
    client: Any,
    *,
    parent_ids: list[str],
    parent_column: str,
    env: str | None = None,
) -> set[str]:
    """Parents whose every active listing is non-genuine (or who have only non-genuine listings)."""
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

    non_genuine_listing_ids = fetch_demo_listing_ids(client, all_listing_ids, env=env)
    non_genuine_only: set[str] = set()
    for parent_id, lids in by_parent.items():
        if lids and all(lid in non_genuine_listing_ids for lid in lids):
            non_genuine_only.add(parent_id)
    return non_genuine_only


def fetch_demo_only_product_ids(
    client: Any, product_ids: list[str], *, env: str | None = None
) -> set[str]:
    """Product IDs whose active listings are entirely non-genuine inventory."""
    return _non_genuine_only_parent_ids(
        client, parent_ids=product_ids, parent_column="product_id", env=env
    )


def fetch_demo_only_vendor_ids(
    client: Any, vendor_ids: list[str], *, env: str | None = None
) -> set[str]:
    """Vendor IDs whose active listings are entirely non-genuine inventory."""
    return _non_genuine_only_parent_ids(
        client, parent_ids=vendor_ids, parent_column="vendor_id", env=env
    )


def fetch_demo_service_ids(
    client: Any, service_ids: list[str], *, env: str | None = None
) -> set[str]:
    """Service IDs whose portfolio carries non-genuine Cloudinary media."""
    if not service_ids:
        return set()
    unique_ids = list(dict.fromkeys(service_ids))
    response = (
        client.table("services")
        .select("id, portfolio_images")
        .in_("id", unique_ids)
        .execute()
    )
    excluded_ids: set[str] = set()
    for row in _rows(response):
        service_id = row.get("id")
        if service_id and has_non_genuine_media(row.get("portfolio_images"), env=env):
            excluded_ids.add(str(service_id))
    return excluded_ids


def fetch_demo_event_ids(client: Any, event_ids: list[str], *, env: str | None = None) -> set[str]:
    """Event IDs whose image array carries non-genuine Cloudinary media."""
    if not event_ids:
        return set()
    unique_ids = list(dict.fromkeys(event_ids))
    response = (
        client.table("events")
        .select("id, images")
        .in_("id", unique_ids)
        .execute()
    )
    excluded_ids: set[str] = set()
    for row in _rows(response):
        event_id = row.get("id")
        if event_id and has_non_genuine_media(row.get("images"), env=env):
            excluded_ids.add(str(event_id))
    return excluded_ids


def drop_demo_listing_hits(client: Any, hits: list[Any], *, env: str | None = None) -> list[Any]:
    """Remove non-genuine discovery hits from a consumer result set.

    Mirrors ``drop_wholesale_listing_hits``: post-filter after ``search_rrf`` so
    the RPC stays unchanged. Listing hits drop when any image is non-genuine; product
    and vendor hits drop when every active listing under them is non-genuine; service
    and event hits drop when any portfolio/event image is non-genuine.
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

    non_genuine_listing_ids = fetch_demo_listing_ids(client, listing_ids, env=env)
    non_genuine_product_ids = fetch_demo_only_product_ids(client, product_ids, env=env)
    non_genuine_vendor_ids = fetch_demo_only_vendor_ids(client, vendor_ids, env=env)
    non_genuine_service_ids = fetch_demo_service_ids(client, service_ids, env=env)
    non_genuine_event_ids = fetch_demo_event_ids(client, event_ids, env=env)

    if (
        not non_genuine_listing_ids
        and not non_genuine_product_ids
        and not non_genuine_vendor_ids
        and not non_genuine_service_ids
        and not non_genuine_event_ids
    ):
        return hits

    kept: list[Any] = []
    for hit in hits:
        kind = getattr(hit, "entity_kind", None)
        entity_id = getattr(hit, "entity_id", None)
        if kind == "listing" and entity_id in non_genuine_listing_ids:
            continue
        if kind == "product" and entity_id in non_genuine_product_ids:
            continue
        if kind == "vendor" and entity_id in non_genuine_vendor_ids:
            continue
        if kind == "service" and entity_id in non_genuine_service_ids:
            continue
        if kind == "event" and entity_id in non_genuine_event_ids:
            continue
        kept.append(hit)
    return kept
