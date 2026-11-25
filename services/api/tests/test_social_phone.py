from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.services.social.phone import normalize_to_e164, require_phone_pepper


def test_normalize_zm_096_formats() -> None:
    samples = ("0966123456", "966123456", "+260966123456", "260966123456")
    for raw in samples:
        assert normalize_to_e164(raw) == "+260966123456", raw


def test_pepper_missing_without_env_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("SOCIAL_PHONE_PEPPER", raising=False)
    settings = MagicMock(social_phone_pepper="", env="development")
    with pytest.raises(AppError) as exc:
        require_phone_pepper(settings)
    assert exc.value.http_status == 503


def test_pepper_dev_fallback_only_when_env_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "development")
    settings = MagicMock(social_phone_pepper="", env="development")
    assert require_phone_pepper(settings) == "dev-social-phone-pepper"


def test_pepper_test_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "test")
    settings = MagicMock(social_phone_pepper="", env="development")
    assert require_phone_pepper(settings) == "dev-social-phone-pepper"


def test_production_without_pepper_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    settings = MagicMock(social_phone_pepper="", env="production")
    with pytest.raises(AppError):
        require_phone_pepper(settings)