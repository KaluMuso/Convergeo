from __future__ import annotations

from functools import cached_property, lru_cache
from typing import Literal, Self
from urllib.parse import urlsplit

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

# Vercel immutable Preview deployment origins for Convergeo's three staging
# portals (customer/vendor/admin), confirmed from primary evidence (strict
# E2E run #52 Playwright traces plus the real fixture URLs already used by
# scripts/qa/self-test/e2e-staging-probe.test.mjs) against the "vergeo-projects"
# Vercel team namespace. Matches both the per-deployment hash suffix (e.g.
# "29zn11wb8") and the mutable branch-alias suffix ("git-staging") — both are
# lowercase letters/digits/hyphens only.
#
# Code-owned and NOT operator-configurable via CORS_ORIGINS: every SHA-pinned
# Preview deployment gets a newly generated hostname, so a static allowlist
# would require an API redeploy per deployment. See RC-6 / PR-F3.
STAGING_PREVIEW_ORIGIN_REGEX = (
    r"^https://convergeo-(customer|vendor|admin)-[a-z0-9-]+-vergeo-projects\.vercel\.app$"
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
    # M17-P02: where Cloudinary posts the async eager-transcode callback.
    # Empty in dev/CI, which simply means no notification_url is signed — the
    # upload still works, the clip just waits in `screening` until one is set.
    cloudinary_notification_url: str = Field(
        alias="CLOUDINARY_NOTIFICATION_URL", default=""
    )
    # Callback signing secret. Kept separate from the API secret so it can be
    # rotated without re-issuing upload credentials.
    cloudinary_webhook_secret: str = Field(
        alias="CLOUDINARY_WEBHOOK_SECRET", default=""
    )
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
    # Outbound n8n webhook for domain events (order.created, vendor.kyc_updated, …).
    # Empty = no-op (dev/CI safe).
    n8n_webhook_url: str = Field(alias="N8N_WEBHOOK_URL", default="")
    # Upstash Redis REST — OTP per-number rate limiting (3 requests / 15 min).
    upstash_redis_rest_url: str = Field(alias="UPSTASH_REDIS_REST_URL", default="")
    upstash_redis_rest_token: str = Field(alias="UPSTASH_REDIS_REST_TOKEN", default="")

    @model_validator(mode="after")
    def validate_cors_origins(self) -> Self:
        if not self.cors_origin_list:
            raise ValueError("CORS_ORIGINS must include at least one origin")
        origins = self.cors_origin_list
        if "*" in origins:
            if self.env != "development":
                raise ValueError("CORS_ORIGINS cannot include '*' outside development")
            if len(origins) != 1:
                raise ValueError("CORS_ORIGINS wildcard cannot be combined with named origins")
            return self

        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "CORS_ORIGINS entries must be exact http(s) origins without a path, "
                    "query, fragment, or credentials"
                )
            hostname = (parsed.hostname or "").lower()
            if not hostname:
                raise ValueError("CORS_ORIGINS entries must include a hostname")
            if self.env == "production":
                if parsed.scheme != "https":
                    raise ValueError("CORS_ORIGINS must use https in production")
                if hostname == "localhost" or hostname in {"127.0.0.1", "::1"}:
                    raise ValueError("CORS_ORIGINS must not include localhost in production")
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

    @property
    def cors_allow_origin_regex(self) -> str | None:
        """Staging-only immutable-Preview CORS pattern for CORSMiddleware.

        Fail-closed: returns None (Starlette's allow_origin_regex disabled)
        for every ENV other than "staging", so this can never become active
        outside staging regardless of CORS_ORIGINS content.
        """
        if self.env != "staging":
            return None
        return STAGING_PREVIEW_ORIGIN_REGEX

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
