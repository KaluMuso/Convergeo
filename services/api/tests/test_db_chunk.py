from __future__ import annotations

from typing import Any

from app.services.db_chunk import DEFAULT_IN_CHUNK_SIZE, chunk_ids, chunked_in_query


def test_chunk_ids_dedupes_and_splits() -> None:
    ids = [f"id-{index}" for index in range(250)]
    chunks = chunk_ids(ids, size=100)
    assert len(chunks) == 3
    assert len(chunks[0]) == 100
    assert len(chunks[2]) == 50


def test_chunked_in_query_merges_chunks() -> None:
    calls: list[int] = []

    def run(chunk: list[str]) -> Any:
        calls.append(len(chunk))
        return type("Result", (), {"data": [{"id": value} for value in chunk]})()

    rows = chunked_in_query([f"x{n}" for n in range(205)], run=run)
    assert len(rows) == 205
    assert calls == [DEFAULT_IN_CHUNK_SIZE, DEFAULT_IN_CHUNK_SIZE, 5]