"""Lenco API configuration — base URLs and env var names (never secret values)."""

from __future__ import annotations

import os
from enum import StrEnum

LENCO_API_TOKEN_ENV = "LENCO_API_TOKEN"
LENCO_ENV_ENV = "LENCO_ENV"
LENCO_SANDBOX_BASE_URL_ENV = "LENCO_SANDBOX_BASE_URL"
LENCO_ENABLE_ZAMTEL_COLLECTIONS_ENV = "LENCO_ENABLE_ZAMTEL_COLLECTIONS"

PROD_BASE_URL = "https://api.lenco.co/access/v2"
# Sandbox REST base is not in the public PDFs (F9b); override via LENCO_SANDBOX_BASE_URL.
DEFAULT_SANDBOX_BASE_URL = "https://api.sandbox.lenco.co/access/v2"

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_IDEMPOTENT_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 0.5


class LencoEnvironment(StrEnum):
    PRODUCTION = "production"
    SANDBOX = "sandbox"


def get_lenco_environment() -> LencoEnvironment:
    raw = os.environ.get(LENCO_ENV_ENV, LencoEnvironment.PRODUCTION.value).strip().lower()
    if raw in {LencoEnvironment.SANDBOX.value, "sandbox", "dev", "development"}:
        return LencoEnvironment.SANDBOX
    return LencoEnvironment.PRODUCTION


def get_base_url() -> str:
    if get_lenco_environment() == LencoEnvironment.SANDBOX:
        return os.environ.get(LENCO_SANDBOX_BASE_URL_ENV, DEFAULT_SANDBOX_BASE_URL)
    return PROD_BASE_URL


def get_api_token() -> str:
    """Return the Lenco API bearer token from the environment."""
    return os.environ[LENCO_API_TOKEN_ENV]


def zamtel_collections_enabled() -> bool:
    """Gate Zamtel USSD-push collections behind F9a confirmation."""
    raw = os.environ.get(LENCO_ENABLE_ZAMTEL_COLLECTIONS_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}
