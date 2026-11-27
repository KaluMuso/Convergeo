from __future__ import annotations

import httpx
import pytest
from app.settings import get_settings
from app.supabase_client import (
    SERVICE_KEEPALIVE_EXPIRY_S,
    build_service_http_client,
    get_supabase_service_client,
)


def test_service_http_client_uses_http1_with_short_keepalive() -> None:
    client = build_service_http_client()
    try:
        pool = client._transport._pool  # type: ignore[attr-defined]
        assert pool._http2 is False
        assert pool._http1 is True
        assert pool._keepalive_expiry == SERVICE_KEEPALIVE_EXPIRY_S
        assert client.follow_redirects is True
    finally:
        client.close()


def test_service_client_postgrest_uses_the_custom_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-test-key")
    get_settings.cache_clear()
    get_supabase_service_client.cache_clear()
    try:
        wrapper = get_supabase_service_client()
        session = wrapper.client.postgrest.session
        assert isinstance(session, httpx.Client)
        assert session._transport._pool._http2 is False  # type: ignore[attr-defined]
    finally:
        get_supabase_service_client.cache_clear()
        get_settings.cache_clear()
