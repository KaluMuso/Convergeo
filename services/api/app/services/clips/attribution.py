"""M17-P05 — clip → cart attribution that the client cannot forge.

The rule in one sentence: **a `clip_id` in a request is a claim, not a credit.**

Credit is granted only when all three hold, checked server-side:

1. the clip exists;
2. the clip is ``published``;
3. the clip actually links the listing being added.

Any failure is **silent**: the cart action succeeds and the attribution is simply
not recorded. Refusing the cart action instead would turn a forged id into a way
to *deny* someone their add-to-cart, which is a worse bug than the one being
prevented — and a real customer whose clip was taken down mid-session would be
blocked from buying for no reason they could understand.

This module is also why the attribution is worth having at all: a vendor-facing
number that a client could inflate is not a metric, it is a rumour.
"""

from __future__ import annotations

import logging
from typing import Any, Final, Protocol

logger = logging.getLogger(__name__)

CLIPS_TABLE: Final = "video_clips"
CLIP_PRODUCTS_TABLE: Final = "clip_products"
PUBLISHED: Final = "published"


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


def validate_clip_attribution(
    service_client: ServiceRoleClient, *, clip_id: str | None, listing_id: str
) -> str | None:
    """Return the clip id if it genuinely earns credit for this listing, else ``None``.

    Never raises: an attribution check failing must not be able to fail a cart
    write. A read error resolves to "no credit", which is the safe direction —
    an under-counted clip is a reporting inaccuracy, an over-counted one is a
    vendor being paid attention they did not earn.
    """
    if not clip_id or not clip_id.strip():
        return None
    candidate = clip_id.strip()

    try:
        clip_rows = _rows(
            service_client.client.table(CLIPS_TABLE)
            .select("id, status")
            .eq("id", candidate)
            .maybe_single()
            .execute()
        )
        if not clip_rows or str(clip_rows[0].get("status")) != PUBLISHED:
            return None

        link_rows = _rows(
            service_client.client.table(CLIP_PRODUCTS_TABLE)
            .select("clip_id")
            .eq("clip_id", candidate)
            .eq("listing_id", listing_id)
            .execute()
        )
    except Exception:
        logger.info("clip attribution check failed; not attributing")
        return None

    return candidate if link_rows else None
