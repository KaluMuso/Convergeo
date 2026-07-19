"""Hard environment-separation guards for staging processes.

Refuse known production identifiers when ``ENV=staging``. Public identifiers
only — never secret values. Keep in sync with
``infra/staging/forbidden-production-identifiers.env``.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

# Canonical forbidden production identifiers (public).
PROD_SUPABASE_PROJECT_REF: Final = "dpadrlxukcjbewpqympu"
PROD_API_HOST: Final = "api.vergeo5.com"
PROD_CUSTOMER_HOST: Final = "vergeo5.com"
PROD_WWW_HOST: Final = "www.vergeo5.com"
PROD_VENDOR_HOST: Final = "vendor.vergeo5.com"
PROD_ADMIN_HOST: Final = "admin.vergeo5.com"
PROD_N8N_HOST: Final = "n8n.vergeo5.com"

_SUPABASE_HOST_RE = re.compile(
    r"^(?P<ref>[a-z0-9]+)\.supabase\.(?:co|in|com)$",
    re.IGNORECASE,
)

_REPO_IDENTIFIERS = (
    Path(__file__).resolve().parents[4]
    / "infra"
    / "staging"
    / "forbidden-production-identifiers.env"
)


class StagingIsolationError(ValueError):
    """Raised when staging configuration collides with production identifiers."""


def extract_supabase_project_ref(supabase_url: str) -> str | None:
    """Return the Supabase project ref from a URL, or None if unparseable."""
    raw = (supabase_url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    match = _SUPABASE_HOST_RE.match(host)
    if match:
        return match.group("ref").lower()
    # Also accept bare refs (CI / misconfigured env).
    if re.fullmatch(r"[a-z0-9]{20}", raw.lower()):
        return raw.lower()
    return None


def normalize_host(value: str) -> str:
    """Normalize a host or URL to a lowercase hostname without port."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    return (parsed.hostname or "").lower()


def assert_staging_supabase_isolated(supabase_url: str, *, env: str) -> None:
    """Refuse production Supabase project ref when ENV=staging."""
    if env != "staging":
        return
    ref = extract_supabase_project_ref(supabase_url)
    if ref == PROD_SUPABASE_PROJECT_REF:
        raise StagingIsolationError(
            "ENV=staging refuses production Supabase project ref "
            f"({PROD_SUPABASE_PROJECT_REF}). Provision a separate staging project."
        )


def assert_staging_api_host_isolated(api_host: str, *, env: str) -> None:
    """Refuse production API hostname when ENV=staging."""
    if env != "staging":
        return
    host = normalize_host(api_host)
    if host == PROD_API_HOST:
        raise StagingIsolationError(
            f"ENV=staging refuses production API host ({PROD_API_HOST}). "
            "Use api.staging.vergeo5.com (or the STAGING_API_HOST secret)."
        )


def outbound_suppressed(*, env: str | None = None) -> bool:
    """True when WhatsApp/SMS/email must not leave the staging plane."""
    resolved = (env if env is not None else os.environ.get("ENV", "development")).strip().lower()
    if resolved != "staging":
        return False
    allow = os.environ.get("STAGING_ALLOW_OUTBOUND", "").strip().lower()
    return allow not in {"1", "true", "yes", "on"}


def payouts_suppressed(*, env: str | None = None) -> bool:
    """True when Lenco payouts must not execute on staging."""
    resolved = (env if env is not None else os.environ.get("ENV", "development")).strip().lower()
    if resolved != "staging":
        return False
    allow = os.environ.get("STAGING_ALLOW_PAYOUTS", "").strip().lower()
    return allow not in {"1", "true", "yes", "on"}


def require_sandbox_payments(*, env: str) -> None:
    """When ENV=staging, refuse LENCO_ENV=production."""
    if env != "staging":
        return
    lenco_env = os.environ.get("LENCO_ENV", "").strip().lower()
    if lenco_env in {"", "production", "prod", "live"}:
        raise StagingIsolationError(
            "ENV=staging requires LENCO_ENV=sandbox (or mock). "
            "Production payment credentials must not be used on staging."
        )


@lru_cache
def load_forbidden_identifiers_file() -> dict[str, str]:
    """Parse infra/staging/forbidden-production-identifiers.env (for sync tests)."""
    path = _REPO_IDENTIFIERS
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        out[key.strip()] = value.strip()
    return out
