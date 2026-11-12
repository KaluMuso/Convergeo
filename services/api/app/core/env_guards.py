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
from urllib.parse import urlparse, urlsplit

# Canonical forbidden production identifiers (public).
PROD_SUPABASE_PROJECT_REF: Final = "dpadrlxukcjbewpqympu"
# Canonical staging project (vergeo-sandbox). Seed/fixture tooling must target this
# ref exactly — there is no generic override env var.
STAGING_SUPABASE_PROJECT_REF: Final = "iyasmrmbcrvlfxpzescb"
PROD_API_HOST: Final = "api.vergeo5.com"
PROD_CUSTOMER_HOST: Final = "vergeo5.com"
PROD_WWW_HOST: Final = "www.vergeo5.com"
PROD_VENDOR_HOST: Final = "vendor.vergeo5.com"
PROD_ADMIN_HOST: Final = "admin.vergeo5.com"
PROD_N8N_HOST: Final = "n8n.vergeo5.com"
DEFAULT_STAGING_LENCO_BASE_URL: Final = "https://api.sandbox.lenco.co/access/v2"
_LENCO_SANDBOX_HOSTS: Final = frozenset({"api.sandbox.lenco.co", "sandbox.lenco.co"})

_SUPABASE_HOST_RE = re.compile(
    r"^(?P<ref>[a-z0-9]+)\.supabase\.(?:co|in|com)$",
    re.IGNORECASE,
)


class StagingIsolationError(ValueError):
    """Raised when staging configuration collides with production identifiers."""


def _forbidden_identifiers_path() -> Path | None:
    """Locate the repo-side forbidden-identifiers file when present.

    In the Docker runtime image the layout is ``/app/app/core/...`` (no monorepo
    root), so this returns ``None`` and callers fall back to the in-module
    constants. Never raise at import time.
    """
    here = Path(__file__).resolve()
    # Walk up looking for infra/staging/forbidden-production-identifiers.env
    for parent in here.parents:
        candidate = parent / "infra" / "staging" / "forbidden-production-identifiers.env"
        if candidate.is_file():
            return candidate
    return None


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


def assert_staging_project_target(
    project_ref: str | None,
    *,
    require_exact: bool = False,
) -> None:
    """Refuse production and, when required, any non-canonical staging project ref.

  Synthetic seed/cleanup must only run against ``STAGING_SUPABASE_PROJECT_REF``.
  There is intentionally no generic ``ALLOW_*`` override environment variable.
    """
    if not project_ref:
        raise StagingIsolationError(
            "staging project ref is required for synthetic seed/cleanup"
        )
    normalized = project_ref.strip().lower()
    if normalized == PROD_SUPABASE_PROJECT_REF:
        raise StagingIsolationError(
            "refusing production Supabase project ref "
            f"({PROD_SUPABASE_PROJECT_REF})"
        )
    if require_exact and normalized != STAGING_SUPABASE_PROJECT_REF:
        raise StagingIsolationError(
            "refusing non-staging project ref "
            f"({normalized}); expected {STAGING_SUPABASE_PROJECT_REF}"
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
    """Require an explicit sandbox label and a sandbox REST destination on staging."""
    if env != "staging":
        return
    lenco_env = os.environ.get("LENCO_ENV", "").strip().lower()
    if lenco_env != "sandbox":
        raise StagingIsolationError(
            "ENV=staging requires LENCO_ENV=sandbox. "
            "Production payment credentials must not be used on staging."
        )
    assert_staging_lenco_destination(
        os.environ.get("LENCO_SANDBOX_BASE_URL", DEFAULT_STAGING_LENCO_BASE_URL)
    )


def assert_staging_lenco_destination(base_url: str) -> None:
    """Refuse non-sandbox or malformed v2 REST targets before a provider request."""
    try:
        parsed = urlsplit(base_url.strip())
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in _LENCO_SANDBOX_HOSTS
            and parsed.port in {None, 443}
            and parsed.username is None
            and parsed.password is None
            and parsed.path.rstrip("/") == "/access/v2"
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise StagingIsolationError(
            "ENV=staging requires an HTTPS Lenco sandbox /access/v2 destination"
        )


@lru_cache
def load_forbidden_identifiers_file() -> dict[str, str]:
    """Parse infra/staging/forbidden-production-identifiers.env (for sync tests)."""
    path = _forbidden_identifiers_path()
    if path is None:
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        out[key.strip()] = value.strip()
    return out
