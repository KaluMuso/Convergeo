> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VF-P04 — Fix `/search` `degraded=true` `[CODE]`

## 1. Context
**Wave 5.** Source: `01-audit-findings.md` §5 (search health); MR-B07. **Live:** `/search` was observed returning `degraded=true` — the hybrid RRF (Postgres FTS + pg_trgm + pgvector) is falling back, so relevance/semantic ranking is impaired. Backend uses `search_rrf(text, vector(384), jsonb)` over GIN + HNSW lanes with `embedding_jobs` feeding `search_documents`. **Sequence after VC-P06** (also edits `search.py`) — rebase on it.
**Type:** `[CODE]`.

## 2. Objective & scope
Diagnose and fix the degraded condition so common queries return `degraded=false`.
**Non-goals:** the demo-exclusion filter (VC-P06); new search features.

## 3. Files (edit ONLY these)
- `services/api/app/routers/search.py`
- `services/api/app/services/embeddings/*` (and/or the RRF/query layer the diagnosis points to)
**Guardrail: rebase on VC-P06's `search.py` changes; do not revert the demo-exclusion filter.**

## 4. Implementation spec
- Determine why `degraded` is set: embedding backlog (`embedding_jobs` pending / `embeddings-cron` not run — VD-P03), missing/failed vector lane, or an FTS/trgm error path. Fix the root cause (e.g. ensure embeddings are backfilled, or the vector lane degrades gracefully only when genuinely unavailable).
- Ensure `degraded` reflects real capability, not a stale flag.

## 10. Tests (RUN before reporting)
- Representative queries return `degraded=false` with sensible RRF ordering.
- `uv run pytest services/api/tests/test_search*.py -q` green; a test asserts non-degraded on seeded data.

## 11. Acceptance criteria / DoD (MR-B07)
- [ ] Common queries `degraded=false`; RRF lanes healthy.
- [ ] Root cause fixed (not the flag suppressed); test proves it.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VF-P04 — Fix `/search` `degraded=true`
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste search tests + a before/after `degraded` probe · **EXCERPTS:** the fix · **QUESTIONS:** …
