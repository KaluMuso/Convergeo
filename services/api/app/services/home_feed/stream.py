"""Keyset-paginated "Popular now" listing stream for the customer home page.

Reuses the public catalogue candidate seam (``build_catalog_candidates``), which
already enforces every public visibility rule server-side: searchable
(``is_public``) documents only, active listings, active vendors (blocked /
suspended vendors never join), active products, released product classes, demo
seed rows removed and wholesale supplies hidden. Nothing here re-opens those
rules; the stream only orders and slices.

Ordering is a total order: ``best_score`` (Bayesian-damped rating, trust, stock,
freshness) with the listing id as the final tie-break. The cursor encodes the
last item's sort key rather than an OFFSET (same philosophy as the Clips feed),
and the next page is "everything strictly after that key". A page can therefore
never repeat an item from an earlier page, even if the catalogue changes
between requests.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import math
from collections.abc import Callable
from typing import Any

from app.errors import AppError
from app.routers.catalog import (
    CatalogCandidate,
    CatalogListingItem,
    best_score,
    build_catalog_candidates,
    catalog_item_from_candidate,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

STREAM_DEFAULT_LIMIT = 6
STREAM_MAX_LIMIT = 12
CURSOR_VERSION = 1
MAX_CURSOR_LENGTH = 256
MAX_ID_LENGTH = 64

SortKey = tuple[float, int, int, str, str]


class HomeStreamPage(BaseModel):
    items: list[CatalogListingItem] = Field(default_factory=list)
    next_cursor: str | None = None


def _invalid_cursor() -> AppError:
    return AppError(
        code="invalid_cursor",
        message="Stream cursor is not valid",
        http_status=400,
    )


def encode_stream_cursor(key: SortKey) -> str:
    payload = {"v": CURSOR_VERSION, "k": list(key[:4]), "id": key[4]}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_stream_cursor(cursor: str | None) -> SortKey | None:
    """Return the sort key to continue after, ``None`` for the first page.

    A malformed cursor is a client error (400) and never silently restarts at
    page one, which would loop a broken client forever.
    """
    if not cursor:
        return None
    if len(cursor) > MAX_CURSOR_LENGTH:
        raise _invalid_cursor()
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise _invalid_cursor() from None
    if not isinstance(decoded, dict) or decoded.get("v") != CURSOR_VERSION:
        raise _invalid_cursor()
    parts = decoded.get("k")
    item_id = decoded.get("id")
    if not (isinstance(parts, list) and len(parts) == 4 and isinstance(item_id, str)):
        raise _invalid_cursor()
    damped, trust, stock, updated_at = parts
    numeric = (
        isinstance(damped, (int, float))
        and not isinstance(damped, bool)
        and math.isfinite(damped)
        and all(isinstance(n, int) and not isinstance(n, bool) for n in (trust, stock))
    )
    if not numeric or not isinstance(updated_at, str) or not 0 < len(item_id) <= MAX_ID_LENGTH:
        raise _invalid_cursor()
    return (float(damped), int(trust), int(stock), updated_at, item_id)


def _sort_key(row: CatalogCandidate) -> SortKey:
    damped, trust, stock, updated_at = best_score(row)
    return (damped, trust, stock, updated_at, row.listing.id)


def build_stream_page(
    client: Any,
    *,
    cursor: str | None,
    limit: int = STREAM_DEFAULT_LIMIT,
    candidate_loader: Callable[[Any], list[CatalogCandidate]] | None = None,
) -> HomeStreamPage:
    after = decode_stream_cursor(cursor)
    size = max(1, min(limit, STREAM_MAX_LIMIT))
    loader = candidate_loader or (lambda c: build_catalog_candidates(c))
    try:
        candidates = loader(client)
    except Exception:
        logger.warning("home_stream_candidates_failed", exc_info=True)
        candidates = []

    keyed: dict[str, tuple[SortKey, CatalogCandidate]] = {}
    for row in candidates:
        if not row.in_stock or row.listing.id in keyed:
            continue
        keyed[row.listing.id] = (_sort_key(row), row)
    ordered = sorted(keyed.values(), key=lambda pair: pair[0], reverse=True)
    if after is not None:
        ordered = [pair for pair in ordered if pair[0] < after]

    page = ordered[:size]
    has_more = len(ordered) > size
    return HomeStreamPage(
        items=[catalog_item_from_candidate(row) for _key, row in page],
        next_cursor=encode_stream_cursor(page[-1][0]) if page and has_more else None,
    )
