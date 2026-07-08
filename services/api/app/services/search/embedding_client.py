from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 384
DEFAULT_EMBEDDING_MODEL = "thenlper/gte-small"
DEFAULT_EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"
DEFAULT_EMBEDDING_TIMEOUT_SECONDS = 2.0


def _embedding_settings() -> tuple[str | None, str, str, float]:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip() or None
    model = os.environ.get("SEARCH_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
    url = os.environ.get("SEARCH_EMBEDDING_URL", DEFAULT_EMBEDDING_URL).strip()
    timeout_raw = os.environ.get("SEARCH_EMBEDDING_TIMEOUT_SECONDS", "").strip()
    timeout = DEFAULT_EMBEDDING_TIMEOUT_SECONDS
    if timeout_raw:
        try:
            timeout = float(timeout_raw)
        except ValueError:
            logger.warning("Invalid SEARCH_EMBEDDING_TIMEOUT_SECONDS; using default")
    return api_key, model, url, timeout


def format_vector_for_rpc(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"


def _parse_embedding_payload(payload: Any) -> list[float] | None:
    if not isinstance(payload, dict):
        return None

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None

    first = data[0]
    if not isinstance(first, dict):
        return None

    embedding = first.get("embedding")
    if not isinstance(embedding, list):
        return None

    values: list[float] = []
    for item in embedding:
        if not isinstance(item, (int, float)):
            return None
        values.append(float(item))

    if len(values) != EMBEDDING_DIMENSION:
        logger.warning(
            "Embedding dimension mismatch",
            extra={"expected": EMBEDDING_DIMENSION, "actual": len(values)},
        )
        return None

    return values


async def fetch_query_embedding(query: str) -> list[float] | None:
    """Return a 384-d query vector, or None to degrade to keyword+trgm lanes."""
    trimmed = query.strip()
    if not trimmed:
        return None

    api_key, model, url, timeout = _embedding_settings()
    if api_key is None:
        logger.info("OPENROUTER_API_KEY not configured; skipping query embedding")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers=headers,
                json={"model": model, "input": trimmed},
            )
            response.raise_for_status()
            embedding = _parse_embedding_payload(response.json())
    except Exception:
        logger.warning(
            "Query embedding request failed; degrading to keyword search",
            exc_info=True,
            extra={"query_length": len(trimmed)},
        )
        return None

    return embedding
