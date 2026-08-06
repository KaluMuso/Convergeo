"""Tests for Convergeo service taxonomy seed data."""

from __future__ import annotations

from collections import Counter

from app.data.convergeo_service_catalogue import CONVERGEO_SERVICE_TAXONOMY
from app.data.service_taxonomy import flatten_taxonomy, slugify


def test_taxonomy_has_seventeen_verticals() -> None:
    assert len(CONVERGEO_SERVICE_TAXONOMY) == 17


def test_flattened_rows_have_unique_slugs_and_paths() -> None:
    rows = flatten_taxonomy()
    slugs = [row.slug for row in rows]
    paths = [row.path for row in rows]
    assert len(slugs) == len(set(slugs))
    assert len(paths) == len(set(paths))


def test_subcategory_count_near_strategy_brief_target() -> None:
    rows = flatten_taxonomy()
    sub_count = sum(1 for row in rows if row.parent_slug is not None)
    assert 110 <= sub_count <= 120


def test_all_rows_active_with_generated_slugs() -> None:
    rows = flatten_taxonomy()
    assert all(row.is_active for row in rows)
    assert all(row.slug == slugify(row.name) for row in rows if row.parent_slug is None)


def test_example_verticals_present() -> None:
    vertical_names = {row.name for row in flatten_taxonomy() if row.parent_slug is None}
    assert "Food & Hospitality" in vertical_names
    assert "Beauty & Personal Care" in vertical_names
    assert "Agriculture" in vertical_names


def test_no_duplicate_subcategory_names_within_vertical() -> None:
    for vertical in CONVERGEO_SERVICE_TAXONOMY:
        names = [sub["name"] for sub in vertical["subcategories"]]
        assert len(names) == len(set(names)), vertical["name"]
        counts = Counter(slugify(name) for name in names)
        assert all(count == 1 for count in counts.values()), vertical["name"]
