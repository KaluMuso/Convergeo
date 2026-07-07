from __future__ import annotations

from functools import cached_property, lru_cache
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    @model_validator(mode="after")
    def validate_cors_origins(self) -> Self:
        if not self.cors_origin_list:
            raise ValueError("CORS_ORIGINS must include at least one origin")
        if self.env != "development" and "*" in self.cors_origin_list:
            raise ValueError("CORS_ORIGINS cannot include '*' outside development")
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
        field_name = str(issue.get("loc", ("settings",))[0])
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
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise ValueError(format_settings_error(exc)) from exc
