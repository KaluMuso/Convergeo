"""Vendor brand theme: AA clamping + validation (services/brand_theme.py)."""

import pytest
from app.services.brand_theme import (
    contrast_ratio,
    ensure_contrast,
    read_brand_theme,
    sanitize_brand_theme,
)


def test_light_primary_is_darkened_until_white_text_passes_aa() -> None:
    fixed = ensure_contrast("#FFD84D", 4.5)
    assert contrast_ratio(fixed, "#FFFFFF") >= 4.5


def test_compliant_colour_is_unchanged() -> None:
    assert ensure_contrast("#0B5D45", 4.5) == "#0B5D45"


def test_sanitize_clamps_primary_and_accent() -> None:
    theme = sanitize_brand_theme({"primary": "#7dd3fc", "accent": "#fde68a"})
    assert theme is not None
    assert contrast_ratio(theme["primary"] or "", "#FFFFFF") >= 4.5
    assert contrast_ratio(theme["accent"] or "", "#FFFFFF") >= 3.0


def test_all_null_theme_clears() -> None:
    assert sanitize_brand_theme({"primary": None, "accent": None}) is None


@pytest.mark.parametrize(
    "bad",
    [{"primary": "red"}, {"accent": "#12345"}, {"primary": "#123456", "extra": "#000000"}, "x"],
)
def test_invalid_input_raises(bad: object) -> None:
    with pytest.raises(ValueError):
        sanitize_brand_theme(bad)


def test_read_path_never_raises() -> None:
    assert read_brand_theme({"primary": "nope"}) is None
    assert read_brand_theme(None) is None


def test_profile_patch_validates_brand_theme_hex() -> None:
    from app.routers.vendor_profile import ProfilePatchRequest
    from pydantic import ValidationError

    ok = ProfilePatchRequest.model_validate({"brand_theme": {"primary": "#0b5d45"}})
    assert ok.brand_theme is not None and ok.brand_theme.primary == "#0B5D45"
    with pytest.raises(ValidationError):
        ProfilePatchRequest.model_validate({"brand_theme": {"primary": "green"}})
    with pytest.raises(ValidationError):
        ProfilePatchRequest.model_validate({"brand_theme": {"primary": "#000000", "x": "#fff"}})
