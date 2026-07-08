> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 4 runs 6 pebbles in parallel. **⚠ SCHEMA-FREEZE WAVE.** You share `packages/types/src/db.ts` with M03-P05 + M03-P06 — see the db.ts rule.

# M03-P08 — Search projection & pgvector

## 1. Context

**Wave 4 (parallel ×6).** Grounded against as-built `master`. `0001_extensions.sql` enables **`pg_trgm` + `vector`** (pgvector). Source tables you project + trigger on: `public.products(id, name, aliases text[], category_id, status)`, `public.vendor_listings(id, product_id, title_override, price_ngwee, wholesale, status, vendor_id)`, `public.services(id, vendor_id, title, description, status)`, `public.events(id, organiser_vendor_id, title, description, status)`, `public.vendors(id, slug, display_name, status)`. Categories carry a **materialized `path`** (`0003`). Publish states: products `'active'`, listings `'active'`, events `'published'`, services `'active'`, vendors `'active'` — only these project (`is_public`). Conventions (binding): one migration; indexes+RLS+FORCE in-file; commented policies. Spec: `docs/plan/02-pebbles/M03-data-core.md` §M03-P08. This is **the same index that feeds M06 "Ask Vergeo" RAG** — embeddings `vector(384)`.

## 2. Objective & scope

Migration `0009_search.sql`: unified `search_documents` projection + sync triggers on all five source tables, FTS/trgm/HNSW indexes, an RRF search function, and a synonyms table.
**Non-goals:** no embedding generation (M06 — column nullable, populated later), no search API/UI (M05 — SQL function only), no AI (M06).

## 3. Files (create/modify ONLY these)

- **Create:** `supabase/migrations/0009_search.sql` · `supabase/tests/0009_search.test.sql`
- **Modify:** `packages/types/src/db.ts` — **append** your tables (db.ts rule below).
  **Guardrail: nothing else. Do NOT touch `0006`/`0007` (siblings) or any app.**

## 4. Implementation spec

- **`search_documents`** — `entity_kind text check in ('product','listing','service','event','vendor')`, `entity_id uuid`, unique(entity_kind, entity_id), `title text`, `body text`, `category_path text null`, `price_min_ngwee bigint null`, `price_max_ngwee bigint null`, `lat/lng double precision null`, `locale_terms text[] null` (aliases incl. Bemba/Nyanja), `tsv tsvector generated always as (to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(body,'') || ' ' || array_to_string(coalesce(locale_terms,'{}'),' '))) stored`, `embedding vector(384) null`, `boost_signals jsonb default '{}'` (in_stock/verified/below_median), `is_public bool default true`, `updated_at`.
- **Sync triggers (`security definer`, `search_path` pinned):** on `products`, `vendor_listings`, `services`, `events`, `vendors` — AFTER INSERT/UPDATE/DELETE: upsert the projected row when the source is in its publish state; **delete/mark `is_public=false` when it leaves publish state or is deleted**. Derive title/body/category_path/price/geo/terms per entity kind. Comment the mapping per kind.
- **Indexes:** `GIN(tsv)`, `GIN(title gin_trgm_ops)`, **`HNSW(embedding vector_cosine_ops)`** (pgvector), plus btree on (entity_kind), (is_public), (price_min_ngwee).
- **`synonyms`** — `term text`, `canonical text`, unique(term, canonical); seed Bemba/Nyanja rows (e.g. `chitange→chitenge`, plus a handful of common variants). Public read; admin write.
- **`public.search_rrf(query text, query_embedding vector(384) default null, filters jsonb default '{}') returns setof …`** — three lanes: FTS (`tsv @@ websearch_to_tsquery`), trgm fuzzy (`title % query`), vector (`embedding <=> query_embedding` when provided), fused by **Reciprocal Rank Fusion** (rank-based, `1/(k+rank)` with k≈60), applying `boost_signals` (in_stock/verified/below-median). Filters honoured (category_path prefix, price range, kind). Only `is_public` rows. Stable, index-using.
- **RLS:** `search_documents` public select **where is_public** (or a public view); writes service-role/trigger only. `synonyms` public read, admin write.

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A. **EXPLAIN all three lanes** (FTS via GIN(tsv); fuzzy via GIN trgm; vector via HNSW) and paste plans proving index use.

## 9. Security

Private/unpublished entities **never projected** (is_public gate + leave-state trigger removes them — tested); projection writable only by triggers/service-role; no client can inject documents.

## 10. Tests (RUN before reporting — pattern per `supabase/tests/0003/0005`; seed a few source rows)

Migrations `0001→0010` apply clean. **Sync triggers per entity kind**: inserting an active product/listing/service/published event/active vendor creates a `search_documents` row; **unpublishing (status change) or deleting removes it / sets is_public=false**; a draft/pending source is never projected. `search_rrf` returns a fused order on fixture data (exact + fuzzy `chitange`→chitenge synonym + a vector case with a dummy embedding). EXPLAIN shows GIN(tsv), GIN(trgm), HNSW used. Regenerate `db.ts`; `pnpm --filter @vergeo/types typecheck`.

## 11. Acceptance criteria / DoD

- [ ] `db reset` clean through `0010` with `0009` in sequence.
- [ ] Sync triggers proven for all 5 kinds incl. leave-publish-state removal; private entities never projected.
- [ ] `search_rrf` fuses FTS+trgm+vector with boosts; EXPLAIN uses all three indexes.
- [ ] `synonyms` seeded (Bemba/Nyanja); db.ts appended + compiles.

## db.ts rule (shared with M03-P05 + M03-P06 this wave)

db.ts is hand-generated in-cloud. **Append ONLY your new tables to `public.Tables`; do NOT reorder/reformat siblings.** Report that CI's `db` job regenerates authoritatively and the later-merging schema PR combines table sets.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M03-P08 — Search projection & pgvector
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste db reset + per-kind sync + unpublish-removal + search_rrf fusion + 3-lane EXPLAIN output
**EXCERPTS:** full SQL of one representative sync trigger + the `search_rrf` function + the is_public RLS (projection/privacy surfaces) — nothing else
**QUESTIONS:** (or "none")
