"""Readable shop slugs derived from the business name.

New vendor drafts used to get ``draft-<hex>``. That URL is public as soon as the
shop is approved, so once the vendor tells us their business name we replace the
placeholder with a readable slug. This is a system rename, not the vendor's
one-time slug change: ``caps_snapshot.slug_locked`` is left untouched.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any

from app.services.kyc.state_machine import ServiceRoleClient

PLACEHOLDER_PREFIX = "draft-"
_MAX_BASE = 60
_RESERVED = frozenset(
    {"admin", "api", "app", "www", "vendor", "vendors", "shop", "shops", "new", "login"}
)


def slugify_business_name(name: str) -> str:
    """ASCII, lowercase, hyphenated slug. Falls back to ``shop`` for empty results."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    # A business literally named "draft-123" must not read as a placeholder slug.
    slug = slug.removeprefix(PLACEHOLDER_PREFIX)
    slug = slug[:_MAX_BASE].strip("-")
    if not slug:
        return "shop"
    if len(slug) < 2 or slug in _RESERVED:
        return f"{slug}-shop"
    return slug


def is_placeholder_slug(slug: str | None) -> bool:
    return bool(slug) and str(slug).startswith(PLACEHOLDER_PREFIX)


def unique_vendor_slug(
    service_client: ServiceRoleClient,
    business_name: str,
    *,
    vendor_id: str | None = None,
) -> str:
    base = slugify_business_name(business_name)
    for suffix in range(0, 50):
        candidate = base if suffix == 0 else f"{base}-{suffix + 1}"
        response = (
            service_client.client.table("vendors")
            .select("id")
            .eq("slug", candidate)
            .limit(1)
            .execute()
        )
        rows: Any = getattr(response, "data", None)
        taken = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        if all(str(row.get("id")) == vendor_id for row in taken):
            return candidate
    return f"{base}-{uuid.uuid4().hex[:6]}"
