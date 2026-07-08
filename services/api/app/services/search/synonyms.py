from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _rows(response: Any) -> list[Any]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return data
    return []


def expand_query(client: Any, query: str) -> str:
    """Expand search terms via the DB synonym table (Bemba/Nyanja aliases)."""
    trimmed = query.strip()
    if not trimmed:
        return trimmed

    try:
        response = client.rpc("expand_search_terms", {"p_query": trimmed}).execute()
    except Exception:
        logger.warning("expand_search_terms RPC failed; using raw query", exc_info=True)
        return trimmed

    rows = _rows(response)
    if not rows:
        return trimmed

    expanded = rows[0]
    if isinstance(expanded, str) and expanded.strip():
        return expanded.strip()
    return trimmed
