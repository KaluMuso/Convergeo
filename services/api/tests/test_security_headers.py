"""Security headers and CORS hardening tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dev")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "dev")
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3001,http://localhost:3002",
    )
    from app.settings import get_settings

    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_secure_headers_on_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers.get("Strict-Transport-Security") is None


def test_secure_headers_include_hsts_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dev")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "dev")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://vergeo5.com,https://vendor.vergeo5.com,https://admin.vergeo5.com",
    )
    from app.settings import get_settings

    get_settings.cache_clear()
    with TestClient(create_app()) as prod_client:
        response = prod_client.get("/healthz")
        assert response.status_code == 200
        hsts = response.headers.get("Strict-Transport-Security", "")
        assert "max-age=63072000" in hsts
        assert "preload" in hsts
    get_settings.cache_clear()


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/healthz",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "GET" in (response.headers.get("access-control-allow-methods") or "")
    assert "Authorization" in (response.headers.get("access-control-allow-headers") or "")


def test_cors_rejects_foreign_origin(client: TestClient) -> None:
    response = client.get("/healthz", headers={"Origin": "https://evil.example"})
    assert response.headers.get("access-control-allow-origin") is None


def test_production_cors_rejects_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dev")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "dev")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    from app.settings import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="localhost"):
        get_settings()
    get_settings.cache_clear()


def test_production_cors_rejects_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dev")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "dev")
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    from app.settings import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="\\*"):
        get_settings()
    get_settings.cache_clear()
