from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any

CACHE_TTL = timedelta(hours=24)


def normalize_query(query: str) -> str:
    """Normalize user query for cache keying: lowercase, trim, collapse whitespace."""
    trimmed = query.strip().lower()
    collapsed = re.sub(r"\s+", " ", trimmed)
    # Strip combining marks for stable matching across unicode variants.
    normalized = unicodedata.normalize("NFKD", collapsed)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def cache_lookup(client: Any, *, normalized_query: str) -> dict[str, Any] | None:
    """Return cached answer payload when a non-expired row exists."""
    now_iso = datetime.now(UTC).isoformat()
    response = (
        client.table("ask_cache")
        .select("answer, cited_ids, expires_at")
        .eq("normalized_query", normalized_query)
        .gt("expires_at", now_iso)
        .maybe_single()
        .execute()
    )
    row = getattr(response, "data", None)
    if not isinstance(row, dict):
        return None

    answer = row.get("answer")
    if not isinstance(answer, dict):
        return None

    cited_ids = row.get("cited_ids")
    if not isinstance(cited_ids, list):
        cited_ids = []

    return {
        "answer": answer,
        "cited_ids": [str(item) for item in cited_ids],
    }


def cache_write(
    client: Any,
    *,
    normalized_query: str,
    answer: dict[str, Any],
    cited_ids: list[str],
) -> None:
    """Upsert a cache row with a 24-hour TTL."""
    expires_at = datetime.now(UTC) + CACHE_TTL
    payload = {
        "normalized_query": normalized_query,
        "answer": answer,
        "cited_ids": cited_ids,
        "expires_at": expires_at.isoformat(),
    }
    client.table("ask_cache").upsert(payload, on_conflict="normalized_query").execute()
