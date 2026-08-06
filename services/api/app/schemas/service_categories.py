"""Pydantic models for the Convergeo service/vendor category taxonomy."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import StrictModel


class ServiceCategorySeed(StrictModel):
    """One row in the Strategy Brief §5 catalogue (vertical or sub-category)."""

    name: str = Field(min_length=1, max_length=200)
    slug: str | None = None
    archetype: str | None = None
    regulator: str | None = None
    sort: int = 0
    is_active: bool = True
    subcategories: list[ServiceCategorySeed] = Field(default_factory=list)


class ServiceCategoryRow(StrictModel):
    """Persisted taxonomy node (matches public.service_categories)."""

    slug: str
    parent_slug: str | None = None
    name: str
    path: str
    archetype: str | None = None
    regulator: str | None = None
    sort: int = 0
    is_active: bool = True


class ServiceCategoryTreeNode(ServiceCategoryRow):
    """Vertical with nested sub-categories for API responses."""

    children: list[ServiceCategoryRow] = Field(default_factory=list)
