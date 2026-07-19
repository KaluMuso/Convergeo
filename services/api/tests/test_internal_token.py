"""Fail-closed internal token resolution (production/staging must not use dev defaults)."""

from __future__ import annotations

import pytest
from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from fastapi.testclient import TestClient

ENV_VAR = "INTERNAL_PAYOUTS_TOKEN"
DEV_DEFAULT = "dev-internal-payouts"


class TestResolveInternalToken:
    def test_development_allows_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "development")
        monkeypatch.delenv(ENV_VAR, raising=False)
        assert resolve_internal_token(ENV_VAR, dev_default=DEV_DEFAULT) == DEV_DEFAULT

    def test_test_env_allows_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "test")
        monkeypatch.delenv(ENV_VAR, raising=False)
        assert resolve_internal_token(ENV_VAR, dev_default=DEV_DEFAULT) == DEV_DEFAULT

    def test_unset_env_defaults_to_development(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv(ENV_VAR, raising=False)
        assert resolve_internal_token(ENV_VAR, dev_default=DEV_DEFAULT) == DEV_DEFAULT

    def test_development_prefers_explicit_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv(ENV_VAR, "local-secret")
        assert resolve_internal_token(ENV_VAR, dev_default=DEV_DEFAULT) == "local-secret"

    @pytest.mark.parametrize("env_name", ["production", "staging", "prod"])
    def test_strict_env_requires_token(
        self, monkeypatch: pytest.MonkeyPatch, env_name: str
    ) -> None:
        monkeypatch.setenv("ENV", env_name)
        monkeypatch.delenv(ENV_VAR, raising=False)
        with pytest.raises(InternalTokenMisconfigured, match=ENV_VAR):
            resolve_internal_token(ENV_VAR, dev_default=DEV_DEFAULT)

    @pytest.mark.parametrize("env_name", ["production", "staging", "prod"])
    def test_strict_env_rejects_empty_token(
        self, monkeypatch: pytest.MonkeyPatch, env_name: str
    ) -> None:
        monkeypatch.setenv("ENV", env_name)
        monkeypatch.setenv(ENV_VAR, "   ")
        with pytest.raises(InternalTokenMisconfigured, match=ENV_VAR):
            resolve_internal_token(ENV_VAR, dev_default=DEV_DEFAULT)

    @pytest.mark.parametrize("env_name", ["production", "staging", "prod"])
    def test_strict_env_rejects_dev_default_string(
        self, monkeypatch: pytest.MonkeyPatch, env_name: str
    ) -> None:
        monkeypatch.setenv("ENV", env_name)
        monkeypatch.setenv(ENV_VAR, DEV_DEFAULT)
        with pytest.raises(InternalTokenMisconfigured, match="development default"):
            resolve_internal_token(ENV_VAR, dev_default=DEV_DEFAULT)

    def test_production_accepts_real_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv(ENV_VAR, "prod-secret-not-default")
        assert (
            resolve_internal_token(ENV_VAR, dev_default=DEV_DEFAULT) == "prod-secret-not-default"
        )

    def test_explicit_env_kwarg_overrides_os(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "development")
        monkeypatch.delenv(ENV_VAR, raising=False)
        with pytest.raises(InternalTokenMisconfigured):
            resolve_internal_token(ENV_VAR, dev_default=DEV_DEFAULT, env="production")


class TestInternalTokenHttpFailClosed:
    """Money-critical routers must 503 when production lacks a real token."""

    def test_payouts_tick_503_when_production_token_unset(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENV", "production")
        monkeypatch.delenv(ENV_VAR, raising=False)
        response = client.post(
            "/internal/payouts/tick",
            headers={"X-Internal-Token": DEV_DEFAULT},
        )
        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "configuration_error"

    def test_payouts_tick_503_when_production_uses_dev_default(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv(ENV_VAR, DEV_DEFAULT)
        response = client.post(
            "/internal/payouts/tick",
            headers={"X-Internal-Token": DEV_DEFAULT},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "configuration_error"

    def test_release_job_tick_503_when_staging_token_unset(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENV", "staging")
        monkeypatch.delenv("INTERNAL_RELEASE_JOB_TOKEN", raising=False)
        response = client.post(
            "/internal/release-job/tick",
            headers={"X-Internal-Token": "dev-internal-release-job"},
        )
        assert response.status_code == 503

    def test_job_completion_autoconfirm_503_when_production_token_unset(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENV", "production")
        monkeypatch.delenv("INTERNAL_JOB_COMPLETION_TOKEN", raising=False)
        response = client.post(
            "/internal/job-completion/auto-confirm",
            json={"limit": 1},
            headers={"X-Internal-Token": "dev-internal-job-completion"},
        )
        assert response.status_code == 503

    def test_development_still_accepts_dev_default_token(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENV", "development")
        monkeypatch.delenv(ENV_VAR, raising=False)
        # Wrong token → 401 (proves default was resolved and compared, not 503).
        denied = client.post(
            "/internal/payouts/tick",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert denied.status_code == 401
        missing = client.post("/internal/payouts/tick")
        assert missing.status_code == 401
