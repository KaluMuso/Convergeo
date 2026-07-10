> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 15 runs pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you own migration `0023` (ask cache) this wave** (renumber to the next free slot if an in-flight PR claims it at merge). **Run the FULL `uv run pytest` before reporting.**

# M06-P02 — RAG answer API

## 1. Context

**Wave 15 (parallel).** Grounded against as-built `master`:

- **Embeddings MERGED (M06-P01):** `search_documents.embedding vector(384)` is populated by the pipeline. **Retrieval MERGED (M05):** `search_rrf` (0009_search.sql) fuses FTS + pg_trgm + pgvector — call it for top-k, do NOT reimplement ranking.
- **OpenRouter** for the answer model (D-spec); grounding prompt **forbids outside knowledge** ("I couldn't find that on Vergeo5" fallback). Per-answer token caps.
- **⚙ Quota/kill-switch is M06-P03 (parallel):** your `/ask` endpoint must call into `app.services.ask.quota` — `check_and_reserve(...)` **before** the model call and `record_answer(...)` **after** a non-cached answer. Import-guard both (`try/except ImportError` → no-op) so you're mergeable before P03; P03 fills them. **A cache hit must NOT decrement** (skip `record_answer`).
- **Response cache (migration `0023_ask_cache.sql`):** normalized-query cache, 24h TTL; a cache hit skips the model call. RLS service-role only.
- **i18n `ai` (append-rule):** append `ai.answer.*` (M06-P03 also appends to `ai.json` — disjoint sections).
  Spec: `docs/plan/02-pebbles/M06-ask-vergeo.md` §M06-P02.

## 2. Objective & scope

`POST /ask`: extract structured filters (price/category/location) → retrieve top-k via `search_rrf` → answer **strictly from retrieved docs** (citation validator strips any entity_id not retrieved) → text + cited listing-card refs; ZMW via server `formatK`-equivalent; per-answer token caps; normalized-query cache (24h, hit skips model). Quota hooks called (P03).
**Non-goals:** no quota/spend logic (M06-P03 — call the hooks), no Ask UI (M06-P04), no embedding pipeline (M06-P01), no ranking change (call `search_rrf`).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/ask.py` · `services/api/app/services/ask/{__init__,filters,retrieve,prompt,citations,cache}.py` · `supabase/migrations/0023_ask_cache.sql` · `services/api/tests/test_ask.py`
- **Modify (APPEND-RULE):** `packages/i18n/messages/en/ai.json` (append `ai.answer.*`)
  **Guardrail: nothing else. Do NOT touch `search_rrf`/search functions (0009 — call), `services/ask/quota.py`/`spend.py` (M06-P03 — import-guard), `main.py`, db.ts beyond `0023`.**

## 4. Implementation spec

- **`ask.py`** (auth optional — guest allowed, uniform envelope, rate-limited): normalize query → **cache lookup** (hit → return cached, NO quota decrement); else `quota.check_and_reserve` (import-guarded) → `filters.extract` → `retrieve.top_k` (`search_rrf`) → `prompt.build` (grounding template, forbids outside knowledge) → model call (token-capped) → `citations.validate` (**strip any cited entity_id not in the retrieved set**) → cache write (24h) → `quota.record_answer` (non-cache only). No-result → graceful refusal.
- **`0023`:** `ask_cache` (normalized_query key, answer jsonb, cited_ids, expires_at); RLS service-role.

## 5–9. Security etc.

Answers cite ONLY retrieved entity_ids (validator); **prompt-injection in listing content cannot change instructions** (system prompt fenced; guard test); no-result refuses; p95 <6s; cache hit skips model; token caps; no secrets.

## 10. Tests (RUN before reporting)

`test_ask.py`: **citation validator** (a fabricated/non-retrieved id is stripped); **filter extraction** fixtures (price/category/location); **cache hit/miss** (hit skips model call + no `record_answer`); **prompt-injection guard** (malicious text in a retrieved doc does not alter the system instruction). `0023` replay note. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Answers cite only retrieved entity_ids; no-result refuses gracefully; cache hit skips the model call (and quota); prompt-injection contained.
- [ ] `0023` additive+reversible; quota hooks called (import-guarded); `ai.answer.*` appended (append-rule); full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M06-P02 — RAG answer API
**STATUS/FILES/DEVIATIONS** (model used; how quota hooks are import-guarded; cache key normalization) **/TESTS** (paste citation-validator + filter-extraction + cache hit/miss + injection-guard + full-pytest tail) **/EXCERPTS** the citation validator + the cache-hit-skips-quota path — nothing else **/QUESTIONS**
