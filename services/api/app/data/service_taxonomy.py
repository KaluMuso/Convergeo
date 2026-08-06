"""Convergeo service/vendor category taxonomy helpers."""

from __future__ import annotations

import re

from app.data.convergeo_service_catalogue import CONVERGEO_SERVICE_TAXONOMY
from app.schemas.service_categories import ServiceCategoryRow

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """URL-safe slug from a display name."""
    value = name.lower().replace("&", "and")
    value = _SLUG_RE.sub("-", value).strip("-")
    return value or "category"


def flatten_taxonomy() -> list[ServiceCategoryRow]:
    """Expand vertical → sub-category tree into flat rows with materialized paths."""
    rows: list[ServiceCategoryRow] = []
    for vertical_index, vertical in enumerate(CONVERGEO_SERVICE_TAXONOMY):
        vertical_slug = slugify(vertical["name"])
        rows.append(
            ServiceCategoryRow(
                slug=vertical_slug,
                parent_slug=None,
                name=vertical["name"],
                path=vertical_slug,
                sort=vertical_index,
                is_active=True,
            )
        )
        for sub_index, sub in enumerate(vertical.get("subcategories", [])):
            sub_slug = slugify(sub["name"])
            rows.append(
                ServiceCategoryRow(
                    slug=sub_slug,
                    parent_slug=vertical_slug,
                    name=sub["name"],
                    path=f"{vertical_slug}/{sub_slug}",
                    archetype=sub.get("archetype"),
                    regulator=sub.get("regulator"),
                    sort=sub_index,
                    is_active=True,
                )
            )
    return rows
