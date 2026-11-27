"""Post-a-job category allowlist stays aligned with service vertical slugs (#984)."""

from __future__ import annotations

import pytest
from app.errors import AppError
from app.routers.jobs import SERVICE_CATEGORIES, _validate_category

NEW_VERTICALS = frozenset(
    {
        "lodging",
        "property",
        "fitness",
        "rentals",
        "family-fun",
        "staffing",
    }
)


def test_service_archetype_verticals_are_post_job_categories() -> None:
    assert NEW_VERTICALS <= SERVICE_CATEGORIES


def test_validate_category_accepts_new_verticals() -> None:
    for category in sorted(NEW_VERTICALS):
        _validate_category(category)


def test_validate_category_rejects_unknown() -> None:
    with pytest.raises(AppError) as exc:
        _validate_category("not-a-vertical")
    assert exc.value.code == "validation_error"