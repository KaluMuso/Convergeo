from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 384
DEFAULT_PRIMARY_MODEL = "thenlper/gte-small"
DEFAULT_FALLBACK_MODEL = "thenlper/gte-small"
DEFAULT_EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"
DEFAULT_GTE_SMALL_URL = "https://openrouter.ai/api/v1/embeddings"
DEFAULT_EMBEDDING_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_SECONDS = 0.5

# Rough OpenRouter pricing for gte-small class models (USD per 1M input tokens).
DEFAULT_COST_PER_MILLION_TOKENS = 0.02


class EmbeddingDimensionError(ValueError):
    """Raised when an embedding vector is not exactly 384 dimensions."""


@dataclass(frozen=True, slots=True)
class EmbeddingSettings:
    api_key: str | None
    primary_model: str
    fallback_model: str
    openrouter_url: str
    gte_small_url: str
    timeout_seconds: float
    max_retries: int
    retry_base_seconds: float
    cost_per_million_tokens: float


def embedding_settings() -> EmbeddingSettings:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip() or None
    timeout_raw = os.environ.get("DOCUMENT_EMBEDDING_TIMEOUT_SECONDS", "").strip()
    timeout = DEFAULT_EMBEDDING_TIMEOUT_SECONDS
    if timeout_raw:
        try:
            timeout = float(timeout_raw)
        except ValueError:
            logger.warning("Invalid DOCUMENT_EMBEDDING_TIMEOUT_SECONDS; using default")

    cost_raw = os.environ.get("DOCUMENT_EMBEDDING_COST_PER_MILLION_TOKENS", "").strip()
    cost_per_million = DEFAULT_COST_PER_MILLION_TOKENS
    if cost_raw:
        try:
            cost_per_million = float(cost_raw)
        except ValueError:
            logger.warning("Invalid DOCUMENT_EMBEDDING_COST_PER_MILLION_TOKENS; using default")

    return EmbeddingSettings(
        api_key=api_key,
        primary_model=os.environ.get("DOCUMENT_EMBEDDING_MODEL", DEFAULT_PRIMARY_MODEL).strip(),
        fallback_model=os.environ.get(
            "DOCUMENT_EMBEDDING_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL
        ).strip(),
        openrouter_url=os.environ.get("DOCUMENT_EMBEDDING_URL", DEFAULT_EMBEDDING_URL).strip(),
        gte_small_url=os.environ.get("GTE_SMALL_EMBEDDING_URL", DEFAULT_GTE_SMALL_URL).strip(),
        timeout_seconds=timeout,
        max_retries=int(os.environ.get("DOCUMENT_EMBEDDING_MAX_RETRIES", str(DEFAULT_MAX_RETRIES))),
        retry_base_seconds=float(
            os.environ.get(
                "DOCUMENT_EMBEDDING_RETRY_BASE_SECONDS",
                str(DEFAULT_RETRY_BASE_SECONDS),
            )
        ),
        cost_per_million_tokens=cost_per_million,
    )


def assert_embedding_dimensions(vectors: list[list[float]]) -> None:
    for index, vector in enumerate(vectors):
        if len(vector) != EMBEDDING_DIMENSION:
            raise EmbeddingDimensionError(
                "Embedding at index "
                f"{index} has dimension {len(vector)}; expected {EMBEDDING_DIMENSION}"
            )


def estimate_batch_cost_usd(prompt_tokens: int, *, cost_per_million_tokens: float) -> float:
    if prompt_tokens <= 0:
        return 0.0
    return round((prompt_tokens / 1_000_000) * cost_per_million_tokens, 8)


def _parse_embeddings_payload(payload: Any) -> list[list[float]]:
    if not isinstance(payload, dict):
        raise ValueError("Embedding response is not a JSON object")

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("Embedding response missing data array")

    vectors: list[list[float]] = []
    for item in sorted(data, key=lambda row: row.get("index", 0) if isinstance(row, dict) else 0):
        if not isinstance(item, dict):
            raise ValueError("Embedding row is not an object")
        embedding = item.get("embedding")
        if not isinstance(embedding, list):
            raise ValueError("Embedding row missing embedding array")
        values: list[float] = []
        for value in embedding:
            if not isinstance(value, (int, float)):
                raise ValueError("Embedding contains non-numeric values")
            values.append(float(value))
        vectors.append(values)

    assert_embedding_dimensions(vectors)
    return vectors


def _extract_prompt_tokens(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return 0
    prompt_tokens = usage.get("prompt_tokens")
    if isinstance(prompt_tokens, int) and prompt_tokens >= 0:
        return prompt_tokens
    total_tokens = usage.get("total_tokens")
    if isinstance(total_tokens, int) and total_tokens >= 0:
        return total_tokens
    return 0


async def _request_embeddings(
    *,
    texts: list[str],
    url: str,
    model: str,
    api_key: str | None,
    timeout_seconds: float,
) -> tuple[list[list[float]], int]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(
            url,
            headers=headers,
            json={"model": model, "input": texts},
        )
        response.raise_for_status()
        payload = response.json()

    vectors = _parse_embeddings_payload(payload)
    if len(vectors) != len(texts):
        raise ValueError(
            f"Embedding count mismatch: expected {len(texts)} vectors, got {len(vectors)}"
        )
    return vectors, _extract_prompt_tokens(payload)


async def _embed_with_model(
    texts: list[str],
    *,
    url: str,
    model: str,
    api_key: str | None,
    settings: EmbeddingSettings,
) -> tuple[list[list[float]], int]:
    last_error: Exception | None = None
    for attempt in range(settings.max_retries):
        try:
            return await _request_embeddings(
                texts=texts,
                url=url,
                model=model,
                api_key=api_key,
                timeout_seconds=settings.timeout_seconds,
            )
        except Exception as exc:
            last_error = exc
            if attempt + 1 >= settings.max_retries:
                break
            delay = settings.retry_base_seconds * (2**attempt)
            logger.warning(
                "Embedding request failed; retrying",
                extra={
                    "model": model,
                    "attempt": attempt + 1,
                    "delay_seconds": delay,
                },
                exc_info=True,
            )
            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error


async def embed_texts_with_fallback(texts: list[str]) -> tuple[list[list[float]], float]:
    """Embed a batch via OpenRouter primary model, falling back to gte-small."""
    if not texts:
        return [], 0.0
    if len(texts) > 64:
        raise ValueError("embed_texts_with_fallback accepts at most 64 texts per call")

    settings = embedding_settings()
    prompt_tokens = 0

    if settings.api_key is None:
        # Do not attempt primary/fallback — both need the same key, and the
        # generic wrap message would hide the ops fix (set OPENROUTER_API_KEY).
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    try:
        vectors, prompt_tokens = await _embed_with_model(
            texts,
            url=settings.openrouter_url,
            model=settings.primary_model,
            api_key=settings.api_key,
            settings=settings,
        )
    except EmbeddingDimensionError:
        raise
    except Exception:
        logger.warning(
            "Primary embedding model failed; falling back to gte-small",
            extra={"primary_model": settings.primary_model},
            exc_info=True,
        )
        try:
            vectors, prompt_tokens = await _embed_with_model(
                texts,
                url=settings.gte_small_url,
                model=settings.fallback_model,
                api_key=settings.api_key,
                settings=settings,
            )
        except Exception as fallback_error:
            raise RuntimeError(
                "Primary and fallback embedding providers failed"
            ) from fallback_error

    cost_usd = estimate_batch_cost_usd(
        prompt_tokens,
        cost_per_million_tokens=settings.cost_per_million_tokens,
    )
    logger.info(
        "Embedding batch completed",
        extra={
            "text_count": len(texts),
            "prompt_tokens": prompt_tokens,
            "cost_usd": cost_usd,
        },
    )
    return vectors, cost_usd
