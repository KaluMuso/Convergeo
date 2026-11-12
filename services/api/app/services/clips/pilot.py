"""Clips pilot allowlist — who may upload, and whose clips the public may see.

The ``clips`` flag (``flags.py``) answers "does the feature exist?". This module
answers the narrower pilot question: **which vendors take part**. While the pilot
gate is enforced (the default), both halves of the feature are limited to the
vendors in ``clip_pilot_vendors``:

* **uploads** — ``POST /clips`` refuses a vendor who is not allowlisted, before an
  upload slot is signed, so a non-pilot vendor cannot spend a transcode credit;
* **viewing** — the feed, clip detail and every engagement endpoint serve only
  clips whose vendor is allowlisted. Removing a vendor hides their published
  clips on the next request, with no status change and nothing to undo.

Same posture as ``flags.py`` and ``services/intake/config.py``:

* **Fail closed.** A missing enforcement row means *enforced*; an unreadable
  enforcement row means *enforced*; an unreadable allowlist means *nobody*. Only
  an explicit JSON ``false`` in ``platform_config.clip_pilot_allowlist_enforced``
  opens Clips to every KYC-verified vendor — the post-pilot state.
* **Read fresh.** No cache, so an admin edit is effective on the next request.

The database carries the same rule for direct (PostgREST) reads through the
``clip_vendor_in_pilot`` function and a restrictive RLS policy on
``video_clips`` (migration ``20261113030000``), so the API and RLS agree.

Comments stay off for the whole pilot regardless of ``clips_comments``: see
:func:`comments_allowed`.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Final, Protocol

from app.errors import AppError

logger = logging.getLogger(__name__)

PILOT_TABLE: Final = "clip_pilot_vendors"
CONFIG_TABLE: Final = "platform_config"

#: ``platform_config`` key. Absent / unreadable / anything but JSON ``false``
#: → the allowlist is enforced.
ENFORCED_KEY: Final = "clip_pilot_allowlist_enforced"

#: Upper bound on one allowlist read. A pilot is "a small allowlist"; if this is
#: ever reached the pilot is over and the gate should be switched off instead.
MAX_PILOT_VENDORS: Final = 200


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


def allowlist_enforced(service_client: ServiceRoleClient) -> bool:
    """Whether Clips is limited to allowlisted vendors. ``True`` on any doubt."""
    try:
        rows = _rows(
            service_client.client.table(CONFIG_TABLE)
            .select("value")
            .eq("key", ENFORCED_KEY)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.warning("clip pilot enforcement read failed; treating as enforced")
        return True
    if not rows:
        return True
    raw = rows[0].get("value")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return True
    # Only an explicit boolean false opens the gate. "false" strings, 0, null and
    # malformed values all keep it closed.
    return raw is not False


def allowlisted_vendor_ids(service_client: ServiceRoleClient) -> frozenset[str]:
    """The pilot vendors. Empty on any read failure — empty means nobody."""
    try:
        rows = _rows(
            service_client.client.table(PILOT_TABLE)
            .select("vendor_id")
            .limit(MAX_PILOT_VENDORS)
            .execute()
        )
    except Exception:
        logger.warning("clip pilot allowlist read failed; treating as empty")
        return frozenset()
    return frozenset(str(row["vendor_id"]) for row in rows if row.get("vendor_id"))


def visible_vendor_ids(service_client: ServiceRoleClient) -> frozenset[str] | None:
    """Vendors whose clips the public may see, or ``None`` when unrestricted."""
    if not allowlist_enforced(service_client):
        return None
    return allowlisted_vendor_ids(service_client)


def vendor_in_pilot(service_client: ServiceRoleClient, vendor_id: str) -> bool:
    """Whether this vendor may take part right now."""
    visible = visible_vendor_ids(service_client)
    if visible is None:
        return True
    return bool(vendor_id) and vendor_id in visible


def require_vendor_in_pilot(service_client: ServiceRoleClient, vendor_id: str) -> None:
    """Refuse an upload from a vendor outside the pilot.

    403 with a ``message_key`` (not the 404 used for the master flag): the vendor
    is authenticated and KYC-verified, the feature is on, and telling them they
    are not in the pilot yet is the honest, actionable answer.
    """
    if vendor_in_pilot(service_client, vendor_id):
        return
    raise AppError(
        code="clip_pilot_not_allowlisted",
        message="Clips is in a limited pilot and this shop is not part of it yet",
        http_status=403,
        details={"message_key": "vendor.clips.errors.notInPilot"},
    )


def comments_allowed(service_client: ServiceRoleClient, comments_flag_on: bool) -> bool:
    """Comments need the flag AND the pilot gate to be off.

    The pilot brief is "comments stay off". Tying that to the pilot gate means an
    accidental ``clips_comments`` flip during the pilot changes nothing, and the
    comment surface can only open once the pilot itself has been ended on purpose.
    """
    return comments_flag_on and not allowlist_enforced(service_client)
