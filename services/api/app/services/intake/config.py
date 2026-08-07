"""M18-P00 — fail-closed config seam for the WAHA vendor-intake lane (D35).

Every later M18 pebble reads its gates from here so there is exactly one place
where "is this lane live, and for whom" is decided.

Three rules govern this module:

1. **Fail closed.** A missing flag row, an unreadable table, a malformed
   allowlist, or any exception resolves to *disabled* / *not allowlisted*. The
   lane is never open by accident. This mirrors the ``public_launch`` read in
   ``app.routers.beta.is_public_launch``.
2. **Read fresh.** The flag is read on every call, never cached, so the
   operator's kill switch (``waha_vendor_intake = false`` in the admin config
   UI) takes effect immediately with no deploy — see
   ``docs/ops/waha-vendor-intake.md`` Part B R4.
3. **Never default a secret.** Each ``WAHA_INTAKE_*`` accessor raises
   ``configuration_error`` when unset rather than falling back to a default or,
   worse, to a Lane 1 / Lenco value. Rotating ``WAHA_INTAKE_*`` must never
   re-key the Cloud API or Lenco credentials.

This module makes **no network calls** and holds **no outbound client** — the
lane is strictly inbound-only.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

from app.errors import AppError

logger = logging.getLogger(__name__)

# --- Config keys ------------------------------------------------------------
INTAKE_FLAG = "waha_vendor_intake"
INTAKE_ALLOWLIST_KEY = "waha_intake_vendor_allowlist"

# --- Secret / config env names (values live only in the isolated host's store)
ENV_BASE_URL = "WAHA_INTAKE_BASE_URL"
ENV_API_KEY = "WAHA_INTAKE_API_KEY"
ENV_SESSION = "WAHA_INTAKE_SESSION"
ENV_WEBHOOK_SECRET = "WAHA_INTAKE_WEBHOOK_SECRET"
ENV_ALLOWED_IPS = "WAHA_INTAKE_ALLOWED_IPS"
ENV_SENDER_E164 = "WAHA_INTAKE_SENDER_E164"

# Lane 1's sender, read ONLY to assert NB-7 three-way number separation. This
# module never sends through it.
_ENV_CLOUD_API_SENDER = "WHATSAPP_PHONE_NUMBER_ID"
_ENV_CLOUD_API_SENDER_E164 = "WHATSAPP_SENDER_E164"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def intake_enabled(service_client: ServiceRoleClient) -> bool:
    """Return whether the WAHA vendor-intake lane is enabled.

    Read fresh on every call so an admin flag flip is effective immediately
    (kill switch, no deploy). Defaults to ``False`` when the row is missing or
    the read fails — the lane is never open by accident.
    """
    try:
        response = (
            service_client.client.table("feature_flags")
            .select("enabled")
            .eq("flag", INTAKE_FLAG)
            .maybe_single()
            .execute()
        )
    except Exception:
        # Fail closed and stay quiet about specifics: a config read failure
        # must not become a channel for probing the lane's existence.
        logger.warning("intake flag read failed; treating lane as disabled")
        return False

    rows = _rows(response)
    if not rows:
        return False
    return bool(rows[0].get("enabled", False))


def _allowlist(service_client: ServiceRoleClient) -> list[str]:
    """Return the pilot vendor allowlist; empty on any doubt."""
    try:
        response = (
            service_client.client.table("platform_config")
            .select("value")
            .eq("key", INTAKE_ALLOWLIST_KEY)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.warning("intake allowlist read failed; treating as empty")
        return []

    rows = _rows(response)
    if not rows:
        return []

    raw = rows[0].get("value")
    # platform_config stores jsonb; a client may hand back either a decoded
    # list or the raw JSON text depending on the driver.
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("intake allowlist is not valid JSON; treating as empty")
            return []

    if not isinstance(raw, list):
        logger.warning("intake allowlist is not a list; treating as empty")
        return []

    return [item for item in raw if isinstance(item, str) and item.strip()]


def vendor_allowlisted(service_client: ServiceRoleClient, vendor_id: str) -> bool:
    """Return whether ``vendor_id`` is in the pilot allowlist.

    An empty or malformed allowlist means *nobody*: enabling the flag alone
    never opens the lane to all vendors before the founder's Stage-1 sign-off
    (``docs/ops/waha-vendor-intake.md`` §9/§10).
    """
    if not vendor_id or not vendor_id.strip():
        return False
    return vendor_id.strip() in set(_allowlist(service_client))


def lane_open_for(service_client: ServiceRoleClient, vendor_id: str) -> bool:
    """Both gates at once: flag on AND vendor allowlisted."""
    return intake_enabled(service_client) and vendor_allowlisted(service_client, vendor_id)


def require_lane_open_for(service_client: ServiceRoleClient, vendor_id: str) -> None:
    """Fail closed unless the pilot lane is open for this vendor.

    404 (not 403) so a disabled lane does not confirm its existence to probes.
    """
    if not lane_open_for(service_client, vendor_id):
        raise AppError(
            code="not_found",
            message="Not found",
            http_status=404,
        )


def _required_env(name: str) -> str:
    """Read a required ``WAHA_INTAKE_*`` value or fail closed.

    Never defaults, never falls back to a Lane 1 / Lenco value, and never logs
    the value itself.
    """
    value = os.environ.get(name, "").strip()
    if not value:
        raise AppError(
            code="configuration_error",
            message="WAHA intake is not configured",
            http_status=503,
            details={"missing": name},
        )
    return value


def base_url() -> str:
    return _required_env(ENV_BASE_URL)


def api_key() -> str:
    return _required_env(ENV_API_KEY)


def session_name() -> str:
    return _required_env(ENV_SESSION)


def webhook_secret() -> str:
    """Shared secret for the inbound HMAC-SHA-512 verification (WAHA 2026.5.1).

    Missing secret raises, so signature verification can never silently pass.
    """
    return _required_env(ENV_WEBHOOK_SECRET)


def allowed_ips() -> list[str]:
    """Space-separated CIDR allowlist for the intake route's edge matcher."""
    return _required_env(ENV_ALLOWED_IPS).split()


def sender_e164() -> str:
    return _required_env(ENV_SENDER_E164)


def _cloud_api_sender() -> str:
    """Lane 1's sender identity, if configured. Read only for the NB-7 check."""
    for name in (_ENV_CLOUD_API_SENDER_E164, _ENV_CLOUD_API_SENDER):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _digits(value: str) -> str:
    return "".join(char for char in value if char.isdigit())


def sender_separation_ok() -> bool:
    """NB-7 guard: the intake number must differ from the Cloud API sender.

    A WhatsApp ban on the WAHA number must never be able to contaminate Lane 1,
    which is only true if they are genuinely different numbers. Fails closed:
    if Lane 1's sender is not configured we cannot prove separation, so we
    report *not ok* rather than assuming it.
    """
    try:
        intake = _digits(sender_e164())
    except AppError:
        return False

    cloud = _digits(_cloud_api_sender())
    if not cloud:
        return False
    return intake != cloud


def assert_sender_separation() -> None:
    """Raise unless NB-7 separation is provable."""
    if not sender_separation_ok():
        raise AppError(
            code="configuration_error",
            message="WAHA intake sender must be a different number from the Cloud API sender",
            http_status=503,
            details={"check": "NB-7"},
        )
