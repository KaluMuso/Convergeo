from __future__ import annotations

from functools import cached_property, lru_cache
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.env_guards import (
    StagingIsolationError,
    assert_staging_api_host_isolated,
    assert_staging_supabase_isolated,
    require_sandbox_payments,
)
from app.media.cloudinary_signing import parse_cloudinary_url

SECRET_FIELDS = frozenset(
    {
        "supabase_service_role_key",
        "supabase_anon_key",
        "cloudinary_url",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "CLOUDINARY_URL",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_anon_key: str = Field(alias="SUPABASE_ANON_KEY")
    env: Literal["development", "staging", "production"] = Field(alias="ENV", default="development")
    log_level: str = Field(alias="LOG_LEVEL", default="INFO")
    cors_origins: str = Field(
        alias="CORS_ORIGINS",
        default="http://localhost:3000,http://localhost:3001,http://localhost:3002",
    )
    cloudinary_url: str = Field(alias="CLOUDINARY_URL", default="")
    # Observability (M16-P06). DSN unset -> Sentry is a strict no-op (dev/CI safe);
    # never commit a DSN. release = git sha, environment defaults to `env`.
    sentry_dsn: str = Field(alias="SENTRY_DSN", default="")
    sentry_environment: str = Field(alias="SENTRY_ENVIRONMENT", default="")
    sentry_release: str = Field(alias="SENTRY_RELEASE", default="")
    sentry_traces_sample_rate: float = Field(alias="SENTRY_TRACES_SAMPLE_RATE", default=0.0)
    # Non-secret build fingerprint (git SHA / image tag). Exposed on /fingerprint.
    git_sha: str = Field(alias="GIT_SHA", default="")
    api_image_tag: str = Field(alias="API_IMAGE_TAG", default="")
    # Public API hostname this process believes it serves (staging isolation check).
    public_api_host: str = Field(alias="PUBLIC_API_HOST", default="")

    @model_validator(mode="after")
    def validate_cors_origins(self) -> Self:
        if not self.cors_origin_list:
            raise ValueError("CORS_ORIGINS must include at least one origin")
        if self.env != "development" and "*" in self.cors_origin_list:
            raise ValueError("CORS_ORIGINS cannot include '*' outside development")
        return self

    @model_validator(mode="after")
    def validate_staging_isolation(self) -> Self:
        """Refuse production Supabase/API identifiers when ENV=staging."""
        try:
            assert_staging_supabase_isolated(self.supabase_url, env=self.env)
            if self.public_api_host:
                assert_staging_api_host_isolated(self.public_api_host, env=self.env)
            require_sandbox_payments(env=self.env)
        except StagingIsolationError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @cached_property
    def cloudinary_cloud_name(self) -> str:
        return self._cloudinary_credentials[0]

    @cached_property
    def cloudinary_api_key(self) -> str:
        return self._cloudinary_credentials[1]

    @cached_property
    def cloudinary_api_secret(self) -> str:
        return self._cloudinary_credentials[2]

    @cached_property
    def _cloudinary_credentials(self) -> tuple[str, str, str]:
        if not self.cloudinary_url:
            raise ValueError("CLOUDINARY_URL is required for media signing")
        return parse_cloudinary_url(self.cloudinary_url)


def format_settings_error(error: ValidationError) -> str:
    messages: list[str] = []
    for issue in error.errors():
        loc = issue.get("loc") or ()
        # Model-level validators (e.g. staging isolation) may have an empty loc.
        if not loc:
            msg = str(issue.get("msg") or "invalid settings")
            # Pydantic prefixes with "Value error, " — strip for a cleaner raise.
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, ") :]
            messages.append(msg)
            continue
        field_name = str(loc[0])
        if field_name in SECRET_FIELDS:
            messages.append(
                f"Missing or invalid required environment variable: {field_name} (value redacted)"
            )
        else:
            messages.append(f"Missing or invalid required environment variable: {field_name}")
    return "\n".join(messages)


@lru_cache
def get_settings() -> Settings:
    try:
        settings = Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise ValueError(format_settings_error(exc)) from exc
    # Initialise Sentry once per process (no-op unless SENTRY_DSN is set).
    from app.core.sentry import init_sentry

    init_sentry(settings)
    return settings
