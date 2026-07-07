from __future__ import annotations

import pytest
from app.settings import Settings, get_settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("ENV", "development")
    get_settings.cache_clear()

    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.supabase_url == "https://example.supabase.co"


def test_missing_required_var_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValueError) as exc_info:
        get_settings()

    message = str(exc_info.value)
    assert "SUPABASE_SERVICE_ROLE_KEY" in message
    assert "value redacted" in message
    assert "service-role-key" not in message


def test_format_settings_error_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValueError) as exc_info:
        get_settings()

    message = str(exc_info.value)
    assert "SUPABASE_SERVICE_ROLE_KEY" in message
    assert "value redacted" in message
