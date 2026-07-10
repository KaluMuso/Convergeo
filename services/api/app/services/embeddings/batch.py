from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.services.embeddings.client import embed_texts_with_fallback
from app.services.search.embedding_client import format_vector_for_rpc

logger = logging.getLogger(__name__)

EMBEDDING_BATCH_LIMIT = 64
MAX_JOB_ATTEMPTS = 5


class SupabaseEmbeddingService(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class BatchEmbedResult:
    vectors: list[list[float]]
    cost_usd: float


@dataclass(frozen=True, slots=True)
class TickResult:
    processed: int
    dead: int
    cost_usd: float


def compose_document_text(
    *,
    title: str,
    body: str,
    locale_terms: list[str] | None,
) -> str:
    terms = " ".join(locale_terms or [])
    return "\n".join(part for part in (title.strip(), body.strip(), terms.strip()) if part)


def chunk_texts(texts: list[str], *, chunk_size: int = EMBEDDING_BATCH_LIMIT) -> list[list[str]]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    return [texts[index : index + chunk_size] for index in range(0, len(texts), chunk_size)]


async def embed_batch(texts: list[str]) -> BatchEmbedResult:
    """Embed up to 64 texts per provider call; larger lists are chunked sequentially."""
    if not texts:
        return BatchEmbedResult(vectors=[], cost_usd=0.0)

    vectors: list[list[float]] = []
    total_cost = 0.0
    for chunk in chunk_texts(texts):
        chunk_vectors, chunk_cost = await embed_texts_with_fallback(chunk)
        vectors.extend(chunk_vectors)
        total_cost += chunk_cost

    return BatchEmbedResult(vectors=vectors, cost_usd=round(total_cost, 8))


def _response_rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None) or []
    return list(data)


def _claim_jobs(service: SupabaseEmbeddingService, *, limit: int) -> list[dict[str, Any]]:
    bounded = max(1, min(limit, EMBEDDING_BATCH_LIMIT))
    response = service.client.rpc(
        "claim_embedding_jobs",
        {"p_limit": bounded},
    ).execute()
    rows = _response_rows(response)
    return rows


def _mark_job_done(
    service: SupabaseEmbeddingService,
    *,
    job_id: str,
    cost_usd: float,
) -> None:
    service.client.table("embedding_jobs").update(
        {
            "status": "done",
            "batch_cost_usd": cost_usd,
            "last_error": None,
            "processed_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", job_id).execute()


def _mark_job_failure(
    service: SupabaseEmbeddingService,
    *,
    job_id: str,
    error_message: str,
    cost_usd: float,
) -> str:
    response = (
        service.client.table("embedding_jobs")
        .select("attempts")
        .eq("id", job_id)
        .maybe_single()
        .execute()
    )
    row = getattr(response, "data", None) or {}
    attempts = int(row.get("attempts", 0)) + 1
    status = "dead" if attempts >= MAX_JOB_ATTEMPTS else "queued"
    service.client.table("embedding_jobs").update(
        {
            "status": status,
            "attempts": attempts,
            "last_error": error_message[:2000],
            "batch_cost_usd": cost_usd,
        }
    ).eq("id", job_id).execute()
    return status


def _write_document_embedding(
    service: SupabaseEmbeddingService,
    *,
    search_document_id: str,
    vector: list[float],
) -> None:
    service.client.table("search_documents").update(
        {"embedding": format_vector_for_rpc(vector)}
    ).eq("id", search_document_id).execute()


async def process_embedding_tick(
    service: SupabaseEmbeddingService,
    *,
    limit: int = EMBEDDING_BATCH_LIMIT,
) -> TickResult:
    """Claim queued jobs, embed document text, and write search_documents.embedding."""
    claimed = _claim_jobs(service, limit=limit)
    if not claimed:
        return TickResult(processed=0, dead=0, cost_usd=0.0)

    texts = [
        compose_document_text(
            title=str(row.get("title") or ""),
            body=str(row.get("body") or ""),
            locale_terms=row.get("locale_terms"),
        )
        for row in claimed
    ]

    try:
        batch = await embed_batch(texts)
    except Exception as exc:
        dead = 0
        for row in claimed:
            status = _mark_job_failure(
                service,
                job_id=str(row["job_id"]),
                error_message=str(exc),
                cost_usd=0.0,
            )
            if status == "dead":
                dead += 1
        logger.warning(
            "Embedding tick batch failed",
            extra={"claimed": len(claimed), "dead": dead},
            exc_info=True,
        )
        return TickResult(processed=0, dead=dead, cost_usd=0.0)

    per_job_cost = round(batch.cost_usd / len(claimed), 8) if claimed else 0.0
    processed = 0
    dead = 0

    for row, vector in zip(claimed, batch.vectors, strict=True):
        job_id = str(row["job_id"])
        search_document_id = str(row["search_document_id"])
        try:
            _write_document_embedding(
                service,
                search_document_id=search_document_id,
                vector=vector,
            )
            _mark_job_done(service, job_id=job_id, cost_usd=per_job_cost)
            processed += 1
        except Exception as exc:
            status = _mark_job_failure(
                service,
                job_id=job_id,
                error_message=str(exc),
                cost_usd=per_job_cost,
            )
            if status == "dead":
                dead += 1

    logger.info(
        "Embedding tick completed",
        extra={
            "claimed": len(claimed),
            "processed": processed,
            "dead": dead,
            "cost_usd": batch.cost_usd,
        },
    )
    return TickResult(processed=processed, dead=dead, cost_usd=batch.cost_usd)
