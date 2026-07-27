"""M17 — the two config gates that hold the whole mountain closed.

``clips`` decides whether the feature exists for customers at all; ``clips_comments``
decides whether the comment surface is live (F-V2: built, shipped OFF).

Both follow the same posture as ``services/intake/config.py``:

* **Fail closed.** A missing row, an unreadable table, or any exception resolves
  to *disabled*. Neither gate is ever open by accident.
* **Read fresh.** No caching, so an admin flipping the flag in the config UI takes
  effect on the next request with no deploy — which is also the kill switch.

Keeping this in one module rather than inlining the read per router means there is
exactly one answer to "is Clips on?", and one place to change it.
"""

from __future__ import annotations

import logging
from typing import Any, Final, Protocol

logger = logging.getLogger(__name__)

#: Master gate (F-V1). OFF until the founder confirms placement and — per F-V4 —
#: Cloudinary plan headroom. While OFF no upload can spend a transcode credit.
CLIPS_FLAG: Final = "clips"

#: Comment surface (F-V2). Built, moderated and rate-limited, but OFF for beta
#: week 1 per the spec's own recommendation.
CLIPS_COMMENTS_FLAG: Final = "clips_comments"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _flag_enabled(service_client: ServiceRoleClient, flag: str) -> bool:
    try:
        response = (
            service_client.client.table("feature_flags")
            .select("enabled")
            .eq("flag", flag)
            .maybe_single()
            .execute()
        )
    except Exception:
        # Stay quiet about specifics: a config read failure must not become a
        # channel for probing which flags exist.
        logger.warning("clip flag read failed; treating as disabled")
        return False

    data = getattr(response, "data", None)
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        return False
    return bool(data.get("enabled", False))


def clips_enabled(service_client: ServiceRoleClient) -> bool:
    """Whether the Clips feature is live for customers."""
    return _flag_enabled(service_client, CLIPS_FLAG)


def comments_enabled(service_client: ServiceRoleClient) -> bool:
    """Whether the comment surface is live (F-V2)."""
    return _flag_enabled(service_client, CLIPS_COMMENTS_FLAG)
