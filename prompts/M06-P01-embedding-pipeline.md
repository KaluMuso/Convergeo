> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 14 runs 9 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you own migration `0022` (embedding jobs) this wave.** **Run the FULL `uv run pytest` before reporting.**

# M06-P01 — Embedding pipeline

## 1. Context

**Wave 14 (parallel ×9).** Grounded against as-built `master`:

- **`search_documents` EXISTS (0009_search.sql:30)** with **`embedding vector(384)`** + HNSW index (`search_documents_embedding_hnsw_idx`, `vector_cosine_ops`). **Your model MUST output 384-dim** (gte-small / bge-small class) — a dimension mismatch is a review-blocking bug. FTS/pg_trgm lanes already populate; you fill the semantic lane.
- **No `ai_usage` table yet** (quota/spend table is M06-P03, later wave) — log per-batch cost to structured logs + the job row (not a new table). Kill-switch wiring is M06-P03; here, just record cost.
- **Job queue = new (migration `0022_embedding_jobs.sql`):** additive table `embedding_jobs` (entity ref, status `queued|processing|done|dead`, attempts, error, timestamps) enqueued by `search_documents` triggers on publish/update. RLS on it (admin/service-role only). Reversible header.
- **Internal endpoint** = n8n-cron-invoked, internal-token guard (mirror `internal_embeddings`-style token pattern used by `internal_n8n.py` / `internal_payment_sweeper.py` — `X-Internal-Token` vs an env secret). Batch ≤64 embeddings/request.
- **OpenRouter** cheap embedding model + **gte-small fallback**; retry/backoff; **dead-letter after 5 attempts**. Budget frugality (D-spec).
  Spec: `docs/plan/02-pebbles/M06-ask-vergeo.md` §M06-P01.

## 2. Objective & scope

Async embedding pipeline: `search_documents` publish/update → `embedding_jobs` row → internal batch endpoint embeds (≤64/req, 384-dim) → writes `search_documents.embedding`; backfill CLI; retry→dead-letter after 5; per-batch cost logged. Idempotent (re-run no-ops).
**Non-goals:** no RAG answer API (M06-P02), no quota/kill-switch table (M06-P03), no search ranking change (M05 merged).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/embeddings/{__init__,client,batch}.py` (OpenRouter client + gte-small fallback, batcher, retry/backoff, dim guard) · `services/api/app/routers/internal_embeddings.py` (internal-token batch tick) · `supabase/migrations/0022_embedding_jobs.sql` (queue + enqueue triggers + RLS) · `scripts/embed_backfill.py` · `infra/n8n/embeddings-cron.json` · `services/api/tests/test_embeddings.py`
  **Guardrail: nothing else. Do NOT touch `search_documents` search functions (0009), `main.py`, other `infra/n8n/*.json`, db.ts beyond `0022`. No i18n (backend/CLI only).**

## 4. Implementation spec

- **`client.py`/`batch.py`:** `embed_batch(texts: list[str]) -> list[list[float]]` — OpenRouter cheap model → gte-small fallback on error; **assert every vector is 384-dim** (else raise). Batch ≤64. Retry with backoff; surface cost per batch (log + return).
- **`internal_embeddings.py`:** `POST /internal/embeddings/tick` (internal-token) — claim ≤64 `queued` job rows (LIMIT + status guard, idempotent), embed, write `search_documents.embedding`, mark `done`; on failure increment attempts → `dead` at 5. Return processed/dead counts + cost.
- **`0022`:** `embedding_jobs` table + AFTER INSERT/UPDATE trigger on `search_documents` enqueuing a `queued` row (dedupe by entity); RLS service-role/admin.
- **`embed_backfill.py`:** enqueue+process all existing `search_documents` rows missing an embedding; idempotent.

## 5–9. Security etc.

Internal endpoint token-guarded (env secret, none in repo/JSON); 384-dim guard; batch idempotent; dead-letters queryable; no secrets.

## 10. Tests (RUN before reporting)

`test_embeddings.py`: batcher unit tests (partial-failure retry, idempotent re-run no-ops, ≤64 chunking); **dimension-mismatch guard** (non-384 → raises); dead-letter after 5 attempts; internal-token guard (401). `0022` replay note. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] New/updated `search_documents` row → embedded ≤5min (job→tick→write); batch idempotent (re-run no-ops); dead-letters visible; 384-dim enforced.
- [ ] `0022` additive+reversible; internal-token guarded; per-batch cost logged; full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M06-P01 — Embedding pipeline
**STATUS/FILES/DEVIATIONS** (model + fallback used; how cost is logged sans ai_usage table; enqueue trigger) **/TESTS** (paste batcher + dim-guard + dead-letter + token-guard + full-pytest tail) **/EXCERPTS** the 384-dim guard + the idempotent tick claim — nothing else **/QUESTIONS**
