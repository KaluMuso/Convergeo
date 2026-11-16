from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.services.vendors.slug import (
    is_placeholder_slug,
    slugify_business_name,
    unique_vendor_slug,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Mulenga's Fabrics & Décor", "mulenga-s-fabrics-decor"),
        ("  Lusaka  Tech   Hub ", "lusaka-tech-hub"),
        ("你好", "shop"),
        ("A", "a-shop"),
        ("Admin", "admin-shop"),
        ("Draft", "draft"),
    ],
)
def test_slugify_business_name(name: str, expected: str) -> None:
    assert slugify_business_name(name) == expected


def test_slug_is_capped_and_never_looks_like_a_placeholder() -> None:
    slug = slugify_business_name("x" * 200)
    assert len(slug) <= 60
    assert not is_placeholder_slug(slugify_business_name("draft-7ca8e1"))
    assert is_placeholder_slug("draft-7ca8e1")


def _service(taken: dict[str, str]) -> Any:
    service = MagicMock()

    def table(_name: str) -> MagicMock:
        query = MagicMock()
        state: dict[str, str] = {}

        def eq(_column: str, value: str) -> MagicMock:
            state["slug"] = value
            return query

        def execute() -> MagicMock:
            slug = state["slug"]
            return MagicMock(data=[{"id": taken[slug]}] if slug in taken else [])

        query.select.return_value = query
        query.eq.side_effect = eq
        query.limit.return_value = query
        query.execute.side_effect = execute
        return query

    service.client.table.side_effect = table
    return service


def test_unique_slug_adds_a_suffix_when_taken_by_another_vendor() -> None:
    service = _service({"mulenga-fabrics": "other"})
    assert unique_vendor_slug(service, "Mulenga Fabrics", vendor_id="me") == "mulenga-fabrics-2"


def test_unique_slug_keeps_the_name_when_only_this_vendor_holds_it() -> None:
    service = _service({"mulenga-fabrics": "me"})
    assert unique_vendor_slug(service, "Mulenga Fabrics", vendor_id="me") == "mulenga-fabrics"
