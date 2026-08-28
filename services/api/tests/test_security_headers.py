"""Security headers and CORS hardening tests."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import httpx
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
    monkeypatch.setenv("CORS_ORIGINS", "https://localhost:3000")
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


@pytest.mark.parametrize(
    "origin",
    [
        "vergeo5.com",
        "https://vergeo5.com/",
        "https://vergeo5.com/api",
        "https://user:password@vergeo5.com",
        "https://vergeo5.com?debug=true",
    ],
)
def test_cors_rejects_non_origin_values(
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dev")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "dev")
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", origin)
    from app.settings import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="exact http\\(s\\) origins"):
        get_settings()
    get_settings.cache_clear()


def test_production_cors_requires_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dev")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "dev")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "http://customer.vergeo5.com")
    from app.settings import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="https"):
        get_settings()
    get_settings.cache_clear()


# ── RC-6 / PR-F3: staging-only immutable Vercel Preview CORS origins ────────
#
# strict E2E run #52 proved (real Playwright traces, not a hypothesis) that
# the deployed Customer/Vendor/Admin Preview origins were rejected by the
# staging API's CORS allowlist, because every SHA-pinned Vercel Preview
# deployment gets a newly generated immutable hostname that a static
# CORS_ORIGINS entry can never anticipate. These tests exercise the real
# CORSMiddleware/TestClient request path (not just the regex in isolation).

_STAGING_STABLE_ORIGIN = "https://staging.vergeo5.com"

# Real immutable Preview hostnames confirmed from primary evidence: run #52's
# own Playwright trace plus scripts/qa/self-test/e2e-staging-probe.test.mjs's
# pre-existing fixtures (both the per-deployment hash suffix and the mutable
# "git-staging" branch-alias suffix).
_CUSTOMER_PREVIEW_ORIGIN = "https://convergeo-customer-29zn11wb8-vergeo-projects.vercel.app"
_VENDOR_PREVIEW_ORIGIN = "https://convergeo-vendor-bm3uged2r-vergeo-projects.vercel.app"
_ADMIN_PREVIEW_ORIGIN = "https://convergeo-admin-e77lx2884-vergeo-projects.vercel.app"
_GIT_STAGING_PREVIEW_ORIGIN = "https://convergeo-customer-git-staging-vergeo-projects.vercel.app"


@pytest.fixture
def staging_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dev")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "dev")
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("LENCO_ENV", "sandbox")
    monkeypatch.setenv("CORS_ORIGINS", _STAGING_STABLE_ORIGIN)
    from app.settings import get_settings

    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def _cart_preflight(client: TestClient, origin: str) -> httpx.Response:
    return cast(
        httpx.Response,
        client.options(
            "/cart/items",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        ),
    )


@pytest.mark.parametrize(
    "origin",
    [
        _CUSTOMER_PREVIEW_ORIGIN,
        _VENDOR_PREVIEW_ORIGIN,
        _ADMIN_PREVIEW_ORIGIN,
        _GIT_STAGING_PREVIEW_ORIGIN,
    ],
)
def test_staging_allows_immutable_preview_origins_on_cart_preflight(
    staging_client: TestClient, origin: str
) -> None:
    response = _cart_preflight(staging_client, origin)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert "POST" in (response.headers.get("access-control-allow-methods") or "")


def test_staging_still_allows_stable_configured_origin(staging_client: TestClient) -> None:
    response = _cart_preflight(staging_client, _STAGING_STABLE_ORIGIN)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == _STAGING_STABLE_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.vercel.app",
        "https://example-staging.vercel.app",
        # wrong project prefix under the same real team namespace
        "https://convergeo-supplies-29zn11wb8-vergeo-projects.vercel.app",
        # lookalike different Vercel team
        "https://convergeo-customer-xyz-attacker.vercel.app",
        "https://convergeo-customer-29zn11wb8-attacker-projects.vercel.app",
        # scheme
        "http://convergeo-customer-29zn11wb8-vergeo-projects.vercel.app",
        # case tricks
        "https://convergeo-CUSTOMER-29zn11wb8-vergeo-projects.vercel.app",
        # path / query / userinfo suffix tricks
        "https://convergeo-customer-29zn11wb8-vergeo-projects.vercel.app/cart",
        "https://convergeo-customer-29zn11wb8-vergeo-projects.vercel.app?x=1",
        "https://convergeo-customer-29zn11wb8-vergeo-projects.vercel.app.evil.com",
        "https://user:pass@convergeo-customer-29zn11wb8-vergeo-projects.vercel.app",
        # malformed
        "not-a-url",
    ],
)
def test_staging_rejects_non_matching_preview_origins(
    staging_client: TestClient, origin: str
) -> None:
    response = _cart_preflight(staging_client, origin)
    assert response.headers.get("access-control-allow-origin") != origin
    assert response.headers.get("access-control-allow-origin") is None


def test_production_rejects_immutable_preview_origin_unless_exact_listed(
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
        response = _cart_preflight(prod_client, _CUSTOMER_PREVIEW_ORIGIN)
        assert response.headers.get("access-control-allow-origin") != _CUSTOMER_PREVIEW_ORIGIN
        assert response.headers.get("access-control-allow-origin") is None

        # Production behavior is otherwise unchanged: the exact configured
        # origin still gets the credentials contract.
        response = _cart_preflight(prod_client, "https://vergeo5.com")
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://vergeo5.com"
        assert response.headers.get("access-control-allow-credentials") == "true"
    get_settings.cache_clear()


def test_development_ignores_staging_preview_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-closed: the Preview regex must never activate outside ENV=staging."""
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
    settings = get_settings()
    assert settings.cors_allow_origin_regex is None

    with TestClient(create_app()) as dev_client:
        response = _cart_preflight(dev_client, _CUSTOMER_PREVIEW_ORIGIN)
        assert response.headers.get("access-control-allow-origin") is None
    get_settings.cache_clear()


def test_staging_preview_regex_only_set_in_staging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dev")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "dev")
    monkeypatch.setenv("CORS_ORIGINS", _STAGING_STABLE_ORIGIN)
    from app.settings import STAGING_PREVIEW_ORIGIN_REGEX, get_settings

    for env, lenco_env, expected in (
        ("development", None, None),
        ("staging", "sandbox", STAGING_PREVIEW_ORIGIN_REGEX),
        ("production", None, None),
    ):
        monkeypatch.setenv("ENV", env)
        if lenco_env is None:
            monkeypatch.delenv("LENCO_ENV", raising=False)
        else:
            monkeypatch.setenv("LENCO_ENV", lenco_env)
        if env == "production":
            monkeypatch.setenv("CORS_ORIGINS", "https://vergeo5.com")
        else:
            monkeypatch.setenv("CORS_ORIGINS", _STAGING_STABLE_ORIGIN)
        get_settings.cache_clear()
        assert get_settings().cors_allow_origin_regex == expected
    get_settings.cache_clear()
