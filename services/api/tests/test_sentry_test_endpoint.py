"""Environment gate + auth for POST /internal/sentry-test."""

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
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("INTERNAL_SENTRY_TEST_TOKEN", "test-sentry-token")
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("ENABLE_SENTRY_TEST_ENDPOINT", raising=False)
    from app.settings import get_settings

    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_sentry_test_requires_token(client: TestClient) -> None:
    response = client.post("/internal/sentry-test")
    assert response.status_code == 401


def test_sentry_test_fails_closed_without_dsn(client: TestClient) -> None:
    response = client.post(
        "/internal/sentry-test",
        headers={"X-Internal-Token": "test-sentry-token"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "configuration_error"


def test_sentry_test_disabled_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dev")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "dev")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://vergeo5.com")
    monkeypatch.setenv("INTERNAL_SENTRY_TEST_TOKEN", "test-sentry-token")
    monkeypatch.delenv("ENABLE_SENTRY_TEST_ENDPOINT", raising=False)
    from app.settings import get_settings

    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/internal/sentry-test",
            headers={"X-Internal-Token": "test-sentry-token"},
        )
        assert response.status_code == 404
    get_settings.cache_clear()
