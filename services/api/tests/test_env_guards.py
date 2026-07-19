"""STG-01 environment isolation guards."""

from __future__ import annotations

import pytest
from app.core.env_guards import (
    PROD_API_HOST,
    PROD_SUPABASE_PROJECT_REF,
    StagingIsolationError,
    assert_staging_api_host_isolated,
    assert_staging_supabase_isolated,
    extract_supabase_project_ref,
    load_forbidden_identifiers_file,
    outbound_suppressed,
    payouts_suppressed,
    require_sandbox_payments,
)
from app.settings import get_settings
from fastapi.testclient import TestClient


def test_forbidden_file_sync() -> None:
    data = load_forbidden_identifiers_file()
    assert data.get("PROD_SUPABASE_PROJECT_REF") == PROD_SUPABASE_PROJECT_REF
    assert data.get("PROD_API_HOST") == PROD_API_HOST


def test_extract_supabase_project_ref() -> None:
    assert (
        extract_supabase_project_ref("https://dpadrlxukcjbewpqympu.supabase.co")
        == "dpadrlxukcjbewpqympu"
    )
    assert extract_supabase_project_ref("https://abcdefghij1234567890.supabase.co") == (
        "abcdefghij1234567890"
    )


def test_assert_staging_refuses_production_supabase() -> None:
    with pytest.raises(StagingIsolationError, match="production Supabase"):
        assert_staging_supabase_isolated(
            f"https://{PROD_SUPABASE_PROJECT_REF}.supabase.co",
            env="staging",
        )


def test_assert_staging_allows_other_supabase() -> None:
    assert_staging_supabase_isolated(
        "https://abcdefghij1234567890.supabase.co",
        env="staging",
    )


def test_assert_staging_refuses_production_api_host() -> None:
    with pytest.raises(StagingIsolationError, match="production API host"):
        assert_staging_api_host_isolated(PROD_API_HOST, env="staging")
    with pytest.raises(StagingIsolationError, match="production API host"):
        assert_staging_api_host_isolated("https://api.vergeo5.com", env="staging")


def test_assert_staging_allows_staging_api_host() -> None:
    assert_staging_api_host_isolated("api.staging.vergeo5.com", env="staging")


def test_guards_noop_outside_staging() -> None:
    assert_staging_supabase_isolated(
        f"https://{PROD_SUPABASE_PROJECT_REF}.supabase.co",
        env="production",
    )
    assert_staging_api_host_isolated(PROD_API_HOST, env="development")


def test_settings_staging_refuses_production_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", f"https://{PROD_SUPABASE_PROJECT_REF}.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("LENCO_ENV", "sandbox")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="production Supabase"):
        get_settings()


def test_settings_staging_refuses_production_api_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefghij1234567890.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("LENCO_ENV", "sandbox")
    monkeypatch.setenv("PUBLIC_API_HOST", "api.vergeo5.com")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="production API host"):
        get_settings()


def test_settings_staging_requires_sandbox_lenco(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefghij1234567890.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.delenv("LENCO_ENV", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="LENCO_ENV=sandbox"):
        get_settings()


def test_settings_staging_accepts_isolated_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefghij1234567890.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("LENCO_ENV", "sandbox")
    monkeypatch.setenv("PUBLIC_API_HOST", "api.staging.vergeo5.com")
    monkeypatch.setenv("GIT_SHA", "abc1234")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.env == "staging"
    assert settings.git_sha == "abc1234"


def test_outbound_and_payouts_suppressed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.delenv("STAGING_ALLOW_OUTBOUND", raising=False)
    monkeypatch.delenv("STAGING_ALLOW_PAYOUTS", raising=False)
    assert outbound_suppressed(env="staging") is True
    assert payouts_suppressed(env="staging") is True
    monkeypatch.setenv("STAGING_ALLOW_OUTBOUND", "true")
    monkeypatch.setenv("STAGING_ALLOW_PAYOUTS", "1")
    # Clear any cached state — helpers read os.environ each call.
    assert outbound_suppressed() is False
    assert payouts_suppressed() is False


def test_require_sandbox_payments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LENCO_ENV", raising=False)
    with pytest.raises(StagingIsolationError):
        require_sandbox_payments(env="staging")
    monkeypatch.setenv("LENCO_ENV", "sandbox")
    require_sandbox_payments(env="staging")


def test_fingerprint_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_SHA", "deadbeef")
    monkeypatch.setenv("API_IMAGE_TAG", "deadbeef")
    get_settings.cache_clear()
    # Recreate app settings by hitting endpoint on existing client — settings
    # already loaded at app create. Probe shape only on the shared client.
    response = client.get("/fingerprint")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "env" in body
    assert "git_sha" in body
    assert "supabase_project_ref" in body
    assert "service_role" not in str(body).lower()
    assert PROD_SUPABASE_PROJECT_REF not in body.get("supabase_project_ref", "")