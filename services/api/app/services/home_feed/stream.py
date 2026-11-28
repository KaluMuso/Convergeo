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
import threading
import time
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


#: In-process snapshot of the fully ordered stream. Every cursor page used to
#: re-run the whole catalogue pipeline (cache read + validate thousands of
#: candidates + sort); the order is identical for every shopper, so one
#: snapshot serves all pages and all callers for a short TTL.
_snapshot_lock = threading.Lock()
_snapshot: tuple[float, list[tuple[SortKey, CatalogListingItem]]] | None = None


def clear_stream_snapshot() -> None:
    global _snapshot
    with _snapshot_lock:
        _snapshot = None


def _order_candidates(
    candidates: list[CatalogCandidate],
) -> list[tuple[SortKey, CatalogListingItem]]:
    keyed: dict[str, tuple[SortKey, CatalogCandidate]] = {}
    for row in candidates:
        if not row.in_stock or row.listing.id in keyed:
            continue
        keyed[row.listing.id] = (_sort_key(row), row)
    ordered = sorted(keyed.values(), key=lambda pair: pair[0], reverse=True)
    return [(key, catalog_item_from_candidate(row)) for key, row in ordered]


def _load_ordered(
    client: Any,
    loader: Callable[[Any], list[CatalogCandidate]],
) -> list[tuple[SortKey, CatalogListingItem]]:
    try:
        candidates = loader(client)
    except Exception:
        logger.warning("home_stream_candidates_failed", exc_info=True)
        candidates = []
    return _order_candidates(candidates)


def _ordered_snapshot(client: Any, ttl_seconds: float) -> list[tuple[SortKey, CatalogListingItem]]:
    """Ordered stream, rebuilt at most once per TTL (single-flight under the lock)."""
    global _snapshot
    now = time.monotonic()
    current = _snapshot
    if current is not None and current[0] > now:
        return current[1]
    with _snapshot_lock:
        current = _snapshot
        if current is not None and current[0] > time.monotonic():
            return current[1]
        ordered = _load_ordered(client, lambda c: build_catalog_candidates(c))
        if ordered:  # never pin an empty/failed build for the whole TTL
            _snapshot = (time.monotonic() + ttl_seconds, ordered)
        return ordered


def build_stream_page(
    client: Any,
    *,
    cursor: str | None,
    limit: int = STREAM_DEFAULT_LIMIT,
    candidate_loader: Callable[[Any], list[CatalogCandidate]] | None = None,
    snapshot_ttl_seconds: float = 0,
) -> HomeStreamPage:
    after = decode_stream_cursor(cursor)
    size = max(1, min(limit, STREAM_MAX_LIMIT))
    if candidate_loader is None and snapshot_ttl_seconds > 0:
        ordered = _ordered_snapshot(client, snapshot_ttl_seconds)
    else:
        loader = candidate_loader or (lambda c: build_catalog_candidates(c))
        ordered = _load_ordered(client, loader)

    if after is not None:
        # Keys are sorted descending, so everything strictly after the cursor is a suffix.
        lo, hi = 0, len(ordered)
        while lo < hi:
            mid = (lo + hi) // 2
            if ordered[mid][0] < after:
                hi = mid
            else:
                lo = mid + 1
        ordered = ordered[lo:]

    page = ordered[:size]
    has_more = len(ordered) > size
    return HomeStreamPage(
        # Copies: the router attaches per-request offer badges onto these items.
        items=[item.model_copy() for _key, item in page],
        next_cursor=encode_stream_cursor(page[-1][0]) if page and has_more else None,
    )
