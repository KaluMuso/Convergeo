from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-key")
os.environ.setdefault("ENV", "development")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# The payment kill switch defaults to OFF in production (safe by default). The
# test suite exercises the payment flows, so enable it here via the explicit
# production-ack path — this leaves LENCO_ENV untouched (base-url tests unaffected).
# The gate's own tests use monkeypatch to drive the disabled/sandbox/production
# states directly, overriding these defaults.
os.environ.setdefault("PAYMENTS_ENABLED", "true")
os.environ.setdefault("PAYMENTS_ALLOW_PRODUCTION", "true")


@pytest.fixture(autouse=True)
def reset_caches() -> Generator[None, None, None]:
    from app.settings import get_settings
    from app.supabase_client import get_supabase_service_client

    get_settings.cache_clear()
    get_supabase_service_client.cache_clear()
    yield
    get_settings.cache_clear()
    get_supabase_service_client.cache_clear()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    from app.errors import AppError
    from app.main import create_app

    app: FastAPI = create_app()

    @app.get("/test/app-error")
    async def raise_app_error() -> None:
        raise AppError("test_error", "Something went wrong", 418, {"field": "value"})

    @app.get("/test/unhandled")
    async def raise_unhandled() -> None:
        raise RuntimeError("secret database connection failed")

    @app.post("/test/validation")
    async def validation_endpoint(count: int) -> dict[str, int]:
        return {"count": count}

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
