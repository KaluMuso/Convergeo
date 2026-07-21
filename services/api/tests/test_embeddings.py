from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from app.main import create_app
from app.services.embeddings.batch import (
    SupabaseEmbeddingService,
    compose_document_text,
    embed_batch,
    process_embedding_tick,
)
from app.services.embeddings.client import (
    EMBEDDING_DIMENSION,
    EmbeddingDimensionError,
    assert_embedding_dimensions,
    embed_texts_with_fallback,
)
from fastapi.testclient import TestClient

VALID_TOKEN = "dev-internal-embeddings"
JOB_ID = "11111111-1111-1111-1111-111111111111"
DOC_ID = "22222222-2222-2222-2222-222222222222"


def _vector(seed: float = 0.1) -> list[float]:
    return [seed + (index * 0.0001) for index in range(EMBEDDING_DIMENSION)]


def _vectors(count: int) -> list[list[float]]:
    return [_vector(0.1 + index * 0.01) for index in range(count)]


class FakeRpc:
    def __init__(self, parent: FakeStore, fn: str, params: dict[str, Any]) -> None:
        self._parent = parent
        self._fn = fn
        self._params = params

    def execute(self) -> Any:
        return self._parent.handle_rpc(self._fn, self._params)


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._maybe_single = False

    def select(self, columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> Any:
        rows = self._parent._filtered_rows(self._filters)
        if self._pending_op == "update":
            for row in rows:
                row.update(self._payload or {})
            return FakeResponse(rows[:1] if self._maybe_single else rows)
        if self._maybe_single:
            return FakeResponse(rows[0] if rows else None)
        return FakeResponse(rows)


class FakeTable:
    def __init__(self, store: FakeStore, name: str) -> None:
        self._store = store
        self._name = name

    def select(self, columns: str) -> FakeQuery:
        return FakeQuery(self, [])

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)

    def _filtered_rows(self, filters: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        rows = self._store.tables.setdefault(self._name, [])
        matched: list[dict[str, Any]] = []
        for row in rows:
            if all(row.get(column) == value for op, column, value in filters if op == "eq"):
                matched.append(row)
        return matched


class FakeStore:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "embedding_jobs": [
                {
                    "id": JOB_ID,
                    "search_document_id": DOC_ID,
                    "entity_kind": "listing",
                    "entity_id": "33333333-3333-3333-3333-333333333333",
                    "status": "queued",
                    "attempts": 0,
                }
            ],
            "search_documents": [
                {
                    "id": DOC_ID,
                    "entity_kind": "listing",
                    "entity_id": "33333333-3333-3333-3333-333333333333",
                    "title": "Chitenge wrap",
                    "body": "Bright cotton fabric",
                    "locale_terms": ["chitenge"],
                    "embedding": None,
                }
            ],
        }
        self.claim_calls = 0
        self.written_embeddings: list[str] = []

    def table(self, name: str) -> FakeTable:
        return FakeTable(self, name)

    def rpc(self, fn: str, params: dict[str, Any]) -> FakeRpc:
        return FakeRpc(self, fn, params)

    def handle_rpc(self, fn: str, params: dict[str, Any]) -> Any:
        if fn == "claim_embedding_jobs":
            self.claim_calls += 1
            if self.claim_calls > 1:
                return FakeResponse([])
            limit = int(params.get("p_limit", 64))
            jobs = [
                row
                for row in self.tables["embedding_jobs"]
                if row["status"] == "queued"
            ][:limit]
            for job in jobs:
                job["status"] = "processing"
            docs = {row["id"]: row for row in self.tables["search_documents"]}
            claimed = []
            for job in jobs:
                doc = docs[job["search_document_id"]]
                claimed.append(
                    {
                        "job_id": job["id"],
                        "search_document_id": job["search_document_id"],
                        "entity_kind": job["entity_kind"],
                        "entity_id": job["entity_id"],
                        "title": doc["title"],
                        "body": doc["body"],
                        "locale_terms": doc.get("locale_terms"),
                    }
                )
            return FakeResponse(claimed)
        raise AssertionError(f"Unexpected rpc: {fn}")


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeSupabaseClient:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    @property
    def client(self) -> FakeSupabaseClient:
        return self

    def table(self, name: str) -> FakeTable:
        return self._store.table(name)

    def rpc(self, fn: str, params: dict[str, Any]) -> FakeRpc:
        return self._store.rpc(fn, params)


class DeadLetterStore(FakeStore):
    def __init__(self, *, attempts: int) -> None:
        super().__init__()
        self.tables["embedding_jobs"][0]["attempts"] = attempts


@pytest.fixture
def fake_service() -> Generator[FakeSupabaseClient, None, None]:
    yield FakeSupabaseClient(FakeStore())


@pytest.fixture
def embeddings_client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


def test_compose_document_text_joins_title_body_and_locale_terms() -> None:
    text = compose_document_text(
        title="Phone",
        body="Dual SIM",
        locale_terms=["foni", "phone"],
    )
    assert "Phone" in text
    assert "Dual SIM" in text
    assert "foni" in text


def asyncio_main(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)


def test_embed_batch_chunks_over_sixty_four() -> None:
    texts = [f"doc-{index}" for index in range(130)]
    call_sizes: list[int] = []

    async def _fake_embed(texts_batch: list[str]) -> tuple[list[list[float]], float]:
        call_sizes.append(len(texts_batch))
        return _vectors(len(texts_batch)), 0.001

    with patch(
        "app.services.embeddings.batch.embed_texts_with_fallback",
        side_effect=_fake_embed,
    ):
        result = asyncio_main(embed_batch(texts))

    assert call_sizes == [64, 64, 2]
    assert len(result.vectors) == 130
    assert result.cost_usd == pytest.approx(0.003)


def test_dimension_mismatch_guard_raises() -> None:
    with pytest.raises(EmbeddingDimensionError):
        assert_embedding_dimensions([_vector(), [0.1, 0.2, 0.3]])


@pytest.mark.asyncio
async def test_partial_failure_retries_then_raises() -> None:
    attempts = {"count": 0}

    async def _flaky_request(**_kwargs: Any) -> tuple[list[list[float]], int]:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary provider outage")
        return [_vector()], 12

    with (
        patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False),
        patch(
            "app.services.embeddings.client._request_embeddings",
            side_effect=_flaky_request,
        ),
    ):
        vectors, cost = await embed_texts_with_fallback(["hello"])

    assert len(vectors) == 1
    assert attempts["count"] == 3
    assert cost >= 0.0


@pytest.mark.asyncio
async def test_dimension_mismatch_from_provider_raises() -> None:
    async def _bad_embed(*_args: Any, **_kwargs: Any) -> tuple[list[list[float]], int]:
        assert_embedding_dimensions([[0.1, 0.2, 0.3]])
        return [[0.1, 0.2, 0.3]], 3

    with (
        patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False),
        patch(
            "app.services.embeddings.client._embed_with_model",
            side_effect=_bad_embed,
        ),
        pytest.raises(EmbeddingDimensionError),
    ):
        await embed_texts_with_fallback(["hello"])


@pytest.mark.asyncio
async def test_process_embedding_tick_is_idempotent_on_second_run(
    fake_service: FakeSupabaseClient,
) -> None:
    with (
        patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False),
        patch(
            "app.services.embeddings.batch.embed_texts_with_fallback",
            new_callable=AsyncMock,
            return_value=(_vectors(1), 0.00042),
        ),
    ):
        service = cast(SupabaseEmbeddingService, fake_service)
        first = await process_embedding_tick(service, limit=64)
        second = await process_embedding_tick(service, limit=64)

    assert first.processed == 1
    assert second.processed == 0
    assert fake_service._store.claim_calls == 2
    assert fake_service._store.tables["embedding_jobs"][0]["status"] == "done"
    assert fake_service._store.tables["search_documents"][0]["embedding"] is not None


@pytest.mark.asyncio
async def test_dead_letter_after_five_attempts() -> None:
    store = DeadLetterStore(attempts=4)
    service = FakeSupabaseClient(store)

    with (
        patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False),
        patch(
            "app.services.embeddings.batch.embed_texts_with_fallback",
            new_callable=AsyncMock,
            side_effect=RuntimeError("provider down"),
        ),
    ):
        result = await process_embedding_tick(
            cast(SupabaseEmbeddingService, service),
            limit=64,
        )

    job = store.tables["embedding_jobs"][0]
    assert result.dead == 1
    assert job["status"] == "dead"
    assert job["attempts"] == 5
    assert "provider down" in str(job["last_error"])


@pytest.mark.asyncio
async def test_missing_openrouter_key_skips_claim_without_burning_queue(
    fake_service: FakeSupabaseClient,
) -> None:
    env = {key: value for key, value in os.environ.items() if key != "OPENROUTER_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        result = await process_embedding_tick(
            cast(SupabaseEmbeddingService, fake_service),
            limit=64,
        )

    job = fake_service._store.tables["embedding_jobs"][0]
    assert result.processed == 0
    assert result.dead == 0
    assert fake_service._store.claim_calls == 0
    assert job["status"] == "queued"
    assert job["attempts"] == 0


@pytest.mark.asyncio
async def test_config_error_after_claim_requeues_without_attempt_bump(
    fake_service: FakeSupabaseClient,
) -> None:
    with (
        patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False),
        patch(
            "app.services.embeddings.batch.embed_texts_with_fallback",
            new_callable=AsyncMock,
            side_effect=RuntimeError("OPENROUTER_API_KEY is not configured"),
        ),
    ):
        result = await process_embedding_tick(
            cast(SupabaseEmbeddingService, fake_service),
            limit=64,
        )

    job = fake_service._store.tables["embedding_jobs"][0]
    assert result.processed == 0
    assert result.dead == 0
    assert fake_service._store.claim_calls == 1
    assert job["status"] == "queued"
    assert job["attempts"] == 0
    assert "OPENROUTER_API_KEY" in str(job["last_error"])


@pytest.mark.asyncio
async def test_embed_texts_with_fallback_raises_clear_missing_key_error() -> None:
    env = {key: value for key, value in os.environ.items() if key != "OPENROUTER_API_KEY"}
    with (
        patch.dict(os.environ, env, clear=True),
        pytest.raises(RuntimeError, match="OPENROUTER_API_KEY is not configured"),
    ):
        await embed_texts_with_fallback(["hello"])


def test_internal_embeddings_tick_requires_token(embeddings_client: TestClient) -> None:
    denied = embeddings_client.post("/internal/embeddings/tick")
    assert denied.status_code == 401

    with patch(
        "app.routers.internal_embeddings.process_embedding_tick",
        new_callable=AsyncMock,
        return_value=type(
            "Tick",
            (),
            {"processed": 2, "dead": 0, "cost_usd": 0.0012},
        )(),
    ):
        ok = embeddings_client.post(
            "/internal/embeddings/tick",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

    assert ok.status_code == 200
    assert ok.json() == {"processed": 2, "dead": 0, "cost_usd": 0.0012}


def test_migration_0022_reversible_header_present() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "supabase"
        / "migrations"
        / "0022_embedding_jobs.sql"
    )
    text = migration.read_text(encoding="utf-8")
    assert "Reversible rollback" in text
    assert "drop table if exists public.embedding_jobs" in text.lower()
