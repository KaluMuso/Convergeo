> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 6 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free (`httpx` already available).

# M05-P05 — Search API (hybrid RRF)

## 1. Context

**Wave 6 (parallel ×8).** Grounded against as-built `master`:

- **`public.search_rrf(query text, query_embedding vector(384) default null, filters jsonb default '{}')`** exists (`0009_search.sql`) — three lanes (FTS/trgm/vector) fused by RRF, boosts, `is_public` gate, filters (`entity_kind`, `category_path` prefix, price range). A **`public.synonyms`** table + `public.expand_search_terms(text)` (Bemba/Nyanja) also exist. `search_documents.embedding` is nullable (populated later by M06) → the **vector lane degrades gracefully when no embedding**.
- API: routers auto-discover (never edit `main.py`); `core/auth.py` (optional auth OK for public search), user-token/service clients as per module. `httpx` **is** a dependency (use it for the query-time embedding call). Error envelope standard.
- **`app/services/` does NOT exist** — create `app/services/search/` as a regular package (its own `__init__.py`). **Do NOT create `app/services/__init__.py`** — leave `app.services` as an implicit namespace package (other Wave-6 pebbles add sibling subdirs in parallel; mypy runs with `--explicit-package-bases`).
  Spec: `docs/plan/02-pebbles/M05-catalog-search-discovery.md` §M05-P05.

## 2. Objective & scope

`GET /search` (RRF over `search_rrf` with facets/kind filter/pagination) + `GET /search/suggest` (prefix+trgm autocomplete), synonym/alias expansion pre-query, graceful keyword-only degrade when the embedding call fails, and a zero-result logging hook.
**Non-goals:** no search UI (M05-P06), no embedding generation/backfill (M06), no schema (calls existing SQL), no AI/RAG.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/search.py` · `services/api/app/services/search/__init__.py` · `services/api/app/services/search/{query_builder,embedding_client,synonyms}.py` (names your call) · `services/api/tests/test_search.py`
  **Guardrail: nothing else. Do NOT create `app/services/__init__.py`, no `main.py`, no schema/`db.ts`, no UI.**

## 4. Implementation spec

- **`GET /search`:** params `q`, `kind` (products|services|events|supplies|vendors), facets (`category_path`, price min/max), `page`/`page_size`. Build `filters` jsonb + call `public.search_rrf(q, embedding_or_null, filters)` via the DB client. **Synonym/alias expansion** pre-query (use `expand_search_terms` / `synonyms`). **Embedding:** call the embedding service (httpx) for a query vector; **on any failure/timeout → pass NULL and degrade to keyword+trgm lanes** (log + continue, never 500). Paginated results; stable order.
- **`GET /search/suggest`:** prefix + trgm autocomplete, ≤80ms target on seed data (title/alias prefix); small payload.
- **Injection-safety:** never interpolate raw user text into SQL — pass `q` as a bound parameter to `search_rrf` / `websearch_to_tsquery` (the function already uses `websearch_to_tsquery`); escape/parameterize everything.
- **Zero-result hook:** when 0 results, emit a logging hook (structured log or a lightweight insert if a table exists — else log only; do NOT add schema).

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A. **Perf:** p95 <150ms keyword lane on seed; suggest ≤80ms; only `is_public` rows.

## 9. Security

Injection-safe (bound params / websearch_to_tsquery); only public projections surface (the `search_rrf`/`is_public` gate — never leak drafts/unpublished); no secrets (embedding key from env only).

## 10. Tests (RUN before reporting — seed via `scripts/seed.py` or fixtures)

`test_search.py`: **three query classes** — exact ("itel A70"), fuzzy ("chitange"→chitenge synonym), semantic ("dress for kitchen party") return relevant seed results; **degrade path** (embedding client raises → keyword-only results, no 500); **facet filters compose**; **injection-safe** (a raw tsquery-breaking string is handled, not errored); suggest returns prefixes (`uv run pytest`, `ruff`, `mypy` with `--explicit-package-bases`).

## 11. Acceptance criteria / DoD

- [ ] Exact/fuzzy/semantic queries return relevant seed results; facets + kind filter compose; paginated.
- [ ] Embedding-failure degrades to keyword+trgm (tested, no 500); zero-result logged.
- [ ] Injection-safe; only public rows; ruff+mypy+pytest green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M05-P05 — Search API (hybrid RRF)
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste the three query classes + degrade-path + injection output
**EXCERPTS:** the `search_rrf` call + the embedding-degrade guard — nothing else
**QUESTIONS:** (or "none")
