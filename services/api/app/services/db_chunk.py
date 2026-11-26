"""Chunk large PostgREST ``.in_()`` id lists to keep GET URLs under proxy limits."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

DEFAULT_IN_CHUNK_SIZE = 100
POSTGREST_PAGE_SIZE = 1000


def unique_preserve_order(ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def chunk_ids(ids: Sequence[str], *, size: int = DEFAULT_IN_CHUNK_SIZE) -> list[list[str]]:
    unique = unique_preserve_order(ids)
    if not unique:
        return []
    return [unique[index : index + size] for index in range(0, len(unique), size)]


def _rows_from_response(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None) or []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def chunked_in_query(
    ids: Sequence[str],
    *,
    chunk_size: int = DEFAULT_IN_CHUNK_SIZE,
    run: Callable[[list[str]], Any],
) -> list[dict[str, Any]]:
    """Run ``run(chunk_ids)`` per chunk and concatenate row dicts from each response."""
    if not ids:
        return []
    merged: list[dict[str, Any]] = []
    for chunk in chunk_ids(ids, size=chunk_size):
        merged.extend(_rows_from_response(run(chunk)))
    return merged